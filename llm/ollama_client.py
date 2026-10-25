import json
import time

import requests

from config import OLLAMA_HOST, OLLAMA_MODEL


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """You are JARVIS, a world-class AI personal assistant running locally on the user's Windows PC.

IDENTITY & PERSONALITY:
- Tone: Professional, courteous, razor-sharp, confident ("Very well, Sir", "Right away").
- Role: Complete PC copilot, software engineer, and researcher.
- Honesty: Never hallucinate facts or pretend tools succeeded when they failed. If you do not have fresh knowledge (current news, today's weather, prices, sports, software versions), say "I will check" and call the search tool.

TOOL USAGE POLICY:
1. When asked to perform an action on the computer (files, applications, media, system status, shell), call the appropriate tool immediately.
2. When asked about current events, news, today's weather, exchange rates, or live data, ALWAYS call web.search, web.research, or web.weather.
3. When controlling YouTube, use the dedicated youtube.* or browser.* tools.
4. Output ONLY valid JSON matching this schema when invoking a tool:
{
  "tool": "tool_name",
  "args": {
    "arg1": "value1"
  }
}
5. Do NOT output markdown code fences around tool call JSON.
6. Do NOT provide explanations before or after a tool call.
7. If no tool is needed (general knowledge, coding logic, conversational chat), respond naturally with clean Markdown formatting.

ANSWER STYLE:
- Direct, concise, and structured.
- For technical explanations, provide clear step-by-step logic and syntax-highlighted code blocks.
- When answering from web research, cite source URLs clearly."""


# ============================================================
# CONNECTION RETRY SETTINGS
#
# Ollama sometimes hasn't finished starting its background
# service yet when JARVIS makes its very first request (e.g.
# right after boot/login). These settings let a request retry
# a few times with a short backoff instead of failing outright
# on a single refused connection.
# ============================================================

OLLAMA_MAX_RETRIES = 4
OLLAMA_RETRY_DELAY_SECONDS = 2
OLLAMA_RETRY_BACKOFF = 1.5


# ============================================================
# KNOWN TOOL NAMESPACES
#
# Used both by the dotted-string repair (existing behaviour)
# and by the nested-object repair added below.
# ============================================================

KNOWN_NAMESPACES = (
    "filesystem",
    "system",
    "browser",
    "youtube",
    "web",
)

known_prefixes = tuple(
    f"{namespace}." for namespace in KNOWN_NAMESPACES
)

SINGLE_ARG_KEY_MAP = {
    "open": "url",
    "open_app": "command",
    "delete_file": "path",
    "search": "query",
    "play": "query_or_url",
    "seek": "seconds",
    "weather": "location",
}


# ============================================================
# RESPONSE CLEANER
# ============================================================

def _clean_response(text):
    """
    Clean common Qwen formatting mistakes.
    """

    if not text:
        return ""

    text = str(text).strip()

    # --------------------------------------------------------
    # Remove markdown code fences
    # --------------------------------------------------------

    if text.startswith("```"):

        lines = text.splitlines()

        cleaned_lines = []

        for line in lines:

            stripped = line.strip()

            if stripped.startswith("```"):
                continue

            cleaned_lines.append(line)

        text = "\n".join(cleaned_lines).strip()

    return text


# ============================================================
# VALID TOOL CALL CHECK
# ============================================================

def _is_valid_tool_call(obj):
    """
    Check whether an object is a valid JARVIS tool call.
    """

    if not isinstance(obj, dict):
        return False

    tool = obj.get("tool")
    args = obj.get("args")

    return (
        isinstance(tool, str)
        and bool(tool.strip())
        and isinstance(args, dict)
    )


# ============================================================
# REPAIR NESTED-NAMESPACE TOOL JSON
#
# Handles the shape the model actually produced in practice:
#
#     {"browser": {"open": "https://..."}}
#
# instead of the correct:
#
#     {"tool": "browser.open", "args": {"url": "https://..."}}
#
# This is a different failure mode from the dotted-string
# malformed JSON handled by _repair_common_tool_json below --
# here the *entire text* is already valid JSON, it's just using
# the wrong schema (nested namespace/action objects instead of
# "tool"/"args"). json.loads() succeeds on it, so the old code
# never even reached the string-repair path for this case.
# ============================================================

