# JARVIS Stark Edition — Official Video Showcase Script
**Target Duration**: 2:30 – 2:50 Minutes (Strictly under 3:00 limit)
**Resolution**: 1080p (1920x1080), 60 FPS, Dark Mode Clay UI
**Audio**: Clear spoken English voiceover + live system demonstrations

---

## 🎬 Technical Shot List & Production Checklist

1. **Clean Screen**: Close all background apps; desktop contains only the browser at `http://127.0.0.1:8765`.
2. **Display Settings**: Windows Display Scaling set to 100% or 125%; browser zoom at 100%.
3. **Audio Setup**: Master system volume set to 50% via `scripts/demo_reset.ps1`.
4. **Pre-Demo Lock**: Confirm `python tests/e2e/regression_lock.py` passed 8/8 before starting recording.
5. **Backup Assets**: All pre-captured fallback clips and screenshots are in `submission/screenshots/`.

---

## ⏱️ Video Timeline & Scene-by-Scene Breakdown

---

### SCENE 1: The Hook & Signature Feature (0:00 – 0:30)
**Visual**: Screen opens on the Neumorphic Clay UI with the glowing Arc Reactor HUD top bar.
**Voiceover**:
> *"Most AI assistants look great in cloud demos, but they share a fatal flaw: they hallucinate success. When an AI says 'file created' or 'application launched', it's just predicting words—it doesn't actually know if the action worked.*
> *This is J.A.R.V.I.S. Stark Edition: a 100% local Windows assistant built on ground-truth state verification. It never reports success unless the real operating system confirms it."*

- **Action**: Click the **HUD** button on the top right.
- **On Screen**: Holographic Mission Control HUD expands, showing live CPU load (<12%), RAM usage (7.1 GB), battery status, and active defense radar.
- **Backup Fallback**: If HUD is slow to render, use pre-recorded clip or `submission/screenshots/03_mission_control_hud.png`.

---

### SCENE 2: Ground-Truth Verification in Action (0:30 – 1:00)
**Visual**: Main chat interface.
**Voiceover**:
> *"Let's test verified hardware control and terminal execution. Watch how JARVIS checks real system state before completing."*

- **Prompt 1**: Type `"make volume 30"` and press Enter.
- **On Screen**: JARVIS uses the Windows Core Audio API to set hardware volume, reads back the scalar from the endpoint, and returns: `"Volume is now 30%."` (0.2s).
- **Prompt 2**: Type `"run python --version"` and press Enter.
- **On Screen**: Terminal agent executes the shell command in a verified subprocess, capturing stdout: `"Python 3.14.7"` with exit code 0.
- **Backup Fallback**: `submission/screenshots/04_verified_briefing.png`.

---

### SCENE 3: Parametric 3D CAD Engineering Bay (1:00 – 1:35)
**Visual**: Chat panel transitioning to 3D WebGL viewport.
**Voiceover**:
> *"In the movies, Tony Stark designs hardware with his voice. Here, we built an offline Text-to-CAD generator that outputs real, watertight 3D-printable binary STL models."*

- **Prompt**: Type `"Create phone stand 80mm wide"` and press Enter.
- **On Screen**: In 0.6 seconds, JARVIS algorithmically generates the 3D model, validates Euler watertightness ($V - E + F = 2$), and loads the 3D interactive viewer.
- **Action**: Click and drag to orbit, zoom, and inspect the phone stand geometry in 3D.
- **Voiceover**:
> *"Every model is verified watertight on the fly—ready for your 3D printer without leaving your machine."*
- **Backup Fallback**: `submission/screenshots/05_3d_cad_engineering.png`.

---

### SCENE 4: First-Class Bilingual Bengali Memory (1:35 – 2:05)
**Visual**: Chat view.
**Voiceover**:
> *"Over 250 million Bengali speakers are neglected by mainstream AI. Watch how JARVIS handles Romanized Banglish and natural memory recall."*

- **Prompt 1**: Type `"amar naam Safin, mone rakho"` and press Enter.
- **On Screen**: Response: `"Noted, sir. I have committed this to long-term memory: 'amar naam Safin'."`
- **Prompt 2**: Type `"amar naam ki?"` and press Enter.
- **On Screen**: Instant recall: `"আপনার নাম Safin, স্যার।"`
- **Voiceover**:
> *"Notice: it recalls the user's name instantly, responds in authentic Bengali script, and strictly eliminates Hindi phoneme bleed. Zero API fees, zero language confusion."*
- **Backup Fallback**: `submission/screenshots/07_bilingual_bangla_memory.png`.

---

### SCENE 5: Real News & Error Handling (2:05 – 2:30)
**Visual**: Chat view.
**Voiceover**:
> *"Instead of hallucinated search results or generic site filler, JARVIS parses live XML feeds directly from BBC World and local news."*

- **Prompt 1**: Type `"What's new today"` and press Enter.
- **On Screen**: Clean structured list of BBC World News headlines with timestamps and direct source links.
- **Prompt 2**: Type `"weather for xyznonexistentcity123"` and press Enter.
- **On Screen**: Returns clean human-readable guidance: `"I could not locate weather data for 'xyznonexistentcity'. Please verify the city spelling..."`—zero raw tracebacks or crashes.
- **Backup Fallback**: `submission/screenshots/06_live_rss_news.png` and `08_human_error_handling.png`.

---

### SCENE 6: Architecture Close & Offline Proof (2:30 – 2:45)
**Visual**: Quick camera pan to network settings showing WiFi turned OFF, while typing `"run ipconfig"` or viewing the 3D CAD model offline.
**Voiceover**:
> *"Powered by local Ollama Qwen 2.5 7B, faster-whisper, and local ONNX embeddings, JARVIS runs 100% locally with zero subscription cost, absolute privacy, and verified execution. An assistant that controls your PC must never lie about what it did."*

- **Closing Title Card**:
  - **J.A.R.V.I.S. (Stark Civilian Edition)**
  - Built for Arbiter Hacks V1 — General Track
  - 100% Local • Ground-Truth Verified • Bilingual EN/BN • Open Source (MIT)
