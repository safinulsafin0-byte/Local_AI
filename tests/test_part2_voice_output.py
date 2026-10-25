import sys
import os
import time
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.tts import clean_text, generate_wav

def test_voice_output():
    print("=== PART 2: VOICE OUTPUT TEST ===")

    # 1. Text Cleaning
    dirty_text = (
        "# Heading 1\n"
        "Here is the result: [click here](https://example.com/data).\n"
        "```python\ndef add(a, b):\n    return a + b\n```\n"
        "I apologize for any confusion. Please see the output at https://api.com/v1."
    )
    cleaned = clean_text(dirty_text)
    print(f"1. Cleaned text:\n   '{cleaned}'")
    assert "https://" not in cleaned, "Raw URLs should be stripped"
    assert "```" not in cleaned, "Code fences should be removed"
    assert "I apologize" not in cleaned, "Apology filler should be removed"
    print("   ✓ Text cleaning verified")

    # 2. English Synthesis
    en_out = str(Path(__file__).resolve().parent / "audio" / "test_out_en.wav")
    t0 = time.time()
    generate_wav("JARVIS voice system is online and ready.", en_out)
    en_time = time.time() - t0
    assert os.path.exists(en_out) and os.path.getsize(en_out) > 5000, "English WAV failed"
    with wave.open(en_out, "rb") as wf:
        en_dur = wf.getnframes() / float(wf.getframerate())
    print(f"2. English speech synthesis ({en_time:.2f}s, duration={en_dur:.2f}s, size={os.path.getsize(en_out)} bytes)")
    print("   ✓ English synthesis verified")

    # 3. Bangla Synthesis
    bn_out = str(Path(__file__).resolve().parent / "audio" / "test_out_bn.wav")
    t0 = time.time()
    generate_wav("আজকের দিনটি চমৎকার।", bn_out)
    bn_time = time.time() - t0
    assert os.path.exists(bn_out) and os.path.getsize(bn_out) > 5000, "Bangla WAV failed"
    with wave.open(bn_out, "rb") as wf:
        bn_dur = wf.getnframes() / float(wf.getframerate())
    print(f"3. Bangla speech synthesis ({bn_time:.2f}s, duration={bn_dur:.2f}s, size={os.path.getsize(bn_out)} bytes)")
    print("   ✓ Bangla synthesis verified")

    # Clean up test output files
    for p in (en_out, bn_out):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    print("\nPART 2 TEST COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_voice_output()

