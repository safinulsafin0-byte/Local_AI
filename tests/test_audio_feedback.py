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
    POST_TTS_COOLDOWN_SEC,
)
from voice.listener import resolve_physical_input_device, is_loopback_device

def run_tests():
    print("--- Test 1: Device filtering ---")
    assert is_loopback_device("Stereo Mix (Realtek HD Audio)") is True
    assert is_loopback_device("PC Speaker (Realtek HD Audio output)") is True
    assert is_loopback_device("Primary Sound Capture Driver") is True
    assert is_loopback_device("Microphone Array (Realtek Audio)") is False
    assert is_loopback_device("Microphone (Realtek Audio)") is False

    phys_dev = resolve_physical_input_device(None)
    print(f"Resolved physical device index: {phys_dev}")
    assert phys_dev is not None, "A valid physical device index must be found"

    print("--- Test 2: Playback state & cooldown transitions ---")
    set_speaking_state(False)
    assert not is_speaking()
    # Wait out any leftover cooldown
    time.sleep(POST_TTS_COOLDOWN_SEC + 0.1)
    assert not is_in_tts_cooldown()

    # Turn on speech
    set_speaking_state(True, "Good evening Sir. All security systems are online.")
    assert is_speaking() is True
    assert is_in_tts_cooldown() is True

    # Turn off speech (playback ends)
    set_speaking_state(False)
    assert is_speaking() is False
    assert is_in_tts_cooldown() is True, "Must stay in cooldown during room reverberation decay"

    # Cooldown expiry
    print("Waiting for acoustic decay cooldown...")
    time.sleep(POST_TTS_COOLDOWN_SEC + 0.1)
    assert is_in_tts_cooldown() is False, "Must exit cooldown after decay timeout"

    print("--- Test 3: Acoustic echo cancellation ---")
    record_tts_output("Good evening Sir. All security systems are online.")
    assert is_acoustic_echo("Good evening Sir. All security systems are online.") is True
    assert is_acoustic_echo("good evening sir all security systems online") is True
    assert is_acoustic_echo("security systems are online") is True
    assert is_acoustic_echo("what is the weather today in Dhaka") is False
    assert is_acoustic_echo("open google chrome") is False

    print("SUCCESS: All audio feedback prevention tests passed!")

if __name__ == "__main__":
    run_tests()
