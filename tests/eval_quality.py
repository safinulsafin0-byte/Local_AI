"""
JARVIS Quality Evaluation Suite — tests/eval_quality.py
=======================================================
All LLM tests fire real HTTP POST /api/v1/chat requests (stream=false).
Tool tests call the tool registry or Python helpers directly.
YouTube tests drive the real Playwright browser.
Extension build test checks the .vsix artifact on disk.

Run with:
    python tests/eval_quality.py

Requires:
    - server.py running on 127.0.0.1:8765
    - BEARER_TOKEN set in .env  (JARVIS_TOKEN key)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── Load bearer token ────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

BASE_URL = "http://127.0.0.1:8765"
TOKEN = os.getenv("JARVIS_TOKEN", "")


# ─── HTTP helper ──────────────────────────────────────────────────────────────

def chat_http(message: str, mode: str = "chat") -> tuple[bool, str]:
    """POST /api/v1/chat with stream=false. Returns (success, response_text)."""
    payload = json.dumps({"message": message, "mode": mode, "stream": False}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/chat",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode())
            if body.get("ok"):
                return True, str(body.get("response", ""))
            return False, str(body.get("error", "unknown error"))
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, f"REQUEST ERROR: {e}"


# ─── Test runner helpers ───────────────────────────────────────────────────────

passed = 0
failed = 0
results: list[dict] = []


def run(test_id: str, category: str, description: str, fn):
    """Execute fn(), check result, print outcome."""
    global passed, failed
    print(f"[{test_id}] ({category}) {description} ... ", end="", flush=True)
    t0 = time.time()
    try:
        ok, detail = fn()
        elapsed = time.time() - t0
        if ok:
            print(f"PASS ({elapsed:.1f}s)")
            passed += 1
            results.append({"id": test_id, "status": "PASS", "elapsed": elapsed, "cat": category, "detail": detail[:120]})
        else:
            print(f"FAIL ({elapsed:.1f}s)")
            print(f"    >> {detail[:160]}")
            failed += 1
            results.append({"id": test_id, "status": "FAIL", "elapsed": elapsed, "cat": category, "detail": detail[:200]})
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"ERROR: {exc}")
        failed += 1
        results.append({"id": test_id, "status": "ERROR", "elapsed": elapsed, "cat": category, "detail": str(exc)})


# ─── Category 1: LLM chat via real /api/v1/chat ──────────────────────────────

def test_chat(msg, check_fn, mode="chat"):
    ok, resp = chat_http(msg, mode=mode)
    if not ok:
        return False, resp
    return check_fn(resp), resp


run("CHAT-01", "Chat/HTTP", "Capital of France", lambda: test_chat(
    "What is the capital of France? Answer in one word.",
    lambda r: "paris" in r.lower()
))

run("CHAT-02", "Chat/HTTP", "2 + 2 = ?", lambda: test_chat(
    "What is 2 + 2? Reply with only the number.",
    lambda r: "4" in r
))

run("CHAT-03", "Chat/HTTP", "Square root of 144", lambda: test_chat(
    "What is the square root of 144? Reply with only the number.",
    lambda r: "12" in r
))

run("CHAT-04", "Chat/HTTP", "Speed of light km/s", lambda: test_chat(
    "What is the approximate speed of light in km/s? Give a number.",
    lambda r: "300" in r or "299" in r
))

run("CHAT-05", "Chat/HTTP", "Python generator keyword", lambda: test_chat(
    "What Python keyword creates a generator? One word only.",
    lambda r: "yield" in r.lower()
))

run("CHAT-06", "Chat/HTTP", "Author of Romeo and Juliet", lambda: test_chat(
    "Who wrote Romeo and Juliet? Answer in one or two words.",
    lambda r: "shakespeare" in r.lower()
))

run("CHAT-07", "Chat/HTTP", "Binary search time complexity", lambda: test_chat(
    "What is the time complexity of binary search? Give the Big-O notation.",
    lambda r: "log" in r.lower()
))

run("CHAT-08", "Chat/HTTP", "Palindrome Python code", lambda: test_chat(
    "Write a Python function to check if a string is a palindrome. Just show the code.",
    lambda r: "def " in r and ("[::-1]" in r or "reversed" in r.lower())
))


# ─── Category 2: Agent mode – uses tools through /api/v1/chat ────────────────

run("AGENT-01", "Agent/HTTP", "What is using my CPU (agent)", lambda: test_chat(
    "What is using my CPU right now? List the top processes.",
    lambda r: any(w in r.lower() for w in ["cpu", "process", "percent", "%", "memory"]),
    # mode="agent" would trigger tool calls
))

run("AGENT-02", "Agent/HTTP", "Create file on Desktop", lambda: (lambda ok, resp: (
    ok and any(w in resp.lower() for w in ["creat", "success", "desktop", "file", "tool"]),
    resp
))(*chat_http(
    "Create a text file called jarvis_test.txt on my Desktop with the content 'JARVIS test file'.",
    mode="agent"
)))

run("AGENT-03", "Agent/HTTP", "System status in agent mode", lambda: test_chat(
    "What is my current CPU and RAM usage? Use system tools to check.",
    lambda r: any(w in r.lower() for w in ["cpu", "ram", "memory", "gb", "%", "percent"]),
    mode="agent"
))


# ─── Category 3: YouTube (direct tool calls, no HTTP) ─────────────────────────

def yt_test(fn_name, *args):
    """Import and call a youtube_tools function, return (ok, output)."""
    from tools.youtube_tools import (
        youtube_search, youtube_play, youtube_pause,
        youtube_seek, youtube_summarize
    )
    fn = {"youtube_search": youtube_search, "youtube_play": youtube_play,
          "youtube_pause": youtube_pause, "youtube_seek": youtube_seek,
          "youtube_summarize": youtube_summarize}[fn_name]
    result = fn(*args)
    return isinstance(result, str) and "ERROR" not in result, result


run("YT-01", "YouTube", "youtube_search('lofi music')", lambda: yt_test("youtube_search", "lofi music"))
run("YT-02", "YouTube", "youtube_play first result", lambda: yt_test("youtube_play", "lofi music chill"))
run("YT-03", "YouTube", "youtube_pause", lambda: yt_test("youtube_pause"))
run("YT-04", "YouTube", "youtube_seek +30 seconds", lambda: yt_test("youtube_seek", 30))
run("YT-05", "YouTube", "youtube_seek -10 seconds", lambda: yt_test("youtube_seek", -10))
run("YT-06", "YouTube", "youtube_summarize (short video)", lambda: (lambda ok, r: (ok, r))(*yt_test(
    "youtube_summarize",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"   # well-known short video
)))


# ─── Category 4: Web search tools (direct) ───────────────────────────────────

def web_test(fn_name, *args):
    from tools.web_tools import web_search, weather
    fn = {"web_search": web_search, "weather": weather}[fn_name]
    result = fn(*args)
    return isinstance(result, str) and len(result) > 30, result


run("WEB-01", "Web", "web_search Python release", lambda: web_test("web_search", "Python latest stable release"))
run("WEB-02", "Web", "weather London", lambda: web_test("weather", "London"))


# ─── Category 5: PC control tools (direct) ───────────────────────────────────

def pc_test(fn_name, *args):
    from tools import file_ops, system_ops
    fn = {
        "create_file": file_ops.create_file,
        "read_file": file_ops.read_file,
        "delete_file": file_ops.delete_file,
        "system_status": system_ops.system_status,
        "clipboard_get": system_ops.clipboard_get,
        "clipboard_set": system_ops.clipboard_set,
    }[fn_name]
    result = fn(*args)
    return isinstance(result, str) and "ERROR" not in result, result


run("PC-01", "PC", "create test file", lambda: pc_test("create_file", "jarvis_eval.tmp", "eval123"))
run("PC-02", "PC", "read test file", lambda: (lambda ok, r: ("eval123" in r, r))(*pc_test("read_file", "jarvis_eval.tmp")))
run("PC-03", "PC", "delete test file", lambda: pc_test("delete_file", "jarvis_eval.tmp"))
run("PC-04", "PC", "system_status (cpu/ram)", lambda: (lambda ok, r: (
    "cpu" in r.lower() and ("ram" in r.lower() or "memory" in r.lower()), r
))(*pc_test("system_status")))

run("PC-05", "PC", "clipboard set/get", lambda: (
    pc_test("clipboard_set", "jarvis_eval_test"),
    (lambda ok, r: ("jarvis_eval_test" in r, r))(*pc_test("clipboard_get"))
)[1])


# ─── Category 6: VS Code extension build artifact ────────────────────────────

def ext_activation_test():
    vsixes = sorted((ROOT / "jarvis-vscode-extension").glob("*.vsix"))
    if not vsixes:
        return False, "No VSIX found in jarvis-vscode-extension"
    vsix = vsixes[-1]
    size_kb = vsix.stat().st_size // 1024
    if size_kb < 500:
        return False, f"VSIX too small: {size_kb} KB"
    # Check extension.js is inside the zip
    with zipfile.ZipFile(vsix, "r") as z:
        names = z.namelist()
    has_ext = any("extension.js" in n for n in names)
    if not has_ext:
        return False, "extension.js not found in VSIX"
    return True, f"VSIX OK: {size_kb} KB, extension.js present"


def ext_syntax_test():
    import subprocess
    ext_js = ROOT / "jarvis-vscode-extension" / "extension.js"
    if not ext_js.exists():
        return False, "extension.js not found"
    r = subprocess.run(["node", "--check", str(ext_js)], capture_output=True, text=True)
    if r.returncode == 0:
        return True, "node --check: syntax OK"
    return False, r.stderr[:200]


run("EXT-01", "Extension", "VSIX exists and contains extension.js", ext_activation_test)
run("EXT-02", "Extension", "extension.js passes node --check", ext_syntax_test)
run("EXT-03", "Extension", "package.json has @jarvis chat participant", lambda: (
    lambda: (
        lambda pkg: (
            any(p.get("id") == "jarvis.chatParticipant" for p in pkg.get("contributes", {}).get("chatParticipants", [])),
            f"participants: {[p['id'] for p in pkg.get('contributes', {}).get('chatParticipants', [])]}"
        )
    )(json.loads((ROOT / "jarvis-vscode-extension" / "package.json").read_text(encoding="utf-8")))
)())


# ─── Category 7: Health endpoint ──────────────────────────────────────────────

def health_test():
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/health",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    checks = ["ok", "ollama", "model_ok", "rag", "memory", "voice_stt", "voice_tts", "vision"]
    missing = [k for k in checks if not body.get(k)]
    if missing:
        return False, f"Missing/false: {missing}  Full: {json.dumps(body)}"
    return True, json.dumps(body)


run("HEALTH-01", "Health", "/api/v1/health all green", health_test)


# ─── Summary ──────────────────────────────────────────────────────────────────

total = passed + failed
pass_rate = (passed / total * 100) if total else 0

print("\n" + "=" * 70)
print(f"  JARVIS EVALUATION SUITE — {passed}/{total} PASSED ({pass_rate:.1f}%)")
if failed == 0:
    print("  STATUS: ALL TESTS PASSED")
else:
    print(f"  FAILED: {failed} test(s)")
print("=" * 70)

# Print per-test table
print("\nDetailed Results:")
print(f"{'ID':<12} {'Status':<8} {'Time':>6}  {'Category':<15}  Detail")
print("-" * 70)
for r in results:
    status = r["status"]
    print(f"{r['id']:<12} {status:<8} {r.get('elapsed', 0):>5.1f}s  {r['cat']:<15}  {r.get('detail','')[:60]}")

sys.exit(0 if failed == 0 else 1)
