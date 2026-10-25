"""
JARVIS Intent Classifier — intent/classifier.py
================================================
LLM-based structured intent classifier using Ollama JSON schema mode.
Called when zero-latency fast rules do not yield high confidence.
Enforces strict JSON schema at temperature 0 to eliminate any filler or markdown leaks.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("jarvis.intent.classifier")

VALID_INTENTS = [
    "chat",
    "web_search",
    "weather",
    "news",
    "youtube_play",
    "youtube_control",
    "image_generate",
    "document_qa",
    "file_op",
    "filesystem",
    "run_command",
    "live_data",
    "app_control",
    "system_control",
    "pc_status",
    "guardian_query",
    "memory_save",
    "memory_recall",
    "code_help",
    "reminder",
    "math",
    "translate",
]

CLASSIFIER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": VALID_INTENTS,
        },
        "confidence": {
            "type": "number",
        },
        "parameters": {
            "type": "object",
        },
        "risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "requires_clarification": {
            "type": "boolean",
        },
        "clarification_prompt": {
            "type": "string",
        },
    },
    "required": ["intent", "confidence", "parameters", "risk"],
}

CLASSIFIER_SYSTEM_PROMPT = """You are the JARVIS Intent Classification Engine.
Classify the user's input into exactly one valid intent, extract relevant parameters, assess execution risk, and output STRICT JSON conforming to the schema.

Valid intents:
- chat: General conversational greeting, small talk, philosophy, creative writing, or personal questions.
- web_search: Real-time web search for fresh information, facts, stock prices, scores, people, current events.
- weather: Local or global weather, forecast, rain, temperature.
- news: Current headlines, breaking news, articles from news outlets.
- youtube_play: Playing a music video, song, lofi, or video on YouTube.
- youtube_control: Media playback actions (pause, resume, next, previous, mute, unmute).
- image_generate: User requesting to create, draw, or generate an image/photo/artwork.
- document_qa: Questions about an uploaded PDF, document, or image.
- file_op: File system operations ONLY when user explicitly mentions a folder, file, directory or path (e.g., "list files in folder", "create file", "delete folder").
  CRITICAL RULE: Words like "information", "all", "clear", "today", "details" in queries like "give me all information of Today.com for today", "make the faces clear", "what's new today", "details about machine learning" are NEVER file_op.
- app_control: Launching, opening, or closing desktop applications (Notepad, Chrome, VS Code, etc.).
- system_control: PC OS actions (shutdown, restart, sleep, lock, volume adjustment, time, date).
- pc_status: Queries about hardware resource usage (CPU, RAM, GPU, why PC is slow).
- guardian_query: Questions about PC security monitoring, suspicious activity, intrusion alerts.
- memory_save: User telling JARVIS to remember something ("remember my favorite color is blue").
- memory_recall: User asking JARVIS what it remembers ("what is my favorite color?").
- code_help: Programming questions, debugging, writing code, refactoring.
- reminder: Setting alarms, timers, or reminders.
- math: Mathematical calculations or unit conversions.
- translate: Language translation requests.

Risk levels:
- high: shutdown, restart, sleep, deleting files.
- medium: closing applications, lock screen.
- low: everything else.

If confidence is < 0.75 or input is genuinely ambiguous with missing referents (e.g. "what's that thing there?"), set "requires_clarification": true and provide a short "clarification_prompt" (e.g. "Could you provide more context on what you are referring to?"). Never call a file tool for ambiguous inputs."""


class LLMIntentClassifier:
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:7b"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def classify(
        self,
        text: str,
        language: str = "en",
        context: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 6.0
    ) -> Dict[str, Any]:
        """
        Classifies input using Ollama structured JSON output.
        Falls back to 'chat' or 'web_search' on network failure.
        """
        user_prompt = f"User input (Language: {language}): \"{text}\""
        if context:
            ctx_summary = []
            if context.get("last_topic"):
                ctx_summary.append(f"Recent Topic: {context['last_topic']}")
            if context.get("last_city"):
                ctx_summary.append(f"Recent City: {context['last_city']}")
            if context.get("last_intent"):
                ctx_summary.append(f"Recent Intent: {context['last_intent']}")
            if ctx_summary:
                user_prompt += f"\nContext: {', '.join(ctx_summary)}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": CLASSIFIER_JSON_SCHEMA,
            "options": {
                "temperature": 0.0,
                "num_predict": 150,
            },
            "stream": False,
        }

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                res = client.post(f"{self.ollama_url}/api/chat", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("message", {}).get("content", "").strip()
                    parsed = json.loads(content)
                    # Validate parsed intent
                    if parsed.get("intent") in VALID_INTENTS:
                        parsed["confidence"] = float(parsed.get("confidence", 0.8))
                        if "parameters" not in parsed or not isinstance(parsed["parameters"], dict):
                            parsed["parameters"] = {}
                        if parsed.get("risk") not in ("low", "medium", "high"):
                            parsed["risk"] = "low"
                        return parsed
        except Exception as e:
            logger.warning(f"LLM classifier failed or timed out: {e}")

        # Safe fallback based on light heuristic
        lower = text.lower()
        if any(w in lower for w in ("who", "what is", "when", "where", "why", "price of", "latest", "score")):
            return {
                "intent": "web_search",
                "parameters": {"query": text},
                "confidence": 0.70,
                "risk": "low",
                "requires_clarification": False,
            }

        return {
            "intent": "chat",
            "parameters": {},
            "confidence": 0.60,
            "risk": "low",
            "requires_clarification": False,
        }

