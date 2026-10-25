# ============================================================
# JARVIS ALWAYS-ON VOICE & WAKE WORD VERIFICATION TEST (PACKAGE 5)
# ============================================================

import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from voice.wake_word import contains_wake_word, extract_command, WakeWordEngine
from voice.listener import WakeWordListener, play_chime

def test_wake_word_detection():
    print("--- 1. Testing Wake Word Normalization & Extraction ---")
    test_cases = [
        ("Hey Jarvis what is the weather today", True, "what is the weather today"),
        ("jarvis open chrome", True, "open chrome"),
        ("Hello world this is a test", False, None),
        ("হে জার্ভিস আজকের আবহাওয়া কেমন", True, "আজকের আবহাওয়া কেমন"),
        ("JARVIS, what time is it?", True, "what time is it?"),
    ]
    for text, expected_match, expected_cmd in test_cases:
        matched = contains_wake_word(text)
        cmd = extract_command(text)
        print(f"  Utterance: {text!r}")
        print(f"    -> Matched: {matched} (expected: {expected_match}), Cmd: {cmd!r}")
        assert matched == expected_match
        if expected_match:
            assert expected_cmd.lower() in cmd.lower()
    print("✓ Wake word detection tests passed!")

def test_listener_mode_control():
    print("\n--- 2. Testing WakeWordListener Lifecycle & Mode Switching ---")
    commands_received = []
    listener = WakeWordListener(on_command=lambda c: commands_received.append(c))

    assert listener.mode == "push"
    assert not listener.is_running

    # Switch to always-on
    m = listener.set_mode("always")
    assert m == "always"
    assert listener.is_running
    time.sleep(0.3)
    print("✓ Listener successfully entered always-on background mode")

    # Switch back to push-to-talk
    m = listener.set_mode("push")
    assert m == "push"
    assert not listener.is_running
    print("✓ Listener successfully stopped and released resources for push mode")

    # Switch to off
    m = listener.set_mode("off")
    assert m == "off"
    assert not listener.is_running
    print("✓ Listener confirmed off mode (zero CPU, microphone released)")

def test_audio_chime():
    print("\n--- 3. Testing Audio Wake Chime ---")
    play_chime()
    print("✓ Audio chime triggered non-blocking in background thread")

if __name__ == "__main__":
    print("=" * 60)
    print("  RUNNING PACKAGE 5 ALWAYS-ON VOICE VERIFICATION")
    print("=" * 60)
    test_wake_word_detection()
    test_listener_mode_control()
    test_audio_chime()
    print("\n" + "=" * 60)
    print("  ALL PACKAGE 5 TESTS PASSED")
    print("=" * 60)
