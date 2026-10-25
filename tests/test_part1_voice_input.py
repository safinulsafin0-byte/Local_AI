import time
import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.stt import transcribe_audio_file_full, _resolve_local_model_path, get_model
from voice.wake_word import contains_wake_word, remove_wake_word

def test_voice_input():
    print("=== PART 1: VOICE INPUT TEST ===")
    
    # 1. Model resolution
    model_path, tag = _resolve_local_model_path()
    print(f"1. Model resolution: tag={tag}, path={model_path}")
    assert Path(model_path).exists(), f"Model path does not exist: {model_path}"
    print("   ✓ Offline model path exists")
    
    # 2. English audio transcription
    en_wav = str(Path(__file__).resolve().parent / "audio" / "en_test.wav")
    t0 = time.time()
    en_res = transcribe_audio_file_full(en_wav, language=None)
    en_dur = time.time() - t0
    print(f"2. English test ({en_dur:.2f}s): text='{en_res['text']}', lang='{en_res['language']}', prob={en_res['language_prob']:.2f}")
    assert "test" in en_res['text'].lower() or "hello" in en_res['text'].lower(), "English transcription failed"
    print("   ✓ English transcription accurate")
    
    # 3. Bangla audio transcription
    bn_wav = str(Path(__file__).resolve().parent / "audio" / "bn_test.wav")
    t0 = time.time()
    bn_res = transcribe_audio_file_full(bn_wav, language=None)
    bn_dur = time.time() - t0
    print(f"3. Bangla test ({bn_dur:.2f}s): text='{bn_res['text']}', lang='{bn_res['language']}', prob={bn_res['language_prob']:.2f}")
    assert bn_res['language'] == 'bn' or any(ord(c) >= 0x0980 and ord(c) <= 0x09FF for c in bn_res['text']), "Bangla detection failed"
    print("   ✓ Bangla transcription accurate")
    
    # 4. Wake word filter check
    test_phrase = "Jarvis what is the weather today"
    has_ww = contains_wake_word(test_phrase)
    clean_cmd = remove_wake_word(test_phrase)
    print(f"4. Wake word: has_ww={has_ww}, cleaned='{clean_cmd}'")
    assert has_ww and "weather" in clean_cmd
    print("   ✓ Wake word detection verified")
    
    print("\nPART 1 TEST COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_voice_input()
