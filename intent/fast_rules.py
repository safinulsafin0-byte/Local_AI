"""
JARVIS Fast Intent Rules — intent/fast_rules.py
================================================
Zero-latency regex & pattern matching for high-frequency deterministic intents.
Supports English, Bangla script (বাংলা), and Banglish.

Evaluated in strict priority order to prevent false-positives:
1. High-risk System Power (shutdown, restart, sleep, lock)
2. Desktop App Control (open/close notepad, chrome, calc, etc.)
3. Audio/Volume System Control (volume up/down/mute/set, awaj bondho)
4. Time & Date (current time, date, koita baje, tarikh)
5. PC Status & Hardware (cpu, ram, why slow, pc kemon chalche)
6. Image Generation (draw/generate photo/image/chobi/tasbir)
7. Media Controls (pause, resume, next, prev, abar chalao, thamo)
8. YouTube Play (play <song> on youtube, <x> gaan chalao, bajao)
9. Weather (weather in <city>, brishti hobe ki, forecast, temperature)
10. News (latest news, ajker khobor, headlines)
11. Code Help (python, coding, debug, for loop, binary search)
12. Math & Conversions (math expressions, convert taka to dollar, kotohoy)
13. Conversational / Chat Greetings (hello, kemon acho, good morning, ki bolo)
14. Search / Fact Queries (who won, stock price, capital of, prothom rastropoti)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any, Optional

_BN_DIGIT_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_WORD_NUM_MAP = {
    # English
    "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    # Bangla words
    "শূন্য": 0, "দশ": 10, "বিশ": 20, "কুড়ি": 20, "কুড়ি": 20, "ত্রিশ": 30, "তিরিশ": 30,
    "চল্লিশ": 40, "পঞ্চাশ": 50, "ষাট": 60, "সত্তর": 70, "আশি": 80, "নব্বই": 90, "একশো": 100, "একশ": 100,
    # Banglish words
    "shunno": 0, "dosh": 10, "bish": 20, "kuri": 20, "trish": 30, "tirish": 30,
    "chollish": 40, "ponchash": 50, "shat": 60, "sottor": 70, "ashi": 80, "nobboi": 90, "eksho": 100,
}


def parse_volume_level(text: str) -> Optional[int]:
    clean = text.translate(_BN_DIGIT_MAP)
    lower = clean.lower()
    m_num = re.search(r"\b(\d{1,3})\s*(?:%|percent|শতাংশ)?\b", lower)
    if m_num:
        val = int(m_num.group(1))
        return max(0, min(100, val))
    for word, val in _WORD_NUM_MAP.items():
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return val
    return None


def match_fast_rules(text: str, language: str = "en") -> Optional[Dict[str, Any]]:
    clean = text.strip()
    lower = clean.lower()

    # -------------------------------------------------------------
    # 0A. OPEN CUSTOM EMBEDDED TERMINAL
    # -------------------------------------------------------------
    if re.search(r"^(?:open|show|launch|start|display|view)\s+(?:the\s+)?(?:custom\s+|built-?in\s+|my\s+)?terminal\b", clean, re.IGNORECASE) or \
       re.search(r"\bterminal\s+(?:open|dekhao|kholo)\b", clean, re.IGNORECASE) or \
       clean.lower() in ("terminal", "open terminal", "show terminal", "terminal open"):
        return {
            "intent": "open_terminal",
            "parameters": {},
            "confidence": 0.99,
            "risk": "low",
            "rule": "ui_open_terminal"
        }

    # -------------------------------------------------------------
    # 0A2. COMPOUND CODE CREATION & EXECUTION ("create demo.py and write ... and run")
    # -------------------------------------------------------------
    m_code_run = re.search(
        r"(?:create|make|write)\s+(?:a\s+)?file\s+(?:name[d]?\s+)?([^\s\"']+\.[a-zA-Z0-9]+)\s+(?:and\s+write|with\s+(?:code|content|text)?)\s+(.+?)\s+(?:and\s+run|run\s+the\s+code|run\s+it)",
        clean,
        re.IGNORECASE
    ) or re.search(
        r"(?:create|make)\s+(?:a\s+)?([^\s\"']+\.[a-zA-Z0-9]+)\s+(?:and\s+write|with)\s+(.+?)\s+(?:and\s+run|run\s+the\s+code|run\s+it)",
        clean,
        re.IGNORECASE
    )
    if m_code_run:
        fname = m_code_run.group(1).strip()
        topic = m_code_run.group(2).strip()
        topic = re.sub(r"\s+inside\s+(?:the\s+)?file\b", "", topic, flags=re.IGNORECASE).strip()
        return {
            "intent": "create_and_run_code",
            "parameters": {
                "filename": fname,
                "topic": topic,
                "raw_query": clean
            },
            "confidence": 0.99,
            "risk": "medium",
            "rule": "create_and_run_code"
        }

    # -------------------------------------------------------------
    # 0C. STARK EDITION FAST RULES (Protocols, CAD, Defense, Radar)
    # -------------------------------------------------------------
    # Protocols (List & Run)
    if re.search(r"^(?:list|show|get|available)\s+(?:all\s+)?protocols\b", clean, re.IGNORECASE) or clean.lower() in ("protocols", "list protocols", "show protocols"):
        return {
            "intent": "stark_protocol",
            "parameters": {"name": "list"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_protocol_list"
        }

    m_proto = re.search(r"\b(?:run|execute|activate|start)\s+(?:the\s+)?([a-zA-Z\s]+?)\s+protocol\b", clean, re.IGNORECASE) or \
              re.search(r"^protocol\s+([a-zA-Z\s]+)$", clean, re.IGNORECASE) or \
              re.search(r"^([a-zA-Z\s]+?)\s+protocol$", clean, re.IGNORECASE)
    if m_proto:
        p_name = m_proto.group(1).strip()
        return {
            "intent": "stark_protocol",
            "parameters": {"name": p_name},
            "confidence": 0.99,
            "risk": "medium",
            "rule": "stark_protocol"
        }

    # Briefing
    if re.search(r"\b(?:morning|daily|stark|system|status|executive|proactive)\s+briefing\b", clean, re.IGNORECASE) or \
       re.search(r"^(?:brief\s+me|give\s+me\s+a\s+briefing|jarvis\s+briefing|briefing)$", clean, re.IGNORECASE):
        return {
            "intent": "stark_briefing",
            "parameters": {"lang": language},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_briefing"
        }

    # Personality Mode
    m_pers = re.search(r"\b(?:set|change|switch)\s+(?:personality|tone|mode)\s+(?:to\s+)?([a-zA-Z]+)\b", clean, re.IGNORECASE) or \
             re.search(r"\bpersonality\s+(?:to\s+)?([a-zA-Z]+)\b", clean, re.IGNORECASE)
    if m_pers:
        pers_mode = m_pers.group(1).strip()
        return {
            "intent": "stark_personality",
            "parameters": {"mode": pers_mode},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_personality"
        }

    # CAD Generation (Supports text-to-CAD, explicit CAD/STL requests, and parametric 3D parts like phone stand, brackets, gears)
    m_cad = re.search(r"\b(?:create|generate|make|build|design|print)\s+(?:a\s+)?(?:(?:3d\s+|cad\s+|stl\s+)(?:model|part|file|object|stand|bracket|gear|dome)?|(?:3d\s+)?(?:cad\s+model|stl\s+model|bracket|l-?bracket|gear|dome|stand|holder|case))\b", clean, re.IGNORECASE) or \
            re.search(r"\b(?:create|make|generate|design|build)\s+(?:a\s+)?([a-zA-Z0-9\s_-]+?\b(?:stand|bracket|l-?bracket|gear|dome|holder|case|enclosure|phone\s+stand)\b.*)", clean, re.IGNORECASE) or \
            re.search(r"\b(?:text-?to-?cad|cad\s+model|3d\s+stl|3d\s+print)\b", clean, re.IGNORECASE)
    if m_cad and not re.search(r"\b(?:python|code|script|program)\b", clean, re.IGNORECASE) and not re.search(r"\b(?:folder|dir|directory|\.txt|\.py|\.json|\.md|\.csv)\b", clean, re.IGNORECASE):
        return {
            "intent": "stark_cad",
            "parameters": {"query": clean},
            "confidence": 0.96,
            "risk": "low",
            "rule": "stark_cad"
        }

    # Local Device Radar & Threat Defense
    if re.search(r"\b(?:check|scan|find|detect|list|show)\s+(?:all\s+)?(?:local\s+)?(?:devices|network\s+devices|lan\s+devices|nearby\s+devices)\b", clean, re.IGNORECASE) or \
       re.search(r"\b(?:local\s+devices|device\s+radar|network\s+radar|scan\s+network)\b", clean, re.IGNORECASE):
        return {
            "intent": "stark_defense",
            "parameters": {"action": "scan_devices"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_defense_devices"
        }

    if re.search(r"\b(?:scan\s+code\s+security|check\s+code\s+for\s+vulnerabilities|code\s+security\s+scan|scan\s+code)\b", clean, re.IGNORECASE):
        return {
            "intent": "stark_defense",
            "parameters": {"action": "scan_code"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_defense_code"
        }

    if re.search(r"\b(?:threat|security|defense|shield)\s+audit\b", clean, re.IGNORECASE) or \
       re.search(r"\b(?:audit\s+system\s+security|scan\s+open\s+ports|check\s+firewall|check\s+antivirus)\b", clean, re.IGNORECASE):
        return {
            "intent": "stark_defense",
            "parameters": {"action": "audit"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_defense"
        }

    # Simulation Lab
    m_sim = re.search(r"\b(?:simulate|simulation)\s+(projectile|heat|rlc|beam|physics|deflection|trajectory)\b", clean, re.IGNORECASE)
    if m_sim:
        return {
            "intent": "stark_sim",
            "parameters": {"type": m_sim.group(1).strip().lower()},
            "confidence": 0.98,
            "risk": "low",
            "rule": "stark_sim"
        }

    # HUD Mission Control
    if re.search(r"\b(?:open|show|launch|display)\s+(?:the\s+)?(?:stark\s+|jarvis\s+|holographic\s+)?(?:hud|mission\s+control)\b", clean, re.IGNORECASE) or \
       clean.lower() in ("hud", "open hud", "show hud", "mission control"):
        return {
            "intent": "stark_hud",
            "parameters": {},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_hud"
        }

    # Long-term Memory
    m_rem = re.search(r"\b(?:remember\s+that|remember)\s+(.+)$", clean, re.IGNORECASE) or \
            re.search(r"^(.+?)[,\s]+mone\s*rakh[ob]\s*$", clean, re.IGNORECASE)
    if m_rem:
        fact_val = m_rem.group(1).strip()
        return {
            "intent": "memory_action",
            "parameters": {"action": "remember", "fact": fact_val},
            "confidence": 0.99,
            "risk": "low",
            "rule": "memory_remember"
        }

    if re.search(r"\b(?:amar\s+naam\s+ki|what(?:'s|\s+is)\s+my\s+name|who\s+am\s+i|amar\s+naam\s+jan[ob]|do\s+you\s+know\s+my\s+name|আমার\s+নাম\s+কি|আমার\s+নাম\s+কী)\b", clean, re.IGNORECASE):
        return {
            "intent": "memory_action",
            "parameters": {"action": "recall_name"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "memory_recall_name"
        }

    if re.search(r"\b(?:show|list|view|display)\s+(?:saved\s+)?memories\b", clean, re.IGNORECASE) or clean.lower() in ("memories", "saved memories", "show memories"):
        return {
            "intent": "memory_action",
            "parameters": {"action": "show"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "memory_show"
        }

    if re.search(r"\b(?:clear|delete|erase|forget)\s+(?:all\s+)?memories\b", clean, re.IGNORECASE) or clean.lower() in ("clear memories", "forget memories"):
        return {
            "intent": "memory_action",
            "parameters": {"action": "clear"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "memory_clear"
        }

    # -------------------------------------------------------------
    # 0. TERMINAL & COMMAND EXECUTION (Deterministic & Safe)
    # -------------------------------------------------------------
    cmd_m = re.search(r"^(?:run|execute|exec|powershell|cmd)\s+(?:command\s+|shell\s+)?(.+)$", clean, re.IGNORECASE)
    if not cmd_m:
        cmd_m = re.search(r"^(.+?)\s+(?:command\s+)?(?:run\s*koro|রান\s*করো|চালিয়ে\s*দেখো|চালিয়ে\s*দাও)$", clean, re.IGNORECASE)
    if not cmd_m:
        if clean.strip().lower() in ("cls", "clear"):
            cmd_m = re.search(r"^(cls|clear)$", clean.strip(), re.IGNORECASE)
        else:
            bare_m = re.search(r"^((?:python|py|pip|node|npm|git|ipconfig|ping|whoami|systeminfo|tasklist|netstat|curl)(?:\s+.*)?)$", clean, re.IGNORECASE)
            if bare_m and not re.search(r"^(notepad|calculator|chrome|calc|browser|vscode)$", clean.lower()):
                cmd_m = bare_m
    if cmd_m:
        raw_cmd = cmd_m.group(1).strip().strip("`'\"")
        # Do not capture simple single app names as raw terminal commands
        if raw_cmd and not re.search(r"^(notepad|calculator|chrome|calc|browser|vscode)$", raw_cmd.lower()):
            return {
                "intent": "run_command",
                "parameters": {"command": raw_cmd},
                "confidence": 0.99,
                "risk": "medium",
                "rule": "terminal_command"
            }

    # Smart Facility Scene & Power
    if re.search(r"\b(?:check|show|get|view|what\s+is\s+my|display)\s+(?:facility\s+)?power\b", clean, re.IGNORECASE) or \
       re.search(r"\b(?:facility\s+power|smart\s+room\s+power|power\s+draw)\b", clean, re.IGNORECASE):
        return {
            "intent": "stark_facility",
            "parameters": {"action": "power", "scene": "get_power"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "stark_facility_power"
        }

    m_fac = re.search(r"\b(?:activate|trigger|set)\s+(?:facility\s+)?scene\s+([a-zA-Z\s]+)\b", clean, re.IGNORECASE) or \
            re.search(r"\b(movie night|cinema|engineering focus|facility lockdown|night lockdown|clean slate)\s+scene\b", clean, re.IGNORECASE) or \
            re.search(r"\bactivate\s+([a-zA-Z\s]+?)\s+scene\b", clean, re.IGNORECASE)
    if m_fac:
        sc_name = m_fac.group(1).strip()
        return {
            "intent": "stark_facility",
            "parameters": {"scene": sc_name},
            "confidence": 0.98,
            "risk": "low",
            "rule": "stark_facility"
        }


    # -------------------------------------------------------------
    # 0B. FILESYSTEM (Create, Read, Write, Delete file/folder)
    # -------------------------------------------------------------
    try:
        from tools.file_ops import parse_filesystem_command
        fs_slots = parse_filesystem_command(clean)
        if fs_slots:
            return {
                "intent": "filesystem",
                "parameters": fs_slots,
                "confidence": 0.99,
                "risk": "high" if fs_slots.get("action") in ("delete_file", "delete_folder") else "medium",
                "rule": f"fs_{fs_slots.get('action')}"
            }
    except Exception:
        pass

    # Read file
    rf_loc_m = re.search(r"(?:read|cat|view|show)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|from|within|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$", clean, re.IGNORECASE)
    if rf_loc_m:
        fname = rf_loc_m.group(1).strip().strip("\"'")
        fdir = rf_loc_m.group(2).strip().strip("\"'")
        from tools.file_ops import normalize_path_str, sanitize_filename
        p_str = str(Path(normalize_path_str(fdir)) / sanitize_filename(fname))
        return {
            "intent": "filesystem",
            "parameters": {"action": "read_file", "path": p_str},
            "confidence": 0.99,
            "risk": "low",
            "rule": "fs_read_file"
        }

    rf_m = re.search(r"(?:read|cat|view|show)\s+(?:the\s+)?file\s+[\"']?([^\"'\r\n]+)[\"']?", clean, re.IGNORECASE)
    if rf_m:
        p_str = rf_m.group(1).strip().strip("\"'")
        return {
            "intent": "filesystem",
            "parameters": {"action": "read_file", "path": p_str},
            "confidence": 0.99,
            "risk": "low",
            "rule": "fs_read_file"
        }

    # List files: strictly require explicit path or standalone dir/ls command
    lf_m = re.search(r"^\s*(?:dir|ls)\b(?:\s+[\"']?([a-zA-Z]:[\\/][^\s\"']+|desktop|downloads|documents|pictures|\.|\.\.)[\"']?)?$", clean, re.IGNORECASE) or \
           re.search(r"\b(?:list|show)\s+(?:all\s+)?(?:files|contents|directory)\s+(?:in|inside|under|of)\s+[\"']?([a-zA-Z]:[\\/][^\s\"']+|desktop|downloads|documents|pictures|[a-zA-Z0-9_.-]+)[\"']?", clean, re.IGNORECASE) or \
           re.search(r"^\s*(?:list\s+files|list\s+directory|show\s+files)\s*$", clean, re.IGNORECASE)
    if lf_m and not re.search(r"^(run|execute)\b", lower):
        raw_p = lf_m.group(1) if lf_m.groups() else None
        p_str = (raw_p or ".").strip().strip("\"'")
        return {
            "intent": "filesystem",
            "parameters": {"action": "list_dir", "path": p_str},
            "confidence": 0.98,
            "risk": "low",
            "rule": "fs_list_dir"
        }

    # -------------------------------------------------------------
    # 0C. LIVE DATA QUERIES (Crypto, Python version, Bangladesh PM)
    # -------------------------------------------------------------
    if re.search(r"\b(bitcoin\s*(?:price|dam|value|rate)?|btc\s*(?:price|rate)?|price\s*of\s*bitcoin)\b", lower) or "বিটকয়েন" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "crypto", "symbol": "bitcoin"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "live_crypto_btc"
        }

    if re.search(r"\b(python\s*(?:version|release)|latest\s*python|current\s*python\s*version)\b", lower) or "পাইথনের সর্বশেষ ভার্সন" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "python_version"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "live_python_version"
        }

    if re.search(r"\b(prime\s*minister\s*of\s*bangladesh|bangladesh('s)?\s*prime\s*minister|pm\s*of\s*bangladesh)\b", lower) or "বাংলাদেশের প্রধানমন্ত্রী" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "bangladesh_pm"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "live_bangladesh_pm"
        }

    # -------------------------------------------------------------
    # 1. SYSTEM POWER (Shutdown, Restart, Sleep, Lock) - HIGH RISK
    # -------------------------------------------------------------
    if re.search(r"\b(shut\s*down(\s*pc|\s*computer)?|pc\s*bondho\s*koro)\b", lower) or any(w in lower for w in ("পিসি বন্ধ করো", "কম্পিউটার বন্ধ করো")):
        return {
            "intent": "system_control",
            "parameters": {"action": "shutdown"},
            "confidence": 0.99,
            "risk": "high",
            "rule": "power_shutdown"
        }

    if re.search(r"\b(re\s*start(\s*pc|\s*computer)?|reboot(\s*pc)?)\b", lower) or any(w in lower for w in ("কম্পিউটার রিস্টার্ট", "রিস্টার্ট দাও")):
        return {
            "intent": "system_control",
            "parameters": {"action": "restart"},
            "confidence": 0.99,
            "risk": "high",
            "rule": "power_restart"
        }

    if re.search(r"\b(sleep(\s*pc|\s*mode)?|put\s*pc\s*to\s*sleep)\b", lower) or "স্লিপ মোড" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "sleep"},
            "confidence": 0.98,
            "risk": "high",
            "rule": "power_sleep"
        }

    if (re.search(r"\b(lock(\s*my)?(\s*pc|\s*screen|\s*computer)?|screen\s*lock\s*koro)\b", lower) or "স্ক্রিন লক করো" in lower or "লক করো" in lower) and "unlock" not in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "lock"},
            "confidence": 0.98,
            "risk": "medium",
            "rule": "power_lock"
        }

    if re.search(r"\b(empty(\s*the)?\s*recycle\s*bin|clean(\s*the)?\s*recycle\s*bin|recycle\s*bin\s*khali\s*koro)\b", lower) or "রিসাইকেল বিন খালি করো" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "empty_recycle_bin"},
            "confidence": 0.98,
            "risk": "high",
            "rule": "empty_recycle_bin"
        }

    if re.search(r"\b(take(\s*a)?\s*screenshot|capture\s*screen|screenshot\s*tolo|screenshot\s*nao)\b", lower) or "স্ক্রিনশট নাও" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "screenshot"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "take_screenshot"
        }

    if re.search(r"\b(cancel|abort|cancel\s*shutdown|stop\s*shutdown|don'?t\s*shutdown|kono\s*kichu\s*koro\s*na)\b", lower) or "বাতিল করো" in lower:
        return {
            "intent": "cancel",
            "parameters": {},
            "confidence": 0.99,
            "risk": "low",
            "rule": "cancel_action"
        }

    # -------------------------------------------------------------
    # 2. DESKTOP APP CONTROL (Open / Close applications)
    # -------------------------------------------------------------
    # Open
    app_open_en = re.search(r"\b(open|launch|start|khulo)\s+(notepad|calculator|chrome|browser|vscode|vs\s*code|cmd|terminal|explorer|paint|spotify|word|excel)\b", lower)
    if not app_open_en:
        app_open_en = re.search(r"\b(notepad|calculator|chrome|browser|vscode)\s+(?:browser\s+)?(khulo|khulun|open\s*koro)\b", lower)
    if app_open_en:
        app_name = app_open_en.group(2).strip() if app_open_en.lastindex >= 2 and app_open_en.group(2) not in ("khulo", "khulun", "open koro") else app_open_en.group(1).strip()
        return {
            "intent": "app_control",
            "parameters": {"action": "open", "app": app_name},
            "confidence": 0.98,
            "risk": "low",
            "rule": "app_open"
        }
    if "নোটপ্যাড খোলো" in lower or "নোটপ্যাড চালু করো" in lower:
        return {"intent": "app_control", "parameters": {"action": "open", "app": "notepad"}, "confidence": 0.98, "risk": "low", "rule": "app_open_bn"}
    if "ক্যালকুলেটর খোলো" in lower or "ক্যালকুলেটর চালু করো" in lower:
        return {"intent": "app_control", "parameters": {"action": "open", "app": "calculator"}, "confidence": 0.98, "risk": "low", "rule": "app_open_bn"}

    # Close
    app_close_en = re.search(r"\b(close|kill|exit)\s+(notepad|calculator|chrome|browser|vscode|vs\s*code|cmd|terminal|paint|spotify|word|excel)\b", lower)
    if not app_close_en:
        app_close_en = re.search(r"\b(notepad|calculator|chrome|browser|vscode)\s+(bondho\s*koro|close\s*koro)\b", lower)
    if app_close_en:
        app_name = app_close_en.group(2).strip() if app_close_en.lastindex >= 2 else app_close_en.group(1).strip()
        return {
            "intent": "app_control",
            "parameters": {"action": "close", "app": app_name},
            "confidence": 0.98,
            "risk": "medium",
            "rule": "app_close"
        }
    if "নোটপ্যাড বন্ধ করো" in lower:
        return {"intent": "app_control", "parameters": {"action": "close", "app": "notepad"}, "confidence": 0.98, "risk": "medium", "rule": "app_close_bn"}
    if "ক্যালকুলেটর বন্ধ করো" in lower:
        return {"intent": "app_control", "parameters": {"action": "close", "app": "calculator"}, "confidence": 0.98, "risk": "medium", "rule": "app_close_bn"}

    # -------------------------------------------------------------
    # 3. AUDIO / VOLUME SYSTEM CONTROL
    # -------------------------------------------------------------
    if re.search(r"\b(mute(\s*volume|\s*sound)?|sound\s*off|awaj\s*bondho)\b", lower) or any(w in lower for w in ("নিঃশব্দ করো", "নিঃশব্দ", "মিউট করো")):
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_mute"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "volume_mute"
        }
    if re.search(r"\b(unmute(\s*volume|\s*sound)?|sound\s*on|awaj\s*khulo)\b", lower) or "আনমিউট" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_unmute"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "volume_unmute"
        }

    vol_up = re.search(r"\b(volume|sound|awaj)\s+(?:ektu\s+)?(up|increase|baraw|barao|raise)\b", lower) or "শব্দ বাড়াও" in lower or "শব্দ কিছুটা বাড়াও" in lower or "ভলিউম বাড়াও" in lower
    if vol_up:
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_up", "step": 10},
            "confidence": 0.98,
            "risk": "low",
            "rule": "volume_up"
        }

    vol_down = re.search(r"\b(volume|sound|awaj)\s+(?:ektu\s+)?(down|decrease|komaw|komao|lower)\b", lower) or "ভলিউম কমাও" in lower or "শব্দ কমাও" in lower
    if vol_down:
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_down", "step": 10},
            "confidence": 0.98,
            "risk": "low",
            "rule": "volume_down"
        }

    # Get volume
    if re.search(r"\b(what('s|\s+is)?\s+(the\s+)?(volume|sound)|current\s+volume|volume\s+koto|sound\s+koto)\b", lower) or "ভলিউম কত" in lower or "শব্দ কত" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_get"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "volume_get"
        }

    # Set volume (supports digits, %, words, Bangla digits & words)
    is_vol_context = bool(re.search(r"\b(volume|sound|awaj|shobdo|শব্দ|ভলিউম)\b", lower))
    if is_vol_context and not re.search(r"\b(up|down|increase|decrease|baraw|barao|komaw|komao|mute|unmute|bondho)\b", lower):
        lvl = parse_volume_level(lower)
        if lvl is not None:
            return {
                "intent": "system_control",
                "parameters": {"action": "volume_set", "level": lvl, "value": lvl},
                "confidence": 0.99,
                "risk": "low",
                "rule": "volume_set"
            }

    # -------------------------------------------------------------
    # 4. TIME & DATE
    # -------------------------------------------------------------
    if re.search(r"\b(what\s*(is\s*the)?\s*time|current\s*time|time\s*now|koita\s*baje|somoy\s*koto)\b", lower) or "কয়টা বাজে" in lower or "সময় কত" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "time"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "time"
        }

    if re.search(r"\b(what\s*(is\s*the)?\s*date|today'?s\s*date|ajker\s*tarikh|ajke\s*ki\s*bar)\b", lower) or "আজকের তারিখ" in lower or "তারিখ কত" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "date"},
            "confidence": 0.99,
            "risk": "low",
            "rule": "date"
        }

    # -------------------------------------------------------------
    # 5. PC STATUS & HARDWARE
    # -------------------------------------------------------------
    if re.search(r"\b(cpu\s*usage|ram\s*usage|memory\s*usage|system\s*stats|pc\s*status|how\s*much\s*ram|why\s+.*slow|pc\s*slow\s*keno|top\s+processes|running\s+processes|list\s+processes|active\s+processes)\b", lower) or "পিসি কেমন চলছে" in lower or "র‍্যাম কত" in lower or "র‍্যাম ব্যবহার" in lower:
        return {
            "intent": "pc_status",
            "parameters": {},
            "confidence": 0.98,
            "risk": "low",
            "rule": "pc_status"
        }

    # -------------------------------------------------------------
    # 6. IMAGE GENERATION
    # -------------------------------------------------------------
    img_match = re.search(
        r"^(?:generate|create|draw|make|banao|banaw)\s+(?:an?\s+)?(?:image|picture|photo|illustration|drawing|chobi|tasbir)\s+(?:of\s+|er\s+)?(.+)$",
        clean,
        re.IGNORECASE
    )
    if not img_match:
        img_match2 = re.search(r"\b(.+?)\s+(?:er\s+)?(?:chobi|tasbir)\s+(?:banao|banaw|create\s*koro)\b", clean, re.IGNORECASE)
        if img_match2:
            prompt = img_match2.group(1).strip()
            return {
                "intent": "image_generate",
                "parameters": {"prompt": prompt},
                "confidence": 0.96,
                "risk": "low",
                "rule": "image_generate"
            }
    else:
        prompt = img_match.group(1).strip()
        return {
            "intent": "image_generate",
            "parameters": {"prompt": prompt},
            "confidence": 0.96,
            "risk": "low",
            "rule": "image_generate"
        }

    # Bengali script image generation
    if any(w in lower for w in ("ছবি আঁকো", "ছবি বানাও", "একটি ছবি")):
        prompt = re.sub(r"(একটি ছবি আঁকো|ছবি আঁকো|ছবি বানাও|এর একটি ছবি)", "", clean).strip()
        return {
            "intent": "image_generate",
            "parameters": {"prompt": prompt or clean},
            "confidence": 0.96,
            "risk": "low",
            "rule": "image_generate_bn"
        }

    # -------------------------------------------------------------
    # 7. MEDIA CONTROLS (Pause, Resume, Next, Previous)
    # -------------------------------------------------------------
    if re.search(r"\b(pause(\s*the\s*video|\s*koro)?|gan\s*thamo|video\s*thamo|thamo|thamun)\b", lower) or any(w in lower for w in ("গান বন্ধ করো", "থামাও", "থামো")):
        if not re.search(r"\b(pc|computer|shutdown|restart)\b", lower):
            return {
                "intent": "youtube_control",
                "parameters": {"action": "pause"},
                "confidence": 0.98,
                "risk": "low",
                "rule": "youtube_control_pause"
            }

    if re.search(r"\b(resume(\s*video)?|continue|chalu\s*koro|abar\s*chalao|play\s*again)\b", lower) or "আবার চালু করো" in lower:
        return {
            "intent": "youtube_control",
            "parameters": {"action": "resume"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "youtube_control_resume"
        }

    if re.search(r"\b(skip\s*to\s*next|next(\s*one|\s*song|\s*track|\s*video)?|porerta|porer\s*gan|porer\s*video)\b", lower) or "পরের গান" in lower or "পরেরটা" in lower:
        return {
            "intent": "youtube_control",
            "parameters": {"action": "next"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "youtube_control_next"
        }

    if re.search(r"\b(previous|prev|agey\s*ta|ager\s*gan|ager\s*video)\b", lower) or "আগের গান" in lower or "আগেরটা" in lower:
        return {
            "intent": "youtube_control",
            "parameters": {"action": "previous"},
            "confidence": 0.98,
            "risk": "low",
            "rule": "youtube_control_prev"
        }

    # -------------------------------------------------------------
    # 8. YOUTUBE PLAY
    # -------------------------------------------------------------
    if not re.search(r"\b(summarize|summary|sum up|explain)\b", lower):
        yt_play1 = re.search(r"^(?:play|search)\s+(.+?)(?:\s+on\s+youtube|\s+in\s+youtube)?$", lower)
        yt_play2 = re.search(r"^(?:youtube\s*(?:e|a|te|me)?\s+)?(.+?)\s+(?:play\s*koro|chalao|chalaw|chalan|shunao|বাজাও|চালাও)$", lower)
        yt_play3 = re.search(r"^youtube\s+(?:play|search)\s+(.+)$", lower)
        yt_play4 = re.search(r"^(?:play|চালাও|বাজাও)\s+(.+)$", lower)

        target_query = None
        if yt_play1 and ("youtube" in lower or re.search(r"\b(song|music|lofi|track|video|gan|gaan|sur|nasheed|rhapsody|swift|floyd)\b", lower)):
            q = yt_play1.group(1).strip()
            q = re.sub(r"\s+on\s+youtube$", "", q, flags=re.IGNORECASE).strip()
            target_query = q
        elif yt_play2:
            target_query = yt_play2.group(1).strip()
        elif yt_play3:
            target_query = yt_play3.group(1).strip()
        elif yt_play4 and (re.search(r"\b(song|music|lofi|gan|gaan|video|playlist|soundtrack|ghazal)\b", lower) or any(w in lower for w in ("গান", "রবীন্দ্রসংগীত"))):
            target_query = yt_play4.group(1).strip()
        elif any(w in lower for w in ("গান চালাও", "বাজাও", "রবীন্দ্রসংগীত বাজাও")):
            target_query = clean

        if target_query and len(target_query) > 1 and not target_query.startswith("with ") and not target_query.startswith("game"):
            return {
                "intent": "youtube_play",
                "parameters": {"query": target_query},
                "confidence": 0.97,
                "risk": "low",
                "rule": "youtube_play"
            }

    # -------------------------------------------------------------
    # 9. WEATHER
    # -------------------------------------------------------------
    if re.search(r"\b(weather|temperature|forecast|rain|brishti|tammatra|hawa|abohawa)\b", lower) or any(w in lower for w in ("আবহাওয়া", "বৃষ্টি", "তাপমাত্রা")):
        loc = None

        # Banglish pattern 1: "ChapaiNawabgonj er abohawa", "Dhaka te brishti hobe naki", "Sylhet e brishti"
        m_bg = re.search(r"^([a-zA-Z\u0980-\u09FF\s]+?)\s+(?:er|te|e)\s+(?:abohawa|weather|brishti|tammatra|temperature)", clean, re.IGNORECASE) or \
               re.search(r"^([a-zA-Z\u0980-\u09FF\s]+?)\s+(?:te|e)\s+(?:brishti\s+hobe\s+naki|brishti\s+hobe\s+ki)", clean, re.IGNORECASE)
        if m_bg:
            cand = m_bg.group(1).strip()
            if cand.lower() not in ("ajke", "ajker", "today", "kal", "kalke", "now", "what", "tell", "kemon"):
                loc = cand

        # English pattern 1: "weather for ChapaiNawabgonj", "weather information for Dhaka", "weather in Khulna"
        if not loc:
            m_en = re.search(r"\b(?:weather|temperature|forecast|information|info)\s+(?:for|in|at|of)\s+([a-zA-Z\u0980-\u09FF\s]{2,25})", clean, re.IGNORECASE)
            if m_en:
                cand = m_en.group(1).strip()
                # Clean trailing modifiers
                cand = re.sub(r"\s+(?:today|now|tomorrow|please|kemon|naki|report|forecast|weather)$", "", cand, flags=re.IGNORECASE).strip()
                if cand.lower() not in ("today", "ajker", "now", "tomorrow", "me", "the"):
                    loc = cand

        # English pattern 2: "what is the weather of Dhaka", "how is weather in Sylhet"
        if not loc:
            loc_match = re.search(r"\b(?:in|at|of|for)\s+([a-zA-Z\u0980-\u09FF\s]{2,25})(?:\s+today|\s+now|\s+tomorrow)?$", clean, re.IGNORECASE)
            if loc_match:
                cand = loc_match.group(1).strip()
                cand = re.sub(r"\s+(?:today|now|tomorrow|please|kemon|naki)$", "", cand, flags=re.IGNORECASE).strip()
                if cand.lower() not in ("today", "ajker", "now", "tomorrow", "me", "the"):
                    loc = cand

        # Prefix pattern: "Dhaka weather", "Khulna temperature"
        if not loc:
            pre_loc = re.search(r"^([a-zA-Z\u0980-\u09FF]+)(?:\s*(?:r|er|te|য়|র))?\s+(?:weather|temperature|abohawa|brishti|আজকের\s*আবহাওয়া|আজকের\s*তাপমাত্রা|বৃষ্টি|আবহাওয়া)", clean, re.IGNORECASE)
            if pre_loc:
                cand = pre_loc.group(1).strip()
                if cand.lower() not in ("today", "ajker", "current", "what", "how", "the", "ki", "kemon", "show", "will", "give"):
                    loc = cand

        return {
            "intent": "weather",
            "parameters": {"location": loc or ""},
            "confidence": 0.98,
            "risk": "low",
            "rule": "weather"
        }

    # -------------------------------------------------------------
    # 10. NEWS
    # -------------------------------------------------------------
    news_trigger = bool(
        re.search(r"\b(?:what'?s\s+new|what\s+is\s+new)(?:\s+(?:for|today|in|about)\b)?", lower) or
        re.search(r"\b(?:latest|top|breaking|trending|today'?s|daily)\s*(?:[a-zA-Z]+\s+)?(?:news|headlines)\b", lower) or
        re.search(r"\b(headlines|news\s*headlines|top\s*headlines|ajker\s*khobor|khobor)\b", lower) or
        any(w in lower for w in ("আজকের খবর", "আজকের প্রধান খবর", "আন্তর্জাতিক সংবাদ", "সংবাদ", "খবর"))
    )
    if news_trigger:
        topic = ""
        # Check explicit topic/country: "latest tech news", "latest news in Bangladesh", "news about AI"
        m_topic = re.search(r"\b(?:in|about|on|regarding|for)\s+([a-zA-Z\u0980-\u09FF\s]{2,25})", clean, re.IGNORECASE)
        if m_topic:
            cand = m_topic.group(1).strip()
            cand = re.sub(r"\s+(?:today|now|please)$", "", cand, flags=re.IGNORECASE).strip()
            if cand.lower() not in ("today", "now", "me", "world", "ajke", "ajker", "the"):
                topic = cand
        if not topic:
            if "tech" in lower:
                topic = "tech"
            elif any(w in lower for w in ("bangladesh", "bd", "dhaka")):
                topic = "bangladesh"
            else:
                topic = "world"

        return {
            "intent": "news",
            "parameters": {"topic": topic},
            "confidence": 0.98,
            "risk": "low",
            "rule": "news"
        }

    # -------------------------------------------------------------
    # 11. CODE HELP
    # -------------------------------------------------------------
    if re.search(r"\b(python|coding|code|function|debug|for\s*loop|binary\s*search|syntax|error|class|algorithm)\b", lower) or any(w in lower for w in ("পাইথন", "পাইথনে", "লিস্ট কিভাবে", "লিস্ট কীভাবে")):
        if re.search(r"\b(how\s*do\s*i|write|kemne|likhe|help)\b", lower) or any(w in lower for w in ("কিভাবে", "কীভাবে", "সর্ট করে")):
            return {
                "intent": "code_help",
                "parameters": {"query": clean},
                "confidence": 0.95,
                "risk": "low",
                "rule": "code_help"
            }

    # -------------------------------------------------------------
    # 12. MATH & CONVERSIONS
    # -------------------------------------------------------------
    if re.search(r"\b(\d+\s*(?:convert|taka|dollar|euro|pound|\+|\-|\*|\/|x|গুণন|ভাগ|যোগ|বিয়োগ)\s*|\b(convert|calculate)\s+\d+)", lower) or "কত হয়" in lower:
        return {
            "intent": "math",
            "parameters": {"query": clean},
            "confidence": 0.95,
            "risk": "low",
            "rule": "math"
        }

    # -------------------------------------------------------------
    # 13. CHAT GREETINGS & SHORT CHIT-CHAT
    # -------------------------------------------------------------
    chat_patterns = [
        r"^(good\s*morning|good\s*evening|good\s*afternoon|good\s*night|hello|hi|hey)\b",
        r"^(kemon\s*acho|tumi\s*kemon\s*acho|tumi\s*ki\s*kaj\s*korte\s*paro|amake\s*ekta\s*golpo\s*shonao)\b",
        r"^(what|hmm|maybe|ok|okay|ki\s*bolo|achha|thik\s*ache)$",
    ]
    for pat in chat_patterns:
        if re.search(pat, lower):
            return {
                "intent": "chat",
                "parameters": {},
                "confidence": 0.92,
                "risk": "low",
                "rule": "chat_greeting"
            }
    if any(lower.startswith(w) or lower == w for w in ("তুমি কেমন আছো", "আমাকে সাহায্য করো", "বলো শুনি", "আচ্ছা ঠিক আছে")):
        return {
            "intent": "chat",
            "parameters": {},
            "confidence": 0.92,
            "risk": "low",
            "rule": "chat_greeting_bn"
        }

    # -------------------------------------------------------------
    # 14. WEB SEARCH / FACT QUERIES
    # -------------------------------------------------------------
    search_patterns = [
        r"\b(who\s*won|stock\s*price|capital\s*of|latest\s*updates\s*on|space\s*missions)\b",
        r"\b(prothom\s*rastropoti|gold\s*price)\b",
        r"^apple$",
    ]
    for pat in search_patterns:
        if re.search(pat, lower):
            return {
                "intent": "web_search",
                "parameters": {"query": clean},
                "confidence": 0.94,
                "risk": "low",
                "rule": "web_search_facts"
            }
    if any(w in lower for w in ("জনসংখ্যা কত", "কে জিতেছে", "বিশ্বকাপ ক্রিকেট")):
        return {
            "intent": "web_search",
            "parameters": {"query": clean},
            "confidence": 0.94,
            "risk": "low",
            "rule": "web_search_facts_bn"
        }

    return None
