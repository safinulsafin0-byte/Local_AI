# JARVIS Feature Matrix & System Audit (Package 0)

Date: 2026-10-14  
Environment: Windows 11 (AMD Ryzen 5 7430U, Radeon iGPU, 14 GB RAM)  
Backend: `http://127.0.0.1:8765`  
Clients: Web UI (`/web/index.html`) & VS Code Extension (`jarvis-ai-copilot` v1.3.11)

---

## 1. Hardware & Runtime Resource Footprint

| Subsystem / Process | PID | Working Set (RAM) | Idle CPU % | Notes / Model |
|---------------------|-----|-------------------|------------|---------------|
| **JARVIS Server** (`server.py`) | 21688 | 536.2 MB | 0.8% | FastAPI, Whisper listener, Guardian observer |
| **Ollama Engine** (`ollama.exe`) | 6220 | 50.4 MB | 0.0% | Core Ollama service daemon (`127.0.0.1:11434`) |
| **Ollama Runner** (`ollama app.exe`) | 19872 | 783.7 MB | 0.0% | Loaded `qwen2.5:7b` (Q4_K_M) |
| **Audio Service** (Whisper + Piper) | In-proc | ~180 MB | 1.2% | Faster-Whisper Small (int8), Piper TTS Lessac |
| **Guardian Security Monitor** | In-proc | ~45 MB | < 1.0% | Background thread (5.0s scan, Authenticode cached) |

### System Hardware
- **CPU**: AMD Ryzen 5 7430U with Radeon Graphics (6 Cores, 12 Logical Processors)
- **RAM**: 13.84 GB Total Physical Memory (~5.4 GB Available)
- **GPU**: AMD Radeon(TM) Graphics (iGPU, 2048 MB Adapter RAM)
- **Primary LLM**: `qwen2.5:7b` (num_ctx: 32768, quant: Q4_K_M)
- **Vision Model**: `moondream:latest` (1B) / fallback OCR
- **TTS**: Piper `en_US-lessac-medium.onnx` (English) + edge-tts fallback (Bangla)
- **STT**: `faster-whisper-small` (CPU, int8)

### Recommended Profiles
1. **Light Profile (Recommended for current iGPU hardware)**:
   - LLM: `qwen2.5:3b` (1.9 GB disk / 2.2 GB RAM). Response time: ~2-4s.
   - Whisper: `faster-whisper-small` (int8).
   - TTS: Piper local ONNX.
   - Peak RAM: ~3.8 GB total. Fluid multi-tasking without memory pressure.
2. **Standard Profile**:
   - LLM: `qwen2.5:7b` (4.7 GB disk / 5.2 GB RAM). Response time: ~25-40s first-token on CPU.
   - Peak RAM: ~7.5 GB total. High reasoning accuracy.

---

## 2. Feature Audit Matrix

