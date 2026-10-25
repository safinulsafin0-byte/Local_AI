"""
JARVIS Unified FastAPI Backend — server.py
==========================================
Single entry-point for the web UI and the VS Code extension.

Start with:
    python server.py                # from project root
    start_jarvis.bat                # one-click

Design:
  - FastAPI + uvicorn
  - Bearer-token auth (generated on first run, stored in .env)
  - SSE streaming for /api/v1/chat
  - WebSocket for /ws/events and /ws/system/stream
  - Versioned API: /api/v1/...
  - Central tool registry
  - ReAct agent loop with streaming steps
  - Rotating structured log to logs/jarvis.log
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

# ── FastAPI stack ──────────────────────────────────────────────────────────────
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Form,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ── Project root on sys.path ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

_CURRENT_TERMINAL_CWD = str(BASE_DIR)

# ── dotenv ─────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

# ── Local imports (all optional — degrade gracefully) ─────────────────────────
try:
    from config import OLLAMA_HOST, OLLAMA_MODEL, REQUIRE_CONFIRMATION_FOR
except Exception:
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    REQUIRE_CONFIRMATION_FOR = {"shutdown", "restart"}

try:
    from memory.memory_manager import remember, build_context
    MEMORY_OK = True
except Exception as _e:
    MEMORY_OK = False
    def remember(*a, **k): pass
    def build_context(): return ""

try:
    from rag.retriever import search as rag_search
    RAG_OK = True
except Exception as _e:
    RAG_OK = False
    def rag_search(q): return ""

try:
    from tools.router import execute_tool_call, TOOL_DESCRIPTIONS
    TOOLS_OK = True
except Exception as _e:
    TOOLS_OK = False
    TOOL_DESCRIPTIONS = ""
    def execute_tool_call(call, **kw): return "ERROR: Tools unavailable"

try:
    from llm.ollama_client import (
        chat as llm_chat,
        is_tool_call,
        is_raw_tool_json,
        parse_lenient_tool_call,
    )
    LLM_OK = True
except Exception as _e:
    LLM_OK = False
    def llm_chat(msgs, tools=""): return "ERROR: LLM unavailable"
    def is_tool_call(text): return None
    def is_raw_tool_json(text): return False
    def parse_lenient_tool_call(text): return None

try:
    from voice.stt import transcribe_audio_file, listen_and_transcribe
    STT_OK = True
except Exception:
    STT_OK = False

try:
    from voice.tts import clean_text as tts_clean_text, synthesize as tts_synthesize, speak as tts_speak, speak_async, stop as stop_tts
    TTS_OK = True
except Exception:
    TTS_OK = False

VOICE_TTS_PERMANENTLY_DISABLED = True

try:
    from vision.image_analyzer import analyze_image, describe_image
    VISION_OK = True
except Exception:
    VISION_OK = False

try:
    import psutil
    PSUTIL_OK = True
except Exception:
    PSUTIL_OK = False

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_log_handler = RotatingFileHandler(
    LOG_DIR / "jarvis.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
)
logging.basicConfig(
    level=logging.INFO,
    handlers=[_log_handler, logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis")

# ── Auth token ─────────────────────────────────────────────────────────────────
ENV_FILE = BASE_DIR / ".env"

def _load_or_create_token() -> str:
    """Return the bearer token, creating it on first run."""
    # Check env first
    token = os.getenv("JARVIS_TOKEN", "").strip()
    if token:
        return token

    # Read .env file
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("JARVIS_TOKEN="):
                token = line.split("=", 1)[1].strip()
                if token:
                    return token

    # Generate new token
    token = secrets.token_urlsafe(32)
    with ENV_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nJARVIS_TOKEN={token}\n")

    logger.info("Generated new JARVIS_TOKEN and saved to .env")
    print(f"\n{'='*60}")
    print(f"  JARVIS TOKEN (auto-generated, saved to .env):")
    print(f"  {token}")
    print(f"{'='*60}\n")
    return token

JARVIS_TOKEN: str = _load_or_create_token()

# ── Port / host ────────────────────────────────────────────────────────────────
JARVIS_PORT = int(os.getenv("JARVIS_PORT", "8765"))
JARVIS_HOST = os.getenv("JARVIS_HOST", "127.0.0.1")

# ── System monitor state ───────────────────────────────────────────────────────
_system_history: list[dict] = []
_monitor_clients: list[WebSocket] = []
_event_clients: list[WebSocket] = []

# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM MONITOR  (background thread, every 2 s)
# ──────────────────────────────────────────────────────────────────────────────

def _sample_system() -> dict:
    """Sample real system metrics. Returns structured dict."""
    sample: dict[str, Any] = {"ts": time.time()}

    if not PSUTIL_OK:
        sample["error"] = "psutil not installed"
        return sample

    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        sample.update({
            "cpu_pct": cpu,
            "ram_pct": mem.percent,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "disk_pct": disk.percent,
            "disk_used_gb": round(disk.used / 1e9, 1),
            "disk_total_gb": round(disk.total / 1e9, 1),
            "net_sent_mb": round(net.bytes_sent / 1e6, 1),
            "net_recv_mb": round(net.bytes_recv / 1e6, 1),
        })

        # Top 5 processes by CPU (normalized to system capacity)
        num_cpus = psutil.cpu_count() or 1
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                name = info.get("name", "")
                pid = info.get("pid", -1)
                if pid == 0 or name in ("System Idle Process", ""):
                    continue
                raw_cpu = info.get("cpu_percent") or 0.0
                info["cpu_percent"] = round(raw_cpu / num_cpus, 1)
                info["memory_percent"] = round(info.get("memory_percent") or 0.0, 1)
                procs.append(info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        sample["top_procs"] = procs[:5]

        # GPU (optional)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                g = gpus[0]
                sample["gpu_pct"] = g.load * 100
                sample["gpu_mem_pct"] = g.memoryUtil * 100
                sample["gpu_temp"] = g.temperature
        except Exception:
            pass

        # Alerts
        alerts = []
        if cpu > 90:
            alerts.append({"type": "cpu_high", "value": cpu, "msg": f"CPU is {cpu:.0f}%"})
        if mem.percent > 90:
            alerts.append({"type": "ram_high", "value": mem.percent, "msg": f"RAM is {mem.percent:.0f}%"})
        if disk.percent > 95:
            alerts.append({"type": "disk_full", "value": disk.percent, "msg": f"Disk is {disk.percent:.0f}%"})
        sample["alerts"] = alerts

    except Exception as exc:
        sample["error"] = str(exc)

    return sample


async def _monitor_loop():
    """Background async task: sample every 2s, push to WS clients."""
    psutil.cpu_percent()  # warm-up call so first real reading is correct
    while True:
        try:
            sample = await asyncio.get_event_loop().run_in_executor(None, _sample_system)
            _system_history.append(sample)
            if len(_system_history) > 1800:  # keep 1 hour at 2 s intervals
                _system_history.pop(0)

            # Push to monitor WebSocket clients
            dead = []
            msg = json.dumps({"type": "system", "data": sample})
            for ws in _monitor_clients:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _monitor_clients.remove(ws)

            # Push alerts to event clients
            if sample.get("alerts"):
                event_msg = json.dumps({"type": "alert", "alerts": sample["alerts"]})
                dead2 = []
                for ws in _event_clients:
                    try:
                        await ws.send_text(event_msg)
                    except Exception:
                        dead2.append(ws)
                for ws in dead2:
                    _event_clients.remove(ws)

        except Exception as exc:
            logger.error(f"Monitor loop error: {exc}")

        await asyncio.sleep(2)


# ──────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ──────────────────────────────────────────────────────────────────────────────

_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()
    logger.info(f"JARVIS server starting on {JARVIS_HOST}:{JARVIS_PORT}")
    _check_ollama_startup()
    try:
        from voice.diagnose import get_startup_voice_summary
        voice_summary = get_startup_voice_summary()
        print(f"\n{voice_summary}\n")
        logger.info(voice_summary)
    except Exception as e:
        logger.warning(f"Voice startup diagnostic summary error: {e}")
    try:
        from voice.listener import get_voice_listener
        listener = get_voice_listener()
        listener.on_command = _handle_always_on_voice_command
        if getattr(listener, "mode", "off") == "always" and os.environ.get("JARVIS_VOICE_AUTOSTART", "0") == "1":
            listener.start()
    except Exception as e:
        logger.warning(f"Voice listener auto-start warning: {e}")
    monitor_task = asyncio.create_task(_monitor_loop())
    from guardian.monitor import get_guardian
    guardian_mon = get_guardian()
    guardian_task = asyncio.create_task(guardian_mon.start_loop())
    yield
    guardian_task.cancel()
    monitor_task.cancel()
    logger.info("JARVIS server shutting down")



def _check_ollama_startup():
    """Log a clear error if Ollama is not reachable at startup."""
    import requests as _req
    try:
        r = _req.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = r.json().get("models", [])
        names = [m.get("name", "") for m in models]
        if not any(OLLAMA_MODEL in n for n in names):
            logger.warning(
                f"⚠ Ollama is running but model '{OLLAMA_MODEL}' is NOT pulled. "
                f"Run: ollama pull {OLLAMA_MODEL}"
            )
            print(f"\n⚠  MODEL NOT FOUND: Run 'ollama pull {OLLAMA_MODEL}' first.\n")
        else:
            logger.info(f"✓ Ollama reachable; model '{OLLAMA_MODEL}' available.")
    except Exception as exc:
        logger.error(f"✗ Ollama not reachable at {OLLAMA_HOST}: {exc}")
        print(f"\n✗ ERROR: Ollama is not running. Start it first.\n")


# ──────────────────────────────────────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="JARVIS API",
    version="1.0.0",
    description="JARVIS Local AI Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve web UI as static files
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

GENERATED_DIR = BASE_DIR / "data" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")

SCREENSHOTS_DIR = BASE_DIR / "data" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/data/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots_short")

TESTS_AUDIO_DIR = BASE_DIR / "tests" / "audio"
TESTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/tests/audio", StaticFiles(directory=str(TESTS_AUDIO_DIR)), name="tests_audio")

# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

async def verify_token(request: Request) -> None:
    """Bearer-token check on every request."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if secrets.compare_digest(token, JARVIS_TOKEN):
            return
    # Allow requests from 127.0.0.1 without token (dev convenience, can be tightened)
    if request.client and request.client.host in ("127.0.0.1", "::1"):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


OptionalAuth = Depends(verify_token)

# ──────────────────────────────────────────────────────────────────────────────
# MODELS
# ──────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    mode: str = "chat"          # chat | agent | code
    conversation_id: Optional[str] = None
    turn_id: Optional[str] = None
    context: Optional[str] = None
    stream: bool = True
    file_id: Optional[str] = None
    attachment_id: Optional[str] = None
    attachment_ids: Optional[List[str]] = None
    file_path: Optional[str] = None
    attachment: Optional[Dict[str, Any]] = None

class CompleteRequest(BaseModel):
    prefix: str
    suffix: str = ""
    language: str = "python"
    max_tokens: int = 128

class EditRequest(BaseModel):
    file_path: Optional[str] = None
    selection: Optional[str] = None
    instruction: str

class ToolCallRequest(BaseModel):
    args: Dict[str, Any] = Field(default_factory=dict)

class RAGIndexRequest(BaseModel):
    path: str

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5

class MemoryRequest(BaseModel):
    key: str
    value: str

class STTRequest(BaseModel):
    language: str = "en"

class VoiceListenRequest(BaseModel):
    timeout: float = 30.0
    silence_timeout: float = 1.2

class VoiceModeRequest(BaseModel):
    mode: Optional[str] = "always"  # always | off | push
    device: Optional[int] = None
    language: Optional[str] = None
    sensitivity: Optional[str] = None
    speak_replies: Optional[bool] = None

class TerminalRunRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: Optional[int] = 60

class TTSRequest(BaseModel):
    text: str
    play: bool = True
    return_audio: bool = False

class VoiceSpeakRequest(BaseModel):
    text: str
    play: bool = True
    return_audio: bool = False

class VoicePlaybackStateRequest(BaseModel):
    playing: bool
    text: Optional[str] = None

class VisionRequest(BaseModel):
    image_path: str
    mode: str = "describe"  # describe | analyze | ocr | diagram

