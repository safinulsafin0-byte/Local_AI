"""
tests/test_pc_control.py — Test PC Control, Confirmation Countdown, and Cancellation
"""

import sys
import time
from pathlib import Path

# Ensure root dir in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from intent.engine import get_intent_engine
from tools.pc_actions import (
    DESTRUCTIVE_ACTIONS,
    schedule_destructive_action,
    cancel_pending_action,
    confirm_pending_action,
    execute_immediate_action,
)


def test_pc_control_intents():
    print("Testing PC control intent classification...")
    engine = get_intent_engine()

    cases = [
        ("mute volume", "system_control", "volume_mute"),
        ("volume up", "system_control", "volume_up"),
        ("volume down", "system_control", "volume_down"),
        ("take a screenshot", "system_control", "screenshot"),
        ("lock the pc", "system_control", "lock"),
        ("empty the recycle bin", "system_control", "empty_recycle_bin"),
        ("shut down the computer", "system_control", "shutdown"),
        ("restart my pc", "system_control", "restart"),
        ("put pc to sleep", "system_control", "sleep"),
        ("cancel", "cancel", None),
        ("abort", "cancel", None),
        ("cancel action", "cancel", None),
    ]

    passed = 0
    for query, expected_intent, expected_action in cases:
        res = engine.classify(query)
        act = res.parameters.get("action")
        assert res.intent == expected_intent, f"Query '{query}': expected intent {expected_intent}, got {res.intent}"
        if expected_action:
            assert act == expected_action, f"Query '{query}': expected action {expected_action}, got {act}"
        passed += 1
        print(f"  [PASS] '{query}' -> intent={res.intent}, action={act}")

    print(f"All {passed}/{len(cases)} intent checks passed.\n")


def test_immediate_actions():
    print("Testing immediate actions...")

    # 1. Volume actions
    res = execute_immediate_action("volume_up", {"value": 2})
    assert res.get("ok") is True, f"volume_up failed: {res}"
    print(f"  [PASS] volume_up: {res.get('message')}")

    res = execute_immediate_action("volume_down", {"value": 2})
    assert res.get("ok") is True, f"volume_down failed: {res}"
    print(f"  [PASS] volume_down: {res.get('message')}")

    # 2. Screenshot
    res = execute_immediate_action("screenshot")
    assert res.get("ok") is True, f"screenshot failed: {res}"
    assert "url" in res and res["url"].startswith("/data/screenshots/"), f"Invalid screenshot url: {res}"
    assert Path(res["path"]).exists(), f"Screenshot file not found at {res['path']}"
    print(f"  [PASS] screenshot captured: {res.get('url')} ({Path(res['path']).stat().st_size} bytes)")

    print("All immediate action checks passed.\n")


def test_destructive_countdown_and_cancellation():
    print("Testing 10s countdown scheduling & cancellation...")

    # Schedule shutdown with 10s countdown
    sched = schedule_destructive_action("shutdown", countdown_sec=10)
    assert sched.get("ok") is True, f"Scheduling failed: {sched}"
    assert sched.get("action") == "shutdown"
    action_id = sched.get("action_id")
    assert action_id is not None
    assert "Say cancel to abort" in sched.get("speech", "")
    print(f"  [PASS] Scheduled action {action_id}: {sched.get('label')}")

    # Verify cancel_pending_action cancels it
    cancelled = cancel_pending_action(action_id)
    assert cancelled is True, "cancel_pending_action returned False for active action"
    print(f"  [PASS] Successfully cancelled pending action {action_id}")

    # Verify cancelling again returns False (idempotent / clean state)
    cancelled_again = cancel_pending_action(action_id)
    assert cancelled_again is False, "cancel_pending_action returned True when nothing was pending"
    print("  [PASS] Second cancellation correctly returned False")

    print("All destructive countdown & cancellation checks passed.\n")


if __name__ == "__main__":
    test_pc_control_intents()
    test_immediate_actions()
    test_destructive_countdown_and_cancellation()
    print("========================================")
    print("ALL PC CONTROL TESTS PASSED (Package 6)")
    print("========================================")
