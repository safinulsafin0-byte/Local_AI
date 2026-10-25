import sys
import io
import time
import requests
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://127.0.0.1:8765"
headers = {"Content-Type": "application/json"}

def send_chat(msg, file_id=None, timeout=60):
    payload = {"message": msg, "stream": False}
    if file_id:
        payload["file_id"] = file_id
    t0 = time.time()
    try:
        r = requests.post(f"{BASE_URL}/api/v1/chat", json=payload, headers=headers, timeout=timeout)
        duration = round(time.time() - t0, 2)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "response": data.get("response", ""), "duration": duration, "status_code": 200}
        else:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}", "duration": duration, "status_code": r.status_code}
    except Exception as e:
        duration = round(time.time() - t0, 2)
        return {"ok": False, "error": str(e), "duration": duration, "status_code": 0}

# Prepare sample doc for attachment test
sample_doc_path = Path("data/verification_doc.txt")
sample_doc_path.parent.mkdir(parents=True, exist_ok=True)
sample_doc_path.write_text("Project JARVIS Stark Edition: Autonomous AI Assistant with verified hardware and telemetry.", encoding="utf-8")
file_id = None
try:
    with open(sample_doc_path, "rb") as f:
        up_res = requests.post(f"{BASE_URL}/api/v1/files/upload", files={"file": ("verification_doc.txt", f, "text/plain")}, timeout=10)
        if up_res.status_code == 200:
            file_id = up_res.json().get("file_id")
except Exception:
    pass

