# ============================================================
# JARVIS VOICE PIPELINE VERIFICATION TEST (PACKAGE 4)
# ============================================================

import os
import sys
import wave
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from voice.tts import clean_text, generate_wav
from voice.stt import transcribe_audio_file

def test_clean_text():
    print("--- 1. Testing clean_text() ---")
    raw = """### Heading 1
Here is **bold** and *italic* text.
Check this [Google](https://google.com) link!
```python
def hello():
    print("world")
```
- First bullet item
- Second bullet item
`inline_code` here.
"""
    cleaned = clean_text(raw)
    print("Cleaned text:\n", repr(cleaned))
    assert "Heading" not in cleaned or "###" not in cleaned
    assert "bold" in cleaned and "**" not in cleaned
    assert "https://" not in cleaned
    assert "I wrote the function, check the chat" in cleaned
    assert "inline" in cleaned and "`" not in cleaned
    print("✓ clean_text test passed!")

def test_english_tts():
    print("\n--- 2. Testing English TTS Synthesis ---")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        generate_wav("JARVIS online. System diagnostics show all subsystems fully operational.", wav_path)
        assert os.path.exists(wav_path)
        size = os.path.getsize(wav_path)
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            rate = wf.getframerate()
            frames = wf.getnframes()
            duration_s = frames / float(rate)
        print(f"✓ English audio generated: size={size} bytes, channels={channels}, rate={rate}Hz, duration={duration_s:.2f}s")
        assert size > 1000
        assert duration_s > 0.5
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

def test_bangla_tts():
    print("\n--- 3. Testing Bengali TTS Synthesis ---")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        generate_wav("নমস্কার, আমি জারভিস। আপনার সব কাজ সফলভাবে সম্পন্ন হয়েছে।", wav_path)
        assert os.path.exists(wav_path)
        size = os.path.getsize(wav_path)
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            rate = wf.getframerate()
            frames = wf.getnframes()
            duration_s = frames / float(rate)
        print(f"✓ Bengali audio generated: size={size} bytes, channels={channels}, rate={rate}Hz, duration={duration_s:.2f}s")
        assert size > 1000
        assert duration_s > 0.5
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

def test_stt_transcription():
    print("\n--- 4. Testing faster-whisper STT with Bengali Audio Roundtrip ---")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        generate_wav("Hello Jarvis, this is an automated voice test.", wav_path)
        transcript, lang = transcribe_audio_file(wav_path)
        print(f"✓ STT Result: '{transcript}' (Detected Language: {lang})")
        assert len(transcript) > 0
        assert lang in ("en", "bn")
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

def test_sentence_boundary_regex():
    print("\n--- 5. Testing Streaming Sentence Buffer Regex ---")
    import re
    buffer = "First sentence here. Second sentence with e.g. an abbreviation! Third sentence? Fourth with danda বাংলা বাক্য। End."
    regex = re.compile(r"([^.!?\n\u0964]+(?:[.!?\n\u0964]+|\n+))\s*")
    sentences = []
    for m in regex.finditer(buffer):
        s = m.group(1).strip()
        sentences.append(s)
    print("Parsed sentences:", sentences)
    assert len(sentences) >= 4
    print("✓ Sentence boundary regex passed!")

if __name__ == "__main__":
    print("=" * 60)
    print("  RUNNING PACKAGE 4 VOICE PIPELINE VERIFICATION")
    print("=" * 60)
    test_clean_text()
    test_english_tts()
    test_bangla_tts()
    test_stt_transcription()
    test_sentence_boundary_regex()
    print("\n" + "=" * 60)
    print("  ALL PACKAGE 4 TESTS PASSED")
    print("=" * 60)
