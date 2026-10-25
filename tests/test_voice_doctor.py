import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.diagnose import run_voice_diagnose

if __name__ == "__main__":
    res = run_voice_diagnose()
    print("=== VOICE DOCTOR RESULTS ===")
    print(f"Overall status: {res.get('ok')}")
    print(f"Timestamp: {res.get('timestamp')}")
    print(f"Selected device: {res.get('selected_device')}")
    print(f"Default device: {res.get('default_device')}")
    print("------------------------------------------")
    for s in res.get("stages", []):
        print(f"Stage {s['stage']} [{s['status']}] {s['name']} ({s['latency_ms']}ms): {s.get('details', '')}")
        if s.get("reason") and s["status"] != "PASS":
            print(f"   Reason: {s['reason']}")
        if s.get("fix") and s["status"] != "PASS":
            print(f"   Fix: {s['fix']}")
    print("------------------------------------------")
    if res.get("failing_stages"):
        print("FAILING STAGES:", res.get("failing_stages"))
    else:
        print("ALL STAGES PASSED!")
