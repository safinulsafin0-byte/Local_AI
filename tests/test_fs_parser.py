import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_WORKING_DIR = r"D:\jarvis_test"

def normalize_path_str(p_str: Optional[str]) -> str:
    if not p_str or not p_str.strip():
        return DEFAULT_WORKING_DIR
    s = p_str.strip().strip("\"'")
    # Collapse double slashes
    s = re.sub(r"[\\/]+", r"\\", s)
    s = os.path.expandvars(s)
    
    # Strip leading prepositions if left in parent_dir
    s = re.sub(r"^(?:in|inside|under|within|on|at|to)\s+", "", s, flags=re.IGNORECASE).strip()
    
    userprofile = os.environ.get("USERPROFILE", r"C:\Users\USER")
    alias_map = {
        "desktop": os.path.join(userprofile, "Desktop"),
        "downloads": os.path.join(userprofile, "Downloads"),
        "documents": os.path.join(userprofile, "Documents"),
        "pictures": os.path.join(userprofile, "Pictures"),
        "home": userprofile,
        "here": r"D:\personal-ai-full",
        "workspace": r"D:\personal-ai-full",
    }
    s_clean = s.lower().strip()
    if s_clean in alias_map:
        return alias_map[s_clean]
    
    return s

def sanitize_filename(name: str) -> str:
    # Strip invalid Windows filename chars: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    return cleaned

def parse_filesystem_command(query: str) -> Optional[Dict[str, Any]]:
    q = query.strip()
    
    # 1. Banglish patterns: "PATH e/te/er moddhe X folder banao", "PATH e X name ekta folder banao"
    m_banglish = re.search(
        r"([a-zA-Z]:[\\/][^\s]+|desktop|downloads|documents|pictures|here|workspace)\s+(?:e|te|er\s+moddhe)\s+(?:(?:ekta|name|called)\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:folder|directory)\s+banao",
        q,
        re.IGNORECASE
    )
    if m_banglish:
        p_raw = m_banglish.group(1)
        name_raw = m_banglish.group(2)
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "create_folder",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": ""
        }

    # 2. Folder creation: "(create|make|mkdir) (a )?folder (name|named|called|naam)? X (inside|in|under|within|on|at) PATH"
    m_folder_loc = re.search(
        r"(?:create|make|mkdir)\s+(?:a\s+)?(?:folder|directory)\s+(?:name[d]?|called|naam)?\s*[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|within|on|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_folder_loc:
        name_raw = m_folder_loc.group(1).strip()
        p_raw = m_folder_loc.group(2).strip()
        # If name accidentally captured "inside ...", handle re-parse
        if re.search(r"\b(?:inside|in|under|within)\b", name_raw, re.IGNORECASE):
            parts = re.split(r"\b(?:inside|in|under|within)\b", name_raw, flags=re.IGNORECASE)
            name_raw = parts[0].strip()
            if not p_raw:
                p_raw = parts[1].strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "create_folder",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": ""
        }

    # 3. File creation with location, name, content: "create a file notes.txt on desktop with text hello"
    m_file = re.search(
        r"(?:create|make|write)\s+(?:a\s+)?file\s+(?:name[d]?|called|naam)?\s*[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|within|on|at)\s+[\"']?([^\"'\r\n]+?)[\"']?(?:\s+(?:with\s+(?:content|text)|and\s+write)\s+[\"']?(.*?)[\"']?)?$",
        q,
        re.IGNORECASE
    )
    if m_file:
        name_raw = m_file.group(1).strip()
        p_raw = m_file.group(2).strip()
        content = (m_file.group(3) or "").strip()
        # If p_raw swallowed "with text ..."
        if " with " in p_raw.lower():
            p_parts = re.split(r"\s+with\s+(?:content|text)?\s*", p_raw, flags=re.IGNORECASE)
            p_raw = p_parts[0].strip()
            if len(p_parts) > 1 and not content:
                content = p_parts[1].strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "create_file",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": content
        }

    # 4. Folder creation simple: "make a folder called 'My Project' in Documents"
    m_fol_simple = re.search(
        r"(?:create|make|mkdir)\s+(?:a\s+)?(?:folder|directory)\s+(?:name[d]?|called|naam)\s+[\"']([^\"']+)[\"']\s+(?:inside|in|under|within|on|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_fol_simple:
        name_raw = m_fol_simple.group(1).strip()
        p_raw = m_fol_simple.group(2).strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "create_folder",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": ""
        }

    # 5. Delete folder/file: "delete the Demo folder" / "delete folder Demo" / "delete file notes.txt"
    m_del = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:folder|directory)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    ) or re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:folder|directory)$",
        q,
        re.IGNORECASE
    )
    if m_del:
        name_raw = m_del.group(1).strip()
        # If absolute path given:
        if re.match(r"^[a-zA-Z]:[\\/]", name_raw):
            full_p = normalize_path_str(name_raw)
            name = Path(full_p).name
            parent = str(Path(full_p).parent)
        else:
            name = sanitize_filename(name_raw)
            parent = DEFAULT_WORKING_DIR
            full_p = str(Path(parent) / name)
        return {
            "action": "delete_folder",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": "",
            "requires_confirmation": True
        }

    m_del_f = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    ) or re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+file$",
        q,
        re.IGNORECASE
    )
    if m_del_f:
        name_raw = m_del_f.group(1).strip()
        if re.match(r"^[a-zA-Z]:[\\/]", name_raw):
            full_p = normalize_path_str(name_raw)
            name = Path(full_p).name
            parent = str(Path(full_p).parent)
        else:
            name = sanitize_filename(name_raw)
            parent = DEFAULT_WORKING_DIR
            full_p = str(Path(parent) / name)
        return {
            "action": "delete_file",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": "",
            "requires_confirmation": True
        }

    # Fallback: Structured output extraction using Ollama
    try:
        from llm.ollama_client import ollama_chat_raw
        schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_folder", "create_file", "delete_folder", "delete_file", "read_file", "list_dir", "none"]
                },
                "name": {"type": "string"},
                "parent_dir": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["action", "name", "parent_dir"]
        }
        prompt = (
            f"Extract filesystem action and slots from this user request: '{q}'.\n"
            f"Return JSON matching the schema. If no location specified, use '{DEFAULT_WORKING_DIR}'."
        )
        res_json = ollama_chat_raw(prompt, schema=schema, temperature=0.0)
        import json
        parsed = json.loads(res_json)
        action = parsed.get("action")
        if action and action != "none":
            parent = normalize_path_str(parsed.get("parent_dir"))
            name = sanitize_filename(parsed.get("name", ""))
            return {
                "action": action,
                "name": name,
                "parent_dir": parent,
                "path": str(Path(parent) / name),
                "content": parsed.get("content", ""),
                "requires_confirmation": action in ("delete_file", "delete_folder")
            }
    except Exception:
        pass

    return None

if __name__ == "__main__":
    queries = [
        "create a folder name Demo inside D:\\jarvis_test",
        "create a folder name Demo inside D:\\\\jarvis_test",
        "create folder Demo in D:\\jarvis_test",
        "D:\\jarvis_test e Demo2 folder banao",
        "create a file notes.txt on desktop with text hello",
        "make a folder called 'My Project' in Documents",
        "delete the Demo folder"
    ]
    for q in queries:
        res = parse_filesystem_command(q)
        print(f"Query: {q}")
        print(f" -> Slots: {res}\n")