| Category | Feature | Status | Evidence / Test Result | Next Steps |
|----------|---------|--------|------------------------|------------|
| **Chat & LLM** | Chat Streaming | **WORKING** | `POST /api/v1/chat` returned HTTP 200, streamed tokens `{"type": "token", "text": "Hello, how ..."}`. Verified across Web & Extension. | Pre-warm model on startup to eliminate cold-start delay (Pkg 6). |
| **Memory** | Local Key-Value & Facts | **WORKING** | `GET /api/v1/memory` (200 OK) and `POST /api/v1/memory` successfully recorded entries in `data/memory/memory.db`. | Persist conversation memory contexts across restarts (Pkg 3). |
| **Attachments** | Upload & Ingest Pipeline | **PARTIAL** | Upload endpoint `POST /api/v1/files/upload` returns `file_id` (200 OK). PyMuPDF & RapidOCR ready. In-bubble ChatGPT-style thumbnail display needed. | Implement ChatGPT-style bubble cards, lightbox, multi-file grid (Pkg 1). |
| **Web Research** | DuckDuckGo Web Search | **WORKING** | `web.search` tool executed in 4.63s via `ddgs`: returned structured titles, URLs, and snippets from python.org. | Add Trafilatura deep extraction and source citation chips (Pkg 2). |
| **Weather** | Open-Meteo Integration | **WORKING** | `web.weather` returned live weather: `"Dhaka is currently 32°C and Clear sky. Humidity is 53%..."` without API keys. | Standardize keyword arguments across direct router and LLM calls (Pkg 2). |
| **News** | Live RSS News Feeds | **WORKING** | Installed `feedparser` into `venv`. RSS feed router reads top headlines without external keys. | Support custom RSS sources (BBC, Reuters, Prothom Alo) (Pkg 2). |
| **YouTube** | Media Control Panel | **WORKING** | `youtube.search({'query': 'bangla lofi'})` returned 5 structured results; pause/resume/summarize video router operational. | Verify synchronized audio ducking during playback (Pkg 4). |
| **Voice Output** | Bilingual TTS (EN & BN) | **WORKING** | Piper ONNX generated 47,660 bytes WAV for English; Bangla TTS generated 262,528 bytes WAV. Fixed missing `threading` import in `server.py:2148`. | Download offline MMS-TTS Bangla model into `models/` (Pkg 6). |
| **Voice Input** | Bilingual STT (Whisper) | **WORKING** | Faster-Whisper Small int8 recognized speech (`p=0.99, avg_lp=-0.33`). Hallucination filter active for repetitive and non-Bangla/English scripts. | Fine-tune VAD threshold during silent background conditions (Pkg 6). |
| **File Operations**| Local Workspace File Ops | **WORKING** | `filesystem.create_file` and `filesystem.read_file` created and read `test_audit_file.txt` with normalized parameters. | Add diff preview card (`str_replace` style) with Accept/Reject (Pkg 4). |
| **Terminal Agent**| PowerShell Execution | **WORKING** | `run_command` dispatched to `system.run_shell`, executed `Write-Output AUDIT_TERMINAL_OK` with Exit code 0. | Add timeout watchdog, background process manager, live streaming cards (Pkg 5). |
| **PC Control** | Windows System Automation | **WORKING** | System stats (CPU/RAM/battery) operational; installed `pycaw` for volume control; safety confirmation required for shutdown. | Add 10s countdown card with voice/click cancel (Pkg 3 & 4). |
| **Guardian** | Security Monitor | **WORKING** | Fixed false positive: Valid Authenticode-signed executables in `%TEMP%` no longer trigger suspicious process alerts. | Group duplicate alerts and polish bell badge notification (Pkg 6). |
| **Conversations** | History & Session Lifecycle | **WORKING** | `GET /api/v1/conversations` returns saved sessions; new chat reset operational. | Clear uploaded files on conversation deletion (Pkg 1). |
| **VS Code Extension** | Copilot Sidebar & Status Bar | **WORKING** | Updated to `v1.3.11`. Fixed ECONNREFUSED hang, added exponential backoff health check, guaranteed stream cleanup to eliminate stuck cursor. | Link native VS Code diff editor for proposed code edits (Pkg 5). |
| **Offline Mode** | Local-First Subsystems | **WORKING** | All core capabilities (LLM, Whisper STT, Piper TTS, Memory, File Ops, Terminal, Guardian) run with 0 external network requests. | Show clear banner when internet-only features (web/YouTube) are accessed offline (Pkg 2). |

---

## 3. Prioritized Fix List (Packages 1 – 8)

1. **Package 1 (Attachments)**:
   - ChatGPT-style in-bubble thumbnails, file cards (PDF/Word/Excel), lightbox preview.
   - Shared ingest layer: PyMuPDF + RapidOCR for scanned pages (< 30 chars).
   - Strict prompt-injection defense for untrusted attachment content.
2. **Package 2 (Web Research & Downloads)**:
   - Trafilatura full-page content extraction with source chips `[1][2]`.
   - Streaming downloader with progress bar, SHA-256 verification, and Windows Defender scan.
3. **Package 3 (Agent Core & Permissions)**:
   - Multi-step structured planner checklist ("1. Create folder, 2. Write code, 3. Run test").
   - 10-second countdown card for destructive actions with voice/click cancellation.
   - Action audit log `data/action_log.jsonl` and snapshot undo mechanism.
4. **Package 4 (Files, Folders & PC Control)**:
   - Workspace file diff cards with [Accept] [Reject] [Undo].
   - Pycaw volume, display controls, and safe process management.
5. **Package 5 (Terminal & Coding Agent)**:
   - Streaming terminal execution cards with Stop/Kill switch.
   - Multi-file code repair loop and git integration.
6. **Package 6 (Reliability & Performance)**:
   - Fixed startup scripts (`scripts/start.ps1`, `start_jarvis.bat`).
   - Profile switcher (Light 3B vs Standard 7B) with startup pre-warming.
7. **Package 7 (E2E Evaluation Suite)**:
   - Scripted test runner `tests/e2e/run.py` with 50+ automated scenarios across 3 runs.
8. **Package 8 (Devpost Submission Package)**:
   - Showcase `README.md`, `DEVPOST_STORY.md`, `VIDEO_SCRIPT.md`, and Mermaid architecture.

