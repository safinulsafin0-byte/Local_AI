import re
from pathlib import Path
import shutil
import hashlib
import os
from typing import Optional, Dict, Any, Tuple
from config import ALLOWED_ROOT_DIRS

try:
    from send2trash import send2trash
    SEND2TRASH_OK = True
except ImportError:
    SEND2TRASH_OK = False

DEFAULT_WORKING_DIR = r"D:\jarvis_test"

def normalize_path_str(p_str: Optional[str]) -> str:
    """Normalizes paths: collapses slashes, expands env vars, maps aliases, defaults to D:\\jarvis_test."""
    if not p_str or not str(p_str).strip():
        return DEFAULT_WORKING_DIR
    s = str(p_str).strip().strip("\"'")
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
    """Validates and strips invalid Windows filename chars: \\ / : * ? \" < > |."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    return cleaned

def translate_exception(exc: Exception) -> str:
    """Translates raw Python exceptions into plain, human-friendly explanations."""
    msg = str(exc)
    if "WinError 123" in msg or "syntax is incorrect" in msg.lower():
        return "That folder or file name is not valid on Windows."
    if "WinError 5" in msg or "permission denied" in msg.lower():
        return "Permission denied when accessing this path."
    if "WinError 2" in msg or "file not found" in msg.lower() or "cannot find the file" in msg.lower():
        return "The specified file or directory was not found."
    if "WinError 183" in msg or "already exists" in msg.lower():
        return "A file or folder with that name already exists."
    return msg

def parse_filesystem_command(query: str) -> Optional[Dict[str, Any]]:
    """Extracts structured slots {action, name, parent_dir, content} with deterministic patterns and Ollama fallback."""
    q = query.strip()
    
    # If the user is requesting compound code generation & execution (e.g. "and run the code", "and run it"),
    # do NOT parse as simple filesystem command! Let it fall through to the compound coding executor.
    if re.search(r"\b(?:and\s+run|and\s+execute|run\s+the\s+code|run\s+it)\b", q, re.IGNORECASE):
        return None

    # 0. If user is asking for general information, search, image, weather, news, or URLs, NEVER parse as filesystem!
    non_fs_triggers = [
        r"\b(?:image|picture|photo|illustration|art|draw|paint|face|faces|render)\b",
        r"\b(?:search|news|weather|price|stock|today|who\s+is|what\s+is|how\s+to|explain|information\s+about|details?\s+about)\b",
        r"\b(?:http|https|www\.|\.com|\.org|\.net|\.io|\.edu)\b",
        r"\b(?:youtube|video|play|song|music|audio|volume)\b"
    ]
    for nft in non_fs_triggers:
        if re.search(nft, q, re.IGNORECASE):
            if not re.search(r"\b(?:create|make|write|delete|remove)\s+(?:a\s+)?(?:file|folder|directory)\b", q, re.IGNORECASE):
                return None

    # 1. Banglish patterns: "PATH e/te/er moddhe X folder banao"
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

    # 1B. Direct file path: "create file D:\test.txt with content abc"
    m_file_direct = re.search(
        r"(?:create|make|write)\s+(?:a\s+)?file\s+[\"']?([a-zA-Z]:[\\/][^\s\"']+)[\"']?(?:\s+(?:with\s+(?:content|text)?|and\s+write)\s+[\"']?(.*?)[\"']?)?$",
        q,
        re.IGNORECASE
    )
    if m_file_direct:
        p_raw = m_file_direct.group(1).strip()
        content = (m_file_direct.group(2) or "").strip()
        full_p = normalize_path_str(p_raw)
        name = Path(full_p).name
        parent = str(Path(full_p).parent)
        return {
            "action": "create_file",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": content
        }

    # 1C. Direct folder path: "create folder D:\my_folder"
    m_folder_direct = re.search(
        r"(?:create|make|mkdir)\s+(?:a\s+)?(?:folder|directory)\s+[\"']?([a-zA-Z]:[\\/][^\s\"']+)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_folder_direct:
        p_raw = m_folder_direct.group(1).strip()
        full_p = normalize_path_str(p_raw)
        name = Path(full_p).name
        parent = str(Path(full_p).parent)
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

    # 2B. Read file with explicit location: "read file sample_note.txt in D:\jarvis_test"
    m_read_loc = re.search(
        r"(?:read|cat|view|show|open)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|from|within|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_read_loc:
        name_raw = m_read_loc.group(1).strip()
        p_raw = m_read_loc.group(2).strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "read_file",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": "",
        }

    # 3. File creation: "create a file notes.txt on desktop with text hello"
    m_file = re.search(
        r"(?:create|make|write)\s+(?:a\s+)?file\s+(?:name[d]?|called|naam)?\s*[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|within|on|at)\s+[\"']?([^\"'\r\n]+?)[\"']?(?:\s+(?:with\s+(?:content|text)|and\s+write)\s+[\"']?(.*?)[\"']?)?$",
        q,
        re.IGNORECASE
    )
    if m_file:
        name_raw = m_file.group(1).strip()
        p_raw = m_file.group(2).strip()
        content = (m_file.group(3) or "").strip()
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

    # 5. Delete folder with explicit location: "delete folder Demo in D:\jarvis_test" or "delete Demo folder inside D:\jarvis_test"
    m_del_fol_loc = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:folder|directory)\s+[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|from|within|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    ) or re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:folder|directory)\s+(?:inside|in|under|from|within|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_del_fol_loc:
        name_raw = m_del_fol_loc.group(1).strip()
        p_raw = m_del_fol_loc.group(2).strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        return {
            "action": "delete_folder",
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": "",
        }

    # 5B. Delete file with explicit location: "delete file demo.txt in D:\jarvis_test" or "delete demo.py inside D:\personal-ai-full"
    m_del_file_loc = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\"'\r\n]+?)[\"']?\s+(?:inside|in|under|from|within|at)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
        q,
        re.IGNORECASE
    )
    if m_del_file_loc:
        name_raw = m_del_file_loc.group(1).strip()
        p_raw = m_del_file_loc.group(2).strip()
        parent = normalize_path_str(p_raw)
        name = sanitize_filename(name_raw)
        full_p = str(Path(parent) / name)
        act = "delete_folder" if os.path.isdir(full_p) else "delete_file"
        return {
            "action": act,
            "name": name,
            "parent_dir": parent,
            "path": full_p,
            "content": "",
        }

    # 5C. Delete file with extension or keyword: "delete demo.py", "delete file notes.txt", "delete D:\jarvis_test\test.py"
    m_del_f = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\"'\r\n]+?\.[a-zA-Z0-9_]{1,10})[\"']?$",
        q,
        re.IGNORECASE
    ) or re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file)\s+[\"']?([^\"'\r\n]+?)[\"']?$",
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
        }

    # 5D. Delete folder: "delete the Demo folder" / "delete folder Demo" / "delete D:\jarvis_test\Demo"
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
        }

    # Structured output fallback via Ollama (ONLY when query explicitly mentions file/folder context)
    if not re.search(r"\b(file|files|folder|folders|directory|dir|ls|documents?|desktop|downloads?|[a-zA-Z]:[\\/])\b", q, re.IGNORECASE):
        return None

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

def _allowed(path):
    p = Path(os.path.expandvars(str(path))).expanduser().resolve()
    from config import TRUST_MODE
    if TRUST_MODE == "full":
        return p
    for root in ALLOWED_ROOT_DIRS:
        try:
            p.relative_to(root.resolve())
            return p
        except (ValueError, RuntimeError):
            continue
    # In Windows, drive root checks
    try:
        if any(str(p).upper().startswith(str(r).upper()) for r in ALLOWED_ROOT_DIRS):
            return p
    except Exception:
        pass
    raise PermissionError(f"Path is outside allowed roots: {p}")

def list_dir(path="."):
    p = _allowed(normalize_path_str(path))
    if not p.is_dir():
        return f"ERROR: Not a directory: {p}"
    items = []
    for x in p.iterdir():
        try:
            items.append(f"{x.name}\t{'DIR' if x.is_dir() else 'FILE'}\t{x.stat().st_size if x.is_file() else ''}")
        except Exception:
            items.append(f"{x.name}\tUNKNOWN")
    return "\n".join(items)

def read_file(path):
    try:
        if any(w in str(path).lower() for w in (" inside ", " in ", " under ", " within ", " on ", " at ")):
            parsed = parse_filesystem_command(f"read file {path}")
            if parsed and parsed.get("path"):
                path = parsed["path"]
            else:
                path = normalize_path_str(path)
        else:
            path = normalize_path_str(path)
        p = _allowed(path)
        if not p.is_file():
            return f"ERROR: File not found: {p}"
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: Could not read file: {translate_exception(e)}"

def create_file(path, content=""):
    try:
        # Check if path needs re-parsing
        if any(w in str(path).lower() for w in (" inside ", " in ", " under ", " within ", " on ", " at ")):
            parsed = parse_filesystem_command(f"create file {path} with {content}")
            if parsed and parsed.get("path"):
                path = parsed["path"]
                if not content and parsed.get("content"):
                    content = parsed["content"]
            else:
                path = normalize_path_str(path)
        else:
            path = normalize_path_str(path)

        p = _allowed(path)
        created_parents = False
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            created_parents = True

        p.write_text(content, encoding="utf-8")
        if not p.is_file():
            return f"ERROR: File was not created at {p}."
        size = p.stat().st_size
        note = f" (created parent directory {p.parent})" if created_parents else ""
        return f"SUCCESS: Created file at {p} ({size} bytes written){note}."
    except Exception as e:
        return f"ERROR: Could not create file: {translate_exception(e)}"

def create_folder(path):
    try:
        if any(w in str(path).lower() for w in (" inside ", " in ", " under ", " within ", " on ", " at ")):
            parsed = parse_filesystem_command(f"create folder {path}")
            if parsed and parsed.get("path"):
                path = parsed["path"]
            else:
                path = normalize_path_str(path)
        else:
            path = normalize_path_str(path)

        p = _allowed(path)
        created_parents = False
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            created_parents = True

        p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            return f"ERROR: Folder was not created at {p}."
        note = f" (created parent directory {p.parent})" if created_parents else ""
        return f"SUCCESS: Created folder at {p}{note}."
    except Exception as e:
        return f"ERROR: Could not create folder: {translate_exception(e)}"

def write_file(path, content):
    try:
        path = normalize_path_str(path)
        p = _allowed(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if not p.is_file():
            return f"ERROR: File was not written at {p}."
        size = p.stat().st_size
        return f"SUCCESS: Written file at {p} ({size} bytes)."
    except Exception as e:
        return f"ERROR: Could not write file: {translate_exception(e)}"

def append_file(path, content):
    try:
        p = _allowed(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        size = p.stat().st_size
        return f"SUCCESS: Appended to file at {p} (total {size} bytes)."
    except Exception as e:
        return f"ERROR: Could not append to file: {e}"

def rename(path, new_name):
    try:
        p = _allowed(path)
        target = _allowed(p.parent / new_name)
        p.rename(target)
        if not target.exists():
            return f"ERROR: File was not renamed to {target}."
        return f"SUCCESS: Renamed to: {target}"
    except Exception as e:
        return f"ERROR: Could not rename: {e}"

def move(path, destination):
    try:
        p = _allowed(path)
        d = _allowed(destination)
        d.mkdir(parents=True, exist_ok=True)
        target = d / p.name
        shutil.move(str(p), str(target))
        if not target.exists():
            return f"ERROR: Target does not exist after move: {target}."
        return f"SUCCESS: Moved to: {target}"
    except Exception as e:
        return f"ERROR: Could not move: {e}"

def copy(path, destination):
    try:
        p = _allowed(path)
        d = _allowed(destination)
        d.mkdir(parents=True, exist_ok=True)
        target = d / p.name
        if p.is_dir():
            shutil.copytree(p, target, dirs_exist_ok=True)
        else:
            shutil.copy2(p, target)
        if not target.exists():
            return f"ERROR: Target does not exist after copy: {target}."
        return f"SUCCESS: Copied to: {target}"
    except Exception as e:
        return f"ERROR: Could not copy: {e}"

def delete_file(path):
    try:
        path = normalize_path_str(path)
        p = _allowed(path)
        if not p.is_file():
            return f"ERROR: File not found: {p}"
        if SEND2TRASH_OK:
            try:
                send2trash(str(p))
                if not p.exists():
                    return f"SUCCESS: Moved file to Recycle Bin: {p}"
            except Exception:
                pass
        p.unlink()
        if p.exists():
            return f"ERROR: File still exists after deletion: {p}"
        return f"SUCCESS: Deleted file: {p}"
    except Exception as e:
        return f"ERROR: Could not delete file: {translate_exception(e)}"

def delete_folder(path):
    try:
        path = normalize_path_str(path)
        p = _allowed(path)
        if not p.is_dir():
            return f"ERROR: Folder not found: {p}"
        if SEND2TRASH_OK:
            try:
                send2trash(str(p))
                if not p.exists():
                    return f"SUCCESS: Moved folder to Recycle Bin: {p}"
            except Exception:
                pass
        shutil.rmtree(p)
        if p.exists():
            return f"ERROR: Folder still exists after deletion: {p}"
        return f"SUCCESS: Deleted folder: {p}"
    except Exception as e:
        return f"ERROR: Could not delete folder: {translate_exception(e)}"

def search_files(root=".", pattern="*", content_query=None):
    p = _allowed(root)
    matches = []
    for x in p.rglob(pattern):
        if not x.is_file():
            continue
        if content_query:
            try:
                text = x.read_text(encoding="utf-8", errors="ignore")
                if content_query.lower() in text.lower():
                    matches.append(str(x))
            except Exception:
                pass
        else:
            matches.append(str(x))
        if len(matches) >= 500:
            break
    if not matches:
        return f"No files matching '{pattern}' found in {p}."
    return "\n".join(matches)

def find_duplicates(root="."):
    p = _allowed(root)
    hashes = {}
    duplicates = {}
    for x in p.rglob("*"):
        if not x.is_file():
            continue
        try:
            if x.stat().st_size == 0 or x.stat().st_size > 100 * 1024 * 1024:
                continue
            hasher = hashlib.md5()
            with open(x, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            h = hasher.hexdigest()
            if h in hashes:
                duplicates.setdefault(h, [hashes[h]]).append(str(x))
            else:
                hashes[h] = str(x)
        except Exception:
            continue
    if not duplicates:
        return "SUCCESS: No duplicate files found."
    out = ["SUCCESS: Found duplicate files:"]
    for h, files in duplicates.items():
        out.append(f"\nGroup (hash {h[:8]}):")
        for f in files:
            out.append(f"  - {f}")
    return "\n".join(out)

def organize_by_type(root="."):
    p = _allowed(root)
    ext_map = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"},
        "Documents": {".pdf", ".docx", ".doc", ".txt", ".pptx", ".xlsx", ".csv", ".md"},
        "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".cpp", ".c", ".rs", ".go"},
        "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
        "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    }
    moved = 0
    for item in p.iterdir():
        if item.is_file() and not item.name.startswith("."):
            ext = item.suffix.lower()
            dest_cat = "Other"
            for cat, exts in ext_map.items():
                if ext in exts:
                    dest_cat = cat
                    break
            dest_dir = p / dest_cat
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(dest_dir / item.name))
            moved += 1
    return f"SUCCESS: Organized {moved} files into category folders in {p}."

def tree_summary(root=".", max_depth=3):
    p = _allowed(root)
    lines = [f"{p.name}/"]
    def _walk(curr: Path, prefix="", depth=0):
        if depth >= max_depth:
            return
        try:
            items = sorted(list(curr.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "
                if item.is_dir():
                    lines.append(f"{prefix}{connector}{item.name}/")
                    _walk(item, prefix + sub_prefix, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{item.name}")
        except PermissionError:
            lines.append(f"{prefix}└── [Access Denied]")
    _walk(p)
    return "\n".join(lines[:300])
