"""
JARVIS Intent Understanding Engine — intent/engine.py
=====================================================
Central orchestrator for input understanding:
1. STT text repair & language detection (English, Bengali script, Banglish).
2. Working context resolution for conversational follow-ups.
3. Zero-latency fast rule engine for high-frequency deterministic intents.
4. Structured LLM JSON classifier fallback via Ollama for open-ended queries.
5. Risk classification (low / medium / high) & safety confirmations.
6. Persistent decision audit logging to data/intent_log.jsonl.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional, List

from intent.normalizer import repair_stt_text, detect_language, expand_follow_up
from intent.fast_rules import match_fast_rules
from intent.classifier import LLMIntentClassifier, VALID_INTENTS

logger = logging.getLogger("jarvis.intent.engine")

INTENT_LOG_PATH = Path("data/intent_log.jsonl")


@dataclass
class IntentResult:
    intent: str
    confidence: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk: str = "low"  # "low", "medium", "high"
    language: str = "en"  # "en", "bn_script", "bn_banglish"
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    was_expanded: bool = False
    source: str = "fast_rule"  # "fast_rule" or "llm_classifier"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IntentEngine:
    def __init__(
        self,
        ollama_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        log_file: Path = INTENT_LOG_PATH
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.classifier = LLMIntentClassifier(ollama_url=ollama_url, model=model)
        self.working_context: Dict[str, Any] = {
            "last_intent": None,
            "last_topic": None,
            "last_city": "Khulna",
            "last_media_title": None,
            "last_query": None,
        }

    def update_context(self, key: str, value: Any) -> None:
        """Updates working conversational context."""
        if value:
            self.working_context[key] = value

    def parse(
        self,
        text: str,
        working_context: Optional[Dict[str, Any]] = None,
        use_llm: bool = True
    ) -> IntentResult:
        """
        Parses intent from user input with language awareness, follow-up resolution,
        fast rules, and LLM classification fallback.
        """
        start_time = time.perf_counter()
        raw = text or ""

        # 1. Speech repair & cleanup
        repaired = repair_stt_text(raw)

        # 2. Language detection
        lang = detect_language(repaired)

        # 3. Contextual follow-up expansion
        active_context = dict(self.working_context)
        if working_context:
            active_context.update(working_context)

        expanded, was_expanded = expand_follow_up(repaired, active_context)

        # 4. Zero-latency fast rule matching
        rule_match = match_fast_rules(expanded, language=lang)
        if rule_match and rule_match.get("confidence", 0) >= 0.85:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            result = IntentResult(
                intent=rule_match["intent"],
                confidence=rule_match["confidence"],
                parameters=rule_match.get("parameters", {}),
                risk=rule_match.get("risk", "low"),
                language=lang,
                requires_clarification=False,
                clarification_prompt=None,
                raw_text=raw,
                normalized_text=expanded,
                was_expanded=was_expanded,
                source="fast_rule",
                latency_ms=round(latency_ms, 2),
            )
            self._record_decision(result)
            self._update_internal_context(result)
            return result

        # 5. LLM Structured Classifier Fallback (if enabled)
        if use_llm:
            llm_res = self.classifier.classify(
                text=expanded,
                language=lang,
                context=active_context
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            confidence = float(llm_res.get("confidence", 0.7))
            intent = llm_res.get("intent", "chat")
            risk = llm_res.get("risk", "low")
            req_clarify = bool(llm_res.get("requires_clarification", False)) or (confidence < 0.70)
            clarify_prompt = llm_res.get("clarification_prompt")

            if req_clarify and not clarify_prompt:
                clarify_prompt = f"Did you mean to search or ask about '{expanded}'?"

            result = IntentResult(
                intent=intent,
                confidence=confidence,
                parameters=llm_res.get("parameters", {}),
                risk=risk,
                language=lang,
                requires_clarification=req_clarify,
                clarification_prompt=clarify_prompt,
                raw_text=raw,
                normalized_text=expanded,
                was_expanded=was_expanded,
                source="llm_classifier",
                latency_ms=round(latency_ms, 2),
            )
        else:
            # When LLM disabled (e.g. offline unit test of fast rules)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            result = IntentResult(
                intent="chat",
                confidence=0.5,
                parameters={},
                risk="low",
                language=lang,
                requires_clarification=False,
                raw_text=raw,
                normalized_text=expanded,
                was_expanded=was_expanded,
                source="default_fallback",
                latency_ms=round(latency_ms, 2),
            )

        self._record_decision(result)
        self._update_internal_context(result)
        return result

    def _update_internal_context(self, result: IntentResult) -> None:
        self.working_context["last_intent"] = result.intent
        params = result.parameters or {}
        if "location" in params and params["location"]:
            self.working_context["last_city"] = params["location"]
        if "query" in params and params["query"]:
            if result.intent == "youtube_play":
                self.working_context["last_media_title"] = params["query"]
            self.working_context["last_topic"] = params["query"]
        if "topic" in params and params["topic"]:
            self.working_context["last_topic"] = params["topic"]

    def _record_decision(self, result: IntentResult) -> None:
        """Appends audit decision record to jsonl."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Failed to log intent decision: {e}")

    classify = parse


_shared_engine = None


def get_intent_engine() -> IntentEngine:
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = IntentEngine()
    return _shared_engine

