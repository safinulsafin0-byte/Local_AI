# JARVIS (Stark Civilian Edition) — Devpost Project Story
**Event**: Arbiter Hacks V1 — General Track

---

## 🌟 Inspiration

Commercial AI assistants look impressive in high-bandwidth Silicon Valley presentations, but for over 250 million Bengali speakers, developers in emerging markets with intermittent internet, and privacy-conscious engineers, they fail in practice:
- **The Monthly Tax**: Paying $20/month for ChatGPT Plus or Copilot Pro is unaffordable for millions of students and freelancers in South Asia.
- **The Cloud Tether**: When your internet drops, your assistant vanishes. You cannot control your PC, write code, or automate local tasks.
- **The Language Gap**: Mainstream cloud models treat Bengali as an afterthought. Prompts in Bengali or Romanized Banglish are frequently returned in broken English, mangled phonetics, or worse, cross-contaminated with Hindi.
- **The Black Box**: Commercial tools send your personal files, keystrokes, and audio transcripts to corporate cloud servers.

We asked: **What if you could run a Stark-grade personal AI assistant on a standard 16GB Windows laptop, completely local, with zero API fees, first-class bilingual Bangla/English intelligence, and a guarantee that it never lies about what it did?**

---

## 🚀 What It Does: Ground-Truth Verified Assistant

JARVIS Stark Edition is a local-first Windows AI assistant and copilot. While it features a Stark-style holographic Arc Reactor HUD, 3D text-to-CAD generation, and live RSS news, its **core signature innovation is Ground-Truth State Verification**.

### 1. The Anti-Hallucination Verified Tool Architecture
Conventional AI assistants suffer from the "Self-Reported Success" flaw: when an LLM claims *"✓ Created folder Demo"* or *"✓ Opened command prompt"*, it is merely predicting the next token. If the folder path was mangled into a subfolder or the process crashed on launch, the user is left misinformed.

In JARVIS:
- **No LLM is ever allowed to declare success on its own.**
- Every action is executed through deterministic operating system hooks.
- **The system queries actual Windows OS state**—reading back hardware audio endpoint scalars (`pycaw`), inspecting active process IDs and Win32 window titles, checking file existence and byte counts on disk—**before reporting success**.
- If a command fails or exits non-zero, JARVIS displays the real exit code and diagnostic error message.

### 2. Native Bilingual Bengali & English Dual-Pipeline
- Speaks and understands natural English and Bengali (including Banglish transliteration).
- Automatically detects linguistic script and strictly isolates responses: when spoken to in Bengali or Banglish, it replies entirely in proper Bengali script (`বাংলা লিপি`), with zero Hindi phoneme drift.
- Remembers user facts naturally across sessions (`"amar naam Safin, mone rakho"` -> `"amar naam ki?"` -> `"আপনার নাম Safin, স্যার।"`).

### 3. Parametric 3D CAD Engineering Bay
- Text-to-CAD generator that synthesizes watertight, 3D-printable binary STL files (spur gears, electronics enclosures, L-brackets, phone stands, domes) locally without cloud APIs.
- Evaluates Euler characteristic watertightness ($V - E + F = 2$) before saving, rendered in an interactive Three.js WebGL viewer.

### 4. Zero-Cloud Local Telemetry & News
- Local Arc Reactor HUD tracking real-time normalized CPU/RAM usage, battery status, and active tasks.
- Live RSS news feeds directly from BBC World, The Verge, and Prothom Alo (no ad-stuffed web scraping).
- Direct Open-Meteo geocoding across all 64 Bangladesh districts (zero stale cache leakage).

---

## 🛠️ How We Built It

- **Core Backend**: Asynchronous FastAPI server (`server.py`) running on `127.0.0.1:8765` streaming Server-Sent Events (SSE).
- **Local Neural Models**: Local Ollama serving `qwen2.5:7b` (Q4_K_M GGUF), `faster-whisper` (INT8 local STT), and `moondream2` (local vision).
- **Local Vector Database**: AST-aware chunker with pure offline 384-dimensional ONNX embeddings (`all-MiniLM-L6-v2`) and ChromaDB vector store.
- **OS Automation Layer**: Python Windows extensions (`pywin32`, `pycaw`, `psutil`, `send2trash`) for hardware audio scalar readback and window tracking.
- **Web Interface**: Neumorphic tactile Clay UI (`web/index.html`) with Three.js WebGL 3D rendering.

