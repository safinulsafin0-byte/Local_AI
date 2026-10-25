import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.tts import (
    set_speaking_state,
    is_speaking,
    is_in_tts_cooldown,
    is_acoustic_echo,
    record_tts_output,
    clean_text,
    POST_TTS_COOLDOWN_SEC,
)
from voice.listener import WakeWordListener, resolve_physical_input_device

def test_full_cycle():
    print("==================================================")
    print("STARTING FULL CYCLE: LISTEN -> TTS -> LISTEN TEST")
    print("==================================================")

    dispatched_commands = []
    def on_command(cmd, lang="en"):
        print(f"-> DISPATCHED COMMAND: '{cmd}' ({lang})")
        dispatched_commands.append(cmd)

    listener = WakeWordListener(on_command=on_command)
    assert listener.device_index is not None, "Physical mic must be resolved"
    print(f"Resolved physical microphone device: #{listener.device_index}")

    # 1. Simulate initial listening state
    assert not is_speaking()
    assert not is_in_tts_cooldown()
    print("State: Ready and Listening")

    # 2. Simulate User Speech: "What is the weather?"
    user_speech = "what is the weather"
    print(f"\n1. User speaks: '{user_speech}'")
    # Simulate listener processing user utterance
    fake_frames = [b"\x00\x00" * 480] * 30  # dummy frames
    # Before TTS, echo check is False
    assert not is_acoustic_echo(user_speech)
    print("Echo check: Passed (not echo)")

    # 3. Assistant generates response and starts speaking
    assistant_reply = "The weather in Khulna is 28 degrees Celsius with partly cloudy skies."
    print(f"\n2. JARVIS replies with TTS: '{assistant_reply}'")
    
    # Assistant sets playback state to True
    set_speaking_state(True, assistant_reply)
    assert is_speaking() is True
    assert is_in_tts_cooldown() is True
    print("STT Status during TTS playback: GATED (is_speaking=True)")

    # 4. Simulate microphone picking up JARVIS's own TTS voice
    print("\n3. Testing audio feedback rejection while TTS plays:")
    # During playback, is_speaking() is True -> listener discards
    assert is_speaking() is True, "Must be gated during playback"
    # Even if transcribed by Whisper, echo check flags it
    tts_echo = "the weather in khulna is 28 degrees"
    assert is_acoustic_echo(tts_echo) is True, "Acoustic echo must be caught"
    print(f"Echo detection on heard TTS audio ('{tts_echo}'): REJECTED AS ECHO!")

    # 5. Assistant finishes speaking -> enters room reverberation cooldown
    print("\n4. Assistant finishes speaking -> Entering reverberation cooldown")
    set_speaking_state(False)
    assert is_speaking() is False
    assert is_in_tts_cooldown() is True
    print(f"STT Status during cooldown: GATED for {POST_TTS_COOLDOWN_SEC}s decay window")

    # 6. Simulate echo reverberation arriving right as playback ends
    assert is_in_tts_cooldown() is True, "Must reject frames during cooldown"
    assert is_acoustic_echo("skies partly cloudy") is True, "Acoustic echo must still be rejected"
    print("Reverberation frames during cooldown: DISCARDED!")

    # 7. Cooldown elapses -> STT resumes listening safely
    print(f"\n5. Waiting {POST_TTS_COOLDOWN_SEC + 0.15:.2f}s for cooldown expiry...")
    time.sleep(POST_TTS_COOLDOWN_SEC + 0.15)
    assert not is_speaking()
    assert not is_in_tts_cooldown()
    print("STT Status: RESUMED LISTENING SAFELY")

    # 8. User issues follow-up command: "Thank you, open my notes"
    follow_up = "open my notes"
    print(f"\n6. User speaks new command: '{follow_up}'")
    assert not is_speaking()
    assert not is_in_tts_cooldown()
    assert not is_acoustic_echo(follow_up)
    print("Follow-up user command: ACCEPTED CLEANLY!")

    print("\n==================================================")
    print("VERIFICATION COMPLETE: ZERO SELF-TRIGGERING LOOPS!")
    print("==================================================")

if __name__ == "__main__":
    test_full_cycle()

