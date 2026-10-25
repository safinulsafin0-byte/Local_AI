# JARVIS Stark Edition — Pre-Demo Checklist & Plan B Protocols

This checklist guarantees a zero-failure video recording and live hackathon demonstration on a 16 GB Windows laptop.

---

## 1. Pre-Recording System Setup (T - 10 Minutes)

- [ ] **Clean Restart**: Run `powershell -ExecutionPolicy Bypass -File scripts/demo_reset.ps1` to clear temporary files, reset master audio to 50%, and verify Ollama.
- [ ] **Display Setup**: Screen resolution set to **1920x1080 (1080p)**, Windows scaling at **100% or 125%**, clear desktop with no extraneous icons.
- [ ] **Notifications Muted**: Windows Focus Assist turned ON (Alarms only); close Discord, Slack, and WhatsApp.
- [ ] **Audio Configuration**: Quiet room; headset microphone selected as default Windows input. Voice output set to text-only mode (`/api/v1/voice/mode` -> `off` or muted).
- [ ] **Browser Prep**: Open Chrome/Edge at `http://127.0.0.1:8765`. Verify all 4 top status chips are green (`✓ Ollama`, `✓ Voice`, `✓ Guardian`, `✓ RAG`).
- [ ] **Verification Lock**: Run `python tests/e2e/regression_lock.py` to confirm 8/8 pass before opening the recorder.

---

## 2. Recommended Demo Hardware & Model Profile

| Metric | Target Specification | Tested Baseline |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 / 11 (64-bit) | Windows 11 Enterprise |
| **System Memory (RAM)** | 16 GB Physical Memory | 13.84 GB Available, 7.1 GB Used under load (51.4%) |
| **CPU Utilization** | Intel Core i5/i7 (8+ threads) or AMD Ryzen 5/7 | 12 Logical Cores, <15% peak load during inference |
| **Local LLM Profile** | `qwen2.5:7b` (via Ollama, Q4_K_M GGUF) | Verified response latency: 0.08s - 3.2s |
| **Fallback LLM Profile** | `qwen2.5:3b` or `qwen2.5-coder:1.5b` | For low-spec 8GB laptops (set via `OLLAMA_MODEL` in `.env`) |

---

## 3. Step-by-Step Demo Script & Plan B Failover Matrix

### Scene 1: Mission Control & Ground-Truth Verification (0:00 - 0:45)
- **Primary Action**: Type `"Give me a briefing"`, then click **HUD** button.
- **Expected Outcome**: Real CPU load (<15%), RAM (7.1 GB), battery status, and weather telemetry displayed; Arc Reactor HUD visualizer renders smoothly.
- **Plan B**: If LLM briefing exceeds 4 seconds, show pre-loaded HUD tab directly from top bar.

### Scene 2: Verified Tool Execution & Safe Filesystem (0:45 - 1:15)
- **Primary Action**: Type `"create a folder name Demo inside D:\jarvis_test"` then `"run python --version"`.
- **Expected Outcome**: Instant folder creation with exact path displayed; terminal executes `python --version` with real stdout (`Python 3.14.7`) and exit code 0.
- **Plan B**: If disk is write-protected, execute `"run ipconfig"` to demonstrate shell execution.

### Scene 3: Parametric 3D CAD Engineering Bay (1:15 - 1:45)
- **Primary Action**: Type `"Create phone stand 80mm wide"`.
- **Expected Outcome**: Binary STL model generated in ~0.6s. Watertightness verified ($V - E + F = 2$), 3D WebGL viewer opens with interactive orbit controls.
- **Plan B**: If WebGL crashes, load existing pre-verified STL `spur_gear_16t.stl` directly in the viewer.

### Scene 4: Bilingual Bangla Long-Term Memory (1:45 - 2:15)
- **Primary Action**: Type `"amar naam Safin, mone rakho"` -> wait for confirmation -> type `"amar naam ki?"`.
- **Expected Outcome**: Instant recall: `"আপনার নাম Safin, স্যার।"`. Pure Bengali script, zero Hindi drift, zero web search timeout.
- **Plan B**: Pre-recorded 5-second MP4 backup clip located in `submission/screenshots/07_bilingual_bangla_memory.png`.

### Scene 5: Live RSS News & Friendly Error Guard (2:15 - 2:45)
- **Primary Action**: Type `"What's new today"`, followed by `"weather for xyznonexistentcity123"`.
- **Expected Outcome**: Real BBC News headlines with timestamps and links; invalid weather returns clean human message without raw tracebacks.
- **Plan B**: Pre-captured screenshots available in `submission/screenshots/06_live_rss_news.png` and `08_human_error_handling.png`.

---

## 4. Post-Recording Quality Verification

- [ ] Video length is strictly between **2:30 and 3:00**.
- [ ] Every spoken statement corresponds to a live feature demonstrated on screen.
- [ ] Video exported in 1080p MP4 with crisp audio.