def _repair_nested_namespace_tool_json(obj):
    """
    Try to convert {"<namespace>": {"<action>": <value>}} into
    a proper {"tool": "<namespace>.<action>", "args": {...}}
    tool call. Returns None if `obj` doesn't match that shape.
    """

    if not isinstance(obj, dict) or len(obj) != 1:
        return None

    (namespace, inner), = obj.items()

    try:
        from tools.router import TOOL_ALIASES
    except Exception:
        TOOL_ALIASES = {}

    if namespace in TOOL_ALIASES or "." in namespace:
        tool_name = TOOL_ALIASES.get(namespace, namespace)
        args = inner if isinstance(inner, dict) else {}
        return {"tool": tool_name, "args": args}

    if namespace not in KNOWN_NAMESPACES:
        return None

    if not isinstance(inner, dict) or len(inner) != 1:
        return None

    (action, value), = inner.items()

    if not isinstance(action, str) or not action.strip():
        return None

    tool_name = f"{namespace}.{action}"

    if isinstance(value, dict):
        args = value
    else:
        arg_key = SINGLE_ARG_KEY_MAP.get(action, "value")
        args = {arg_key: value}

    return {
        "tool": tool_name,
        "args": args,
    }


# ============================================================
# REPAIR MALFORMED TOOL JSON
# ============================================================

def _repair_common_tool_json(text):
    """
    Repair common malformed tool JSON generated by Qwen.

    Examples:

        {"filesystem.delete_file":"path":"test.txt"}

    becomes:

        {
            "tool": "filesystem.delete_file",
            "args": {
                "path": "test.txt"
            }
        }

    Also supports multiple arguments such as:

        {"filesystem.create_file":"path":"test.txt","content":""}
    """

    if not text:
        return None

    text = _clean_response(text).strip()

    # --------------------------------------------------------
    # First: try valid JSON
    # --------------------------------------------------------

    try:

        obj = json.loads(text)

        if _is_valid_tool_call(obj):
            return obj

        # The text is valid JSON but not in {"tool","args"}
        # shape -- check for the nested-namespace mistake
        # (e.g. {"browser": {"open": "url"}}) before giving up.
        nested_repair = _repair_nested_namespace_tool_json(obj)

        if nested_repair:
            return nested_repair

    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # --------------------------------------------------------
    # Only attempt repair on object-looking text
    # --------------------------------------------------------

    if not (
        text.startswith("{")
        and text.endswith("}")
        
    ):
        return None

    # --------------------------------------------------------
    # Known tool prefixes (dotted-string malformed JSON, e.g.
    # {"filesystem.delete_file":"path":"test.txt"})
    # --------------------------------------------------------

    tool_name = None

    for prefix in known_prefixes:

        marker = '"' + prefix

        start = text.find(marker)

        if start == -1:
            continue

        end = text.find('"', start + 1)

        if end == -1:
            continue

        candidate = text[
            start + 1:end
        ]

        if candidate.startswith(prefix):

            tool_name = candidate
            break

    if not tool_name:
        return None

    # --------------------------------------------------------
    # Get content after tool name
    # --------------------------------------------------------

    tool_pos = text.find(
        '"' + tool_name + '"'
    )

    if tool_pos == -1:
        return None

    remainder = text[
        tool_pos + len(tool_name) + 2:
    ].strip()

    # Usually starts with :
    if remainder.startswith(":"):
        remainder = remainder[1:].strip()

    # --------------------------------------------------------
    # Parse malformed arguments
    #
    # "path":"test.txt"
    # "path":"test.txt","content":"hello"
    # --------------------------------------------------------

    args = {}

    while remainder:

        remainder = remainder.strip()

        # Remove separators
        while remainder.startswith(","):
            remainder = remainder[1:].strip()

        # Remove final }
        if remainder == "}":
            break

        if remainder.endswith("}"):
            remainder = remainder[:-1].strip()

        if not remainder:
            break

        # ----------------------------------------------------
        # Argument name
        # ----------------------------------------------------

        if not remainder.startswith('"'):
            break

        remainder = remainder[1:]

        name_end = remainder.find('"')

        if name_end == -1:
            break

        arg_name = remainder[:name_end]

        remainder = remainder[
            name_end + 1:
        ].strip()

        # ----------------------------------------------------
        # Colon
        # ----------------------------------------------------

        if not remainder.startswith(":"):
            break

        remainder = remainder[1:].strip()

        # ----------------------------------------------------
        # String value
        # ----------------------------------------------------

        if remainder.startswith('"'):

            remainder = remainder[1:]

            value_end = None
            escaped = False

            for i, char in enumerate(remainder):

                if char == '"' and not escaped:
                    value_end = i
                    break

                if char == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False

            if value_end is None:
                break

            arg_value = remainder[:value_end]

            # Unescape JSON-style strings
            try:
                arg_value = json.loads(
                    '"' + arg_value + '"'
                )
            except Exception:
                pass

            args[arg_name] = arg_value

            remainder = remainder[
                value_end + 1:
            ].strip()

        # ----------------------------------------------------
        # Non-string JSON value
        # ----------------------------------------------------

        else:

            value_end = len(remainder)

            comma_pos = remainder.find(",")

            brace_pos = remainder.find("}")

            positions = [
                p for p in (
                    comma_pos,
                    brace_pos
                )
                if p != -1
            ]

            if positions:
                value_end = min(positions)

            raw_value = remainder[
                :value_end
            ].strip()

            try:
                arg_value = json.loads(raw_value)
            except Exception:
                arg_value = raw_value.strip('"')

            args[arg_name] = arg_value

            remainder = remainder[
                value_end:
            ].strip()

        # ----------------------------------------------------
        # Continue if comma exists
        # ----------------------------------------------------

        if remainder.startswith(","):
            remainder = remainder[1:].strip()
            continue

        if remainder.startswith("}"):
            break

        if not remainder:
            break

        # Unexpected remainder
        break

    # --------------------------------------------------------
    # Return repaired tool call
    # --------------------------------------------------------

    if tool_name and isinstance(args, dict):

        return {
            "tool": tool_name,
            "args": args,
        }

    return None


