"""
Test Suite: Full Laptop Access, Windows CMD Navigation, and Bare Command Execution
"""

import sys
import json
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8765"
TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def parse_sse_events(response):
    events = []
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except Exception:
                    pass
    return events

def run_term(command, cwd=None):
    payload = {"command": command}
    if cwd:
        payload["cwd"] = cwd
    r = requests.post(f"{BASE_URL}/api/v1/terminal/run", headers=HEADERS, json=payload, timeout=20)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    return r.json()

def test_1_directory_navigation():
    print("\n--- TEST 1: Windows CMD-Style Directory Navigation (cd, drive switch, cwd tracking) ---")
    
    # 1. Start at D:\personal-ai-full
    start = run_term("cd", "D:\\personal-ai-full")
    print("Initial cwd check:", start.get("output"))
    assert start.get("output") == "D:\\personal-ai-full"

    # 2. cd C:\
    res_cd = run_term("cd C:\\", "D:\\personal-ai-full")
    print("cd C:\\ result:", res_cd)
    assert res_cd.get("ok") is True
    assert res_cd.get("cwd") == "C:\\"

    # 3. dir in C:\
    res_dir = run_term("dir", res_cd.get("cwd"))
    print("dir in C:\\ lines:", len(res_dir.get("output", "").splitlines()))
    assert "Windows" in res_dir.get("output", "") or "Program Files" in res_dir.get("output", "")
    assert res_cd.get("cwd") == "C:\\"

    # 4. cd Users
    res_users = run_term("cd Users", res_cd.get("cwd"))
    print("cd Users cwd:", res_users.get("cwd"))
    assert "C:\\Users" in res_users.get("cwd")

    # 5. cd ..
    res_up = run_term("cd ..", res_users.get("cwd"))
    print("cd .. cwd:", res_up.get("cwd"))
    assert res_up.get("cwd") == "C:\\"

    # 6. Drive switch "D:"
    res_drive = run_term("D:", res_up.get("cwd"))
    print("Drive switch D: cwd:", res_drive.get("cwd"))
    assert res_drive.get("cwd") == "D:\\"

    # 7. cls
    res_cls = run_term("cls", "D:\\")
    print("cls response:", res_cls)
    assert res_cls.get("clear") is True

    print("[PASS] TEST 1 PASSED: Directory navigation, drive switching, and cwd tracking verified.")

def test_2_system_commands():
    print("\n--- TEST 2: Running System Commands with Full Access (ipconfig, whoami, python) ---")
    
    # whoami
    r_whoami = run_term("whoami")
    print("whoami output:", r_whoami.get("output"))
    assert "\\" in r_whoami.get("output", "")

    # ipconfig
    r_ip = run_term("ipconfig")
    print("ipconfig output (first 2 lines):", r_ip.get("output", "").splitlines()[:2])
    assert "Windows IP Configuration" in r_ip.get("output", "")

    # python --version
    r_py = run_term("python --version")
    print("python --version output:", r_py.get("output"))
    assert "Python 3." in r_py.get("output", "")

    print("[PASS] TEST 2 PASSED: Full laptop access commands executed successfully.")

def test_3_chat_terminal_integration():
    print("\n--- TEST 3: Chat Integration with Terminal Auto-Open & Live Execution ---")
    
    # Send "run ipconfig" in chat
    r = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={"message": "run ipconfig", "stream": True}, stream=True, timeout=20)
    assert r.status_code == 200
    events = parse_sse_events(r)
    event_types = [e.get("type") for e in events]
    print("Chat 'run ipconfig' events:", event_types)
    assert "terminal_open" in event_types, "terminal_open should be emitted"
    assert "terminal_exec" in event_types, "terminal_exec should be emitted"
    
    exec_event = next(e for e in events if e.get("type") == "terminal_exec")
    assert "Windows IP Configuration" in exec_event.get("output", "")
    print("Terminal Exec Event CWD:", exec_event.get("cwd"))
    assert exec_event.get("cwd") is not None

    # Send bare command "whoami" in chat
    r2 = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={"message": "whoami", "stream": True}, stream=True, timeout=20)
    assert r2.status_code == 200
    events2 = parse_sse_events(r2)
    event_types2 = [e.get("type") for e in events2]
    print("Chat bare 'whoami' events:", event_types2)
    assert "terminal_open" in event_types2
    assert "terminal_exec" in event_types2

    print("[PASS] TEST 3 PASSED: Chat triggers terminal opening and live execution.")

if __name__ == "__main__":
    print("RUNNING FULL LAPTOP ACCESS & CMD SUITE...")
    test_1_directory_navigation()
    test_2_system_commands()
    test_3_chat_terminal_integration()
    print("\n==========================================")
    print("ALL FULL ACCESS TESTS PASSED (3/3)!")
    print("==========================================")