---

## 🧗 Challenges We Ran Into (And How We Solved Them)

1. **The False-Success Bug**: Early in development, the system would show `"✓ Completed"` even when a subprocess exited with an error code. We solved this by rebuilding the SSE event generator in `server.py` to require verified `ok: bool` status and real error messages from the OS layer before emitting `tool_result`.
2. **Path Preposition Parsing**: Commands like `"create a folder name Demo inside D:\jarvis_test"` originally created `"Demo inside D:\jarvis_test"` as a single folder name. We built a deterministic regex parser in `tools/file_ops.py` that separates action, target name, and parent directory with recursive path normalization.
3. **Bangla Speech & Memory Hallucinations**: When the background Whisper listener ran on ambient room noise, it hallucinated Hindi and Russian phonemes, pegging the CPU at 100%. We resolved this by disabling the ambient microphone thread by default (text-first mode), isolating language prompts in `server.py`, and filtering out question sentences from long-term memory.
4. **Devanagari Danda Encoding Bug**: During regression testing, our language guard flagged Bengali sentences as Hindi because the standard Bengali full stop (Dari `।`, Unicode `U+0964`) is historically allocated inside the Devanagari block. We corrected our regex validator to specifically isolate Devanagari alphabetic characters (`\u0904-\u0939`), ensuring authentic Bengali punctuation is validated correctly.

---

## 🏆 Accomplishments That We're Proud Of

- **8/8 Regression Lock Pass (100.0%)**: Our master regression lock suite (`tests/e2e/regression_lock.py`) rigorously validates real system state across all core capabilities:
  ```text
  [PASS] Test 1: Filesystem Exact Path          (0.31s) — Real folder exists=True, mangled=False
  [PASS] Test 2: Visible CMD Launch             (0.95s) — Spawned PID=19372, window confirmed=True
  [PASS] Test 3: Weather Geocoding Precision    (0.23s) — City matched=True, temp present=True
  [PASS] Test 4: Volume Hardware Readback       (0.22s) — Hardware readback=30%
  [PASS] Test 5: Live RSS Headlines             (4.63s) — Headlines=True, source/links=True
  [PASS] Test 6: Image Attachment Vision        (14.39s) — Described content=True
  [PASS] Test 7: Terminal Command Routing       (0.40s) — Python stdout=True, not system status=True
  [PASS] Test 8: Bangla Memory & Language Guard (0.08s) — Recalls Safin=True, Bengali script=True, No Hindi=True
  ```
- **60/60 Master Features Verified (100.0%)**: All 60 commands in Part II of our feature matrix passed with zero regressions.
- **Lean Footprint**: Idles at under 5% CPU and uses ~7.1 GB RAM under active local LLM inference on a standard 16GB laptop.
- **$0 Cost**: Entirely free of proprietary API tokens, subscription keys, or telemetry tracking.

---

## 📚 What We Learned

- **Verification beats prompting**: You cannot prompt an LLM to reliably report whether its tool succeeded. Decoupling tool execution from ground-truth OS state inspection is the only architecture that eliminates false positives in computer control.
- **Small local models are extraordinarily capable**: When paired with deterministic routing and clean preprocessing, a local 7B parameter model (`qwen2.5:7b`) can outperform cloud assistants on operating system tasks while preserving 100% data privacy.

---

## 🔮 What's Next (Roadmap)

- **v2.0 Encrypted Mobile Relay**: Outbound encrypted Telegram and email notification bridges for remote alert dispatching.
- **Hardware Sensor Bridge**: Physical USB-UART serial protocol connecting JARVIS to Arduino and ESP32 environmental sensors.
- **Edge Model Optimization**: Exploring 4-bit INT4 quantization on ONNX DirectML to bring inference latency down to under 500ms on integrated graphics.