# ============================================================
# EXTRACT JSON OBJECT FROM SURROUNDING TEXT
# ============================================================

def _extract_json_object(text):
    """
    Extract the first balanced JSON object from text.

    Example:

        Sure, I will delete it.
        {"tool":"filesystem.delete_file","args":{"path":"test.txt"}}

    Returns the JSON object portion.
    """

    if not text:
        return None

    start = text.find("{")

    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):

        char = text[i]

        # Handle escaped characters inside strings
        if in_string:

            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = False

            continue

        # Start string
        if char == '"':
            in_string = True
            continue

        # Object depth
        if char == "{":

            depth += 1

        elif char == "}":

            depth -= 1

            if depth == 0:
                return text[
                    start:i + 1
                ]

    return None


# ============================================================
# POST TO OLLAMA WITH RETRY/BACKOFF
# ============================================================

def _post_chat_with_retry(payload):
    """
    POST to the Ollama /api/chat endpoint, retrying a few times
    with backoff if the connection is refused or times out.

    This covers the common case where Ollama's background
    service hasn't finished starting yet (e.g. right after
    Windows boot/login) when JARVIS makes its first request.

    Real HTTP errors (bad model, bad request, etc.) are NOT
    retried -- raise_for_status() will raise immediately for
    those on the first attempt that gets a response.
    """

    last_error = None

    delay = OLLAMA_RETRY_DELAY_SECONDS

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):

        try:

            response = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

            return response

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:

            last_error = e

            if attempt < OLLAMA_MAX_RETRIES:

                print(
                    f"[OLLAMA] Connection attempt {attempt} "
                    f"failed ({e}). Retrying in {delay:.1f}s..."
                )

                time.sleep(delay)

                delay *= OLLAMA_RETRY_BACKOFF

                continue

            raise

    if last_error:
        raise last_error

    raise RuntimeError(
        "Failed to reach Ollama for an unknown reason."
    )


# ============================================================
# OLLAMA NATIVE TOOLS DEFINITION
# ============================================================

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": "Search YouTube for music, songs, or videos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_play",
            "description": "Play a YouTube video by search query or URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_or_url": {"type": "string", "description": "Search query or YouTube URL"}
                },
                "required": ["query_or_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_pause",
            "description": "Pause the currently playing YouTube video.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_seek",
            "description": "Seek forward or backward in the YouTube video by N seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer", "description": "Seconds to seek (+forward, -backward)"}
                },
                "required": ["seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "Open a website URL in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Website URL to open"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for up-to-date information, news, or facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get current weather forecast for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location name"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_status",
            "description": "Get real-time CPU, RAM, disk usage, and top processes.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filesystem_create_file",
            "description": "Create a file on the filesystem with content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filesystem_read_file",
            "description": "Read contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filesystem_delete_file",
            "description": "Delete a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filesystem_list_dir",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"}
                },
                "required": ["path"]
            }
        }
    }
]


# ============================================================
# CHAT
# ============================================================

