import os
import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN = os.getenv("JARVIS_TOKEN", "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA")
API_URL = "http://127.0.0.1:8765/api/v1"

def test_tts_speak_and_clean():
    print("Testing TTS speak and markdown code summary...")
    b = chr(96) * 3
    text = f"Here is the function:\n{b}python\ndef square(n):\n    return n * n\n{b}\nDone!"
    url = f"{API_URL}/voice/speak"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
    req = urllib.request.Request(url, data=json.dumps({"text": text, "play": False, "return_audio": True}).encode(), headers=headers)
    with urllib.request.urlopen(req) as resp:
        wav_data = resp.read()
    assert len(wav_data) > 1000, f"WAV too small: {len(wav_data)}"
    print(f"  [OK] TTS speech synthesized {len(wav_data)} bytes WAV")
    return wav_data

def test_stt_transcribe(wav_data):
    print("Testing STT transcribe endpoint...")
    url = f"{API_URL}/voice/transcribe"
    headers = {"Content-Type": "audio/wav", "Authorization": f"Bearer {TOKEN}"}
    req = urllib.request.Request(url, data=wav_data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
    assert res.get("ok") is True, f"Failed: {res}"
    assert "text" in res, f"No text in res: {res}"
    print(f"  [OK] STT transcribed: '{res['text']}' (lang: {res.get('language')})")

def test_chat_turn_stream():
    print("Testing /chat SSE stream protocol with turn_id...")
    url = f"{API_URL}/chat"
    turn_id = "turn_test_12345"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "Authorization": f"Bearer {TOKEN}"}
    payload = {"message": "Say hello in 3 words", "mode": "chat", "turn_id": turn_id, "stream": True}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    received_tokens = []
    has_done = False
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            line_str = line.decode().strip()
            if line_str.startswith("data: "):
                data_str = line_str[6:].strip()
                if data_str == "[DONE]":
                    has_done = True
                    break
                try:
                    obj = json.loads(data_str)
                    if obj.get("type") == "token" or "token" in obj:
                        received_tokens.append(obj.get("token") or obj.get("text"))
                    if obj.get("type") == "done":
                        has_done = True
                except Exception:
                    pass
    print(f"  [OK] SSE streamed {len(received_tokens)} tokens, done={has_done}")
    assert len(received_tokens) > 0, "No tokens received"

def test_extension_csp_and_static_files():
    print("Testing VS Code extension CSP & static integrity...")
    ext_js = (BASE_DIR / "jarvis-vscode-extension" / "extension.js").read_text(encoding="utf-8")
    main_js = (BASE_DIR / "jarvis-vscode-extension" / "media" / "main.js").read_text(encoding="utf-8")
    pkg_json = json.loads((BASE_DIR / "jarvis-vscode-extension" / "package.json").read_text(encoding="utf-8"))

    assert pkg_json["version"] == "1.3.1", f"Version is {pkg_json['version']}"
    assert "Content-Security-Policy" in ext_js, "CSP missing in extension.js"
    assert "nonce-" in ext_js, "Nonce missing in CSP"
    assert "media/main.js" in ext_js or "main.js" in ext_js, "main.js not linked"
    assert "<script>" not in ext_js.split("_getHtmlForWebview")[1], "Inline <script> found in _getHtmlForWebview"
    assert "onclick=" not in ext_js.split("_getHtmlForWebview")[1], "Inline onclick found in _getHtmlForWebview"
    assert "acquireVsCodeApi()" in main_js, "acquireVsCodeApi missing in main.js"
    assert "DOMContentLoaded" in main_js, "DOMContentLoaded missing in main.js"
    print("  [OK] Extension version 1.3.1, strict CSP nonce, external main.js verified")

if __name__ == "__main__":
    wav = test_tts_speak_and_clean()
    test_stt_transcribe(wav)
    test_chat_turn_stream()
    test_extension_csp_and_static_files()
    print("\nALL EXTENSION & VOICE INTEGRATION TESTS PASSED!")
