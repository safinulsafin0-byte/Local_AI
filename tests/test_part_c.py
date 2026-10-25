import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import time
import os
import re
import json
import urllib.request

TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE_URL = "http://127.0.0.1:8765/api/v1"

def test_part_c():
    print("=" * 60)
    print("RUNNING PART C VERIFICATION: BILINGUAL SPEECH & LANGUAGE ENFORCEMENT")
    print("=" * 60)

    # 1. Per-utterance Language Detection Test
    from intent.normalizer import detect_language
    test_cases = [
        ("how is the weather in Khulna", "en"),
        ("what is my cpu usage right now", "en"),
        ("আজকের আবহাওয়া কেমন?", "bn_script"),
        ("আমার জন্য এক কাপ চা বানাও", "bn_script"),
        ("amake VS Code ta open kore dao", "bn_banglish"),
        ("ekta sundor pahar er chobi banao", "bn_banglish"),
        ("ajker khobor ki", "bn_banglish"),
    ]

    print("1. Testing Language & Banglish Detection:")
    for text, expected in test_cases:
        detected = detect_language(text)
        assert detected == expected, f"Failed for '{text}': got {detected}, expected {expected}"
        print(f"   [PASS] '{text}' -> {detected}")

    # 2. Testing Chat Streaming with Language Enforcement & Lang Badge
    print("\n2. Testing Chat SSE Stream Language Rule & Lang Badge:")

    # 2a. English Query
    req_en = urllib.request.Request(
        f"{BASE_URL}/chat",
        data=json.dumps({"message": "What is Python in one sentence?", "stream": True}).encode(),
        headers=HEADERS
    )
    en_full = ""
    en_badge = ""
    with urllib.request.urlopen(req_en, timeout=60) as res:
        for line in res:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data:"):
                try:
                    evt = json.loads(line_str[5:].strip())
                    if evt.get("type") == "token":
                        en_full += evt.get("text", "")
                    elif evt.get("type") == "done":
                        en_badge = evt.get("lang", "")
                except Exception:
                    pass

    print(f"   [EN Query Response] Badge: {en_badge} | Text: {en_full[:70]}...")
    assert en_badge == "EN", f"Expected EN badge, got {en_badge}"
    assert not bool(re.search(r"[\u0980-\u09FF]", en_full)), "English response should not contain Bengali script"

    # 2b. Bengali / Banglish Query (User spoke Banglish -> Must reply in Bengali script)
    req_bn = urllib.request.Request(
        f"{BASE_URL}/chat",
        data=json.dumps({"message": "tumi kemon acho? ekta choto uttor dao", "stream": True}).encode(),
        headers=HEADERS
    )
    bn_full = ""
    bn_badge = ""
    with urllib.request.urlopen(req_bn, timeout=60) as res:
        for line in res:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data:"):
                try:
                    evt = json.loads(line_str[5:].strip())
                    if evt.get("type") == "token":
                        bn_full += evt.get("text", "")
                    elif evt.get("type") == "done":
                        bn_badge = evt.get("lang", "")
                except Exception:
                    pass

    print(f"   [BN Query Response] Badge: {bn_badge} | Text: {bn_full[:70]}...")
    assert bn_badge == "BN", f"Expected BN badge, got {bn_badge}"
    assert bool(re.search(r"[\u0980-\u09FF]", bn_full)), "Bangla/Banglish query MUST reply in Bengali script!"

    # 3. Voice TTS Engines (Piper English + Edge-TTS/Bengali fallback)
    print("\n3. Testing Voice TTS Engines (Audio Generation):")
    from voice.tts import synthesize_to_wav
    import tempfile

    # English Piper
    tmp_en = tempfile.mktemp(suffix=".wav")
    t0 = time.time()
    res_en = synthesize_to_wav("Testing offline English synthesis with Piper.", tmp_en)
    en_dur = time.time() - t0
    assert os.path.exists(res_en) and os.path.getsize(res_en) > 0, "Piper English WAV generation failed"
    print(f"   [PASS] English Piper synthesized in {en_dur:.2f}s (size: {os.path.getsize(res_en)} bytes)")
    if os.path.exists(tmp_en): os.remove(tmp_en)

    # Bengali Voice
    tmp_bn = tempfile.mktemp(suffix=".wav")
    t0 = time.time()
    res_bn = synthesize_to_wav("আমি যারভিস, আপনার ব্যক্তিগত এআই সহকারী।", tmp_bn)
    bn_dur = time.time() - t0
    assert os.path.exists(res_bn) and os.path.getsize(res_bn) > 0, "Bengali Voice generation failed"
    print(f"   [PASS] Bengali Voice synthesized in {bn_dur:.2f}s (size: {os.path.getsize(res_bn)} bytes)")
    assert bn_dur < 5.0, f"Bengali voice took too long: {bn_dur}s"
    if os.path.exists(tmp_bn): os.remove(tmp_bn)

    # 4. VS Code Extension Parity Verification
    print("\n4. Verifying VS Code Extension v1.3.7:")
    pkg_path = Path("jarvis-vscode-extension/package.json")
    pkg_data = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert pkg_data.get("version") == "1.3.7", f"Expected version 1.3.7, got {pkg_data.get('version')}"
    print(f"   [PASS] Extension version is 1.3.7")

    vsix_path = Path("jarvis-vscode-extension/jarvis-ai-copilot-1.3.7.vsix")
    assert vsix_path.exists(), "VSIX 1.3.7 artifact does not exist"
    print(f"   [PASS] VSIX 1.3.7 artifact exists ({vsix_path.stat().st_size} bytes)")

    print("\n" + "=" * 60)
    print("PART C VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_part_c()

