# JARVIS Voice + Intelligence Audit Report
> Generated: 2026-10-12 | Platform: Windows 11, Python 3.14 (venv), AMD Radeon Graphics (Integrated), 13.84 GB RAM

---

## 1. Current Hardware & Environment Diagnostics

- **CPU / System RAM**:
  - Total Physical RAM: **13.84 GB**
  - Current Available RAM: **4.41 GB** (~68.2% RAM utilized prior to heavy model load)
  - Memory pressure is real: Host cannot simultaneously keep `qwen2.5:7b` in memory alongside Whisper and diffusion pipelines without paging/OOM risk.
- **GPU / VRAM**:
  - `Get-CimInstance Win32_VideoController`: AMD Radeon (TM) Graphics (`AdapterRAM`: 2,147,483,648 bytes / 2 GB shared).
  - `nvidia-smi`: Not installed (No NVIDIA discrete GPU).
  - `torch.cuda.is_available()`: `False`.
  - All inference (LLM, STT, TTS, Embeddings, Diffusion) runs on CPU.
- **Models Installed (`ollama list`)**:
  - `qwen2.5:7b` (4.7 GB) — Primary chat / agent reasoning model
  - `qwen2.5-coder:7b` (4.7 GB) — Code completion / refactor model
  - `qwen2.5:3b` (1.9 GB) — Fast lightweight alternative
  - `qwen2.5-coder:1.5b` (986 MB) — Low-latency code completion
  - `moondream:latest` (1.7 GB) — Vision / image analysis
- **Context & Inference Configuration** (`llm/ollama_client.py`):
  - Model: `qwen2.5:7b`
  - `num_ctx`: 2048 tokens
  - `num_predict`: 256 tokens
  - `temperature`: 0.3

---

## 2. Current Chat Pipeline & Intent Routers

The streaming chat pipeline in `server.py` (`_agent_stream`) operates as a linear cascade before falling into the ReAct loop:

```
User Message
    │
    ├── 1. Document Extraction & OCR (if file attached or file_id provided)
    │
    ├── 2. Deterministic YouTube Router (parse_youtube_intent in tools/youtube_router.py)
    │       - Summarize / Direct Play / Search and Play
    │
    ├── 3. Deterministic Image Generation Router (image.generate via SD-Turbo)
    │       - Regex match (English/Bangla) -> LLM Translation -> Safety Filter -> SD-Turbo
    │
    ├── 4. Deterministic Guardian Telemetry Router (handle_guardian_query)
    │       - Queries process/port/network anomalies
    │
    ├── 5. Deterministic System Status Router (system_status)
    │       - Matches CPU/RAM/battery queries
    │
    ├── 6. Deterministic Web Search Router
    │       - Matches news/weather/latest/price/current
    │       - Injects search data into messages as "WEB SOURCES"
    │
    ├── 7. Memory Context Injection (`build_context(message)`)
    │
    ├── 8. Local Documents RAG (`rag_search(message)`)
    │
    └── 9. ReAct Loop (`MAX_STEPS = 4` calling `llm_chat(messages, tools_text)`)
            - Checks `is_tool_call(response_text)` and `parse_lenient_tool_call(response_text)`
            - Executes tool via `execute_tool_call`
            - Sends tool result back to LLM for final natural reply
```

---

## 3. Tool Registry & PC Control Tools

- **Tool Registry (`tools/registry.py`)**:
  - Central singleton `registry` with schema-checked handlers.
  - Registered domains: `filesystem` (list, read, create, write, rename, move, copy, delete, search), `system` (open_app, open_path, type_text, press, hotkey, click, scroll, screenshot, clipboard_set, system_status, shutdown, cancel_shutdown), `browser` (open, back, forward, scroll, click_text, type, search, page_text, video controls), `youtube` (search, play, pause, seek, mute, next, summarize, ask, control), `web` (search, research, news, weather, fetch_page, currency, stock), `schedule` (add_reminder, list_jobs, cancel_job), `memory` (remember, recall, clear), `rag` (query, index), `image` (generate).
