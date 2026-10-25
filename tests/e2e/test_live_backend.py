import sys
import io
import requests
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

headers = {"Content-Type": "application/json"}
BASE_URL = "http://127.0.0.1:8765"

def send_chat(msg):
    try:
        r = requests.post(f"{BASE_URL}/api/v1/chat", json={"message": msg, "stream": False}, headers=headers, timeout=30)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

print("=== 1. Health ===")
h = requests.get(f"{BASE_URL}/api/v1/health", timeout=5).json()
print("Health:", h.get("backend"), "model_ok:", h.get("model_ok"), "model:", h.get("model"))

print("\n=== 2. Weather ChapaiNawabgonj ===")
w1 = send_chat("give me weather information for ChapaiNawabgonj")
print("Reply:", w1.get("response"))

print("\n=== 3. Weather Khulna ===")
w2 = send_chat("weather in Khulna")
print("Reply:", w2.get("response"))

print("\n=== 4. News ===")
n = send_chat("what's new for today?")
print("Reply:\n", n.get("response"))

print("\n=== 5. Briefing ===")
b = send_chat("Give me a briefing")
print("Reply:\n", b.get("response"))

print("\n=== 6. Study Protocol ===")
p1 = send_chat("Run Study protocol")
print("Reply:\n", p1.get("response"))

print("\n=== 7. Night Mode Protocol ===")
p2 = send_chat("Run Night Mode protocol")
print("Reply:\n", p2.get("response"))

print("\n=== 8. Filesystem: Create Folder Demo in D:\\jarvis_test ===")
f1 = send_chat("create a folder name Demo inside D:\\jarvis_test")
print("Reply:", f1.get("response"))

print("\n=== 9. Terminal Command: run python --version ===")
c1 = send_chat("run python --version")
print("Reply:\n", c1.get("response"))

print("\n=== 10. Volume Control: set volume to 40 ===")
v1 = send_chat("set volume to 40")
print("Reply:", v1.get("response"))

print("\n=== 11. Screenshot ===")
s1 = send_chat("take a screenshot")
print("Reply:", s1.get("response"))
