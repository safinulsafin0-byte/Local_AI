import re
from pathlib import Path
from typing import Optional, Dict, Any

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
    
    # Check digits
    m_num = re.search(r"\b(\d{1,3})\s*(?:%|percent|শতাংশ)?\b", lower)
    if m_num:
        val = int(m_num.group(1))
        return max(0, min(100, val))
        
    # Check words
    for word, val in _WORD_NUM_MAP.items():
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return val
    return None

def match_preview(text: str) -> Optional[Dict[str, Any]]:
    clean = text.strip()
    lower = clean.lower()

    # 1. RUN COMMAND / TERMINAL
    cmd_m = re.search(r"^(?:run|execute|exec|terminal|powershell|cmd)\s+(?:command\s+|shell\s+)?(.+)$", clean, re.IGNORECASE)
    if not cmd_m:
        cmd_m = re.search(r"^(.+?)\s+(?:command\s+)?(?:run\s*koro|রান\s*করো|চালিয়ে\s*দেখো|চালিয়ে\s*দাও)$", clean, re.IGNORECASE)
    if cmd_m:
        raw_cmd = cmd_m.group(1).strip().strip("`'\"")
        if raw_cmd and not re.search(r"^(notepad|calculator|chrome|calc|browser|vscode)$", raw_cmd.lower()):
            return {
                "intent": "run_command",
                "parameters": {"command": raw_cmd},
                "confidence": 0.99,
                "rule": "run_command"
            }

    # 2. FILESYSTEM
    # Create file:
    cf_m = re.search(
        r"(?:create|make|write)\s+(?:a\s+)?file\s+(?:named?|called|name)?\s*[\"']?([^\"'\r\n]+?)[\"']?\s+in\s+[\"']?([^\"'\r\n]+?)[\"']?(?:\s+(?:and\s+write|with\s+content|with)\s+[\"']?(.*?)[\"']?)?$",
        clean,
        re.IGNORECASE
    )
    if cf_m:
        fname = cf_m.group(1).strip().strip("\"'")
        fdir = cf_m.group(2).strip().strip("\"'")
        content = (cf_m.group(3) or "").strip()
        full_p = str(Path(fdir) / fname)
        return {
            "intent": "filesystem",
            "parameters": {"action": "create_file", "path": full_p, "content": content},
            "confidence": 0.99,
            "rule": "fs_create_file"
        }

    cf_direct = re.search(
        r"(?:create|make)\s+(?:a\s+)?file\s+(?:at\s+|named?\s+)?[\"']?([a-zA-Z]:[\\/][^\s\"'\r\n]+|[\.\w\-_/\\\\]+\.[a-zA-Z0-9]+)[\"']?(?:\s+(?:with\s+content|and\s+write|with)\s+[\"']?(.*?)[\"']?)?$",
        clean,
        re.IGNORECASE
    )
    if cf_direct:
        p_str = cf_direct.group(1).strip().strip("\"'")
        content = (cf_direct.group(2) or "").strip()
        return {
            "intent": "filesystem",
            "parameters": {"action": "create_file", "path": p_str, "content": content},
            "confidence": 0.99,
            "rule": "fs_create_file_direct"
        }

    # Create folder:
    cfol_m = re.search(
        r"(?:create|make|mkdir)\s+(?:a\s+)?(?:folder|directory)\s+(?:named?|called|at)?\s*[\"']?([^\"'\r\n]+?)[\"']?(?:\s+in\s+[\"']?([^\"'\r\n]+?)[\"']?)?$",
        clean,
        re.IGNORECASE
    )
    if cfol_m:
        fol_name = cfol_m.group(1).strip().strip("\"'")
        parent = cfol_m.group(2)
        full_p = str(Path(parent.strip().strip("\"'")) / fol_name) if parent else fol_name
        return {
            "intent": "filesystem",
            "parameters": {"action": "create_folder", "path": full_p},
            "confidence": 0.99,
            "rule": "fs_create_folder"
        }

    # Delete file:
    df_m = re.search(r"(?:delete|remove|rm)\s+(?:the\s+)?file\s+[\"']?([^\"'\r\n]+)[\"']?", clean, re.IGNORECASE) or ("ফাইল মুছে দাও" in lower)
    if df_m and hasattr(df_m, "group"):
        p_str = df_m.group(1).strip().strip("\"'")
        return {
            "intent": "filesystem",
            "parameters": {"action": "delete_file", "path": p_str},
            "confidence": 0.99,
            "rule": "fs_delete_file"
        }

    # Read file:
    rf_m = re.search(r"(?:read|cat|view|show|open)\s+(?:the\s+)?file\s+[\"']?([^\"'\r\n]+)[\"']?", clean, re.IGNORECASE)
    if rf_m:
        p_str = rf_m.group(1).strip().strip("\"'")
        return {
            "intent": "filesystem",
            "parameters": {"action": "read_file", "path": p_str},
            "confidence": 0.99,
            "rule": "fs_read_file"
        }

    # List files:
    lf_m = re.search(r"(?:list\s+files|dir|ls)(?:\s+in\s+[\"']?([^\"'\r\n]+)[\"']?)?", clean, re.IGNORECASE)
    if lf_m:
        p_str = (lf_m.group(1) or ".").strip().strip("\"'")
        return {
            "intent": "filesystem",
            "parameters": {"action": "list_dir", "path": p_str},
            "confidence": 0.98,
            "rule": "fs_list_dir"
        }

    # 3. VOLUME CONTROL
    # Get volume
    if re.search(r"\b(what('s|\s+is)?\s+(the\s+)?(volume|sound)|current\s+volume|volume\s+koto|sound\s+koto)\b", lower) or "ভলিউম কত" in lower or "শব্দ কত" in lower:
        return {
            "intent": "system_control",
            "parameters": {"action": "volume_get"},
            "confidence": 0.99,
            "rule": "volume_get"
        }

    # Set volume
    is_vol_context = bool(re.search(r"\b(volume|sound|awaj|shobdo|শব্দ|ভলিউম|sound level)\b", lower))
    if is_vol_context and not re.search(r"\b(up|down|increase|decrease|baraw|barao|komaw|komao|mute|unmute|bondho)\b", lower):
        lvl = parse_volume_level(lower)
        if lvl is not None:
            return {
                "intent": "system_control",
                "parameters": {"action": "volume_set", "level": lvl, "value": lvl},
                "confidence": 0.99,
                "rule": "volume_set"
            }

    # 4. LIVE DATA
    if re.search(r"\b(bitcoin\s*(?:price|dam|value|rate)?|btc\s*(?:price|rate)?|price\s*of\s*bitcoin)\b", lower) or "বিটকয়েন" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "crypto", "symbol": "bitcoin"},
            "confidence": 0.99,
            "rule": "live_crypto_btc"
        }

    if re.search(r"\b(python\s*(?:version|release)|latest\s*python|current\s*python\s*version)\b", lower) or "পাইথনের সর্বশেষ ভার্সন" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "python_version"},
            "confidence": 0.99,
            "rule": "live_python_version"
        }

    if re.search(r"\b(prime\s*minister\s*of\s*bangladesh|bangladesh('s)?\s*prime\s*minister|pm\s*of\s*bangladesh)\b", lower) or "বাংলাদেশের প্রধানমন্ত্রী" in lower:
        return {
            "intent": "live_data",
            "parameters": {"data_type": "bangladesh_pm"},
            "confidence": 0.99,
            "rule": "live_bangladesh_pm"
        }

    return None

if __name__ == "__main__":
    tests = [
        'run python --version',
        'create a file name "Demo.txt" in "D:\\personal-ai-full" and write " Ok jarvis working perfectly"',
        'create file D:\\jarvis_test\\sample.txt with content hello',
        'create folder D:\\jarvis_test',
        'delete file D:\\jarvis_test\\sample.txt',
        'read file D:\\jarvis_test\\sample.txt',
        'list files in D:\\jarvis_test',
        'volume set to 50%',
        'set volume to 50%',
        'volume 30',
        'volume tirish koro',
        'ভলিউম ৩০ করো',
        'what is the volume',
        'bitcoin price',
        'latest python version',
        'prime minister of bangladesh',
    ]

    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    for t in tests:
        res = match_preview(t)
        print(f"PASS: {t} -> {res['intent']} ({res.get('parameters')})" if res else f"FAIL: {t}")