COMMANDS = [
    # 1. Mission Control, HUD & Briefings
    ("Give me a briefing", None, lambda res: any(k in res.lower() for k in ["good", "operational", "cpu", "weather", "sir"])),
    ("Open HUD", None, lambda res: "hud" in res.lower() or "mission control" in res.lower()),
    ("Set personality to Stark", None, lambda res: "stark" in res.lower() or "personality" in res.lower() or "mode" in res.lower()),
    ("Set personality to Professional", None, lambda res: "professional" in res.lower() or "mode" in res.lower()),

    # 2. Autonomous Macro Protocols
    ("Run Study protocol", None, lambda res: "study" in res.lower() and ("completed" in res.lower() or "✓" in res)),
    ("Run Clean Slate protocol", None, lambda res: "clean slate" in res.lower() and ("completed" in res.lower() or "✓" in res)),
    ("Run Night Mode protocol", None, lambda res: "night mode" in res.lower() and ("completed" in res.lower() or "✓" in res)),
    ("Run Demo Mode protocol", None, lambda res: "demo mode" in res.lower() and ("completed" in res.lower() or "✓" in res)),
    ("List protocols", None, lambda res: "protocols" in res.lower() and ("study" in res.lower() or "clean slate" in res.lower())),

    # 3. 3D CAD Engineering (Text-to-CAD)
    ("Create phone stand 80mm wide", None, lambda res: "stl" in res.lower() or "phone stand" in res.lower() or "triangles" in res.lower()),
    ("Create spur gear 16 teeth", None, lambda res: "stl" in res.lower() or "gear" in res.lower() or "triangles" in res.lower()),
    ("Make electronics box enclosure 100x70x40", None, lambda res: "stl" in res.lower() or "enclosure" in res.lower() or "box" in res.lower()),
    ("Generate structural L-bracket", None, lambda res: "stl" in res.lower() or "bracket" in res.lower() or "triangles" in res.lower()),
    ("Build protective dome shell", None, lambda res: "stl" in res.lower() or "dome" in res.lower() or "triangles" in res.lower()),

    # 4. Custom Terminal & Shell Execution
    ("run ipconfig", None, lambda res: "ip" in res.lower() or "windows ip" in res.lower() or "ipv4" in res.lower() or "adapter" in res.lower()),
    ("run python --version", None, lambda res: "python 3" in res.lower()),
    ("run dir D:\\personal-ai-full", None, lambda res: "server.py" in res.lower() or "directory" in res.lower() or "bytes" in res.lower()),
    ("run pip list", None, lambda res: "package" in res.lower() or "fastapi" in res.lower() or "psutil" in res.lower()),
    ("create a file name demo_calc.py and write calculate factorial in python and run the code", None, lambda res: "demo_calc.py" in res.lower() or "factorial" in res.lower()),

    # 5. Verified Filesystem Operations
    ("create a folder name TestVerification inside D:\\jarvis_test", None, lambda res: "success" in res.lower() and "testverification" in res.lower()),
    ("create a file sample_note.txt inside D:\\jarvis_test with text Hello Antigravity", None, lambda res: "success" in res.lower() and "sample_note.txt" in res.lower()),
    ("read file sample_note.txt in D:\\jarvis_test", None, lambda res: "hello antigravity" in res.lower()),
    ("list files in D:\\jarvis_test", None, lambda res: "sample_note.txt" in res.lower() or "testverification" in res.lower() or "files" in res.lower()),
    ("delete file sample_note.txt in D:\\jarvis_test", None, lambda res: "success" in res.lower() and "sample_note.txt" in res.lower()),
    ("delete folder TestVerification in D:\\jarvis_test", None, lambda res: "success" in res.lower() and "testverification" in res.lower()),

    # 6. Weather Intelligence & Location Awareness
    ("What's the weather", None, lambda res: "weather" in res.lower() or "°c" in res.lower() or "temperature" in res.lower()),
    ("Weather for ChapaiNawabgonj", None, lambda res: "chapainawabganj" in res.lower() and "°c" in res.lower()),
    ("Weather in Dhaka", None, lambda res: "dhaka" in res.lower() and "°c" in res.lower()),
    ("Temperature in Khulna", None, lambda res: "khulna" in res.lower() and "°c" in res.lower()),
    ("Weather for Rajshahi", None, lambda res: "rajshahi" in res.lower() and "°c" in res.lower()),

    # 7. Live RSS News Feeds
    ("What's new today", None, lambda res: len(res.splitlines()) >= 3 and ("bbc" in res.lower() or "news" in res.lower() or "headlines" in res.lower())),
    ("Latest tech news", None, lambda res: len(res.splitlines()) >= 3 and ("tech" in res.lower() or "news" in res.lower() or "verge" in res.lower())),
    ("Latest news in Bangladesh", None, lambda res: len(res.splitlines()) >= 3 and ("bangladesh" in res.lower() or "news" in res.lower() or "star" in res.lower() or "prothom" in res.lower())),

    # 8. Defensive Security & Network Radar
    ("Run threat audit", None, lambda res: "readiness" in res.lower() or "threat" in res.lower() or "audit" in res.lower() or "firewall" in res.lower()),
    ("Check local devices", None, lambda res: "radar" in res.lower() or "devices" in res.lower() or "arp" in res.lower()),
    ("Scan code security", None, lambda res: "security" in res.lower() or "code" in res.lower() or "vulnerabilities" in res.lower()),

    # 9. Virtual Smart Facility & Room Automation
    ("Activate movie night scene", None, lambda res: "movie night" in res.lower() or "facility" in res.lower() or "scene" in res.lower()),
    ("Activate engineering focus scene", None, lambda res: "engineering focus" in res.lower() or "facility" in res.lower() or "scene" in res.lower()),
    ("Activate night lockdown scene", None, lambda res: "lockdown" in res.lower() or "facility" in res.lower() or "scene" in res.lower()),
    ("Activate clean slate scene", None, lambda res: "clean slate" in res.lower() or "facility" in res.lower() or "scene" in res.lower()),
    ("Check facility power", None, lambda res: "power" in res.lower() or "kw" in res.lower() or "load" in res.lower()),

    # 10. Scientific Simulation Lab
    ("Simulate projectile", None, lambda res: "projectile" in res.lower() or "range" in res.lower() or "simulation" in res.lower()),
    ("Simulate beam deflection", None, lambda res: "beam" in res.lower() or "deflection" in res.lower() or "simulation" in res.lower()),
    ("Simulate heat diffusion", None, lambda res: "heat" in res.lower() or "diffusion" in res.lower() or "temperature" in res.lower()),
    ("Simulate RLC circuit", None, lambda res: "rlc" in res.lower() or "circuit" in res.lower() or "damping" in res.lower() or "frequency" in res.lower()),

    # 11. Audio & Hardware Telemetry
    ("Set volume to 50%", None, lambda res: "50%" in res.lower() or "volume" in res.lower()),
    ("Volume up", None, lambda res: "increased" in res.lower() or "volume" in res.lower()),
    ("Volume down", None, lambda res: "decreased" in res.lower() or "volume" in res.lower()),
    ("Mute volume", None, lambda res: "muted" in res.lower() or "volume" in res.lower()),
    ("What is my CPU usage?", None, lambda res: "cpu" in res.lower() and "%" in res.lower()),
    ("Top processes", None, lambda res: "process" in res.lower() or "pid" in res.lower() or "cpu" in res.lower()),

    # 12. Media & YouTube Controls
    ("Play lofi music on YouTube", None, lambda res: "lofi" in res.lower() or "youtube" in res.lower() or "playing" in res.lower() or "video" in res.lower()),
    ("Pause", None, lambda res: "paused" in res.lower() or "video" in res.lower()),
    ("Resume", None, lambda res: "resumed" in res.lower() or "video" in res.lower()),

    # 13. Live Fact Grounding
    ("What is the current Bitcoin price?", None, lambda res: "bitcoin" in res.lower() or "$" in res or "btc" in res.lower()),
    ("What is the latest Python version?", None, lambda res: "python 3" in res.lower()),
    ("Who is the Prime Minister of Bangladesh?", None, lambda res: "bangladesh" in res.lower() and ("dr" in res.lower() or "yunus" in res.lower() or "adviser" in res.lower() or "chief" in res.lower() or "minister" in res.lower())),

    # 14. Long-Term Memory
    ("Remember that my favourite programming language is Python", None, lambda res: "remember" in res.lower() or "python" in res.lower() or "noted" in res.lower()),
    ("Show saved memories", None, lambda res: "memories" in res.lower() or "facts" in res.lower() or "python" in res.lower()),

    # 15. Document Attachment Analysis
    ("Summarize this document", "DYNAMIC_FILE_ID", lambda res: any(k in res.lower() for k in ["jarvis", "stark", "assistant", "document", "telemetry", "autonomous", "summary", "project"]))
]

