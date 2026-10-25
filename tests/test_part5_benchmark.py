import psutil
import time
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def measure_benchmark():
    print("=== PART 5: SYSTEM BENCHMARK & MEASUREMENTS ===")
    
    # Pre-test metrics
    mem_before = psutil.virtual_memory()
    cpu_before = psutil.cpu_percent(interval=1.0)
    print(f"Pre-test RAM: {mem_before.used / 1e9:.2f} GB / {mem_before.total / 1e9:.2f} GB ({mem_before.percent}%)")
    print(f"Pre-test CPU: {cpu_before}%")
    
    # Voice STT operation
    from voice.stt import transcribe_audio_file_full
    en_wav = str(Path(__file__).resolve().parent / "audio" / "en_test.wav")
    t0 = time.time()
    stt_res = transcribe_audio_file_full(en_wav)
    stt_time = time.time() - t0
    
    # Voice TTS operation
    from voice.tts import generate_wav
    test_out = str(Path(__file__).resolve().parent / "audio" / "bench_out.wav")
    t0 = time.time()
    generate_wav("JARVIS benchmark measurement complete.", test_out)
    tts_time = time.time() - t0
    if Path(test_out).exists():
        Path(test_out).unlink(missing_ok=True)
        
    # Post-test metrics
    mem_after = psutil.virtual_memory()
    cpu_after = psutil.cpu_percent(interval=1.0)
    print(f"Post-test RAM: {mem_after.used / 1e9:.2f} GB / {mem_after.total / 1e9:.2f} GB ({mem_after.percent}%)")
    print(f"Post-test CPU: {cpu_after}%")
    print(f"STT Latency (faster-whisper small): {stt_time:.2f}s")
    print(f"TTS Latency (Piper English): {tts_time:.2f}s")
    print("✓ Measured system benchmarks recorded.")

if __name__ == "__main__":
    measure_benchmark()

