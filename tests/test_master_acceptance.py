"""
Master Acceptance Test Suite for JARVIS (Work Order: jarvis-voice-merged)
Covers Parts A, B, C, D, E, F with real measured outputs.
"""

import sys
import time
import json
import uuid
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_BASE = "http://127.0.0.1:8765"
TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def run_master_acceptance():
    print("======================================================================")
    print("      JARVIS MASTER ACCEPTANCE VERIFICATION (PARTS A - F)             ")
    print("======================================================================")

    results = {}

    # ------------------------------------------------------------------
    # 1. Health & Server Metrics
    # ------------------------------------------------------------------
    print("\n[1] Checking Server Health & Footprint...")
    try:
        t0 = time.time()
        res = requests.get(f"{API_BASE}/api/v1/health", timeout=5).json()
        latency = (time.time() - t0) * 1000
        print(f"  -> Health OK: {res.get('ok')}, Model: {res.get('model')}, Latency: {latency:.1f}ms")
        assert res.get("ok") is True

        stats = requests.get(f"{API_BASE}/api/v1/system/stats", timeout=5).json()
        cpu = stats.get("cpu_percent", 0)
        ram = stats.get("ram_percent", 0)
        top_procs = stats.get("top_processes", [])
        print(f"  -> System CPU: {cpu}%, RAM: {ram}%, Top processes count: {len(top_procs)}")
        # Check System Idle Process is not in top processes
        top_names = [p.get("name", "").lower() for p in top_procs]
        assert "system idle process" not in top_names, "System Idle Process should never be in top consumers"
        results["Health & Server Metrics"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Health/Stats: {e}")
        results["Health & Server Metrics"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 2. Part A: Single Always-On Voice Control
    # ------------------------------------------------------------------
    print("\n[2] Part A: Voice Control & Settings Sync...")
    try:
        # Check voice devices
        devs = requests.get(f"{API_BASE}/api/v1/voice/devices", headers=HEADERS, timeout=5).json()
        print(f"  -> Available Audio Input Devices: {len(devs.get('devices', []))}")

        # Toggle mode to 'always'
        m_res = requests.post(f"{API_BASE}/api/v1/voice/mode", headers=HEADERS, json={"mode": "always"}, timeout=5).json()
        assert m_res.get("mode") == "always"

        # Update settings
        s_res = requests.post(f"{API_BASE}/api/v1/voice/settings", headers=HEADERS, json={
            "mode": "always",
            "language": "auto",
            "sensitivity": "medium",
            "speak_replies": True
        }, timeout=5).json()
        assert s_res.get("ok") is True
        print("  -> Voice Mode set to 'always', language 'auto', sensitivity 'medium', speak_replies True")
        results["Part A: Single Voice Control"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part A: {e}")
        results["Part A: Single Voice Control"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 3. Part B: VAD & False-Trigger Hygiene
    # ------------------------------------------------------------------
    print("\n[3] Part B: VAD & Idle CPU Hygiene...")
    try:
        from voice.listener import WakeWordListener, FRAME_DURATION_MS, FRAME_SIZE
        assert FRAME_DURATION_MS == 30
        assert FRAME_SIZE == 480
        listener = WakeWordListener()
        assert listener.mode in ("always", "off", "push")
        print(f"  -> WakeWordListener initialized: WebRTC VAD 30ms frame (480 samples), mode: {listener.mode}")
        results["Part B: VAD & Listener Hygiene"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part B: {e}")
        results["Part B: VAD & Listener Hygiene"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 4. Part C: Bilingual Speech (Bangla + English)
    # ------------------------------------------------------------------
    print("\n[4] Part C: Bilingual Language Disambiguation & TTS...")
    try:
        from intent.normalizer import detect_language
        lang_bn = detect_language("আজকের আবহাওয়া কেমন?")
        lang_en = detect_language("What is the weather today?")
        lang_bg = detect_language("tumi kemon acho?")  # Banglish
        print(f"  -> 'আজকের আবহাওয়া কেমন?' => {lang_bn}")
        print(f"  -> 'What is the weather today?' => {lang_en}")
        print(f"  -> 'tumi kemon acho?' => {lang_bg}")
        assert lang_bn == "bn_script"
        assert lang_en == "en"
        assert lang_bg == "bn_banglish"

        # Test TTS synthesis latency
        import tempfile
        import os
        from voice.tts import generate_wav
        wav_en = tempfile.mktemp(suffix=".wav")
        t0 = time.time()
        generate_wav("System online.", wav_en)
        t_en = time.time() - t0
        sz_en = os.path.getsize(wav_en) if os.path.exists(wav_en) else 0
        print(f"  -> English TTS synthesis time: {t_en:.2f}s (Bytes: {sz_en})")
        assert sz_en > 0
        if os.path.exists(wav_en): os.remove(wav_en)

        wav_bn = tempfile.mktemp(suffix=".wav")
        t0 = time.time()
        generate_wav("সিস্টেম প্রস্তুত।", wav_bn)
        t_bn = time.time() - t0
        sz_bn = os.path.getsize(wav_bn) if os.path.exists(wav_bn) else 0
        print(f"  -> Bangla TTS synthesis time: {t_bn:.2f}s (Bytes: {sz_bn})")
        assert sz_bn > 0
        if os.path.exists(wav_bn): os.remove(wav_bn)
        results["Part C: Bilingual Speech"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part C: {e}")
        results["Part C: Bilingual Speech"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 5. Part D: Image & PDF Attachments
    # ------------------------------------------------------------------
    print("\n[5] Part D: Document & Image Attachments...")
    try:
        from ingest.extractor import extract, is_binary_or_corrupt, get_ocr_engine
        from ingest.document_processor import build_document_prompt

        # Create sample text file
        sample_txt = BASE_DIR / "data" / "sample_test_doc.txt"
        sample_txt.write_text("JARVIS Autonomous Copilot Specification Document\nKey metric: 99.4% uptime.", encoding="utf-8")

        extracted = extract(sample_txt)
        assert extracted["kind"] == "text"
        assert "JARVIS Autonomous Copilot" in extracted["pages"][0]["text"]

        sys_prompt, user_content = build_document_prompt("Explain this file", extracted)
        assert "[Attachment: sample_test_doc.txt, 1 pages, text]" in user_content
        print("  -> Document extraction & prompt formatting verified")

        # Binary guard verification
        assert is_binary_or_corrupt(bytes([0, 1, 2, 3, 255, 0, 12, 14])) is True
        assert is_binary_or_corrupt(b"Hello world, plain English text!") is False
        print("  -> Binary guard verified (>5% non-printable detection)")
        results["Part D: Attachments & Extraction"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part D: {e}")
        results["Part D: Attachments & Extraction"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 6. Part E: Guardian Noise Suppression & Baseline
    # ------------------------------------------------------------------
    print("\n[6] Part E: Guardian Noise Suppression & Active Alert Badge...")
    try:
        # Query guardian status
        g_st = requests.get(f"{API_BASE}/api/v1/guardian/status", headers=HEADERS, timeout=5).json()
        print(f"  -> Guardian Enabled: {g_st.get('enabled')}, Footprint CPU: {g_st.get('guardian_cpu_pct')}%, RAM: {g_st.get('guardian_mem_mb')}MB")
        print(f"  -> Unread alerts: {g_st.get('unread_alerts')}, Total: {g_st.get('total_alerts')}")
        assert g_st.get("guardian_cpu_pct", 0) < 3.0, "Guardian CPU must be sub-3%"
        assert g_st.get("unread_alerts", 0) == 0, "Unread alerts badge must be 0"

        # Verify baseline reset API
        r_reset = requests.post(f"{API_BASE}/api/v1/guardian/baseline/reset", headers=HEADERS, timeout=10).json()
        assert r_reset.get("ok") is True
        print(f"  -> Guardian baseline reset API verified (Processes: {r_reset.get('processes_count')})")
        results["Part E: Guardian Noise Suppression"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part E: {e}")
        results["Part E: Guardian Noise Suppression"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # 7. Part F: UI Polish, Chat SSE Stream & Extension
    # ------------------------------------------------------------------
    print("\n[7] Part F: Personal Agent Polish, Chat Stream & Extension 1.3.8...")
    try:
        # Check VS Code Extension version
        ext_pkg = json.loads((BASE_DIR / "jarvis-vscode-extension" / "package.json").read_text(encoding="utf-8"))
        assert ext_pkg.get("version") == "1.3.8", f"Extension package.json version is {ext_pkg.get('version')}"
        vsix_file = BASE_DIR / "jarvis-vscode-extension" / "jarvis-ai-copilot-1.3.8.vsix"
        assert vsix_file.exists(), "jarvis-ai-copilot-1.3.8.vsix must exist"
        print(f"  -> VS Code Extension 1.3.8 verified (VSIX size: {vsix_file.stat().st_size} bytes)")

        # Test live SSE chat stream with turn_id echo
        turn_id = str(uuid.uuid4())
        chat_req = {
            "message": "Respond with the single word: READY",
            "turn_id": turn_id,
            "stream": True
        }
        res = requests.post(f"{API_BASE}/api/v1/chat", json=chat_req, headers=HEADERS, stream=True, timeout=90)
        events = []
        for line in res.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
                if data.get("type") == "done":
                    break

        types = [e.get("type") for e in events]
        print(f"  -> Received SSE Event types: {set(types)}")
        assert "token" in types or "done" in types, "Stream must emit tokens or done"
        done_evt = next((e for e in events if e.get("type") == "done"), {})
        assert done_evt.get("turn_id") == turn_id, "turn_id must be echoed in done event"
        print(f"  -> Chat stream verified with turn_id: {turn_id}")
        results["Part F: Personal Polish & SSE Turn Isolation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Part F: {e}")
        results["Part F: Personal Polish & SSE Turn Isolation"] = f"FAIL ({e})"

    # ------------------------------------------------------------------
    # Final Summary
    # ------------------------------------------------------------------
    print("\n======================================================================")
    print("                     MASTER VERIFICATION SUMMARY                     ")
    print("======================================================================")
    all_pass = True
    for item, status in results.items():
        print(f"  {item.ljust(45)} : {status}")
        if status != "PASS":
            all_pass = False

    print("======================================================================")
    if all_pass:
        print(">>> ALL PACKAGES A, B, C, D, E, F SUCCESSFULLY VERIFIED AND PASSED <<<")
    else:
        print(">>> SOME VERIFICATION CHECKS FAILED <<<")
    print("======================================================================\n")

if __name__ == "__main__":
    run_master_acceptance()
