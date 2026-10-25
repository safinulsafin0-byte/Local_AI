"""
Automated verification test for Terminal, Immediate Deletion, Code Creation & Execution, and Voice Output Mute.
"""

import os
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

def test_1_terminal_run():
    print("\n--- TEST 1: Direct /api/v1/terminal/run ---")
    payload = {"command": "python --version", "cwd": "D:\\personal-ai-full"}
    r = requests.post(f"{BASE_URL}/api/v1/terminal/run", headers=HEADERS, json=payload, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    print("Terminal Run Response:", data)
    assert data["ok"] is True
    assert "Python 3." in data["output"]
    assert data["exit_code"] == 0
    print("[PASS] TEST 1 PASSED: Terminal execution works and returns real output.")

def test_2_voice_tts_mute():
    print("\n--- TEST 2: Voice TTS Output Permanently Disabled ---")
    payload = {"text": "Hello JARVIS", "play": True}
    r = requests.post(f"{BASE_URL}/api/v1/voice/speak", headers=HEADERS, json=payload, timeout=5)
    print(f"POST /api/v1/voice/speak status: {r.status_code}")
    assert r.status_code == 204 or (r.ok and "disabled" in r.text.lower())
    print("[PASS] TEST 2 PASSED: Voice output permanently muted (204 No Content).")

def test_3_open_terminal_intent():
    print("\n--- TEST 3: 'open terminal' Intent & SSE Event ---")
    payload = {"message": "open terminal"}
    r = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={**payload, "stream": True}, stream=True, timeout=15)
    assert r.status_code == 200
    events = parse_sse_events(r)
    event_types = [e.get("type") for e in events]
    print("Events received:", event_types)
    assert "terminal_open" in event_types, f"Expected 'terminal_open' in {event_types}"
    print("[PASS] TEST 3 PASSED: 'open terminal' triggered terminal_open event.")

def test_4_create_and_run_code():
    print("\n--- TEST 4: 'create file name demo.py and write binary search in python inside the file and run the code' ---")
    demo_file = Path("D:/jarvis_test/demo.py")
    if demo_file.exists():
        try:
            demo_file.unlink()
        except Exception:
            pass

    payload = {
        "message": "create file name demo.py and write binary search in python inside the file and run the code"
    }
    r = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={**payload, "stream": True}, stream=True, timeout=60)
    assert r.status_code == 200
    events = parse_sse_events(r)
    event_types = [e.get("type") for e in events]
    print("Events received:", event_types)

    assert "terminal_open" in event_types, "terminal_open should be emitted"
    assert "terminal_exec" in event_types, "terminal_exec should be emitted"

    # Verify file was written to disk
    assert demo_file.exists(), f"Expected {demo_file} to exist on disk!"
    file_content = demo_file.read_text(encoding="utf-8")
    print(f"File created on disk ({len(file_content)} chars):")
    print(file_content[:200] + "...")
    assert "binary_search" in file_content.lower() or "def " in file_content

    # Verify terminal_exec event content
    exec_event = next(e for e in events if e.get("type") == "terminal_exec")
    print("Terminal Exec Event:", exec_event)
    assert "output" in exec_event
    print("Terminal Output:", exec_event["output"])
    print("[PASS] TEST 4 PASSED: demo.py created, executed in terminal, and output returned.")

def test_5_immediate_deletion():
    print("\n--- TEST 5: Immediate File & Folder Deletion ---")
    demo_file = Path("D:/jarvis_test/demo.py")
    assert demo_file.exists(), "demo.py should exist before deletion test"

    # Delete demo.py
    payload = {"message": "delete file demo.py"}
    r = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={**payload, "stream": True}, stream=True, timeout=15)
    assert r.status_code == 200
    events = parse_sse_events(r)
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    print("Tool results for delete file:", tool_results)
    assert not demo_file.exists(), "demo.py must be deleted immediately from disk!"
    print("[PASS] File deleted immediately without delay.")

    # Create folder and delete folder
    print("\nTesting folder creation & deletion...")
    r1 = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={"message": "create a folder name Demo inside D:\\jarvis_test", "stream": True}, stream=True, timeout=15)
    parse_sse_events(r1)
    demo_dir = Path("D:/jarvis_test/Demo")
    assert demo_dir.is_dir(), f"Expected {demo_dir} to exist!"
    print(f"Folder exists: {demo_dir.is_dir()}")

    r2 = requests.post(f"{BASE_URL}/api/v1/chat", headers=HEADERS, json={"message": "delete folder Demo in D:\\jarvis_test", "stream": True}, stream=True, timeout=15)
    parse_sse_events(r2)
    assert not demo_dir.exists(), f"Expected {demo_dir} to be deleted!"
    print(f"Folder removed immediately: {not demo_dir.exists()}")
    print("[PASS] TEST 5 PASSED: File and folder deletions execute immediately and successfully.")

if __name__ == "__main__":
    print("RUNNING LIVE JARVIS VERIFICATION SUITE...")
    test_1_terminal_run()
    test_2_voice_tts_mute()
    test_3_open_terminal_intent()
    test_4_create_and_run_code()
    test_5_immediate_deletion()
    print("\n==========================================")
    print("ALL 5 LIVE INTEGRATION TESTS PASSED (5/5)!")
    print("==========================================")