- **Execution & Safety (`tools/router.py`)**:
  - Dispatches tool names with `TOOL_ALIASES`.
  - Checks `REQUIRE_CONFIRMATION_FOR = ["delete_file", "delete_folder", "shutdown"]`.
  - PC controls exist in `tools/system_ops.py` (via `subprocess`, `pyautogui`, `psutil`).
  - Missing features: sleep, hibernate, lock workstation, volume control, brightness control, app discovery/switching, recycle bin integration (currently permanent delete).

---

## 4. Voice Subsystems & Guardian Security Monitor

- **Speech-to-Text (`voice/stt.py`)**:
  - Library: `faster-whisper`
  - Model: `small` (int8 on CPU)
  - Features: Sounddevice recording, silence detection (~1.2s threshold), VAD filtering.
  - Endpoints: `POST /api/v1/voice/transcribe`, `POST /api/v1/voice/listen`.
- **Text-to-Speech (`voice/tts.py`)**:
  - Library: Piper TTS CLI (`piper.exe`) with ONNX voice `en_US-lessac-medium.onnx` + Windows SAPI fallback (`winsound` / COM).
  - Features: Markdown stripping (`clean_text`), code block substitution ("I wrote the function, check the chat").
  - Endpoints: `POST /api/v1/voice/speak`, `POST /api/v1/voice/stop`.
- **Guardian Monitor (`guardian/`)**:
  - Background observer running at 5.0s interval.
  - Monitors high CPU/RAM, file modification bursts in user folders, new listening network ports, processes running in `%TEMP%` or `%APPDATA%`.
  - Issue: Alerts trigger on normal development processes (e.g. `llama-server.exe`, `python.exe`), accumulating 20+ unread alerts without deduplication or self-process filtering.

---

## 5. Comprehensive Audit: Places That Can Leak Raw JSON into Chat Bubbles

Our audit identified the following specific failure modes where raw JSON leaks into user bubbles:

1. **Model-Fabricated Structured Responses in ReAct Loop (`server.py` lines 1110–1175)**:
   - When the model outputs arbitrary JSON (e.g. `{"location": "Khulna", "temperature": "25C", ...}`) or Markdown code-fenced JSON, `is_tool_call(response_text)` evaluates to `False` because it only checks for recognized tool schemas (`"tool": "..."`).
   - `is_raw_tool_json(response_text)` also fails to match because it only checks known prefixes (`web_search`, `browser_open`, etc.).
   - Consequently, the model's invented JSON is treated as normal conversational text and streamed directly into the bubble!
2. **Double Tool Event Signaling in UI (`web/index.html` lines 1025–1038 & 1109–1120)**:
   - In `server.py`, the web search router emits a `tool_start` and `tool_result` event before calling the LLM.
   - If the LLM then issues a tool call in the ReAct loop, a second set of `tool_start` and `tool_result` events is emitted.
   - In `web/index.html`, `evt.type === 'tool_result'` blindly overwrites or appends with `"Search results found"`, creating duplicate status strips in the same turn.
3. **Weather Tool Fallback (`tools/web_tools.py` line 245)**:
   - When `wttr.in` fails or times out, `weather()` calls `web_search()`.
   - The returned search text is fed as unstructured text into the prompt. The model, instructed to be concise, prints a JSON data block followed by an apology.
4. **Tool Execution Return Values (`tools/router.py`)**:
   - Several direct tools (e.g. `system.system_status`, `memory.recall`) return raw serialized JSON strings rather than human-formatted strings or structured UI card payloads.
   - When streamed to the client, the user sees raw JSON dictionaries.

---

## 6. Audit Conclusion & Progression Plan

- No blocking impediments found.
- Hardware is ready; RAM requires aggressive memory management and single-turn model lifecycle discipline.
- Proceeding immediately to **PACKAGE 1: Intent Understanding Engine**.

