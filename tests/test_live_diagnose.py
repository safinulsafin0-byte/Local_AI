import urllib.request
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

req = urllib.request.Request(
    'http://127.0.0.1:8765/api/v1/voice/diagnose',
    headers={'Authorization': 'Bearer auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA'}
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("=== LIVE VOICE DOCTOR ENDPOINT RESPONSE ===")
        print(f"Overall status: {data.get('ok')}")
        print(f"Timestamp: {data.get('timestamp')}")
        print(f"Selected device: {data.get('selected_device')}")
        print(f"Default device: {data.get('default_device')}")
        print("------------------------------------------")
        for s in data.get('stages', []):
            print(f"Stage {s['stage']} [{s['status']}] {s['name']} ({s['latency_ms']}ms): {s.get('details', '')}")
            if s.get("reason") and s['status'] != "PASS":
                print(f"   Reason: {s['reason']}")
            if s.get("fix") and s['status'] != "PASS":
                print(f"   Fix: {s['fix']}")
        print("------------------------------------------")
        if data.get("failing_stages"):
            print("FAILING STAGES:", data.get("failing_stages"))
        else:
            print("ALL 10 STAGES PASSED ON LIVE SERVER!")
except Exception as e:
    print(f"Endpoint request failed: {e}")