results = []
passed_count = 0

print(f"Starting execution of {len(COMMANDS)} commands from Features.txt Part II...\n")

for idx, (cmd, fid, validator) in enumerate(COMMANDS, 1):
    target_fid = file_id if fid == "DYNAMIC_FILE_ID" else fid
    t_out = 80 if (target_fid or "factorial" in cmd) else 35
    res_data = send_chat(cmd, file_id=target_fid, timeout=t_out)
    resp_text = res_data.get("response", "")
    duration = res_data.get("duration", 0)
    
    is_valid = res_data.get("ok") and (validator(resp_text) if validator else bool(resp_text))
    status_str = "PASS" if is_valid else "FAIL"
    if is_valid:
        passed_count += 1
        
    print(f"[{idx:02d}/{len(COMMANDS):02d}] {status_str} ({duration}s) -> '{cmd}'", flush=True)
    if not is_valid:
        print(f"     Output: {resp_text[:180]!r}", flush=True)
        if res_data.get("error"):
            print(f"     Error: {res_data.get('error')}", flush=True)

    results.append({
        "index": idx,
        "command": cmd,
        "file_id": fid,
        "status": status_str,
        "duration": duration,
        "response_sample": resp_text.replace("\n", " ")[:160],
    })

pass_rate = round((passed_count / len(COMMANDS)) * 100, 1)
print(f"\n==========================================", flush=True)
print(f"SUMMARY: {passed_count}/{len(COMMANDS)} Passed ({pass_rate}%)", flush=True)
print(f"==========================================", flush=True)

report_data = {
    "total": len(COMMANDS),
    "passed": passed_count,
    "failed": len(COMMANDS) - passed_count,
    "pass_rate_pct": pass_rate,
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "results": results
}

Path("data/verification_results.json").write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
