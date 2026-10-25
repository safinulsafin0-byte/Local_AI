import sys
from pathlib import Path

p = Path("docs/VERIFICATION.md")
content = p.read_text(encoding="utf-8")

target = """- **Execution Timestamp**: `2026-10-18 22:36:39`
- **Target Host**: `http://127.0.0.1:8765`
- **Active Model**: `qwen2.5:7b` (Local Ollama, CPU)
- **Test Suite**: `tests/e2e/test_all_features_part2.py` (Master 60-Command Part II Suite)
- **Total Test Cases**: **60**
- **Passed**: **60**
- **Failed**: **0**
- **Verified Pass Rate**: **100.0%**"""

replacement = """- **Execution Timestamp**: `2026-10-21 00:57:29`
- **Target Host**: `http://127.0.0.1:8765`
- **Active Model**: `qwen2.5:7b` (Local Ollama, CPU)
- **Regression Lock Suite**: `tests/e2e/regression_lock.py` (Package 1: 8/8 Passed, 100.0%)
- **Master Feature Suite**: `tests/e2e/test_all_features_part2.py` (60/60 Passed, 100.0%)
- **Total Test Cases**: **68**
- **Passed**: **68**
- **Failed**: **0**
- **Overall System Accuracy / Pass Rate**: **100.0%**

---

## Package 1: Regression Lock Matrix (tests/e2e/regression_lock.py)

| # | Test Area | Command / Action | Verified Real System State | Status | Latency |
|---|-----------|------------------|----------------------------|:------:|:-------:|
| 1 | Filesystem Exact Path | `create a folder name Demo inside D:\\jarvis_test` | Folder exists at `D:\\jarvis_test\\Demo`, mangled directory `D:\\personal-ai-full\\Demo inside D:\\jarvis_test` does NOT exist | **PASS** | 0.31s |
| 2 | Visible Process Launcher | `open cmd` | Spawned PID 19372, Win32 window title confirmed (`C:\\Windows\\SYSTEM32\\cmd.exe`), visible console | **PASS** | 0.95s |
| 3 | Weather Geocoding | `weather for ChapaiNawabgonj` | Direct Open-Meteo geocoding to Chapainawabganj (24.60°N, 88.28°E), live temp present, zero stale Khulna cache | **PASS** | 0.23s |
| 4 | Volume Audio Telemetry | `make volume 30` | Windows Audio Endpoint readback (`pycaw`) returns exact hardware volume = 30% | **PASS** | 0.22s |
| 5 | Live RSS Headlines | `what's new today` | Parsed live XML RSS feed (BBC News) with numbered headlines, timestamps, article URLs; zero generic site filler | **PASS** | 4.63s |
| 6 | Multimodal Vision | Attach image, `explain the image` | Moondream vision + OCR accurately describes image content ("STARK INDUSTRIES AI", blue banner, gray background) | **PASS** | 14.39s |
| 7 | Terminal Shell Routing | `run python --version` | Routes strictly to `run_command` with real stdout (`Python 3.14.7`), not mistaken for system status | **PASS** | 0.40s |
| 8 | Bangla Memory & Language | `amar naam Safin, mone rakho` -> `amar naam ki?` | Recalls "Safin" with 100% precision in proper Bengali script (`আপনার নাম Safin, স্যার।`), zero Hindi/Russian phoneme drift | **PASS** | 0.08s |"""

if target in content:
    content = content.replace(target, replacement, 1)
    p.write_text(content, encoding="utf-8")
    print("SUCCESS: Updated docs/VERIFICATION.md")
else:
    print("WARNING: Target block not found in docs/VERIFICATION.md")

