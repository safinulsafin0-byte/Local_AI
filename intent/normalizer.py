"""
JARVIS Input Normalizer — intent/normalizer.py
=============================================
1. Normalizes text and repairs common speech-to-text mistakes.
2. Detects input language: English ('en'), Bengali Script ('bn_script'), or Banglish ('bn_banglish').
3. Resolves contextual follow-up pronouns and phrases ('pause it', 'ar ekta', 'what about tomorrow')
   using recent working context.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Any

# Common Speech-To-Text phonetic replacements
STT_REPAIR_MAP = [
    (r"\b(you\s*tube|u\s*tube)\b", "youtube"),
    (r"\b(charvis|jarvice|zharvis|jarvis\'s)\b", "jarvis"),
    (r"\b(lo\s*fi|low\s*fi)\b", "lofi"),
    (r"\b(voulme|valume|volumn)\b", "volume"),
    (r"\b(shut\s*down)\b", "shutdown"),
    (r"\b(play\s*list)\b", "playlist"),
    (r"\b(vs\s*code|v\s*s\s*code)\b", "vscode"),
    (r"\b(note\s*pad)\b", "notepad"),
    (r"\b(screen\s*shot)\b", "screenshot"),
]

# Banglish keywords (common Romanized Bengali terms)
BANGLISH_WORDS = {
    "koro", "korun", "korbo", "kore", "kora", "korte",
    "banao", "banaw", "banate", "banaben",
    "chalao", "chalaw", "chalan", "chalate",
    "bondho", "khulo", "khulun",
    "khobor", "brishti", "tahole", "shunao", "shunte",
    "gan", "gaan", "chobi", "tasbir", "pahar", "nodi",
    "ektu", "ekta", "kono", "onek", "aro", "ar",
    "ki", "kothay", "kemne", "kemon", "keno", "kobe",
    "hobe", "hoy", "hoyeche", "hobe ki", "hobe na",
    "ta", "te", "er", "ke", "die", "diye",
    "dao", "den", "din", "dekhaw", "dekhao", "dekhte",
    "thamo", "thamun", "thakbe",
    "amar", "amake", "amader", "tomar", "tomake", "apnar",
    "ajker", "kalke", "gotokal", "agami", "porer", "porerta",
    "baje", "koita", "somoy",
    "komao", "komaw", "baraw", "barao",
}


def repair_stt_text(text: str) -> str:
    """Repairs common speech-to-text recognition errors and artifacts."""
    clean = (text or "").strip()
    for pattern, repl in STT_REPAIR_MAP:
        clean = re.sub(pattern, repl, clean, flags=re.IGNORECASE)
    # Collapse duplicate whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def detect_language(text: str) -> str:
    """
    Detects if query is in English ('en'), Bengali Script ('bn_script'), or Banglish ('bn_banglish').
    """
    if not text:
        return "en"

    # 1. Bengali Unicode range (\u0980 - \u09FF)
    if re.search(r"[\u0980-\u09FF]", text):
        return "bn_script"

    # 2. Check for Banglish words
    tokens = [w.lower().strip(".,?!\"'()") for w in text.split()]
    matched_banglish = [w for w in tokens if w in BANGLISH_WORDS]

    # If 15% or more words or >=2 distinct Banglish words, classify as Banglish
    if len(matched_banglish) >= 2 or (tokens and (len(matched_banglish) / len(tokens)) >= 0.25):
        return "bn_banglish"

    # Also check short queries like "ajker khobor ki" or "pause koro"
    if any(w in BANGLISH_WORDS for w in tokens) and len(tokens) <= 5:
        # Check against high-confidence Banglish markers
        high_confidence = {"koro", "korun", "banao", "chalao", "bondho", "khobor", "brishti", "gan", "gaan", "chobi", "ta", "ajker"}
        if any(w in high_confidence for w in tokens):
            return "bn_banglish"

    return "en"


def expand_follow_up(
    text: str,
    working_context: Optional[Dict[str, Any]] = None,
    history_turns: Optional[List[Dict[str, str]]] = None
) -> Tuple[str, bool]:
    """
    Expands contextual follow-ups like 'pause it', 'ar ekta', 'what about tomorrow'
    using working context and recent history.
    Returns: (expanded_text, was_expanded)
    """
    if not working_context:
        working_context = {}

    lower = text.lower().strip()
    last_topic = working_context.get("last_topic", "")
    last_media = working_context.get("last_media_title", "")
    last_city = working_context.get("last_city", "")
    last_intent = working_context.get("last_intent", "")

    # 1. Media follow-ups
    if lower in ("pause it", "pause that", "it pause koro", "oita bondho koro", "thamo", "stop it"):
        if last_media or last_intent in ("youtube_play", "youtube_control"):
            return "pause video", True

    if lower in ("resume it", "play it", "continue", "chalao", "abar chalao"):
        if last_media or last_intent in ("youtube_play", "youtube_control"):
            return "resume video", True

    if lower in ("next one", "play next", "ar ekta chalao", "porerta chalao", "porer gan", "next gan", "next"):
        if last_intent in ("youtube_play", "youtube_control"):
            return "play next video in playlist", True

    # 2. Weather follow-ups
    weather_followup = re.search(r"\b(what about|kemon thakbe|kalke kemon|and)\s+(tomorrow|kal|kalke|next day|weekend)\b", lower)
    if weather_followup and (last_intent == "weather" or last_city):
        target_city = last_city or "Khulna"
        time_frame = weather_followup.group(2)
        if time_frame in ("kal", "kalke", "tomorrow"):
            return f"weather tomorrow in {target_city}", True
        return f"weather forecast in {target_city}", True

    # 3. Topic follow-ups ("tell me more", "ar ki bolte paro", "explain further")
    if lower in ("tell me more", "explain more", "ar ki", "ar kichu", "elaborate") and last_topic:
        return f"tell me more about {last_topic}", True

    return text, False

