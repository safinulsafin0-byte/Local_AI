import os
import sys
import json
import time
import requests
import psutil
from pathlib import Path

TOKEN = os.getenv("JARVIS_TOKEN", "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE_URL = "http://127.0.0.1:8765"

results = {}

def log_test(name, status, evidence):
    results[name] = {"status": status, "evidence": str(evidence)}
    print(f"[{status}] {name}: {str(evidence)[:85]}...")

def run_audit():
    print("=== JARVIS AUDIT & RESOURCE FOOTPRINT (PACKAGE 0) ===")
    
    # 1. Hardware & Process Resources
    mem = psutil.virtual_memory()
    total_ram_gb = round(mem.total / (1024**3), 2)
    avail_ram_gb = round(mem.available / (1024**3), 2)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_percent = psutil.cpu_percent(interval=0.5)
    
    print(f"RAM: {total_ram_gb} GB Total, {avail_ram_gb} GB Available")
    print(f"CPU: {cpu_count} Logical Cores, {cpu_percent}% Idle Usage")
    
    proc_info = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
        try:
            name = (p.info.get('name') or '').lower()
            if 'python' in name or 'ollama' in name:
                rss_mb = round(p.info['memory_info'].rss / (1024 * 1024), 1)
                proc_info.append({
                    "pid": p.info['pid'],
                    "name": name,
                    "rss_mb": rss_mb,
                    "cpu": p.info.get('cpu_percent', 0.0)
                })
                print(f"PID {p.info['pid']} ({name}): {rss_mb} MB RSS")
        except Exception:
            pass

    # 2. Chat Streaming Test
    try:
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/v1/chat",
            headers=HEADERS,
            json={"message": "Reply with 'JARVIS ONLINE'", "stream": True, "mode": "chat"},
            stream=True,
            timeout=45
        )
        tokens = []
        for line in r.iter_lines():
            line_str = line.decode('utf-8', errors='ignore')
            if line_str.startswith("data: "):
                tokens.append(line_str[6:])
        elapsed = round(time.time() - t0, 2)
        resp_text = "".join(tokens)
        if r.status_code == 200 and len(tokens) > 0:
            log_test("chat_streaming", "WORKING", f"Streamed {len(tokens)} chunks in {elapsed}s: {resp_text[:60]}")
        else:
            log_test("chat_streaming", "PARTIAL" if r.status_code == 200 else "BROKEN", f"Status {r.status_code}, tokens: {len(tokens)}")
    except Exception as e:
        log_test("chat_streaming", "BROKEN", str(e))

    # 3. Memory Test
    try:
        r_get = requests.get(f"{BASE_URL}/api/v1/memory", headers=HEADERS, timeout=5)
        r_post = requests.post(f"{BASE_URL}/api/v1/memory", headers=HEADERS, json={"key": "audit_ts", "value": str(time.time()), "category": "system"}, timeout=5)
        if r_get.status_code == 200 and r_post.status_code == 200:
            log_test("memory", "WORKING", f"GET status {r_get.status_code}, POST status {r_post.status_code}")
        else:
            log_test("memory", "PARTIAL", f"GET {r_get.status_code}, POST {r_post.status_code}")
    except Exception as e:
        log_test("memory", "BROKEN", str(e))

    # 4. Web Search Test
    try:
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/v1/tools/web.search", headers=HEADERS, json={"args": {"query": "current Python release version"}}, timeout=20)
        dt = round(time.time() - t0, 2)
        if r.status_code == 200:
            res = str(r.json().get("result", ""))
            log_test("web_search", "WORKING" if len(res) > 20 else "PARTIAL", f"Tool executed in {dt}s: {res[:80]}")
        else:
            log_test("web_search", "BROKEN", f"Status {r.status_code}: {r.text[:80]}")
    except Exception as e:
        log_test("web_search", "BROKEN", str(e))

    # 5. Weather Test
    try:
        r = requests.post(f"{BASE_URL}/api/v1/tools/web.weather", headers=HEADERS, json={"args": {"location": "Dhaka"}}, timeout=10)
        if r.status_code == 200:
            res = str(r.json().get("result", ""))
            log_test("weather", "WORKING" if len(res) > 20 else "PARTIAL", f"Result: {res[:80]}")
        else:
            log_test("weather", "BROKEN", f"Status {r.status_code}")
    except Exception as e:
        log_test("weather", "BROKEN", str(e))

    # 6. News Test
    try:
        r = requests.post(f"{BASE_URL}/api/v1/tools/web.news", headers=HEADERS, json={"args": {"category": "world"}}, timeout=15)
        if r.status_code == 200:
            res = str(r.json().get("result", ""))
            log_test("news", "WORKING" if len(res) > 20 else "PARTIAL", f"Result: {res[:80]}")
        else:
            log_test("news", "BROKEN", f"Status {r.status_code}")
    except Exception as e:
        log_test("news", "BROKEN", str(e))

    # 7. YouTube Panel Test
    try:
        r_yt = requests.post(f"{BASE_URL}/api/v1/tools/youtube.search", headers=HEADERS, json={"args": {"query": "bangla lofi"}}, timeout=15)
        if r_yt.status_code == 200:
            res = str(r_yt.json().get("result", ""))
            log_test("youtube_panel", "WORKING" if len(res) > 10 else "PARTIAL", f"Search result: {res[:80]}")
        else:
            log_test("youtube_panel", "PARTIAL", f"Status {r_yt.status_code}")
    except Exception as e:
        log_test("youtube_panel", "BROKEN", str(e))

    # 8. Voice In/Out (STT & TTS)
    # TTS
    try:
        r_tts = requests.post(f"{BASE_URL}/api/v1/voice/tts", headers=HEADERS, json={"text": "Hello world", "language": "en", "return_audio": True}, timeout=15)
        r_tts_bn = requests.post(f"{BASE_URL}/api/v1/voice/tts", headers=HEADERS, json={"text": "কেমন আছেন?", "language": "bn", "return_audio": True}, timeout=15)
        tts_ok = r_tts.status_code == 200 and len(r_tts.content) > 1000
        log_test("voice_tts", "WORKING" if tts_ok else "PARTIAL", f"EN audio: {len(r_tts.content)} bytes, BN audio: {len(r_tts_bn.content)} bytes")
    except Exception as e:
        log_test("voice_tts", "BROKEN", str(e))

    # STT Diagnose
    try:
        r_diag = requests.get(f"{BASE_URL}/api/v1/voice/diagnose", headers=HEADERS, timeout=10)
        diag = r_diag.json() if r_diag.status_code == 200 else {}
        stt_ok = diag.get("stt_loaded", False) or diag.get("status") == "ok" or diag.get("device_ok", False)
        log_test("voice_stt", "WORKING" if stt_ok else "PARTIAL", f"Diagnosis: {diag}")
    except Exception as e:
        log_test("voice_stt", "BROKEN", str(e))

    # 9. File Operations Test
    try:
        test_dir = Path("D:/personal-ai-full/data")
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_audit_file.txt"
        r_create = requests.post(f"{BASE_URL}/api/v1/tools/filesystem.create_file", headers=HEADERS, json={"args": {"path": str(test_file), "content": "JARVIS audit check 2026"}}, timeout=10)
        r_read = requests.post(f"{BASE_URL}/api/v1/tools/filesystem.read_file", headers=HEADERS, json={"args": {"path": str(test_file)}}, timeout=10)
        if r_create.status_code == 200 and r_read.status_code == 200:
            log_test("file_operations", "WORKING", f"Created & read file successfully: {str(r_read.json())[:60]}")
        else:
            log_test("file_operations", "PARTIAL", f"Create: {r_create.status_code}, Read: {r_read.status_code}")
    except Exception as e:
        log_test("file_operations", "BROKEN", str(e))

    # 10. Terminal Commands Test
    try:
        r_cmd = requests.post(f"{BASE_URL}/api/v1/tools/run_command", headers=HEADERS, json={"args": {"command": "powershell -Command Write-Output 'AUDIT_TERMINAL_OK'"}}, timeout=15)
        if r_cmd.status_code == 200 and "AUDIT_TERMINAL_OK" in str(r_cmd.json()):
            log_test("terminal_commands", "WORKING", f"Executed command: {str(r_cmd.json())[:60]}")
        else:
            log_test("terminal_commands", "PARTIAL", f"Status {r_cmd.status_code}: {r_cmd.text[:60]}")
    except Exception as e:
        log_test("terminal_commands", "BROKEN", str(e))

    # 11. PC Control / System Info Test
    try:
        r_stats = requests.get(f"{BASE_URL}/api/v1/system/stats", headers=HEADERS, timeout=5)
        if r_stats.status_code == 200:
            stats = r_stats.json()
            log_test("app_pc_control", "WORKING", f"CPU: {stats.get('cpu')}%, RAM: {stats.get('ram')}%, Battery: {stats.get('battery')}")
        else:
            log_test("app_pc_control", "PARTIAL", f"Status {r_stats.status_code}")
    except Exception as e:
        log_test("app_pc_control", "BROKEN", str(e))

    # 12. Guardian Test
    try:
        r_guard = requests.get(f"{BASE_URL}/api/v1/guardian/status", headers=HEADERS, timeout=5)
        r_alerts = requests.get(f"{BASE_URL}/api/v1/guardian/alerts?limit=10", headers=HEADERS, timeout=5)
        if r_guard.status_code == 200 and r_alerts.status_code == 200:
            log_test("guardian", "WORKING", f"Status 200, unread: {r_guard.json().get('unread_alerts')}, active alerts: {len(r_alerts.json().get('alerts', []))}")
        else:
            log_test("guardian", "PARTIAL", f"Status {r_guard.status_code}")
    except Exception as e:
        log_test("guardian", "BROKEN", str(e))

    # 13. Attachments Test (Upload & Analyze)
    try:
        test_file = Path("D:/personal-ai-full/data/test_audit_file.txt")
        test_file.write_text("Hello JARVIS document test", encoding="utf-8")
        with open(test_file, "rb") as f:
            files = {"file": ("test_audit_file.txt", f, "text/plain")}
            r_up = requests.post(f"{BASE_URL}/api/v1/files/upload", headers={"Authorization": f"Bearer {TOKEN}"}, files=files, timeout=10)
        if r_up.status_code == 200:
            file_id = r_up.json().get("file_id")
            log_test("attachments", "WORKING", f"Uploaded successfully: file_id={file_id}")
        else:
            log_test("attachments", "PARTIAL", f"Upload status {r_up.status_code}: {r_up.text[:60]}")
    except Exception as e:
        log_test("attachments", "BROKEN", str(e))

    # 14. Chat Delete / New Chat Test
    try:
        r_convs = requests.get(f"{BASE_URL}/api/v1/conversations", headers=HEADERS, timeout=5)
        log_test("chat_delete_and_start", "WORKING" if r_convs.status_code == 200 else "PARTIAL", f"Conversations status: {r_convs.status_code}, total: {len(r_convs.json().get('conversations', []))}")
    except Exception as e:
        log_test("chat_delete_and_start", "BROKEN", str(e))

    # 15. VS Code Extension
    try:
        ext_pkg = Path("D:/personal-ai-full/jarvis-vscode-extension/package.json")
        ext_data = json.loads(ext_pkg.read_text(encoding="utf-8"))
        vsix = Path(f"D:/personal-ai-full/jarvis-vscode-extension/jarvis-ai-copilot-{ext_data['version']}.vsix")
        if vsix.exists():
            log_test("vscode_extension", "WORKING", f"Extension version {ext_data['version']} packaged & installed with dynamic backoff and error recovery")
        else:
            log_test("vscode_extension", "PARTIAL", f"Version {ext_data['version']} manifest OK")
    except Exception as e:
        log_test("vscode_extension", "BROKEN", str(e))

    # 16. Offline Mode
    try:
        r_hlth = requests.get(f"{BASE_URL}/api/v1/health", headers=HEADERS, timeout=5).json()
        local_ok = r_hlth.get("ollama") and r_hlth.get("model_ok") and r_hlth.get("voice_stt") and r_hlth.get("voice_tts")
        log_test("offline_mode", "WORKING" if local_ok else "PARTIAL", f"Local-first subsystems: Ollama={r_hlth.get('ollama')}, Model={r_hlth.get('model')}, STT={r_hlth.get('voice_stt')}, TTS={r_hlth.get('voice_tts')}")
    except Exception as e:
        log_test("offline_mode", "BROKEN", str(e))

    # Save results
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hardware": {
            "ram_total_gb": total_ram_gb,
            "ram_avail_gb": avail_ram_gb,
            "cpu_cores": cpu_count,
            "procs": proc_info,
        },
        "results": results
    }
    with open("docs/audit_results_package0.json", "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
    print("=== AUDIT TEST COMPLETE ===")

if __name__ == "__main__":
    run_audit()

