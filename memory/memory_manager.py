from __future__ import annotations

from pathlib import Path
from datetime import datetime
from threading import RLock
import json
import re

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "jarvis_memory.json"

MAX_RECENT_TURNS = 12
MAX_STORED_TURNS = 500
MAX_FACTS = 100
_lock = RLock()

def _now():
    return datetime.now().isoformat(timespec="seconds")

def _load():
    with _lock:
        if not MEMORY_FILE.exists():
            now = _now()
            return {
                "version": 1,
                "created_at": now,
                "updated_at": now,
                "facts": [],
                "history": []
            }
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("version", 1)
        data.setdefault("created_at", _now())
        data.setdefault("updated_at", _now())
        data.setdefault("facts", [])
        data.setdefault("history", [])
        if not isinstance(data["facts"], list):
            data["facts"] = []
        if not isinstance(data["history"], list):
            data["history"] = []
        return data

def _save(data):
    with _lock:
        data["updated_at"] = _now()
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = MEMORY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(MEMORY_FILE)

def _clean(text, limit=4000):
    return str(text or "").strip()[:limit]

def _extract_explicit_memory(user_text):
    text = _clean(user_text, 1000)
    # Ignore interrogative / question sentences
    if "?" in text or re.search(r"\b(?:ki|konta|kothay|what|who|why|how)\b", text, re.IGNORECASE):
        return None
    patterns = (
        r"^\s*remember that\s+(.+)$",
        r"^\s*remember\s+(.+)$",
        r"^\s*my name is\s+(.+)$",
        r"^\s*i like\s+(.+)$",
        r"^\s*i love\s+(.+)$",
        r"^\s*i prefer\s+(.+)$",
        r"^\s*i use\s+(.+)$",
        r"^\s*my favorite\s+(.+)$",
        r"^\s*mone\s*rakh[ob]\s+(.+)$",
        r"^(.+?)[,\s]+mone\s*rakh[ob]\s*$",
        r"^\s*amar\s*naam\s+(.+)$",
        r"^\s*আমার\s*নাম\s+(.+)$",
        r"^\s*মনে\s*রাখ[বনো]\s+(.+)$",
        r"^(.+?)[,\s]+মনে\s*রাখ[বনো]\s*$",
    )
    for pattern in patterns:
        m = re.match(pattern, text, flags=re.IGNORECASE)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip()
            if value:
                return f"User fact: {text}"
    return None

def remember(user_text, assistant_text):
    user_text = _clean(user_text)
    assistant_text = _clean(assistant_text)
    if not user_text and not assistant_text:
        return
    with _lock:
        data = _load()
        data["history"].append({
            "timestamp": _now(),
            "user": user_text,
            "assistant": assistant_text
        })
        data["history"] = data["history"][-MAX_STORED_TURNS:]
        fact = _extract_explicit_memory(user_text)
        if fact and fact.lower() not in {str(x).lower() for x in data["facts"]}:
            data["facts"].append(fact)
            data["facts"] = data["facts"][-MAX_FACTS:]
        _save(data)

def add_fact(fact):
    fact = re.sub(r"\s+", " ", str(fact or "").strip())
    if not fact:
        return
    with _lock:
        data = _load()
        if fact.lower() not in {str(x).lower() for x in data["facts"]}:
            data["facts"].append(fact)
            data["facts"] = data["facts"][-MAX_FACTS:]
            _save(data)

def get_facts():
    return list(_load().get("facts", []))

def get_recent_history(limit=MAX_RECENT_TURNS):
    return _load().get("history", [])[-max(1, int(limit)):]

GREETING_PATTERNS = (
    r"^\s*(hi|hello|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening|what'?s\s+up|sup|howdy)\b",
    r"^\s*kemon\s+acho\b",
    r"^\s*assalamualaikum\b",
)

def _is_greeting(query: str) -> bool:
    if not query:
        return True
    q = query.strip().lower()
    if len(q.split()) <= 3 and any(re.search(pat, q) for pat in GREETING_PATTERNS):
        return True
    return False

def build_context(query: str = ""):
    if query and _is_greeting(query):
        return ""

    data = _load()
    sections = []
    facts = data.get("facts", [])

    if facts:
        # If query provided, only include facts with token overlap / relevance
        if query:
            q_words = set(re.findall(r"\w+", query.lower())) - {"a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it", "i", "my", "me", "what", "who", "where", "how"}
            relevant_facts = [
                f for f in facts
                if any(w in str(f).lower() for w in q_words) or "user" in str(f).lower() or "name" in str(f).lower()
            ]
        else:
            relevant_facts = facts[-MAX_FACTS:]

        if relevant_facts:
            sections.append("LONG-TERM MEMORY:\n" + "\n".join(f"- {x}" for x in relevant_facts[:10]))

    recent = data.get("history", [])[-MAX_RECENT_TURNS:]
    lines = []
    for turn in recent:
        user = str(turn.get("user", "")).strip()
        assistant = str(turn.get("assistant", "")).strip()
        if user:
            lines.append(f"User: {user}")
        if assistant:
            lines.append(f"JARVIS: {assistant}")
    if lines:
        sections.append("RECENT CONVERSATION:\n" + "\n".join(lines))
    return "\n\n".join(sections)

def clear_memory():
    with _lock:
        now = _now()
        _save({"version": 1, "created_at": now, "updated_at": now, "facts": [], "history": []})

def clear_history():
    with _lock:
        data = _load()
        data["history"] = []
        _save(data)

def clear_facts():
    with _lock:
        data = _load()
        data["facts"] = []
        _save(data)

def memory_stats():
    data = _load()
    return {
        "memory_file": str(MEMORY_FILE),
        "facts": len(data.get("facts", [])),
        "history_turns": len(data.get("history", [])),
        "updated_at": data.get("updated_at")
    }

def search(query: str, limit: int = 10) -> list[dict]:
    """Search stored facts and history for matching query keywords."""
    if not query:
        return []
    data = _load()
    q_lower = query.lower()
    matches = []
    # Search facts
    for fact in data.get("facts", []):
        if q_lower in str(fact).lower():
            matches.append({"type": "fact", "content": fact})
    # Search history
    for turn in reversed(data.get("history", [])):
        u = str(turn.get("user", ""))
        a = str(turn.get("assistant", ""))
        if q_lower in u.lower() or q_lower in a.lower():
            matches.append({"type": "conversation", "user": u, "assistant": a, "timestamp": turn.get("timestamp")})
        if len(matches) >= limit:
            break
    return matches[:limit]

def export_memory():
    return _load()

if __name__ == "__main__":
    print(json.dumps(memory_stats(), ensure_ascii=False, indent=2))

