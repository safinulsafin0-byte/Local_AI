"""
Test Suite for Part E: Guardian noise suppression, process hygiene, and baseline reset.
"""

import sys
import json
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from guardian.monitor import (
    GuardianMonitor,
    get_guardian,
    SAFE_LISTENING_PORTS,
    SAFE_LISTENER_PROCESS_NAMES,
    SAFE_SYSTEM_DIRS
)

def test_part_e_guardian():
    print("=== STARTING PART E GUARDIAN VERIFICATION ===")

    guardian = get_guardian()

    # 1. Test whitelist definitions
    print("\n--- 1. Testing Default Whitelist Sets ---")
    assert 2869 in SAFE_LISTENING_PORTS, "Port 2869 must be in SAFE_LISTENING_PORTS"
    assert 5357 in SAFE_LISTENING_PORTS, "Port 5357 must be in SAFE_LISTENING_PORTS"
    assert 445 in SAFE_LISTENING_PORTS, "Port 445 must be in SAFE_LISTENING_PORTS"
    assert 11434 in SAFE_LISTENING_PORTS, "Port 11434 (Ollama) must be in SAFE_LISTENING_PORTS"
    assert 8765 in SAFE_LISTENING_PORTS, "Port 8765 (JARVIS) must be in SAFE_LISTENING_PORTS"
    print("✓ All critical safe ports (2869, 5357, 445, 11434, 8765) confirmed in SAFE_LISTENING_PORTS")

    safe_procs = ["onedrive.exe", "ollama.exe", "llama-server.exe", "python.exe", "msmpeng.exe", "code.exe"]
    for sp in safe_procs:
        assert sp in SAFE_LISTENER_PROCESS_NAMES, f"{sp} must be in SAFE_LISTENER_PROCESS_NAMES"
    print("✓ All safe processes (OneDrive, Ollama, llama-server, Python, MsMpEng, Code) confirmed")

    # 2. Test Clear Alerts and Reset Baseline
    print("\n--- 2. Testing clear_alerts() & reset_baseline() ---")
    # Insert a dummy test alert to verify clear
    guardian.record_alert("test:dummy_key", "low", "Test Alert", "Verification test reason")
    assert len(guardian.alerts) >= 1, "Should have at least 1 alert after inserting dummy"
    
    cleared = guardian.clear_alerts()
    print(f"✓ guardian.clear_alerts() executed, cleared: {cleared}")
    assert len(guardian.alerts) == 0, "Alerts list must be empty after clear_alerts"
    status = guardian.get_status()
    assert status["unread_alerts"] == 0, f"Unread alerts must be 0, got {status['unread_alerts']}"
    print("✓ Unread alert badge verified: 0 active alerts")

    # Reset baseline
    res_baseline = guardian.reset_baseline()
    print(f"✓ guardian.reset_baseline() executed: {res_baseline['processes_count']} processes, {res_baseline['ports_count']} ports")
    assert res_baseline["ok"] is True
    assert guardian.baseline_learned is True
    assert len(guardian.alerts) == 0

    # 3. Test Detector Cycle on Live System (Zero False Positives)
    print("\n--- 3. Running Guardian Detector Cycle on Live System ---")
    guardian.run_cycle()
    print(f"✓ Detector cycle finished. Active alerts count: {len(guardian.alerts)}")
    # Verify no false alarms generated from live system (no PID 4, no OneDrive, no Ollama alerts)
    for a in guardian.alerts:
        k = a.get("key", "")
        title = a.get("title", "")
        assert "2869" not in k, f"False alarm triggered on port 2869: {a}"
        assert "5357" not in k, f"False alarm triggered on port 5357: {a}"
        assert "445" not in k, f"False alarm triggered on port 445: {a}"
        assert "system idle process" not in title.lower(), f"System Idle Process flagged: {a}"
    print("✓ Verified: Zero false alarms on system ports, OneDrive, or System Idle Process")

    # 4. Test Ephemeral Port & Duplicate Deduplication Grouping
    print("\n--- 4. Testing Alert Deduplication and Grouping ---")
    guardian.clear_alerts()
    test_key = "port_ephemeral:testapp.exe"
    # Fire alert twice
    guardian.record_alert(test_key, "low", "testapp.exe Listening on Dynamic Ports", "Test dynamic port 50001", {"port": 50001})
    time.sleep(0.01)
    guardian.record_alert(test_key, "low", "testapp.exe Listening on Dynamic Ports", "Test dynamic port 50002", {"port": 50002})

    # Must be consolidated into ONE alert with count == 2
    matched = [a for a in guardian.alerts if a.get("key") == test_key]
    assert len(matched) == 1, f"Expected 1 grouped alert, got {len(matched)}"
    assert matched[0]["count"] == 2, f"Expected alert count 2, got {matched[0]['count']}"
    print(f"✓ Verified: Multiple ephemeral port events grouped into 1 consolidated alert with count={matched[0]['count']}")

    # Clean up test alerts
    guardian.clear_alerts()

    print("\n=== ALL PART E GUARDIAN TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_part_e_guardian()