def chat(messages, tools_text=""):
    """
    Send a conversation to local Ollama/Qwen.
    Uses native Ollama tool calling when tools_text is provided.
    """

    msgs = [
        {
            "role": "system",
            "content": (
                SYSTEM_PROMPT
                + ("\n\nTOOLS:\n" + tools_text if tools_text else "")
            ),
        }
    ]

    msgs.extend(messages)

    payload = {
        "model": OLLAMA_MODEL,
        "messages": msgs,
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "num_predict": 256,
            "temperature": 0.3,
        },
    }

    if tools_text:
        payload["tools"] = OLLAMA_TOOLS

    response = _post_chat_with_retry(payload)
    data = response.json()
    msg = data.get("message", {})

    # Check for native Ollama tool calling
    tool_calls = msg.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
        first = tool_calls[0]
        fn = first.get("function", {})
        raw_name = fn.get("name", "")
        args = fn.get("arguments", {})
        try:
            from tools.router import TOOL_ALIASES
            tool_name = TOOL_ALIASES.get(raw_name)
            if not tool_name:
                parts = raw_name.split("_", 1)
                if len(parts) == 2 and parts[0] in ("filesystem", "system", "browser", "youtube", "web", "image", "schedule"):
                    tool_name = f"{parts[0]}.{parts[1]}"
                else:
                    tool_name = raw_name
        except Exception:
            tool_name = raw_name
        return json.dumps({"tool": tool_name, "args": args if isinstance(args, dict) else {}})

    content = msg.get("content", "")
    return _clean_response(content)


# ============================================================
# TOOL CALL DETECTOR
# ============================================================

def is_tool_call(text):
    """
    Detect and parse a JARVIS tool call.
    Returns:
        dict -> valid tool call
        None -> normal assistant response
    """
    if not text:
        return None

    text = _clean_response(text)
    if not text:
        return None

    # 1. Entire response is valid JSON
    try:
        obj = json.loads(text)
        if _is_valid_tool_call(obj):
            return obj

        nested_repair = _repair_nested_namespace_tool_json(obj)
        if nested_repair and _is_valid_tool_call(nested_repair):
            return nested_repair
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # 2. JSON surrounded by normal text
    candidate = _extract_json_object(text)
    if candidate:
        try:
            obj = json.loads(candidate)
            if _is_valid_tool_call(obj):
                return obj
            nested_repair = _repair_nested_namespace_tool_json(obj)
            if nested_repair and _is_valid_tool_call(nested_repair):
                return nested_repair
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        repaired = _repair_common_tool_json(candidate)
        if repaired and _is_valid_tool_call(repaired):
            return repaired

    # 3. Repair malformed Qwen JSON
    repaired = _repair_common_tool_json(text)
    if repaired and _is_valid_tool_call(repaired):
        return repaired

    # 4. Emergency lenient tool call extraction
    return parse_lenient_tool_call(text)


def parse_lenient_tool_call(text: str) -> Optional[dict]:
    """
    Emergency lenient parser: if assistant text contains a JSON object
    or fragment that looks like a tool call, extract and repair it.
    """
    if not text:
        return None
    cleaned = _clean_response(text).strip()

    # Match patterns like {"browser_open": {"url": "..."}} or {"web_research": {"query": "..."}}
    patterns = [
        r'\{\s*["\']?(browser[._]\w+|youtube[._]\w+|system[._]\w+|web[._]\w+|filesystem[._]\w+|weather|news)["\']?\s*:\s*(\{.*?\}|["\'].*?["\'])\s*\}',
        r'\{\s*["\']tool["\']\s*:\s*["\']([^"\']+)["\']\s*,\s*["\']args["\']\s*:\s*(\{.*?\})\s*\}',
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.DOTALL)
        if m:
            tool_name = m.group(1)
            raw_args = m.group(2)
            try:
                from tools.router import TOOL_ALIASES
                normalized_name = TOOL_ALIASES.get(tool_name)
                if not normalized_name:
                    parts = tool_name.split("_", 1)
                    if len(parts) == 2 and parts[0] in ("filesystem", "system", "browser", "youtube", "web", "image", "schedule"):
                        normalized_name = f"{parts[0]}.{parts[1]}"
                    else:
                        normalized_name = tool_name
                tool_name = normalized_name
            except Exception:
                pass
            args = {}
            try:
                args = json.loads(raw_args)
            except Exception:
                s = raw_args.strip("\"'")
                if "open" in tool_name or "url" in tool_name:
                    args = {"url": s}
                elif "search" in tool_name or "query" in tool_name or "research" in tool_name:
                    args = {"query": s}
                elif "play" in tool_name:
                    args = {"query_or_url": s}
                else:
                    args = {"value": s}
            if not isinstance(args, dict):
                args = {"value": args}
            return {"tool": tool_name, "args": args}
    return None


def is_raw_tool_json(text: str) -> bool:
    """Return True if text looks like raw tool JSON that should never be shown to user."""
    t = text.strip()
    if (t.startswith("{") and t.endswith("}")) or t.startswith("```json") or t.startswith("```"):
        keywords = [
            "browser_open", "browser.open", "youtube_search", "youtube_play",
            "web_search", "web.search", "web_research", "web.research",
            "system_status", "system.status", '"tool":', '"args":'
        ]
        if any(kw in t for kw in keywords):
            return True
    return False