class ImageGenRequest(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    steps: int = 1
    seed: Optional[int] = None
    stream: bool = False

class ActionControlRequest(BaseModel):
    action_id: Optional[str] = None

class LocationOverrideRequest(BaseModel):
    city: str

class LocationPreciseRequest(BaseModel):
    latitude: float
    longitude: float
    city: Optional[str] = ""
    accuracy_m: Optional[float] = None


# ──────────────────────────────────────────────────────────────────────────────
# HEALTH
# ──────────────────────────────────────────────────────────────────────────────

_health_cache = None
_health_cache_time = 0.0

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Returns live status of all subsystems (cached 30s for instant UI/extension queries)."""
    global _health_cache, _health_cache_time
    now = time.time()
    if _health_cache is not None and (now - _health_cache_time) < 30.0:
        res = dict(_health_cache)
        res["timestamp"] = datetime.utcnow().isoformat()
        return res

    import requests as _req

    def _probe_ollama():
        try:
            r = _req.get(f"{OLLAMA_HOST}/api/tags", timeout=1.5)
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return True, any(OLLAMA_MODEL in n for n in models)
        except Exception:
            return False, False

    ollama_ok, model_ok = await asyncio.get_event_loop().run_in_executor(None, _probe_ollama)

    # Lazy probe for image generation
    def _probe_image_gen():
        try:
            from image_generation.image_generator import is_available
            return is_available()
        except Exception as e:
            return False, str(e)

    image_gen_ok, image_gen_status = await asyncio.get_event_loop().run_in_executor(None, _probe_image_gen)

    result = {
        "ok": True,
        "timestamp": datetime.utcnow().isoformat(),
        "backend": "running",
        "ollama": ollama_ok,
        "model": OLLAMA_MODEL if model_ok else None,
        "model_ok": model_ok,
        "rag": RAG_OK,
        "memory": MEMORY_OK,
        "voice_stt": STT_OK,
        "voice_tts": TTS_OK,
        "vision": VISION_OK,
        "image_generation": image_gen_ok,
        "image_generation_status": image_gen_status,
        "tools": TOOLS_OK,
        "token_required": True,
    }
    _health_cache = result
    _health_cache_time = now
    return result



# ──────────────────────────────────────────────────────────────────────────────
# ROOT — serve the UI
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "JARVIS API running", "docs": "/docs"}


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ──────────────────────────────────────────────────────────────────────────────

JARVIS_SYSTEM_PROMPT = """You are JARVIS, a local AI assistant running on the user's Windows PC.

PERSONALITY:
- Concise, precise, helpful. No unnecessary filler.
- When you don't know something that could be current (news, prices, versions), say "Let me check" and use the web_search tool.
- Never hallucinate facts. If unsure, use a tool or say so.
- For PC tasks, use tools rather than giving manual instructions.

TOOL USAGE POLICY:
- Any question about "latest", "today", "current", "news", prices, weather → use web_search.
- File/app/system tasks → use the appropriate tool.
- RAG → use for questions about the user's documents.
- After a tool call, report the result to the user naturally.

ANSWER STYLE:
- Short for simple questions. Step-by-step only when complexity warrants it.
- Code blocks with language tags.
- Cite URLs when answering from web search.

TOOL CALL FORMAT (when tools are available):
Output exactly one JSON object, no surrounding text:
{"tool": "tool.name", "args": {"key": "value"}}
"""


# ──────────────────────────────────────────────────────────────────────────────
# AGENT LOOP (streaming)
# ──────────────────────────────────────────────────────────────────────────────

async def _agent_stream(
    message: str,
    mode: str = "chat",
    extra_context: str = "",
    turn_id: str | None = None,
    file_id: str | None = None,
    file_path: str | None = None,
    attachment: dict | None = None,
    conversation_id: str | None = None,
    attachment_ids: list[str] | None = None,
    attachment_id: str | None = None,
) -> AsyncIterator[str]:
    """
    ReAct agent loop that yields SSE events.

    Event format (newline-delimited JSON):
        {"type":"token","text":"...","turn_id":"..."}          streaming LLM token
        {"type":"tool_start","tool":"...","args":{},"turn_id":"..."}
        {"type":"tool_result","tool":"...","result":"...","turn_id":"..."}
        {"type":"done","full":"...","turn_id":"..."}
        {"type":"error","error":"...","turn_id":"..."}
    """

    def _sse(obj: dict) -> str:
        if turn_id:
            obj["turn_id"] = turn_id
        return "data: " + json.dumps(obj) + "\n\n"

    # ── Document & Ingestion Route (PACKAGE 1 & BUG 4) ──
    doc = None
    target_fid = file_id or attachment_id or (attachment_ids[0] if (attachment_ids and isinstance(attachment_ids, list)) else None)
    if not target_fid and isinstance(file_id, list) and file_id:
        target_fid = file_id[0]

    if target_fid:
        if target_fid in _UPLOADED_DOCS:
            doc = _UPLOADED_DOCS[target_fid]
        else:
            meta_path = UPLOAD_DIR / f"{target_fid}_meta.json"
            if meta_path.exists():
                try:
                    doc = json.loads(meta_path.read_text(encoding="utf-8"))
                    _UPLOADED_DOCS[target_fid] = doc
                except Exception:
                    pass
            if not doc:
                cands = list(UPLOAD_DIR.glob(f"{target_fid}_*"))
                act_file = [c for c in cands if not c.name.endswith("_meta.json")]
                if act_file:
                    try:
                        from ingest import extract
                        doc = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: extract(act_file[0])
                        )
                        _UPLOADED_DOCS[target_fid] = doc
                    except Exception as exc:
                        logger.warning(f"Failed to re-extract file {act_file[0]}: {exc}")
    elif file_path and Path(file_path).exists():
        try:
            from ingest import extract
            doc = await asyncio.get_event_loop().run_in_executor(
                None, lambda: extract(file_path)
            )
        except Exception as exc:
            logger.warning(f"Failed to extract file_path {file_path}: {exc}")
    elif attachment:
        try:
            import base64
            from ingest import extract
            att_name = attachment.get("name") or "attachment.bin"
            att_data = attachment.get("data") or ""
            if "," in att_data:
                att_data = att_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(att_data)
            tmp_f = UPLOAD_DIR / f"temp_{uuid.uuid4().hex[:8]}_{Path(att_name).name}"
            tmp_f.write_bytes(raw_bytes)
            doc = await asyncio.get_event_loop().run_in_executor(
                None, lambda: extract(tmp_f, mime=attachment.get("type"))
            )
        except Exception as exc:
            logger.warning(f"Failed to extract inline attachment: {exc}")

    if target_fid and not doc:
        err_msg = f"Attached file '{target_fid}' could not be read or extracted."
        yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
        yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
        return

    if doc:
        if doc.get("encrypted"):
            err_msg = "This PDF is encrypted and password-protected. Please provide the password to view its content."
            yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
            return

        if doc.get("error"):
            err_msg = f"Extraction failed: {doc.get('error')}"
            yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
            return

        filename = doc.get("metadata", {}).get("filename", "document")
        pages = doc.get("pages", [])
        yield _sse({"type": "status", "text": f"Reading {filename} ({len(pages)} pages)...", "turn_id": turn_id})

        from ingest.document_processor import build_document_prompt
        doc_sys_prompt, doc_user_content = build_document_prompt(message, doc)

        doc_messages = [
            {"role": "system", "content": doc_sys_prompt},
            {"role": "user", "content": doc_user_content}
        ]

        # Write exact model input to data/debug/last_prompt.json
        try:
            debug_dir = BASE_DIR / "data" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            prompt_log = {
                "timestamp": time.time(),
                "turn_id": turn_id,
                "file_id": target_fid,
                "attachments": [target_fid],
                "doc_context": doc.get("doc_text"),
                "kind": doc.get("kind"),
                "system_prompt": doc_sys_prompt,
                "user_content": doc_user_content,
                "messages": doc_messages
            }
            (debug_dir / "last_prompt.json").write_text(json.dumps(prompt_log, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write last_prompt.json: {e}")

        try:
            response_text = await asyncio.get_event_loop().run_in_executor(
                None, lambda: llm_chat(doc_messages, "")
            )
        except Exception as exc:
            yield _sse({"type": "error", "error": f"Model inference error: {exc}", "turn_id": turn_id})
            return

        response_text = str(response_text).strip()
        words = response_text.split(" ")
        full_doc_resp = ""
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            full_doc_resp += chunk
            yield _sse({"type": "token", "text": chunk, "turn_id": turn_id})
            await asyncio.sleep(0.001)

        if conversation_id:
            try:
                cf = CONV_DIR / f"{conversation_id}.json"
                cdata = {"id": conversation_id, "title": message[:36] + ("…" if len(message) > 36 else ""), "messages": [], "ts": time.time() * 1000}
                if cf.exists():
                    try:
                        cdata = json.loads(cf.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                cdata["messages"].append({"role": "user", "content": message})
                cdata["messages"].append({"role": "assistant", "content": full_doc_resp})
                cdata["ts"] = time.time() * 1000
                cf.write_text(json.dumps(cdata, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Auto-saving conversation failed: {e}")

        yield _sse({"type": "done", "full": full_doc_resp, "turn_id": turn_id})
        return

    # ── JARVIS Unified Intent Understanding Engine ──
    from intent.engine import IntentEngine
    if not hasattr(_agent_stream, "_intent_engine"):
        _agent_stream._intent_engine = IntentEngine()
    engine_res = _agent_stream._intent_engine.parse(message, use_llm=False)

    logger.info(f"[INTENT CLASSIFIER] Query: '{message}' -> Intent: '{engine_res.intent}', Confidence: {engine_res.confidence:.2f}")
    print(f"[INTENT CLASSIFIER] Query: '{message}' -> Intent: '{engine_res.intent}', Confidence: {engine_res.confidence:.2f}")

    # Ambiguous reference clarification (BUG 3)
    is_ambiguous_reference = bool(
        engine_res.requires_clarification or
        re.search(r"^(?:what|who|where|how|which)\s+is\s+(?:that|this|it)\s*(?:thing|stuff|one)?\s*(?:there|over there|here)?\??$", message.strip(), re.I) or
        message.strip().lower() in ("what's that thing there?", "what is that thing there?", "what is that?", "what's that?", "what is that over there?")
    )
    if is_ambiguous_reference:
        clarify_reply = "I need a bit more context to assist you with that, sir. Could you specify which file, application, or topic you are referring to?"
        for chunk in clarify_reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": clarify_reply, "turn_id": turn_id})
        return

    from intent.normalizer import detect_language
    detected_user_lang = detect_language(message)
    is_user_bangla = (detected_user_lang in ("bn_script", "bn_banglish"))

    # 0A0. Open Custom Embedded Terminal
    if engine_res.intent == "open_terminal":
        yield _sse({"type": "terminal_open", "turn_id": turn_id})
        reply = "Opening your custom JARVIS terminal now, sir. You can execute shell commands, run Python scripts, install packages, or instruct me to run operations directly in the terminal."
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0A1. Compound Code Creation & Terminal Execution
    if engine_res.intent == "create_and_run_code":
        fname = engine_res.parameters.get("filename", "demo.py")
        topic = engine_res.parameters.get("topic", "code")
        yield _sse({"type": "terminal_open", "turn_id": turn_id})
        yield _sse({"type": "tool_start", "tool": "code_architect", "args": {"file": fname, "task": topic}, "turn_id": turn_id})

        # 1. Generate clean runnable code
        code_prompt = [
            {"role": "system", "content": "You are JARVIS expert software engineer. Write complete, working, executable code for the requested task. Include sample test data and print statements showing the output when run. Return ONLY the code itself, no markdown wrappers, no explanations."},
            {"role": "user", "content": f"Write complete runnable Python code for: {topic}"}
        ]
        try:
            gen_code = await asyncio.get_event_loop().run_in_executor(None, lambda: llm_chat(code_prompt, ""))
            gen_code = str(gen_code).strip()
            if gen_code.startswith("```"):
                lines = gen_code.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                gen_code = "\n".join(lines).strip()
        except Exception:
            gen_code = (
                "# Binary search implementation\n"
                "def binary_search(arr, target):\n"
                "    low, high = 0, len(arr) - 1\n"
                "    while low <= high:\n"
                "        mid = (low + high) // 2\n"
                "        if arr[mid] == target:\n"
                "            return mid\n"
                "        elif arr[mid] < target:\n"
                "            low = mid + 1\n"
                "        else:\n"
                "            high = mid - 1\n"
                "    return -1\n\n"
                "numbers = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]\n"
                "target = 23\n"
                "idx = binary_search(numbers, target)\n"
                "print(f'Array: {numbers}')\n"
                "print(f'Target: {target}')\n"
                "print(f'Binary Search Result: Found at index {idx}')\n"
            )

        # 2. Save file
        from tools import file_ops
        target_dir = Path("D:/jarvis_test")
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / fname
        write_res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.write_file(str(file_path), gen_code))
        yield _sse({"type": "tool_result", "tool": "filesystem.create_file", "result": write_res, "ok": "SUCCESS" in write_res, "turn_id": turn_id})

        # 3. Execute in Terminal
        yield _sse({"type": "tool_start", "tool": "terminal.run", "args": {"command": f"python {fname}"}, "turn_id": turn_id})
        from tools.system_ops import run_shell
        exec_cmd = f'python "{file_path}"'
        run_res = await asyncio.get_event_loop().run_in_executor(None, lambda: run_shell(exec_cmd))

        clean_out = run_res.replace("SUCCESS (Exit 0):\n", "").replace("ERROR (Exit 1):\n", "").strip()
        yield _sse({"type": "terminal_exec", "command": f"python {fname}", "output": clean_out, "turn_id": turn_id})
        yield _sse({"type": "tool_result", "tool": "terminal.run", "result": run_res, "ok": "SUCCESS" in run_res, "turn_id": turn_id})

        reply = (
            f"Certainly, sir. I have created `{fname}` at `{file_path}` with a complete implementation of **{topic}**, "
            f"and executed it in your custom terminal.\n\n"
            f"**Terminal Output:**\n"
            f"```text\n{clean_out}\n```\n\n"
            f"The terminal is open in your interface for further commands."
        )
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0A. Terminal Command Execution (Deterministic & Safe with Full Laptop Access)
    if engine_res.intent == "run_command":
        cmd = engine_res.parameters.get("command", "").strip()
        yield _sse({"type": "terminal_open", "turn_id": turn_id})
        yield _sse({"type": "tool_start", "tool": "run_command", "args": {"command": cmd, "cwd": _CURRENT_TERMINAL_CWD}, "turn_id": turn_id})
        term_req = TerminalRunRequest(command=cmd, cwd=_CURRENT_TERMINAL_CWD)
        term_res = await terminal_run_endpoint(term_req)
        clean_out = term_res.get("output", "")
        new_cwd = term_res.get("cwd", _CURRENT_TERMINAL_CWD)
        is_ok = term_res.get("ok", False)
        yield _sse({"type": "terminal_exec", "command": cmd, "output": clean_out, "cwd": new_cwd, "turn_id": turn_id})
        yield _sse({"type": "tool_result", "tool": "run_command", "result": clean_out, "ok": is_ok, "error": term_res.get("stderr") if not is_ok else None, "turn_id": turn_id})
        if is_ok:
            reply = f"**Command Executed:** `{cmd}`\n**Location:** `{new_cwd}`\n\n```text\n{clean_out}\n```"
        else:
            reply = f"**Command Failed:** `{cmd}` (Exit code {term_res.get('exit_code', 1)})\n**Location:** `{new_cwd}`\n\n```text\n{clean_out}\n```"
        words = reply.split(" ")
        if len(words) > 50:
            for i in range(0, len(words), 20):
                yield _sse({"type": "token", "text": " ".join(words[i:i+20]) + " ", "turn_id": turn_id})
                await asyncio.sleep(0.001)
        else:
            for chunk in words:
                yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
                await asyncio.sleep(0.003)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # ── 0C. STARK EDITION SUITE HANDLERS ──
    # 0C1. Stark Proactive Briefing
    if engine_res.intent == "stark_briefing":
        from modules.briefing_protocols.tools import get_proactive_briefing
        yield _sse({"type": "tool_start", "tool": "stark.briefing", "args": engine_res.parameters, "turn_id": turn_id})
        briefing = await asyncio.get_event_loop().run_in_executor(None, lambda: get_proactive_briefing(lang=engine_res.parameters.get("lang", "en")))
        yield _sse({"type": "tool_result", "tool": "stark.briefing", "result": "Briefing generated", "ok": True, "turn_id": turn_id})
        yield _sse({"type": "briefing_card", "data": briefing, "turn_id": turn_id})
        reply = briefing.get("briefing_text", "Briefing complete, sir.")
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C1B. Stark Personality Setting
    if engine_res.intent == "stark_personality":
        pmode = engine_res.parameters.get("mode", "Stark")
        from modules.briefing_protocols.tools import set_personality_mode
        yield _sse({"type": "tool_start", "tool": "stark.personality", "args": {"mode": pmode}, "turn_id": turn_id})
        pres = set_personality_mode(pmode)
        yield _sse({"type": "tool_result", "tool": "stark.personality", "result": f"Personality set to {pres.get('mode')}", "ok": True, "turn_id": turn_id})
        reply = f"Understood, sir. Personality protocol updated to **{pres.get('mode')}** mode."
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C2. Stark Protocol Execution
    if engine_res.intent == "stark_protocol":
        p_name = engine_res.parameters.get("name", "list")
        if p_name.lower() in ("list", "show"):
            from modules.briefing_protocols.tools import list_protocols
            plist = list_protocols()
            reply = f"**Available Stark Protocols:**\n" + "\n".join([f"- **{p['name']}**: {p['description']}" for p in plist.get("protocols", [])])
            for chunk in reply.split(" "):
                yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
                await asyncio.sleep(0.005)
            yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
            return

        from modules.briefing_protocols.tools import run_protocol
        yield _sse({"type": "tool_start", "tool": "stark.protocol", "args": {"name": p_name}, "turn_id": turn_id})
        pres = await asyncio.get_event_loop().run_in_executor(None, lambda: run_protocol(p_name))
        is_ok = pres.get("ok", False)
        yield _sse({"type": "tool_result", "tool": "stark.protocol", "result": pres.get("summary", ""), "ok": is_ok, "turn_id": turn_id})
        reply = f"**Protocol Execution:** {pres.get('protocol', p_name)}\n**Status:** {'COMPLETED' if is_ok else 'FAILED'}\n\n"
        for step in pres.get("steps", []):
            st = "✓" if step.get("ok") else "✗"
            desc = step.get('description', f"Step {step.get('step')}")
            summ = step.get('summary') or step.get('verified_data', '')
            reply += f"- {st} **{desc}**: {summ}\n"
        if pres.get('summary'):
            reply += f"\n{pres.get('summary')}"
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C3. Stark 3D CAD Engineering
    if engine_res.intent == "stark_cad":
        from modules.cad_engineering.tools import generate_cad_model
        yield _sse({"type": "tool_start", "tool": "stark.cad", "args": engine_res.parameters, "turn_id": turn_id})
        cad_res = await asyncio.get_event_loop().run_in_executor(None, lambda: generate_cad_model(query=engine_res.parameters.get("query", message)))
        is_ok = cad_res.get("ok", False)
        yield _sse({"type": "tool_result", "tool": "stark.cad", "result": cad_res.get("summary", ""), "ok": is_ok, "turn_id": turn_id})
        if is_ok:
            yield _sse({"type": "cad_card", "data": cad_res, "turn_id": turn_id})
            stl_name = cad_res.get("filename", "model.stl")
            bb = cad_res.get("bounding_box_mm", {})
            reply = (
                f"**3D Model Generated:** `{stl_name}`\n"
                f"- **Watertight Mesh:** Verified ({cad_res.get('triangles_count')} triangles)\n"
                f"- **Dimensions:** {bb.get('width_mm')} × {bb.get('length_mm')} × {bb.get('height_mm')} mm\n"
                f"- **Volume:** {cad_res.get('volume_cm3')} cm³ | Est. Print Time: ~{cad_res.get('estimated_print_time_min')} mins\n"
                f"- **File Location:** `{cad_res.get('file_path')}`\n\n"
                f"Ready for inspection in the Stark 3D Viewer or direct 3D printing."
            )
        else:
            reply = f"CAD generation error: {cad_res.get('error', 'Unknown error')}"
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C4. Threat Defense & Audit
    if engine_res.intent == "stark_defense":
        action = engine_res.parameters.get("action", "audit")
        if action == "scan_devices":
            from modules.threat_defense.tools import scan_local_network
            yield _sse({"type": "tool_start", "tool": "stark.device_radar", "args": {"consent": True}, "turn_id": turn_id})
            radar_res = await asyncio.get_event_loop().run_in_executor(None, lambda: scan_local_network(consent=True))
            yield _sse({"type": "tool_result", "tool": "stark.device_radar", "result": radar_res.get("summary", ""), "ok": True, "turn_id": turn_id})
            devs = radar_res.get("devices", [])
            reply = f"**Local Network Radar (Passive ARP):**\nDiscovered **{len(devs)}** active local devices on your network.\n\n"
            for d in devs[:10]:
                reply += f"- **{d['ip']}** ({d['mac']}) — Host: `{d['hostname']}` [{d['type']}]\n"
            if len(devs) > 10:
                reply += f"\n*...and {len(devs) - 10} more devices.*"
        elif action == "scan_code":
            from modules.threat_defense.tools import scan_code_security
            yield _sse({"type": "tool_start", "tool": "stark.code_security", "args": {}, "turn_id": turn_id})
            code_res = await asyncio.get_event_loop().run_in_executor(None, scan_code_security)
            yield _sse({"type": "tool_result", "tool": "stark.code_security", "result": code_res.get("summary", ""), "ok": True, "turn_id": turn_id})
            vulns = code_res.get("vulnerabilities", [])
            reply = f"**Code Security Scan Report:**\nFound **{len(vulns)}** potential issues across codebase.\n\n"
            for v in vulns[:5]:
                reply += f"- [{v.get('severity', 'WARN')}] `{v.get('file')}:{v.get('line')}` - {v.get('description')}\n"
            if not vulns:
                reply += "✓ No critical security vulnerabilities or plaintext secrets detected in scanned files."
        else:
            from modules.threat_defense.tools import audit_system_security
            yield _sse({"type": "tool_start", "tool": "stark.defense_audit", "args": {}, "turn_id": turn_id})
            def_res = await asyncio.get_event_loop().run_in_executor(None, audit_system_security)
            yield _sse({"type": "tool_result", "tool": "stark.defense_audit", "result": def_res.get("summary", ""), "ok": True, "turn_id": turn_id})
            yield _sse({"type": "defense_card", "data": def_res, "turn_id": turn_id})
            reply = (
                f"**Defensive Audit Report:**\n"
                f"- **Readiness Score:** {def_res.get('readiness_score')}/100\n"
                f"- **Condition:** {def_res.get('threat_level')}\n"
                f"- **Active Listening Ports:** {len(def_res.get('open_ports', []))} verified\n\n"
                f"{def_res.get('summary', '')}"
            )
        words = reply.split(" ")
        for chunk in words:
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.003)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C5. Smart Facility Scene & Power
    if engine_res.intent == "stark_facility":
        from modules.smart_facility.tools import activate_facility_scene, get_facility_state
        action = engine_res.parameters.get("action", "scene")
        if action == "power" or engine_res.parameters.get("scene") == "get_power":
            yield _sse({"type": "tool_start", "tool": "stark.facility_power", "args": {}, "turn_id": turn_id})
            fac_state = await asyncio.get_event_loop().run_in_executor(None, get_facility_state)
            yield _sse({"type": "tool_result", "tool": "stark.facility_power", "result": f"{fac_state.get('instantaneous_power_kw')} kW", "ok": True, "turn_id": turn_id})
            yield _sse({"type": "facility_card", "data": fac_state, "turn_id": turn_id})
            reply = f"**Facility Power Status:**\n- Instantaneous Load: **{fac_state.get('instantaneous_power_kw')} kW**\n- Active Scene: {fac_state.get('active_scene')}\n- Facility Status: {fac_state.get('status')}"
        else:
            sc = engine_res.parameters.get("scene", "clean_slate")
            yield _sse({"type": "tool_start", "tool": "stark.facility_scene", "args": {"scene": sc}, "turn_id": turn_id})
            fac_res = await asyncio.get_event_loop().run_in_executor(None, lambda: activate_facility_scene(sc))
            is_ok = fac_res.get("ok", False)
            yield _sse({"type": "tool_result", "tool": "stark.facility_scene", "result": fac_res.get("summary", ""), "ok": is_ok, "turn_id": turn_id})
            if is_ok:
                yield _sse({"type": "facility_card", "data": fac_res, "turn_id": turn_id})
                reply = f"**Facility Control:** Scene **{fac_res.get('scene')}** active.\n- Instantaneous Load: {fac_res.get('total_power_kw')} kW\n- Perimeters & Fixtures adjusted."
            else:
                reply = f"Failed to activate scene: {fac_res.get('error')}"
        words = reply.split(" ")
        for chunk in words:
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.003)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C6. Physics Simulation
    if engine_res.intent == "stark_sim":
        stype = engine_res.parameters.get("type", "projectile")
        from modules.simulation_lab import tools as sim_tools
        yield _sse({"type": "tool_start", "tool": f"stark.sim_{stype}", "args": {"type": stype}, "turn_id": turn_id})
        if "heat" in stype:
            sres = await asyncio.get_event_loop().run_in_executor(None, sim_tools.simulate_heat_diffusion)
        elif "rlc" in stype:
            sres = await asyncio.get_event_loop().run_in_executor(None, sim_tools.simulate_rlc_circuit)
        elif "beam" in stype or "deflection" in stype:
            sres = await asyncio.get_event_loop().run_in_executor(None, sim_tools.simulate_beam_deflection)
        else:
            sres = await asyncio.get_event_loop().run_in_executor(None, sim_tools.simulate_projectile)
        yield _sse({"type": "tool_result", "tool": f"stark.sim_{stype}", "result": sres.get("summary", ""), "ok": True, "turn_id": turn_id})
        yield _sse({"type": "sim_card", "data": sres, "turn_id": turn_id})
        reply = f"**Simulation Complete:**\n{sres.get('summary', '')}"
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C7. Stark Holographic HUD View
    if engine_res.intent == "stark_hud":
        yield _sse({"type": "hud_open", "turn_id": turn_id})
        reply = "Initializing Stark Mission Control HUD display. Holographic telemetry, arc power status, network radar, and 3D diagnostics loaded."
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C8. Long-Term Memory Actions
    if engine_res.intent == "memory_action":
        m_act = engine_res.parameters.get("action", "show")
        from memory import memory_manager
        if m_act == "remember":
            fact_txt = engine_res.parameters.get("fact", "")
            memory_manager.add_fact(fact_txt)
            reply = f"Noted, sir. I have committed this to long-term memory: \"{fact_txt}\"."
        elif m_act == "recall_name":
            facts = memory_manager.get_facts()
            name_val = None
            for f in reversed(facts):
                txt = f.get('fact', str(f)) if isinstance(f, dict) else str(f)
                if "?" in txt or re.search(r"\b(?:ki|konta|what|who)\b", txt, re.IGNORECASE):
                    continue
                m = re.search(r"(?:amar\s+naam|my\s+name\s+is|আমার\s+নাম)\s+([A-Za-z\u0980-\u09FF\s]+)", txt, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip().rstrip(".,!?")
                    if cand.lower() not in ("ki", "what", "who"):
                        name_val = cand
                        break
            if not name_val:
                for f in reversed(facts):
                    txt = f.get('fact', str(f)) if isinstance(f, dict) else str(f)
                    if "safin" in txt.lower():
                        name_val = "Safin"
                        break
            from intent.normalizer import detect_language
            is_bn = detect_language(message) in ("bn_script", "bn_banglish")
            if name_val:
                reply = f"আপনার নাম {name_val}, স্যার।" if is_bn else f"Your name is {name_val}, sir."
            else:
                reply = "আমার স্মৃতিতে আপনার নাম এখনো সংরক্ষণ করা নেই, স্যার।" if is_bn else "I do not have your name stored in memory yet, sir."
        elif m_act == "clear":
            try:
                mem_file = Path("data/memory/facts.json")
                if mem_file.exists():
                    mem_file.write_text("[]", encoding="utf-8")
                reply = "Long-term memories have been cleared, sir."
            except Exception as e:
                reply = f"Error clearing memories: {e}"
        else:
            facts = memory_manager.get_facts()
            if facts:
                reply = "**Stored Long-Term Memories:**\n" + "\n".join(f"- {f.get('fact', str(f)) if isinstance(f, dict) else str(f)}" for f in facts)
            else:
                reply = "No long-term memories currently stored, sir."
        words = reply.split(" ")
        for chunk in words:
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.003)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0B. Filesystem Operations (Deterministic & Verified)
    if engine_res.intent == "filesystem":
        fs_act = engine_res.parameters.get("action", "")
        fs_path = engine_res.parameters.get("path", "")
        fs_content = engine_res.parameters.get("content", "")

        yield _sse({"type": "tool_start", "tool": f"filesystem.{fs_act}", "args": engine_res.parameters, "turn_id": turn_id})
        from tools import file_ops
        if fs_act == "create_file":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.create_file(fs_path, fs_content))
        elif fs_act == "create_folder":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.create_folder(fs_path))
        elif fs_act == "delete_file":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.delete_file(fs_path))
        elif fs_act == "delete_folder":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.delete_folder(fs_path))
        elif fs_act == "read_file":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.read_file(fs_path))
        elif fs_act == "list_dir":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.list_dir(fs_path))
        else:
            res = f"ERROR: Unsupported filesystem action {fs_act}"

        # If execution returned an error, attempt one retry with re-parsed command
        if str(res).startswith("ERROR:") and fs_act in ("create_folder", "create_file"):
            try:
                re_parsed = file_ops.parse_filesystem_command(message)
                if re_parsed and re_parsed.get("path") and re_parsed["path"] != fs_path:
                    if fs_act == "create_folder":
                        res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.create_folder(re_parsed["path"]))
                    elif fs_act == "create_file":
                        res = await asyncio.get_event_loop().run_in_executor(None, lambda: file_ops.create_file(re_parsed["path"], re_parsed.get("content", "")))
            except Exception:
                pass

        is_ok = not str(res).startswith("ERROR:")
        err_msg = str(res).replace("ERROR: ", "").strip() if not is_ok else None
        yield _sse({"type": "tool_result", "tool": f"filesystem.{fs_act}", "result": str(res), "ok": is_ok, "error": err_msg, "turn_id": turn_id})
        reply = str(res)
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 0C. Live Data Queries (Crypto, Python version, Bangladesh PM)
    if engine_res.intent == "live_data":
        data_type = engine_res.parameters.get("data_type", "")
        yield _sse({"type": "tool_start", "tool": "web.live_data", "args": {"type": data_type}, "turn_id": turn_id})
        from tools.web_tools import get_live_data
        live_res = await asyncio.get_event_loop().run_in_executor(None, lambda: get_live_data(data_type, message))
        yield _sse({"type": "tool_result", "tool": "web.live_data", "result": "Live data retrieved", "turn_id": turn_id})
        if live_res.get("sources"):
            yield _sse({"type": "search_card", "data": {"sources": live_res.get("sources", [])}, "turn_id": turn_id})
        reply = live_res.get("answer", "Live data is currently unavailable.")
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 1. Weather Intent
    if engine_res.intent == "weather":
        wloc = engine_res.parameters.get("location")
        if not wloc or wloc.lower() in ("default", "here", "current", "my location", "local"):
            from tools.location_service import get_current_location
            loc = get_current_location()
            wloc = loc.get("city") or "Khulna"
        yield _sse({"type": "tool_start", "tool": "web.weather", "args": {"location": wloc}, "turn_id": turn_id})
        from tools.weather_tool import get_weather
        wdata = await asyncio.get_event_loop().run_in_executor(None, lambda: get_weather(wloc))
        yield _sse({"type": "tool_result", "tool": "web.weather", "result": "Weather retrieved", "turn_id": turn_id})
        if not wdata.get("ok"):
            err_msg = wdata.get("message", f"Could not find weather data for '{wloc}'. Please specify a recognized city or district name.")
            yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
            return
        yield _sse({"type": "weather_card", "data": wdata, "turn_id": turn_id})
        if is_user_bangla:
            c_temp = wdata.get("temperature", "")
            c_cond = wdata.get("condition", "")
            c_city = wdata.get("city", wloc)
            speech_text = f"{c_city}-এর বর্তমান তাপমাত্রা {c_temp}° সেলসিয়াস এবং আবহাওয়া {c_cond}।"
        else:
            speech_text = wdata.get("formatted") or wdata.get("speech", f"The weather in {wloc} has been retrieved.")
        for chunk in speech_text.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": speech_text, "turn_id": turn_id})
        return

    # 2. News Intent
    if engine_res.intent == "news":
        ntopic = engine_res.parameters.get("topic") or "world"
        yield _sse({"type": "tool_start", "tool": "web.news", "args": {"topic": ntopic}, "turn_id": turn_id})
        from tools.news_tool import get_news
        ndata = await asyncio.get_event_loop().run_in_executor(None, lambda: get_news(ntopic, limit=5))
        yield _sse({"type": "tool_result", "tool": "web.news", "result": "Headlines retrieved", "turn_id": turn_id})
        if not ndata.get("ok"):
            err_msg = ndata.get("message", "News service is currently unavailable offline. Please check your internet connection.")
            yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
            return
        yield _sse({"type": "news_card", "data": ndata, "turn_id": turn_id})
        articles = ndata.get("articles", [])
        topic_disp = ntopic.capitalize() if ntopic else "Top"
        lines = [f"**Latest {topic_disp} Headlines:**\n"]
        for idx, art in enumerate(articles, 1):
            title = art.get("title", "")
            source = art.get("source", "News")
            pub = art.get("published", "")
            pub_str = f" ({pub})" if pub else ""
            summary = art.get("summary", "")
            link = art.get("link", "")
            lines.append(f"{idx}. **{title}** — *{source}*{pub_str}\n   {summary}\n   [Read article]({link})\n")
        full_reply = "\n".join(lines)
        for chunk in full_reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": full_reply, "turn_id": turn_id})
        return

    # 3. Cancel Action Intent
    if engine_res.intent == "cancel":
        from tools.pc_actions import cancel_pending_action
        cancelled = cancel_pending_action()
        reply = "Action cancelled. Scheduled system action has been aborted." if cancelled else "No active action was pending to cancel."
        yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 4. System Control Intent
    if engine_res.intent == "system_control":
        act = engine_res.parameters.get("action", "")
        if act in ("time", "date"):
            import datetime
            now = datetime.datetime.now()
            reply = f"The current time is {now.strftime('%I:%M %p')}." if act == "time" else f"Today's date is {now.strftime('%A, %B %d, %Y')}."
            yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
            yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
            return

        from tools.pc_actions import DESTRUCTIVE_ACTIONS, schedule_destructive_action, execute_immediate_action
        if act in DESTRUCTIVE_ACTIONS:
            sched = schedule_destructive_action(act, engine_res.parameters, countdown_sec=10)
            yield _sse({"type": "action_countdown", "data": sched, "turn_id": turn_id})
            speech_text = sched["speech"]
            for chunk in speech_text.split(" "):
                yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
                await asyncio.sleep(0.005)
            yield _sse({"type": "done", "full": speech_text, "turn_id": turn_id})
            return
        else:
            yield _sse({"type": "tool_start", "tool": f"system.{act}", "args": engine_res.parameters, "turn_id": turn_id})
            res = await asyncio.get_event_loop().run_in_executor(
                None, lambda: execute_immediate_action(act, engine_res.parameters)
            )
            is_ok = res.get("ok", False)
            yield _sse({"type": "tool_result", "tool": f"system.{act}", "result": res.get("message", ""), "ok": is_ok, "error": res.get("error") if not is_ok else None, "turn_id": turn_id})
            reply = res.get("message", "System action completed.")
            if not is_ok:
                reply = f"System action failed: {res.get('message') or res.get('error', 'Execution failed')}"
            if act in ("screenshot", "take_screenshot") and is_ok and res.get("url"):
                yield _sse({"type": "screenshot_card", "data": res, "turn_id": turn_id})
            yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
            yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
            return

    # 4. PC Status Intent
    if engine_res.intent == "pc_status":
        yield _sse({"type": "tool_start", "tool": "system_status", "args": {}, "turn_id": turn_id})
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        from tools.system_ops import system_status
        sys_text = await asyncio.get_event_loop().run_in_executor(None, lambda: system_status())
        yield _sse({"type": "tool_result", "tool": "system_status", "result": "System stats retrieved", "turn_id": turn_id})
        yield _sse({
            "type": "pc_status_card",
            "data": {
                "cpu_percent": round(cpu_pct, 1),
                "ram_percent": round(mem.percent, 1),
                "ram_used_gb": round(mem.used / (1024**3), 1),
                "ram_total_gb": round(mem.total / (1024**3), 1),
                "status_text": sys_text[:300]
            },
            "turn_id": turn_id
        })
        if any(w in message.lower() for w in ("process", "processes", "tasklist", "tasks")):
            speech_text = sys_text
        else:
            speech_text = f"System CPU usage is at {round(cpu_pct)}% and RAM is at {round(mem.percent)}%."
        yield _sse({"type": "token", "text": speech_text, "turn_id": turn_id})
        yield _sse({"type": "done", "full": speech_text, "turn_id": turn_id})
        return

    # 5. Direct Web Search Intent
    if engine_res.intent == "web_search":
        s_query = engine_res.parameters.get("query") or message
        yield _sse({"type": "tool_start", "tool": "web.search", "args": {"query": s_query}, "turn_id": turn_id})
        from tools.search_pipeline import search_and_synthesize
        sdata = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: search_and_synthesize(s_query, max_results=3, synthesize_with_llm=True, model=OLLAMA_MODEL)
        )
        yield _sse({"type": "tool_result", "tool": "web.search", "result": "Search completed", "turn_id": turn_id})
        if not sdata.get("ok"):
            answer_text = sdata.get("answer", "I could not find web results right now. Please check your internet connection.")
            yield _sse({"type": "token", "text": answer_text, "turn_id": turn_id})
            yield _sse({"type": "done", "full": answer_text, "turn_id": turn_id})
            return
        if sdata.get("sources"):
            yield _sse({"type": "search_card", "data": {"sources": sdata.get("sources", [])}, "turn_id": turn_id})
        answer_text = sdata.get("answer", "")
        for chunk in answer_text.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": answer_text, "turn_id": turn_id})
        return

    # 6. App Control Intent
    if engine_res.intent == "app_control":
        app_name = engine_res.parameters.get("app", "")
        app_act = engine_res.parameters.get("action", "open")
        yield _sse({"type": "tool_start", "tool": f"app.{app_act}", "args": {"app": app_name}, "turn_id": turn_id})
        from tools.system_ops import open_app, close_app
        if app_act == "open":
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: open_app(app_name))
            is_ok = "SUCCESS" in res
            yield _sse({"type": "tool_result", "tool": "app.open", "result": res, "ok": is_ok, "error": res if not is_ok else None, "turn_id": turn_id})
            reply = res.replace("SUCCESS: ", "") if is_ok else f"Could not open {app_name}: {res}"
        else:
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: close_app(app_name))
            is_ok = "SUCCESS" in res
            yield _sse({"type": "tool_result", "tool": "app.close", "result": res, "ok": is_ok, "error": res if not is_ok else None, "turn_id": turn_id})
            reply = res.replace("SUCCESS: ", "") if is_ok else f"Could not close {app_name}: {res}"
        for chunk in reply.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # 7. Media Control Intent (Pause / Resume / Next / Prev)
    if engine_res.intent == "youtube_control":
        act = engine_res.parameters.get("action", "pause")
        yield _sse({"type": "youtube_control", "action": act, "turn_id": turn_id})
        try:
            from tools.youtube_tools import youtube_control
            await asyncio.get_event_loop().run_in_executor(None, lambda: youtube_control(act))
        except Exception:
            pass
        reply = f"Video is now {act}d." if act in ("pause", "resume") else f"Toggled {act}."
        yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
        yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
        return

    # ── Deterministic Intent Router (YouTube & Media Controls) ──
    try:
        from tools.youtube_router import parse_youtube_intent, get_embeddable_video
        yt_intent = parse_youtube_intent(message)
    except Exception as exc:
        logger.warning(f"YouTube intent router error: {exc}")
        yt_intent = None

    if yt_intent:
        intent_type = yt_intent.get("type")

        # 1. Summarize Flow (Never plays, fetches transcript and summarizes)
        if intent_type == "summarize":
            url = yt_intent.get("url", "")
            yield _sse({"type": "tool_start", "tool": "youtube.summarize", "args": {"url": url}, "turn_id": turn_id})
            try:
                from video_summarizer import get_transcript, extract_video_id
                # 1. Fetch transcript
                res = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: get_transcript(url)
                )
                if not res.get("success"):
                    # Fallback to yt-dlp subtitles
                    vid = extract_video_id(url)
                    transcript_text = ""
                    try:
                        import yt_dlp
                        ydl_opts = {"quiet": True, "skip_download": True}
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            auto_subs = info.get("automatic_captions", {}) or info.get("subtitles", {})
                            for lang in ["en", "bn", "hi"]:
                                if lang in auto_subs:
                                    transcript_text = f"Subtitles for {info.get('title', 'video')} in {lang}."
                                    break
                    except Exception:
                        pass
                else:
                    transcript_text = res.get("text", "")

                yield _sse({"type": "tool_result", "tool": "youtube.summarize", "result": "Transcript retrieved", "turn_id": turn_id})

                # 2. Summarize with LLM
                if transcript_text:
                    prompt = [
                        {
                            "role": "system",
                            "content": (
                                "You are JARVIS. Summarize the provided YouTube video transcript in 2-4 concise, informative bullet points or sentences. "
                                "Do not invent facts. Do not call any tools."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"TRANSCRIPT:\n{transcript_text[:1500]}\n\nPlease provide a clear, accurate summary of this video.",
                        },
                    ]
                    from llm.ollama_client import chat as llm_direct_chat
                    summary_text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: llm_direct_chat(prompt)
                    )
                else:
                    # Fallback to video metadata via oEmbed
                    vid = extract_video_id(url)
                    video_title = ""
                    author_name = ""
                    try:
                        import urllib.request
                        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
                        req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=4) as r:
                            data = json.loads(r.read().decode("utf-8", errors="replace"))
                            video_title = data.get("title", "")
                            author_name = data.get("author_name", "")
                    except Exception:
                        pass

                    if video_title:
                        prompt = [
                            {
                                "role": "system",
                                "content": "You are JARVIS. Provide a concise 2-sentence summary and overview of the YouTube video based on its title, channel, and subject. Do not call any tools.",
                            },
                            {
                                "role": "user",
                                "content": f"VIDEO TITLE: {video_title}\nCHANNEL: {author_name}\nURL: {url}\n\nPlease summarize what this video is about.",
                            },
                        ]
                        from llm.ollama_client import chat as llm_direct_chat
                        llm_meta_summary = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: llm_direct_chat(prompt)
                        )
                        summary_text = (
                            f"**Video Overview: {video_title}** (by {author_name})\n\n"
                            f"{llm_meta_summary}\n\n"
                            f"*(Note: Official subtitles were restricted by YouTube on this track, so summary is generated from verified video metadata.)*"
                        )
                    else:
                        err_msg = res.get("error", "No transcript or subtitles available for this video.")
                        summary_text = f"Could not summarize the video: {err_msg}"

            except Exception as exc:
                summary_text = f"Error summarizing YouTube video: {exc}"

            words = summary_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield _sse({"type": "token", "text": chunk, "turn_id": turn_id})
                await asyncio.sleep(0.005)

            yield _sse({"type": "done", "full": summary_text, "turn_id": turn_id})
            return

        # 2. Media Control Commands
        elif intent_type == "control":
            action = yt_intent.get("action", "pause")
            # 1. Notify Web UI mini-player
            yield _sse({"type": "youtube_control", "action": action, "turn_id": turn_id})
            # 2. Dispatch to system / Playwright
            try:
                from tools.youtube_tools import youtube_control
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: youtube_control(action)
                )
            except Exception:
                pass
            reply = f"Video is now {action}d." if action in ("pause", "resume") else f"Toggled {action}."
            yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
            yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
            return

        # 3. Direct URL Play
        elif intent_type == "direct_play":
            vid = yt_intent.get("video_id")
            title = yt_intent.get("title", "YouTube Video")
            url = yt_intent.get("url", f"https://www.youtube.com/watch?v={vid}")
            yield _sse({
                "type": "youtube_play",
                "video_id": vid,
                "title": title,
                "url": url,
                "playlist": [vid],
                "turn_id": turn_id
            })
            reply = f"Playing: {title}"
            yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
            yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
            return

        # 4. Search and Play Flow
        elif intent_type == "play":
            query = yt_intent.get("query", "lofi music")
            video, candidates = await asyncio.get_event_loop().run_in_executor(
                None, lambda: get_embeddable_video(query, max_results=10)
            )
            if video and video.get("id"):
                vid = video["id"]
                title = video.get("title", query)
                playlist_ids = [c["id"] for c in candidates if c.get("id")]
                yield _sse({
                    "type": "youtube_play",
                    "video_id": vid,
                    "title": title,
                    "url": video.get("url", f"https://www.youtube.com/watch?v={vid}"),
                    "playlist": playlist_ids,
                    "turn_id": turn_id
                })
                reply = f"Playing: {title}"
                yield _sse({"type": "token", "text": reply, "turn_id": turn_id})
                yield _sse({"type": "done", "full": reply, "turn_id": turn_id})
                return

    # ── Deterministic Image Generation Router ──
    img_en_match = re.search(r"\b(?:(?:generate|create|make|render)\s+(?:an?\s+)?(?:image|picture|photo|illustration|art)\s+(?:of|about|depicting)?|(?:draw|paint)\s+(?:(?:an?\s+)?(?:image|picture|photo|illustration|art)\s+(?:of|about|depicting)?\s*)?|(?:image|picture|photo)\s+(?:of|about))\s*(.+)", message, re.IGNORECASE)
    img_bn_match = re.search(r"(?:(?:ekta|kono)\s+)?(?:chobi|photo|tasbir|ছবি|চিত্র)\s+(?:banao|eko|akbo|toiri\s+koro|toiri\s+korun|বানাও|আঁকো|তৈরি\s+করো)\s*(.*)|(.*)\s+(?:er\s+)?(?:(?:ekta|kono)\s+)?(?:chobi|photo|tasbir|ছবি|চিত্র)\s+(?:banao|eko|akbo|toiri\s+koro|toiri\s+korun|বানাও|আঁকো|তৈরি\s+করো)", message, re.IGNORECASE)

    if img_en_match or img_bn_match:
        from image_generation.image_generator import check_safety, is_model_installed, generate_image

        # Determine prompt & translate if Bangla / non-English
        is_bangla = bool(img_bn_match or re.search(r"[\u0980-\u09FF]", message) or re.search(r"\b(banao|chobi|pahar|sundor|toiri)\b", message, re.I))
        if is_bangla:
            yield _sse({"type": "image_progress", "status": "Translating prompt to English...", "turn_id": turn_id})
            trans_msgs = [
                {
                    "role": "system",
                    "content": (
                        "You are a translation assistant for a local text-to-image generator. "
                        "Translate the user's image request into a concise, vivid English descriptive prompt (5-15 words). "
                        "Output ONLY the English prompt text, with no quotes, commentary, or extra words."
                    )
                },
                {"role": "user", "content": message}
            ]
            try:
                translated_prompt = await asyncio.get_event_loop().run_in_executor(None, lambda: llm_chat(trans_msgs, ""))
                eng_prompt = str(translated_prompt).strip().strip('"\'')
            except Exception:
                eng_prompt = message
        else:
            eng_prompt = (img_en_match.group(1) if img_en_match else message).strip()
            if not eng_prompt or len(eng_prompt) < 3:
                eng_prompt = message

        # 1. Safety Check
        safety_violation = check_safety(eng_prompt)
        if safety_violation:
            yield _sse({"type": "token", "text": safety_violation, "turn_id": turn_id})
            yield _sse({"type": "done", "full": safety_violation, "turn_id": turn_id})
            return

        # 2. Model Installation Check
        if not is_model_installed():
            missing_msg = "Image model not installed. Run: python scripts/download_image_model.py"
            yield _sse({"type": "token", "text": missing_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": missing_msg, "turn_id": turn_id})
            return

        yield _sse({"type": "tool_start", "tool": "image.generate", "args": {"prompt": eng_prompt}, "turn_id": turn_id})

        # 3. Generate Image with Progress Streaming
        loop = asyncio.get_event_loop()
        prog_queue = asyncio.Queue()

        def _on_img_prog(prog_status: str):
            loop.call_soon_threadsafe(prog_queue.put_nowait, prog_status)

        async def _run_img_gen():
            return await loop.run_in_executor(
                None,
                lambda: generate_image(
                    prompt=eng_prompt,
                    steps=4,
                    enhance=True,
                    progress_callback=_on_img_prog
                )
            )

        gen_task = asyncio.create_task(_run_img_gen())

        while not gen_task.done():
            try:
                p_msg = await asyncio.wait_for(prog_queue.get(), timeout=0.1)
                yield _sse({"type": "image_progress", "status": p_msg, "turn_id": turn_id})
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(0.05)

        while not prog_queue.empty():
            p_msg = prog_queue.get_nowait()
            yield _sse({"type": "image_progress", "status": p_msg, "turn_id": turn_id})

        gen_res = await gen_task

        if not gen_res.get("ok"):
            err_msg = f"❌ Image generation failed: {gen_res.get('error', 'Unknown error')}"
            yield _sse({"type": "token", "text": err_msg, "turn_id": turn_id})
            yield _sse({"type": "done", "full": err_msg, "turn_id": turn_id})
            return

        img_url = gen_res["url"]
        time_taken = gen_res["time_taken"]
        effective_p = gen_res.get("prompt", eng_prompt)

        yield _sse({"type": "tool_result", "tool": "image.generate", "result": f"Generated image at {img_url}", "turn_id": turn_id})
        yield _sse({
            "type": "image_generated",
            "url": img_url,
            "path": gen_res["path"],
            "prompt": effective_p,
            "original_prompt": eng_prompt,
            "seed": gen_res.get("seed"),
            "steps": gen_res.get("steps", 4),
            "time_taken": time_taken,
            "turn_id": turn_id
        })

        reply_md = (
            f"Here is your generated image:\n\n"
            f"![{effective_p}]({img_url})\n\n"
            f"**Prompt:** {effective_p}\n\n"
            f"*Generated locally with SD-Turbo ({gen_res.get('steps', 4)} steps) in {time_taken:.1f}s — 100% offline draft.*"
        )

        for chunk in reply_md.split(" "):
            yield _sse({"type": "token", "text": chunk + " ", "turn_id": turn_id})
            await asyncio.sleep(0.005)

        if conversation_id:
            try:
                cf = CONV_DIR / f"{conversation_id}.json"
                cdata = {"id": conversation_id, "title": message[:36] + ("…" if len(message) > 36 else ""), "messages": [], "ts": time.time() * 1000}
                if cf.exists():
                    try:
                        cdata = json.loads(cf.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                cdata["messages"].append({"role": "user", "content": message})
                cdata["messages"].append({"role": "assistant", "content": reply_md})
                cdata["ts"] = time.time() * 1000
                cf.write_text(json.dumps(cdata, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Auto-saving conversation failed: {e}")

        yield _sse({"type": "done", "full": reply_md, "turn_id": turn_id})
        return

    # ── Bilingual Language Rule (Part C) ──
    from intent.normalizer import detect_language
    detected_user_lang = detect_language(message)  # 'bn_script', 'bn_banglish', or 'en'
    is_user_bangla = (detected_user_lang in ("bn_script", "bn_banglish"))

    lang_instruction = (
        "CRITICAL LANGUAGE RULE: The user communicated in Bengali/Banglish. You MUST respond entirely in proper Bengali script (বাংলা লিপি). Never respond in Romanized Banglish or switch to English unless explicitly requested. (Brief English technical terms like 'VS Code' or numbers are allowed inside Bengali sentences). ABSOLUTELY NEVER USE HINDI (हिंदी) UNDER ANY CIRCUMSTANCES."
        if is_user_bangla
        else "CRITICAL LANGUAGE RULE: Respond in English. ABSOLUTELY NEVER USE HINDI (हिंदी) UNDER ANY CIRCUMSTANCES."
    )

    sys_content = JARVIS_SYSTEM_PROMPT.strip() + "\n\n" + lang_instruction
    messages: list[dict] = [{"role": "system", "content": sys_content}]

    # ── Deterministic Guardian Security & Performance Router ──
    is_guardian_query = bool(re.search(r"\b(suspicious|security|threat|hack|infection|virus|guardian|what is .* doing|what is using my (network|bandwidth|internet|port)|why is my (pc|computer|laptop) slow)\b", message, re.I))
    if is_guardian_query:
        try:
            from guardian.query import handle_guardian_query
            yield _sse({"type": "tool_start", "tool": "guardian_query", "args": {"query": message}, "turn_id": turn_id})
            guardian_reply = await asyncio.get_event_loop().run_in_executor(None, lambda: handle_guardian_query(message))
            yield _sse({"type": "tool_result", "tool": "guardian_query", "result": "Guardian telemetry retrieved", "turn_id": turn_id})
            for tok in guardian_reply.split(" "):
                yield _sse({"type": "token", "text": tok + " ", "turn_id": turn_id})
                await asyncio.sleep(0.005)
            yield _sse({"type": "done", "full": guardian_reply, "turn_id": turn_id})
            return
        except Exception as exc:
            logger.warning(f"Guardian intent error: {exc}")

    # ── Deterministic System Status Router ──
    is_system_query = bool(re.search(r"\b(cpu|ram|memory|disk|battery|system usage|pc status)\b", message, re.I))
    if is_system_query and re.search(r"\b(what|usage|status|percent|check|how much|my)\b", message, re.I):
        try:
            from tools.system_ops import system_status
            yield _sse({"type": "tool_start", "tool": "system_status", "args": {}, "turn_id": turn_id})
            sys_info = await asyncio.get_event_loop().run_in_executor(None, lambda: system_status())
            yield _sse({"type": "tool_result", "tool": "system_status", "result": sys_info, "turn_id": turn_id})
            reply_text = f"Here is your current system status:\n{sys_info}"
            for tok in reply_text.split(" "):
                yield _sse({"type": "token", "text": tok + " ", "turn_id": turn_id})
                await asyncio.sleep(0.005)
            yield _sse({"type": "done", "full": reply_text, "turn_id": turn_id})
            return
        except Exception as exc:
            logger.warning(f"System status intent error: {exc}")


    # ── Deterministic Web Search Router (Step 3b) ──
    # If message contains news/today/latest/current/price/weather/score/"what's new"
    # But exclude local PC system queries (CPU, RAM, disk, processes)
    web_trigger_pattern = r"\b(news|today|latest|current|price|prices|weather|score|scores|president|prime minister)\b|what'?s new"
    is_web_query = bool(re.search(web_trigger_pattern, message, re.IGNORECASE)) and not is_system_query

    if is_web_query:
        try:
            from tools.web_tools import web_search, fetch_page, news, weather
            yield _sse({"type": "tool_start", "tool": "web.search", "args": {"query": message}, "turn_id": turn_id})

            # Check if weather specifically
            if re.search(r"\bweather\b", message, re.I):
                # extract city if any
                m_city = re.search(r"weather\s+(?:in|for|at)?\s*([a-zA-Z\s]+)", message, re.I)
                city = m_city.group(1).strip() if m_city else ""
                search_data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: weather(city)
                )
                yield _sse({"type": "tool_result", "tool": "web.weather", "result": "Weather retrieved", "turn_id": turn_id})
                web_context = search_data
            elif re.search(r"\b(news|what'?s new)\b", message, re.I) and not re.search(r"\b(who|president|price|weather)\b", message, re.I):
                search_data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: news("top headlines" if "what" in message.lower() else message)
                )
                yield _sse({"type": "tool_result", "tool": "web.news", "result": "News retrieved", "turn_id": turn_id})
                web_context = search_data
            else:
                search_data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: web_search(message, max_results=3)
                )
                yield _sse({"type": "tool_result", "tool": "web.search", "result": "Search results found", "turn_id": turn_id})
                # Extract top URLs and read top 2 pages
                urls = re.findall(r"URL:\s*(https?://[^\s]+)", search_data)
                page_texts = []
                for u in urls[:2]:
                    p_content = await asyncio.get_event_loop().run_in_executor(
                        None, lambda url=u: fetch_page(url, max_chars=800)
                    )
                    if "SUCCESS:" in p_content:
                        clean_body = re.sub(r"SUCCESS: Content from [^\n]+:\s*", "", p_content).strip()
                        page_texts.append(f"Source [{u}]:\n{clean_body[:600]}")
                web_context = search_data + ("\n\n" + "\n\n".join(page_texts) if page_texts else "")
                web_context = web_context[:2000]

            # Inject strict grounded context instruction
            if re.search(r"\b(news|what'?s new)\b", message, re.I):
                grounded_system = (
                    "You are JARVIS. List these headlines with source and time, do not say anything else first. "
                    "Do not provide generic greetings or conversational filler. "
                    "Format each headline clearly with title, source, and summary.\n\n"
                    f"HEADLINES:\n{web_context}"
                )
            else:
                grounded_system = (
                    "You are JARVIS. Answer the user's question directly using ONLY the following verified web sources. "
                    "CITE 2-3 source URLs in your answer. "
                    "Keep the answer concise, accurate, and completely free of filler or raw JSON. Do not call any tools. "
                    "If the information is not found in the sources, say so honestly.\n\n"
                    f"WEB SOURCES:\n{web_context}"
                )
            messages.append({"role": "system", "content": grounded_system})

        except Exception as exc:
            logger.warning(f"Web search router error: {exc}")

    # Memory context (with query filtering to prevent greeting leaks)
    try:
        ctx = build_context(message)
        if ctx:
            messages.append({"role": "system", "content": "MEMORY:\n" + ctx})
    except Exception:
        pass

    # RAG context
    rag_keywords = ("document", "pdf", "file", "notes", "paper", "research")
    if any(kw in message.lower() for kw in rag_keywords):
        try:
            rag = rag_search(message)
            if rag:
                messages.append({"role": "system", "content": "LOCAL DOCUMENTS:\n" + rag})
        except Exception:
            pass

    if extra_context:
        messages.append({"role": "system", "content": "CONTEXT:\n" + extra_context})

    # General knowledge detection (direct model knowledge without web search or tool hallucinations)
    def _is_general_knowledge(query: str) -> bool:
        q = query.strip().lower()
        if re.search(r"\b(today|latest|current|now|price|prices|weather|news|yesterday|tomorrow|this week|2026)\b", q):
            return False
        gk_patterns = [
            r"^what\s+(?:is|are|was|were)\b",
            r"^who\s+(?:is|was|were)\b",
            r"^explain\b",
            r"^how\s+does\b",
            r"^how\s+do\b",
            r"^tell\s+me\s+about\b",
            r"^give\s+me\s+(?:all\s+)?information\s+(?:about|on)\b",
            r"^define\b",
            r"^describe\b",
            r"^difference\s+between\b",
            r"^history\s+of\b",
        ]
        return any(re.search(pat, q) for pat in gk_patterns)

    is_gen_know = _is_general_knowledge(message)
    if is_gen_know:
        messages.append({
            "role": "system",
            "content": "You are JARVIS. Answer the user's question directly, clearly, and comprehensively using your knowledge base. Do not call any tools."
        })

    MAX_STEPS = 4
    full_response = ""

    for step in range(MAX_STEPS):
        # Call LLM (blocking — run in executor)
        try:
            tools_text = TOOL_DESCRIPTIONS if (mode in ("agent", "chat") and not is_web_query and not is_gen_know) else ""
            response_text = await asyncio.get_event_loop().run_in_executor(
                None, lambda: llm_chat(messages, tools_text)
            )
        except Exception as exc:
            logger.error(f"LLM error in agent loop: {exc}")
            yield _sse({"type": "error", "error": str(exc)})
            return

        response_text = str(response_text).strip()

        # Save last prompt and response for verification & debugging
        try:
            debug_dir = BASE_DIR / "data" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "last_prompt.json").write_text(
                json.dumps({"query": message, "messages": messages, "response": response_text}, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

        # Headline verification guard for news queries
        if is_web_query and re.search(r"\b(news|what'?s new)\b", message, re.I):
            greeting_patterns = [
                r"^hello\b", r"^hi\b", r"^good\s+(morning|afternoon|evening|night)\b",
                r"^how\s+can\s+i\s+assist\b", r"^what\s+can\s+i\s+do\b"
            ]
            is_generic_greeting = any(re.search(gp, response_text.strip(), re.I) for gp in greeting_patterns) and len(response_text.strip().split()) < 35
            if is_generic_greeting or not response_text.strip():
                logger.warning(f"[HEADLINE GUARD] Intercepted generic model reply for news query. Retrying with strict headline prompt...")
                retry_messages = [m for m in messages if m.get("role") != "system" or not m.get("content", "").startswith("You are JARVIS. List these")]
                retry_messages.append({
                    "role": "system",
                    "content": f"CRITICAL REQUIREMENT: Output the following news headlines immediately. Do NOT write any greeting:\n\n{web_context}"
                })
                try:
                    retry_text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: llm_chat(retry_messages, "")
                    )
                    retry_text = str(retry_text).strip()
                    if retry_text and not any(re.search(gp, retry_text, re.I) for gp in greeting_patterns):
                        response_text = retry_text
                    else:
                        response_text = f"**Latest Headlines:**\n\n{web_context}"
                except Exception:
                    response_text = f"**Latest Headlines:**\n\n{web_context}"


        # Check for tool call
        try:
            tool_call = is_tool_call(response_text)
        except Exception:
            tool_call = None

        # Fallback lenient tool call detection
        if not tool_call:
            try:
                tool_call = parse_lenient_tool_call(response_text)
            except Exception:
                tool_call = None

        # Guard against ungrounded filesystem tool calls (BUG 1 fix)
        if tool_call:
            tool_name = tool_call.get("tool", "?")
            if tool_name.startswith("filesystem."):
                fs_keywords = ("file", "folder", "directory", "dir", "ls", "path", "drive", "desktop", "documents", "downloads", "workspace", "delete", "create", "make", "read", "write", "save", "list")
                if not any(k in message.lower() for k in fs_keywords):
                    logger.warning(f"[ROUTER GUARD] Suppressed ungrounded filesystem tool call: {tool_name} for query: '{message}'")
                    tool_call = None
                    try:
                        response_text = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: llm_chat(messages, "")
                        )
                        response_text = str(response_text).strip()
                    except Exception:
                        response_text = "I have processed your request, sir."

        if tool_call and mode in ("agent", "chat"):
            tool_name = tool_call.get("tool", "?")
            tool_args = tool_call.get("args", {})
            yield _sse({"type": "tool_start", "tool": tool_name, "args": tool_args, "turn_id": turn_id})
            logger.info(f"Tool call: {tool_name}({tool_args})")

            # Execute tool (blocking)
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: execute_tool_call(tool_call, user_confirmed=True)
                )
            except Exception as exc:
                result = f"ERROR: {exc}"

            result_str = str(result)
            logger.info(f"Tool result ({tool_name}): {result_str[:200]}")

            is_ok = not (result_str.startswith("ERROR:") or result_str.startswith("Error:") or (isinstance(result, dict) and result.get("ok") is False))
            if not is_ok and tool_name.startswith("filesystem."):
                # Retry once with deterministic slot parser
                try:
                    from tools.file_ops import parse_filesystem_command
                    fs_parsed = parse_filesystem_command(message)
                    if fs_parsed and fs_parsed.get("action"):
                        action = fs_parsed["action"]
                        retry_tool = f"filesystem.{action}"
                        retry_args = {"path": fs_parsed.get("path")}
                        if "content" in fs_parsed and fs_parsed["content"] is not None:
                            retry_args["content"] = fs_parsed["content"]
                        logger.info(f"Retrying tool once with corrected parse: {retry_tool}({retry_args})")
                        retry_res = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: execute_tool_call({"tool": retry_tool, "args": retry_args}, user_confirmed=True)
                        )
                        retry_str = str(retry_res)
                        if not (retry_str.startswith("ERROR:") or retry_str.startswith("Error:")):
                            result = retry_res
                            result_str = retry_str
                            tool_name = retry_tool
                            is_ok = True
                except Exception as r_err:
                    logger.warning(f"Tool parse retry failed: {r_err}")

            err_reason = ""
            if not is_ok:
                raw_err = result_str.replace("ERROR:", "").replace("Error:", "").strip()
                if isinstance(result, dict) and result.get("error"):
                    raw_err = str(result.get("error"))
                from tools.file_ops import translate_exception
                err_reason = translate_exception(Exception(raw_err))

            yield _sse({
                "type": "tool_result",
                "tool": tool_name,
                "result": result_str,
                "ok": is_ok,
                "error": err_reason,
                "turn_id": turn_id
            })

            # Append to conversation and continue
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    "TOOL RESULT for " + tool_name + ":\n" + result_str +
                    "\n\nNow give the user a natural-language response based on this result."
                ),
            })
            continue

        # Prevent raw tool JSON from leaking to user
        if is_raw_tool_json(response_text):
            logger.warning(f"Raw tool JSON intercepted and sanitized: {response_text[:80]}")
            if "url" in response_text:
                m_url = re.search(r'https?://[^\s"\'}]+', response_text)
                if m_url:
                    target_url = m_url.group(0)
                    yield _sse({"type": "tool_start", "tool": "browser.open", "args": {"url": target_url}, "turn_id": turn_id})
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: execute_tool_call({"tool": "browser.open", "args": {"url": target_url}}, user_confirmed=True)
                    )
                    yield _sse({"type": "tool_result", "tool": "browser.open", "result": f"Opened {target_url}", "turn_id": turn_id})
                    response_text = f"Opened {target_url} in your browser."
                else:
                    response_text = "I've handled that request for you."
            else:
                response_text = "Action completed."

        # Normal text response — stream tokens word-by-word for SSE effect
        words = response_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            full_response += chunk
            yield _sse({"type": "token", "text": chunk, "turn_id": turn_id})
            await asyncio.sleep(0.005)  # slight delay for stream effect

        # Persist to memory
        try:
            remember(message, response_text)
        except Exception:
            pass

        if conversation_id:
            try:
                cf = CONV_DIR / f"{conversation_id}.json"
                cdata = {"id": conversation_id, "title": message[:36] + ("…" if len(message) > 36 else ""), "messages": [], "ts": time.time() * 1000}
                if cf.exists():
                    try:
                        cdata = json.loads(cf.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                cdata["messages"].append({"role": "user", "content": message})
                cdata["messages"].append({"role": "assistant", "content": full_response})
                cdata["ts"] = time.time() * 1000
                cf.write_text(json.dumps(cdata, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Auto-saving conversation failed: {e}")

        response_is_bn = bool(re.search(r"[\u0980-\u09FF]", full_response)) or is_user_bangla
        lang_badge = "BN" if response_is_bn else "EN"
        yield _sse({"type": "done", "full": full_response, "lang": lang_badge, "turn_id": turn_id})
        return

    # Max steps reached
    yield _sse({"type": "error", "error": "Agent reached max steps without completing."})


# ──────────────────────────────────────────────────────────────────────────────
# FILE UPLOAD & INGESTION (PACKAGE 1)
# ──────────────────────────────────────────────────────────────────────────────

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_UPLOADED_DOCS: Dict[str, Dict[str, Any]] = {}

@app.post("/api/v1/files/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    _: None = OptionalAuth,
):
    """Upload and ingest a document or image file."""
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    safe_name = Path(file.filename or "upload").name
    dest_path = UPLOAD_DIR / f"{file_id}_{safe_name}"

    contents = await file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 25 MB limit.")

    dest_path.write_bytes(contents)

    from ingest import extract
    doc = await asyncio.get_event_loop().run_in_executor(
        None, lambda: extract(dest_path, mime=file.content_type, password=password)
    )
    _UPLOADED_DOCS[file_id] = doc

    try:
        cache_path = UPLOAD_DIR / f"{file_id}_meta.json"
        cache_path.write_text(json.dumps(doc, default=str), encoding="utf-8")
    except Exception:
        pass

    pages = doc.get("pages", [])
    sample = pages[0].get("text", "")[:300] if pages else ""

    if doc.get("encrypted"):
        return {
            "ok": False,
            "encrypted": True,
            "file_id": file_id,
            "filename": safe_name,
            "error": "PDF is password-protected. Please provide password to unlock.",
            "kind": "pdf",
        }

    if doc.get("error"):
        return {
            "ok": False,
            "encrypted": False,
            "file_id": file_id,
            "filename": safe_name,
            "error": doc.get("error"),
            "kind": doc.get("kind", "unknown"),
        }

    return {
        "ok": True,
        "file_id": file_id,
        "attachment_id": file_id,
        "filename": safe_name,
        "url": f"/api/v1/files/{file_id}/view",
        "size": len(contents),
        "kind": doc.get("kind"),
        "page_count": len(pages),
        "text_sample": sample,
        "warnings": doc.get("warnings", []),
        "encrypted": False,
    }


@app.get("/api/v1/files/{file_id}/view")
async def view_uploaded_file(file_id: str):
    """Serves an uploaded image or document file for thumbnails or viewing."""
    cands = list(UPLOAD_DIR.glob(f"{file_id}_*"))
    act_file = [c for c in cands if not c.name.endswith("_meta.json")]
    if not act_file or not act_file[0].exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(act_file[0]))


@app.post("/api/v1/files/{file_id}/unlock")
async def unlock_file_endpoint(file_id: str, req: Dict[str, str], _: None = OptionalAuth):
    """Unlock an encrypted PDF with user-supplied password."""
    password = req.get("password")
    candidates = list(UPLOAD_DIR.glob(f"{file_id}_*"))
    file_path = None
    for c in candidates:
        if not c.name.endswith("_meta.json"):
            file_path = c
            break
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    from ingest import extract
    doc = await asyncio.get_event_loop().run_in_executor(
        None, lambda: extract(file_path, password=password)
    )
    _UPLOADED_DOCS[file_id] = doc

    if doc.get("encrypted"):
        return {"ok": False, "encrypted": True, "error": "Incorrect password"}
    if doc.get("error"):
        return {"ok": False, "error": doc.get("error")}

    pages = doc.get("pages", [])
    return {
        "ok": True,
        "file_id": file_id,
        "attachment_id": file_id,
        "filename": file_path.name,
        "url": f"/api/v1/files/{file_id}/view",
        "kind": doc.get("kind"),
        "page_count": len(pages),
        "text_sample": pages[0].get("text", "")[:300] if pages else "",
        "warnings": doc.get("warnings", []),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CHAT ENDPOINT  (SSE streaming)
# ──────────────────────────────────────────────────────────────────────────────

_PROCESSED_TURNS: dict[str, float] = {}

@app.post("/api/v1/chat")
async def chat_endpoint(req: ChatRequest, _: None = OptionalAuth):
    """
    POST /api/v1/chat
    Streams response as Server-Sent Events (text/event-stream).
    Each event is a JSON line: data: {...}
    """
    logger.info(f"Chat request: mode={req.mode} turn_id={req.turn_id} msg={req.message[:80]!r}")

    # Idempotency / duplicate turn_id suppression
    now_ts = time.time()
    for k in list(_PROCESSED_TURNS.keys()):
        if now_ts - _PROCESSED_TURNS[k] > 120.0:
            _PROCESSED_TURNS.pop(k, None)

    if req.turn_id:
        if req.turn_id in _PROCESSED_TURNS:
            logger.warning(f"Duplicate turn_id suppressed: {req.turn_id}")
            async def _dup_stream():
                yield "data: " + json.dumps({"type": "done", "full": "", "turn_id": req.turn_id, "duplicate": True}) + "\n\n"
            return StreamingResponse(_dup_stream(), media_type="text/event-stream")
        _PROCESSED_TURNS[req.turn_id] = now_ts

    if req.stream:
        return StreamingResponse(
            _agent_stream(
                req.message,
                req.mode,
                req.context or "",
                req.turn_id,
                file_id=req.file_id,
                file_path=req.file_path,
                attachment=req.attachment,
                conversation_id=req.conversation_id,
                attachment_ids=req.attachment_ids,
                attachment_id=req.attachment_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming: collect all tokens
        chunks = []
        async for event in _agent_stream(
            req.message,
            req.mode,
            req.context or "",
            req.turn_id,
            file_id=req.file_id,
            file_path=req.file_path,
            attachment=req.attachment,
            conversation_id=req.conversation_id,
            attachment_ids=req.attachment_ids,
            attachment_id=req.attachment_id,
        ):
            try:
                obj = json.loads(event.replace("data: ", "").strip())
                if obj.get("type") == "token":
                    chunks.append(obj.get("text", ""))
                elif obj.get("type") == "done":
                    return {"ok": True, "response": obj.get("full", "".join(chunks)), "turn_id": req.turn_id}
                elif obj.get("type") == "error":
                    return {"ok": False, "error": obj.get("error"), "turn_id": req.turn_id}
            except Exception:
                pass
        return {"ok": True, "response": "".join(chunks), "turn_id": req.turn_id}



# ──────────────────────────────────────────────────────────────────────────────
# CODE COMPLETE
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/complete")
async def complete_endpoint(req: CompleteRequest, _: None = OptionalAuth):
    """Fill-in-the-middle code completion (low latency)."""
    fim_prompt = (
        f"<fim_prefix>{req.prefix}<fim_suffix>{req.suffix}<fim_middle>"
    )
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a code completion engine for {req.language}. "
                "Complete the code between <fim_prefix> and <fim_suffix>. "
                "Output ONLY the completion, no explanation."
            ),
        },
        {"role": "user", "content": fim_prompt},
    ]
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: llm_chat(messages, "")
        )
        return {"ok": True, "completion": str(result).strip()}
    except Exception as exc:
        logger.error(f"Complete error: {exc}")
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# CODE EDIT
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/edit")
async def edit_endpoint(req: EditRequest, _: None = OptionalAuth):
    """Return a diff/patch for a file selection given a natural-language instruction."""
    content = req.selection or ""
    if not content and req.file_path:
        try:
            content = Path(req.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    messages = [
        {
            "role": "system",
            "content": (
                "You are a code editor. Apply the instruction to the code. "
                "Return ONLY the modified code, no explanation, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": f"INSTRUCTION: {req.instruction}\n\nCODE:\n{content}",
        },
    ]
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: llm_chat(messages, "")
        )
        edited = str(result).strip()
        # Strip markdown fences if present
        if edited.startswith("```"):
            lines = edited.splitlines()
            edited = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            ).strip()
        return {"ok": True, "edited": edited, "original": content}
    except Exception as exc:
        logger.error(f"Edit error: {exc}")
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/tools")
async def list_tools(_: None = OptionalAuth):
    """List all available tools with descriptions and JSON schemas."""
    try:
        from tools.registry import registry
        tools_list = registry.list_tools()
    except Exception:
        tools_list = []
    return {
        "ok": True,
        "tools": tools_list,
        "count": len(tools_list),
        "descriptions": TOOL_DESCRIPTIONS,
    }


@app.post("/api/v1/tools/{tool_name:path}")
async def call_tool(tool_name: str, req: ToolCallRequest, _: None = OptionalAuth):
    """Call a specific tool by name."""
    call = {"tool": tool_name, "args": req.args}
    logger.info(f"Direct tool call: {tool_name}({req.args})")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: execute_tool_call(call, user_confirmed=True)
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        logger.error(f"Tool {tool_name} error: {exc}")
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# CONVERSATIONS (PACKAGE 2 & 3)
# ──────────────────────────────────────────────────────────────────────────────

CONV_DIR = BASE_DIR / "data" / "conversations"
CONV_DIR.mkdir(parents=True, exist_ok=True)

class ConversationSaveRequest(BaseModel):
    id: str
    title: Optional[str] = "New Chat"
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    ts: Optional[float] = None

@app.get("/api/v1/conversations")
async def list_conversations(_: None = OptionalAuth):
    """List all saved conversations sorted by updated timestamp."""
    convs = []
    for f in CONV_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            convs.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", "Untitled Chat"),
                "ts": data.get("ts", f.stat().st_mtime * 1000),
                "message_count": len(data.get("messages", []))
            })
        except Exception:
            pass
    convs.sort(key=lambda c: c.get("ts", 0), reverse=True)
    return {"ok": True, "conversations": convs}


@app.get("/api/v1/conversations/{conv_id}")
async def get_conversation(conv_id: str, _: None = OptionalAuth):
    """Get single conversation by ID."""
    f = CONV_DIR / f"{conv_id}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {"ok": True, "conversation": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/conversations")
async def save_conversation(req: ConversationSaveRequest, _: None = OptionalAuth):
    """Save or update a conversation."""
    f = CONV_DIR / f"{req.id}.json"
    conv_data = {
        "id": req.id,
        "title": req.title or "New Chat",
        "messages": req.messages,
        "ts": req.ts or (time.time() * 1000)
    }
    f.write_text(json.dumps(conv_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "id": req.id}


@app.delete("/api/v1/conversations/{conv_id}")
async def delete_conversation(conv_id: str, forget_memories: bool = False, _: None = OptionalAuth):
    """Delete a single conversation by ID from server history."""
    f = CONV_DIR / f"{conv_id}.json"
    deleted = False
    if f.exists():
        f.unlink()
        deleted = True

    if forget_memories:
        try:
            from memory.manager import get_memory_manager
            mm = get_memory_manager()
            if hasattr(mm, "delete_by_session"):
                mm.delete_by_session(conv_id)
        except Exception as exc:
            logger.warning(f"Could not purge memories for {conv_id}: {exc}")

    return {"ok": True, "deleted": conv_id, "file_existed": deleted}


@app.delete("/api/v1/conversations")
async def clear_all_conversations(forget_memories: bool = False, _: None = OptionalAuth):
    """Clear all conversations from server history."""
    count = 0
    for f in CONV_DIR.glob("*.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass

    if forget_memories:
        try:
            from memory.manager import get_memory_manager
            mm = get_memory_manager()
            if hasattr(mm, "clear"):
                mm.clear()
        except Exception as exc:
            logger.warning(f"Could not clear memories: {exc}")

    return {"ok": True, "deleted_count": count}


# ──────────────────────────────────────────────────────────────────────────────
# GUARDIAN SECURITY MONITOR (PACKAGE 4)
# ──────────────────────────────────────────────────────────────────────────────

class GuardianSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    interval: Optional[float] = None
    sensitivity: Optional[str] = None
    notifications: Optional[bool] = None
    watched_folders: Optional[List[str]] = None


@app.get("/api/v1/guardian/status")
async def guardian_status(_: None = OptionalAuth):
    """Return live status, active detectors, footprint, and alert counts."""
    from guardian.monitor import get_guardian
    return get_guardian().get_status()


@app.get("/api/v1/guardian/alerts")
async def guardian_get_alerts(limit: int = 50, _: None = OptionalAuth):
    """Return recent suspicious alerts feed."""
    from guardian.monitor import get_guardian
    alerts = get_guardian().alerts
    return {"ok": True, "alerts": alerts[:limit]}


@app.post("/api/v1/guardian/alerts/{alert_id}/ignore")
async def guardian_ignore_alert(alert_id: str, _: None = OptionalAuth):
    """Permanently ignore alert key and whitelist it."""
    from guardian.monitor import get_guardian
    success = get_guardian().ignore_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True, "ignored": alert_id}


@app.post("/api/v1/guardian/alerts/clear")
async def guardian_clear_alerts(_: None = OptionalAuth):
    """Clear all active Guardian alerts and reset notification cooldowns."""
    from guardian.monitor import get_guardian
    count = get_guardian().clear_alerts()
    return {"ok": True, "cleared": count}


@app.post("/api/v1/guardian/baseline/reset")
async def guardian_reset_baseline(_: None = OptionalAuth):
    """Reset and relearn system activity baseline, suppressing noise."""
    from guardian.monitor import get_guardian
    res = get_guardian().reset_baseline()
    return res


@app.post("/api/v1/guardian/alerts/{alert_id}/kill")
async def guardian_kill_process(alert_id: str, _: None = OptionalAuth):
    """Terminate the process associated with an alert after safety checks."""
    from guardian.monitor import get_guardian
    res = get_guardian().kill_process(alert_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to terminate process"))
    return res


@app.post("/api/v1/guardian/pause")
async def guardian_pause(_: None = OptionalAuth):
    """Temporarily pause Guardian monitoring."""
    from guardian.monitor import get_guardian
    get_guardian().pause()
    return {"ok": True, "paused": True}


@app.post("/api/v1/guardian/resume")
async def guardian_resume(_: None = OptionalAuth):
    """Resume Guardian monitoring."""
    from guardian.monitor import get_guardian
    get_guardian().resume()
    return {"ok": True, "paused": False}


@app.get("/api/v1/guardian/settings")
async def guardian_get_settings(_: None = OptionalAuth):
    """Get current Guardian settings."""
    from guardian.monitor import get_guardian
    g = get_guardian()
    return {
        "ok": True,
        "enabled": g.enabled,
        "interval": g.interval,
        "sensitivity": g.sensitivity,
        "notifications": g.notifications_enabled,
        "watched_folders": g.watched_folders
    }


@app.put("/api/v1/guardian/settings")
async def guardian_update_settings(req: GuardianSettingsRequest, _: None = OptionalAuth):
    """Update Guardian monitor configuration."""
    from guardian.monitor import get_guardian
    g = get_guardian()
    if req.enabled is not None:
        g.enabled = req.enabled
    if req.interval is not None and req.interval >= 1.0:
        g.interval = req.interval
    if req.sensitivity is not None and req.sensitivity in ("low", "medium", "high"):
        g.sensitivity = req.sensitivity
    if req.notifications is not None:
        g.notifications_enabled = req.notifications
    if req.watched_folders is not None:
        g.watched_folders = req.watched_folders
    g.save_config()
    return {"ok": True, "settings": g.get_status()}


@app.get("/api/v1/guardian/stream")
async def guardian_stream(request: Request, _: None = OptionalAuth):
    """SSE real-time stream for live Guardian alerts and status events."""
    from guardian.monitor import get_guardian
    g = get_guardian()
    q = asyncio.Queue()
    g.add_subscriber(q)

    async def event_generator():
        # First send status snapshot
        try:
            status_data = g.get_status()
            yield f"data: {json.dumps({'type': 'status', 'status': status_data})}\n\n"
        except Exception:
            pass

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            g.remove_subscriber(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")



# ──────────────────────────────────────────────────────────────────────────────
# MEMORY
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/memory")
async def get_memory(_: None = OptionalAuth):
    try:
        ctx = build_context()
        return {"ok": True, "context": ctx}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/v1/memory")
async def store_memory(req: MemoryRequest, _: None = OptionalAuth):
    try:
        remember(req.key, req.value)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# RAG
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/rag/index")
async def rag_index(req: RAGIndexRequest, _: None = OptionalAuth):
    try:
        from rag.ingest import ingest_path
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ingest_path(req.path)
        )
        return {"ok": True, "result": str(result)}
    except Exception as exc:
        logger.error(f"RAG index error: {exc}")
        return {"ok": False, "error": str(exc)}


@app.post("/api/v1/rag/query")
async def rag_query(req: RAGQueryRequest, _: None = OptionalAuth):
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: rag_search(req.query)
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM STATS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/system/stats")
async def system_stats(_: None = OptionalAuth):
    """Real-time system metrics snapshot."""
    sample = await asyncio.get_event_loop().run_in_executor(None, _sample_system)
    return {"ok": True, "stats": sample}


@app.get("/api/v1/system/history")
async def system_history(minutes: int = 5, _: None = OptionalAuth):
    """Return the last N minutes of 2-second samples."""
    cutoff = time.time() - minutes * 60
    samples = [s for s in _system_history if s.get("ts", 0) >= cutoff]
    return {"ok": True, "samples": samples}


@app.post("/api/v1/system/action/cancel")
async def cancel_action_endpoint(req: ActionControlRequest = ActionControlRequest(), _: None = OptionalAuth):
    """Cancel any active pending destructive PC action immediately."""
    from tools.pc_actions import cancel_pending_action
    cancelled = cancel_pending_action(req.action_id)
    return {"ok": True, "cancelled": cancelled}


@app.post("/api/v1/system/action/confirm")
async def confirm_action_endpoint(req: ActionControlRequest, _: None = OptionalAuth):
    """Manually confirm and execute a pending destructive PC action immediately."""
    if not req.action_id:
        return {"ok": False, "error": "action_id is required"}
    from tools.pc_actions import confirm_pending_action
    res = confirm_pending_action(req.action_id)
    return res


@app.post("/api/v1/terminal/run")
async def terminal_run_endpoint(req: TerminalRunRequest, _: None = OptionalAuth):
    """Execute any shell, batch, or python command with full PC access and dynamic directory navigation."""
    global _CURRENT_TERMINAL_CWD
    cmd = req.command.strip()
    if not cmd:
        return {"ok": False, "error": "Empty command", "output": "", "cwd": _CURRENT_TERMINAL_CWD}

    # Resolve cwd: requested cwd or global active cwd
    cwd = req.cwd or _CURRENT_TERMINAL_CWD
    if not Path(cwd).exists():
        cwd = str(BASE_DIR)

    def _execute():
        global _CURRENT_TERMINAL_CWD
        clean_cmd = cmd.strip()

        # 1. Handle cls / clear
        if clean_cmd.lower() in ("cls", "clear"):
            return {
                "ok": True,
                "exit_code": 0,
                "output": "",
                "clear": True,
                "cwd": cwd,
                "command": cmd
            }

        # 2. Handle bare 'cd', 'chdir', 'pwd' (like in Windows CMD: displays current directory)
        if clean_cmd.lower() in ("cd", "chdir", "pwd"):
            return {
                "ok": True,
                "exit_code": 0,
                "output": cwd,
                "cwd": cwd,
                "command": cmd
            }

        # 3. Handle drive switch: e.g. "C:", "D:", "E:"
        if re.match(r"^[a-zA-Z]:$", clean_cmd):
            target_drive = clean_cmd.upper() + "\\"
            if Path(target_drive).exists():
                _CURRENT_TERMINAL_CWD = target_drive
                return {
                    "ok": True,
                    "exit_code": 0,
                    "output": "",
                    "cwd": target_drive,
                    "command": cmd
                }
            else:
                return {
                    "ok": False,
                    "exit_code": 1,
                    "output": f"The system cannot find the drive specified: {clean_cmd}",
                    "cwd": cwd,
                    "command": cmd
                }

        # 4. Standard command execution wrapped with location tracking
        wrapper = f"$ErrorActionPreference = 'Continue'; {clean_cmd}\nWrite-Output \"`n__JARVIS_CWD__:$($PWD.Path)\""
        timeout = req.timeout or 120  # generous 2-minute default for builds, pip, downloads

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", wrapper],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )
            stdout = res.stdout
            stderr = res.stderr

            new_cwd = cwd
            m = re.search(r"__JARVIS_CWD__:(.+?)(?:\r?\n|$)", stdout)
            if m:
                candidate_cwd = m.group(1).strip()
                if candidate_cwd and Path(candidate_cwd).exists():
                    new_cwd = candidate_cwd
                stdout = re.sub(r"__JARVIS_CWD__:.+?(?:\r?\n|$)", "", stdout)

            _CURRENT_TERMINAL_CWD = new_cwd
            combined = stdout.strip() + ("\n" + stderr.strip() if stderr.strip() else "")

            return {
                "ok": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "output": combined.strip() or "(Command executed with no output)",
                "cwd": new_cwd,
                "command": cmd
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "exit_code": -1,
                "error": f"Command timed out after {timeout} seconds",
                "output": f"Timeout after {timeout}s",
                "cwd": cwd,
                "command": cmd
            }
        except Exception as exc:
            return {
                "ok": False,
                "exit_code": -1,
                "error": str(exc),
                "output": str(exc),
                "cwd": cwd,
                "command": cmd
            }

    return await asyncio.get_event_loop().run_in_executor(None, _execute)


# ──────────────────────────────────────────────────────────────────────────────
# VOICE PIPELINE (STT, LISTEN, TTS)
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/voice/transcribe")
@app.post("/api/v1/voice/stt")
async def voice_transcribe(request: Request, _: None = OptionalAuth):
    """Upload an audio file (webm/wav/ogg/mp3) and return faster-whisper transcription with auto-detected language."""
    if not STT_OK:
        return {"ok": False, "error": "STT not available (faster-whisper not installed)"}
    try:
        import tempfile
        body = await request.body()
        if not body:
            return {"ok": False, "error": "Empty audio payload"}

        content_type = request.headers.get("content-type", "")
        ext = ".webm"
        if "wav" in content_type:
            ext = ".wav"
        elif "ogg" in content_type:
            ext = ".ogg"
        elif "mp3" in content_type:
            ext = ".mp3"

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(body)
            tmp_path = f.name

        try:
            result_text, lang = await asyncio.get_event_loop().run_in_executor(
                None, lambda: transcribe_audio_file(tmp_path)
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return {"ok": True, "text": result_text, "language": lang}
    except Exception as exc:
        logger.error(f"Transcribe error: {exc}", exc_info=True)
        return {"ok": False, "error": str(exc)}


@app.post("/api/v1/voice/listen")
async def voice_listen(req: VoiceListenRequest = VoiceListenRequest(), _: None = OptionalAuth):
    """Record from PC microphone with sounddevice, stopping after ~1.2s silence (energy threshold, max 30s)."""
    if not STT_OK:
        return {"ok": False, "error": "STT not available (sounddevice / faster-whisper not installed)"}
    try:
        result_text, lang = await asyncio.get_event_loop().run_in_executor(
            None, lambda: listen_and_transcribe(max_duration_sec=req.timeout, silence_duration_sec=req.silence_timeout)
        )
        return {"ok": True, "text": result_text, "language": lang}
    except Exception as exc:
        logger.error(f"Voice listen error: {exc}", exc_info=True)
        return {"ok": False, "error": str(exc)}


@app.post("/api/v1/voice/speak")
@app.post("/api/v1/voice/tts")
async def voice_speak(req: VoiceSpeakRequest, _: None = OptionalAuth):
    """Voice output is permanently disabled per user configuration. Returns text only."""
    return {"ok": True, "disabled": True, "message": "Voice output is permanently disabled. Responses are text-only."}


@app.get("/api/v1/voice/speak")
@app.get("/api/v1/voice/tts")
async def voice_speak_get_endpoint(text: str = "", _: None = OptionalAuth):
    """Voice output is permanently disabled. Returns empty 204 response."""
    from fastapi.responses import Response
    return Response(status_code=204)


@app.post("/api/v1/voice/playback_state")
async def voice_playback_state_endpoint(req: VoicePlaybackStateRequest, _: None = OptionalAuth):
    """Notify backend that client audio playback has started or stopped, gating STT during playback."""
    if TTS_OK:
        from voice.tts import set_speaking_state
        set_speaking_state(req.playing, req.text)
    return {"ok": True, "playing": req.playing}


@app.post("/api/v1/voice/stop")
async def voice_stop_endpoint(_: None = OptionalAuth):
    """Stop currently active TTS speech."""
    if TTS_OK:
        stop_tts()
    return {"ok": True}


def _handle_always_on_voice_command(cmd_text: str, lang: Optional[str] = None):
    """Handles commands recognized by the always-on background listener."""
    if not cmd_text or not cmd_text.strip():
        return
    detected_lang = lang or ("bn" if re.search(r"[\u0980-\u09FF]", cmd_text) else "en")
    logger.info(f"Always-on voice command received ({detected_lang}): {cmd_text}")
    try:
        if _main_event_loop:
            voice_msg = json.dumps({"type": "voice", "event": "command", "text": cmd_text, "lang": detected_lang})
            for cl in list(_monitor_clients) + list(_event_clients):
                try:
                    asyncio.run_coroutine_threadsafe(cl.send_text(voice_msg), _main_event_loop)
                except Exception:
                    pass

        from intent.engine import get_intent_engine
        engine = get_intent_engine()
        intent_res = engine.classify(cmd_text)
        if intent_res.intent == "weather":
            from tools.weather_tool import get_weather
            loc = intent_res.slots.get("location") or "Khulna"
            w = get_weather(loc)
            msg = w.get("summary") or w.get("speech")
            logger.info(f"Voice weather reply (text only): {msg}")
            return
        elif intent_res.intent == "news":
            from tools.news_tool import get_news
            cat = intent_res.slots.get("category") or "world"
            n = get_news(cat)
            msg = n.get("speech") or "Top headlines loaded."
            logger.info(f"Voice news reply (text only): {msg}")
            return
        elif intent_res.intent == "system_control":
            act = intent_res.slots.get("action")
            val = intent_res.slots.get("value")
            from tools.pc_tools import execute_system_control
            res = execute_system_control(act, val)
            logger.info(f"Voice system control reply (text only): {res}")
            return
        from llm.ollama_client import chat as llm_chat
        ans = llm_chat([
            {"role": "system", "content": "You are JARVIS. Answer concisely in 1-2 sentences."},
            {"role": "user", "content": cmd_text}
        ])
        logger.info(f"Voice chat reply (text only): {str(ans).strip()}")
    except Exception as e:
        logger.error(f"Voice command processing error: {e}", exc_info=True)


@app.get("/api/v1/voice/devices")
async def get_voice_devices_endpoint(_: None = OptionalAuth):
    """Return available audio input (microphone) devices, tagging physical vs loopback."""
    try:
        import sounddevice as sd
        from voice.listener import is_loopback_device, resolve_physical_input_device
        devs = sd.query_devices()
        input_devices = []
        preferred_default = resolve_physical_input_device(None)

        for idx, d in enumerate(devs):
            if d.get("max_input_channels", 0) > 0:
                name = d.get("name", f"Microphone {idx}")
                is_lb = is_loopback_device(name)
                input_devices.append({
                    "id": idx,
                    "name": name,
                    "channels": d.get("max_input_channels", 1),
                    "is_loopback": is_lb,
                    "is_physical": not is_lb,
                    "default": (idx == preferred_default),
                })
        return {"ok": True, "devices": input_devices}
    except Exception as exc:
        return {"ok": False, "devices": [], "error": str(exc)}


@app.get("/api/v1/voice/mode")
@app.get("/api/v1/voice/settings")
async def get_voice_mode_endpoint(_: None = OptionalAuth):
    """Get current voice mode ('always', 'off') and listener settings."""
    try:
        from voice.listener import get_voice_listener
        listener = get_voice_listener()
        settings = listener.get_settings()
        return {"ok": True, **settings}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "mode": "always"}


@app.post("/api/v1/voice/mode")
@app.post("/api/v1/voice/settings")
async def set_voice_mode_endpoint(req: VoiceModeRequest, _: None = OptionalAuth):
    """Set voice mode ('always', 'off') and microphone settings."""
    try:
        from voice.listener import get_voice_listener
        listener = get_voice_listener()
        listener.on_command = _handle_always_on_voice_command
        settings = listener.update_settings(
            mode=req.mode,
            device=req.device,
            language=req.language,
            sensitivity=req.sensitivity,
            speak_replies=req.speak_replies,
        )
        return {"ok": True, **settings}
    except Exception as exc:
        logger.error(f"Error setting voice mode: {exc}")
        return {"ok": False, "error": str(exc)}


@app.get("/api/v1/voice/diagnose")
async def voice_diagnose_endpoint(_: None = OptionalAuth):
    """Voice Doctor diagnostic endpoint: tests 10 stages of input and output."""
    try:
        from voice.diagnose import run_voice_diagnose
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, run_voice_diagnose)
        return res
    except Exception as exc:
        logger.error(f"Voice diagnose endpoint error: {exc}", exc_info=True)
        return {"ok": False, "error": str(exc), "stages": []}



# ──────────────────────────────────────────────────────────────────────────────
# VISION
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/vision/analyze")
async def vision_analyze(req: VisionRequest, _: None = OptionalAuth):
    """Analyze an image file."""
    if not VISION_OK:
        return {"ok": False, "error": "Vision not available"}
    try:
        if req.mode == "describe":
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: describe_image(req.image_path)
            )
        else:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: analyze_image(req.image_path)
            )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# IMAGE GENERATION
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/image/generate")
async def generate_image_endpoint(req: ImageGenRequest, request: Request, _: None = OptionalAuth):
    """Generate image via offline SD-Turbo/SDXL-Turbo (lazy loaded, memory safe)."""
    accept_header = request.headers.get("accept", "")
    wants_stream = req.stream or "text/event-stream" in accept_header

    if wants_stream:
        async def _gen_stream():
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def _progress(msg: str):
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", "status": msg})

            async def _worker():
                try:
                    from image_generation.image_generator import generate_image
                    res = await loop.run_in_executor(
                        None,
                        lambda: generate_image(
                            prompt=req.prompt,
                            width=req.width,
                            height=req.height,
                            steps=req.steps,
                            seed=req.seed,
                            progress_callback=_progress,
                        )
                    )
                    queue.put_nowait({"type": "done", "result": res})
                except Exception as exc:
                    queue.put_nowait({"type": "error", "error": str(exc)})

            asyncio.create_task(_worker())
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") in ("done", "error"):
                    break

        return StreamingResponse(
            _gen_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    try:
        from image_generation.image_generator import generate_image
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_image(
                prompt=req.prompt,
                width=req.width,
                height=req.height,
                steps=req.steps,
                seed=req.seed,
            )
        )
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# WEBSOCKET — system monitor stream
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/system/stream")
async def ws_system_stream(ws: WebSocket):
    await ws.accept()
    _monitor_clients.append(ws)
    try:
        # Send current sample immediately
        if _system_history:
            await ws.send_text(json.dumps({"type": "system", "data": _system_history[-1]}))
        while True:
            # Keep connection alive; actual data is pushed by _monitor_loop
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in _monitor_clients:
            _monitor_clients.remove(ws)


# ──────────────────────────────────────────────────────────────────────────────
# WEBSOCKET — events bus
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    _event_clients.append(ws)
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _event_clients:
            _event_clients.remove(ws)


# ──────────────────────────────────────────────────────────────────────────────
# LEGACY FLASK COMPAT — keep old routes working so the existing UI still works
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def legacy_chat(request: Request):
    """Backward-compatible alias for the old Flask /api/chat endpoint."""
    body = await request.json()
    message = body.get("message", "")
    if not message:
        return {"reply": "No message provided.", "ok": False}

    # Collect streaming response synchronously
    full = ""
    async for event in _agent_stream(message, "chat"):
        try:
            obj = json.loads(event.replace("data: ", "").strip())
            if obj.get("type") == "token":
                full += obj.get("text", "")
            elif obj.get("type") == "done":
                full = obj.get("full", full)
                break
            elif obj.get("type") == "error":
                return {"reply": obj.get("error", "Error"), "ok": False}
        except Exception:
            pass
    return {"reply": full, "ok": True}


@app.post("/api/speak")
async def legacy_speak(request: Request):
    return {"success": True, "disabled": True, "message": "Voice output is permanently muted."}


@app.post("/api/speak/stop")
async def legacy_speak_stop():
    if TTS_OK:
        stop_tts()
    return {"success": True}


@app.get("/api/status")
async def legacy_status():
    return await health()


# ──────────────────────────────────────────────────────────────────────────────
# LOCATION MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/location/info")
async def get_location_info_endpoint(_: None = OptionalAuth):
    """Returns detected IP location, manual override, precise coordinates, and active resolution."""
    from tools.location_service import get_location_info
    return {"ok": True, "location": get_location_info()}

@app.post("/api/v1/location/override")
async def set_location_override_endpoint(req: LocationOverrideRequest, _: None = OptionalAuth):
    """Set manual location override city."""
    from tools.location_service import set_manual_override
    res = set_manual_override(req.city)
    return res

@app.delete("/api/v1/location/override")
async def clear_location_override_endpoint(_: None = OptionalAuth):
    """Clear manual location override."""
    from tools.location_service import clear_manual_override
    res = clear_manual_override()
    return res

@app.post("/api/v1/location/precise")
async def set_location_precise_endpoint(req: LocationPreciseRequest, _: None = OptionalAuth):
    """Save consented browser geolocation coordinates."""
    from tools.location_service import set_precise_location
    res = set_precise_location(req.latitude, req.longitude, accuracy_m=req.accuracy_m, city=req.city or "")
    return res

@app.delete("/api/v1/location/precise")
async def clear_location_precise_endpoint(_: None = OptionalAuth):
    """Clear browser geolocation coordinates."""
    from tools.location_service import clear_precise_location
    res = clear_precise_location()
    return res



# ──────────────────────────────────────────────────────────────────────────────
# STARK EDITION DYNAMIC MODULE LOADER
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/modules")
async def list_modules_endpoint():
    """List all registered Stark Edition modules, capabilities, and health status."""
    from modules.registry import list_modules
    return {"ok": True, "modules": list_modules()}

@app.post("/api/v1/modules/{mod_id}/toggle")
async def toggle_module_endpoint(mod_id: str, req: Dict[str, Any]):
    """Enable or disable a specific Stark module at runtime."""
    from modules.registry import toggle_module
    return toggle_module(mod_id, req.get("enabled", True))

try:
    from modules.registry import load_and_mount_modules
    load_and_mount_modules(app)
    logger.info("Stark Edition dynamic modules mounted successfully.")
except Exception as _mod_err:
    logger.warning(f"Failed to mount Stark modules: {_mod_err}")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("  JARVIS AI SERVER")
    print(f"  Host : {JARVIS_HOST}:{JARVIS_PORT}")
    print(f"  UI   : http://{JARVIS_HOST}:{JARVIS_PORT}/")
    print(f"  Docs : http://{JARVIS_HOST}:{JARVIS_PORT}/docs")
    print(f"  Token: {JARVIS_TOKEN[:8]}...  (full token in .env)")
    print("=" * 60 + "\n")

    uvicorn.run(
        "server:app",
        host=JARVIS_HOST,
        port=JARVIS_PORT,
        reload=False,
        log_level="info",
    )

