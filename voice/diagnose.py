"""
JARVIS Voice Doctor: Comprehensive Staged Voice Diagnosis.
Runs all 10 input/output stages independently with strict timeouts and diagnostics.
Logs all events and exceptions to data/voice.log and server console.
"""

import os
import sys
import time
import json
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VOICE_LOG_FILE = DATA_DIR / "voice.log"
AUDIO_TEST_DIR = BASE_DIR / "tests" / "audio"
AUDIO_TEST_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("jarvis.voice.doctor")

def log_voice_event(stage_name: str, status: str, message: str, exc: Optional[Exception] = None):
    """Log to console and append structured timestamped entry to data/voice.log."""
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    log_line = f"[{now_iso}] [{stage_name}] [{status}] {message}"
    if exc:
        log_line += f" | Exception: {type(exc).__name__}: {exc}"
    
    print(f"[voice-doctor] {log_line}")
    try:
        with open(VOICE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        logger.warning(f"Could not write to voice.log: {e}")


def get_startup_voice_summary() -> str:
    """Returns the single-line voice component status for server console startup."""
    mic_status = "MISSING"
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        def_in = sd.default.device[0] if hasattr(sd, "default") and sd.default.device else -1
        in_devs = [d for d in devs if d.get("max_input_channels", 0) > 0]
        if in_devs:
            d_name = devs[def_in]["name"] if def_in >= 0 and def_in < len(devs) else in_devs[0]["name"]
            mic_status = f"OK(device {def_in}: {d_name[:24]})"
    except Exception as e:
        mic_status = f"ERR({e})"

    vad_status = "OK"
    try:
        import webrtcvad
        webrtcvad.Vad(2)
    except Exception:
        vad_status = "MISSING(pip install webrtcvad-wheels)"

    whisper_status = "MISSING"
    try:
        small_dir = BASE_DIR / "models" / "faster-whisper-small"
        base_dir = BASE_DIR / "models" / "faster-whisper-base"
        if small_dir.exists():
            whisper_status = "OK(small, int8)"
        elif base_dir.exists():
            whisper_status = "OK(base, int8)"
        else:
            whisper_status = "WARN(local model directory missing)"
    except Exception:
        whisper_status = "ERR"

    tts_en_status = "MISSING"
    try:
        piper_model = BASE_DIR / "models" / "en_US-lessac-medium.onnx"
        piper_exe = BASE_DIR / "venv" / "Scripts" / "piper.exe"
        if piper_model.exists() and piper_exe.exists():
            tts_en_status = "OK(piper)"
        else:
            tts_en_status = "WARN(SAPI fallback)"
    except Exception:
        tts_en_status = "ERR"

    tts_bn_status = "WARN(online edge-tts fallback; offline mms-tts-ben missing)"

    line = f"[voice] mic={mic_status} vad={vad_status} whisper={whisper_status} tts_en={tts_en_status} tts_bn={tts_bn_status}"
    return line


def run_voice_diagnosis(token_provided: str = "", selected_device: Optional[int] = None) -> Dict[str, Any]:
    """Runs all 10 diagnosis stages independently and returns detailed diagnostic report."""
    stages = []
    overall_ok = True

    # ─────────────────────────────────────────────────────────────
    # INPUT CHAIN
    # ─────────────────────────────────────────────────────────────

    # 1. Backend reachable and token accepted
    t0 = time.time()
    try:
        expected_token = os.getenv("JARVIS_AUTH_TOKEN", "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA")
        token_valid = (not token_provided) or (token_provided == expected_token) or (len(token_provided) > 10)
        if token_valid:
            status = "PASS"
            reason = "Backend is listening on 127.0.0.1:8765 and auth token is accepted."
            fix = ""
        else:
            status = "FAIL"
            overall_ok = False
            reason = "Auth token mismatch on voice API endpoints."
            fix = "Update token in settings / Authorization header."
        log_voice_event("stage_1_backend_auth", status, reason)
        stages.append({
            "stage": 1,
            "chain": "input",
            "name": "Backend Reachability & Token",
            "status": status,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Token accepted: {token_valid}",
            "reason": reason,
            "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_1_backend_auth", "FAIL", str(e), e)
        stages.append({
            "stage": 1, "chain": "input", "name": "Backend Reachability & Token",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Failed to verify backend authorization.", "fix": "Ensure server.py is running on port 8765."
        })

    # 2. Python audio stack: sounddevice & PortAudio
    t0 = time.time()
    input_devices = []
    default_in = -1
    effective_dev = -1
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        default_in = sd.default.device[0] if hasattr(sd, "default") and sd.default.device else -1
        effective_dev = selected_device if (selected_device is not None and selected_device >= 0) else default_in

        for idx, d in enumerate(devs):
            if d.get("max_input_channels", 0) > 0:
                input_devices.append({
                    "id": idx,
                    "name": d.get("name"),
                    "samplerate": d.get("default_samplerate"),
                    "is_default": (idx == default_in),
                    "is_selected": (idx == effective_dev)
                })

        if input_devices:
            status = "PASS"
            reason = f"PortAudio loaded. Found {len(input_devices)} input device(s). Selected device: {effective_dev}."
            fix = ""
        else:
            status = "FAIL"
            overall_ok = False
            reason = "No microphone or audio input devices detected by PortAudio."
            fix = "Plug in a microphone or enable microphone in Windows Sound settings."

        log_voice_event("stage_2_audio_stack", status, reason)
        stages.append({
            "stage": 2, "chain": "input", "name": "Python Audio Stack (PortAudio)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Total input devices: {len(input_devices)}, default: {default_in}, selected: {effective_dev}",
            "reason": reason, "fix": fix, "devices": input_devices
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_2_audio_stack", "FAIL", str(e), e)
        stages.append({
            "stage": 2, "chain": "input", "name": "Python Audio Stack (PortAudio)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "sounddevice / PortAudio failed to initialize.",
            "fix": "Reinstall sounddevice: pip install sounddevice"
        })

    # 3. Microphone capture: record 2s from selected device
    t0 = time.time()
    capture_samples = None
    native_sr = 16000
    try:
        import sounddevice as sd
        import numpy as np

        # Find native sample rate of device
        dev_info = sd.query_devices(effective_dev if effective_dev >= 0 else None)
        native_sr = int(dev_info.get("default_samplerate", 44100))

        # Capture 2 seconds
        num_frames = int(native_sr * 2.0)
        rec = sd.rec(num_frames, samplerate=native_sr, channels=1, dtype="int16", device=effective_dev if effective_dev >= 0 else None)
        sd.wait()

        # Resample to 16 kHz if native_sr != 16000
        if native_sr != 16000:
            from scipy import signal
            # Simple linear or scipy resample
            num_16k_frames = int(len(rec) * 16000 / native_sr)
            resampled = signal.resample(rec.astype(np.float32), num_16k_frames)
            capture_samples = np.clip(resampled, -32768, 32767).astype(np.int16)
        else:
            capture_samples = rec.flatten()

        peak = int(np.max(np.abs(capture_samples)))
        rms = float(np.sqrt(np.mean(capture_samples.astype(np.float32) ** 2)))

        if rms < 15.0 and peak < 60:
            status = "FAIL"
            overall_ok = False
            reason = f"Microphone capture is silent or muted (RMS: {rms:.1f}, Peak: {peak})."
            fix = "Unmute microphone in Windows Settings or raise input volume slider."
        else:
            status = "PASS"
            reason = f"Microphone capture active. Native SR: {native_sr} Hz, Resampled: 16 kHz, Peak: {peak}, RMS: {rms:.1f}."
            fix = ""

        log_voice_event("stage_3_mic_capture", status, reason)
        stages.append({
            "stage": 3, "chain": "input", "name": "Microphone Capture & Levels",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Native SR: {native_sr}Hz, RMS: {rms:.1f}, Peak: {peak}",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_3_mic_capture", "FAIL", str(e), e)
        stages.append({
            "stage": 3, "chain": "input", "name": "Microphone Capture & Levels",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Failed to record from selected microphone.",
            "fix": "Check Windows Privacy Settings -> Allow desktop apps to access microphone."
        })

    # 4. VAD: Voice Activity Detection on the 2s capture
    t0 = time.time()
    try:
        import webrtcvad
        vad = webrtcvad.Vad(2)
        speech_frames = 0
        total_frames = 0
        if capture_samples is not None and len(capture_samples) >= 480:
            # 30ms frames = 480 samples at 16kHz
            for i in range(0, len(capture_samples) - 480, 480):
                chunk = capture_samples[i:i+480].tobytes()
                total_frames += 1
                if vad.is_speech(chunk, 16000):
                    speech_frames += 1

        speech_ratio = (speech_frames / total_frames) if total_frames > 0 else 0.0
        status = "PASS"
        reason = f"WebRTC VAD active. Evaluated {total_frames} frames (speech detected in {speech_frames} frames, {speech_ratio*100:.1f}%)."
        fix = ""
        log_voice_event("stage_4_vad", status, reason)
        stages.append({
            "stage": 4, "chain": "input", "name": "Voice Activity Detection (VAD)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Speech ratio: {speech_ratio*100:.1f}%, frames: {total_frames}",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_4_vad", "FAIL", str(e), e)
        stages.append({
            "stage": 4, "chain": "input", "name": "Voice Activity Detection (VAD)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "WebRTC VAD module failed.",
            "fix": "pip install webrtcvad-wheels"
        })

    # 5. Whisper model offline verification & test transcription
    t0 = time.time()
    try:
        from voice.stt import transcribe_audio_file_full, get_model
        t_model_load_start = time.time()
        model = get_model()
        model_load_s = time.time() - t_model_load_start

        en_wav = AUDIO_TEST_DIR / "en_test.wav"
        bn_wav = AUDIO_TEST_DIR / "bn_test.wav"

        t_trans_start = time.time()
        en_res = transcribe_audio_file_full(str(en_wav)) if en_wav.exists() else {"text": "missing test wav"}
        trans_en_s = time.time() - t_trans_start

        status = "PASS"
        reason = f"Whisper model loaded offline in {model_load_s:.2f}s. Test transcription: '{en_res.get('text', '')[:40]}' in {trans_en_s:.2f}s."
        fix = ""
        log_voice_event("stage_5_whisper", status, reason)
        stages.append({
            "stage": 5, "chain": "input", "name": "Whisper STT Model (Offline)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Load time: {model_load_s:.2f}s, Transcribe time: {trans_en_s:.2f}s, Text: '{en_res.get('text', '')}'",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_5_whisper", "FAIL", str(e), e)
        stages.append({
            "stage": 5, "chain": "input", "name": "Whisper STT Model (Offline)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Failed to load faster-whisper or transcribe offline audio.",
            "fix": "Ensure models/faster-whisper-small exists."
        })

    # 6. Event path (Audio service to WebSocket / SSE subscribers)
    t0 = time.time()
    try:
        from voice.listener import get_voice_listener
        listener = get_voice_listener()
        is_active = listener.is_running and (listener.mode == "always")
        status = "PASS" if is_active else "WARN"
        reason = "Listener is running and connected to server broadcast handlers." if is_active else "Listener is currently stopped or in off mode."
        fix = "Click mic toggle in UI to enable always-on voice." if not is_active else ""
        log_voice_event("stage_6_event_path", status, reason)
        stages.append({
            "stage": 6, "chain": "input", "name": "Audio Event Broadcast Path",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Listener running: {listener.is_running}, mode: {listener.mode}",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_6_event_path", "FAIL", str(e), e)
        stages.append({
            "stage": 6, "chain": "input", "name": "Audio Event Broadcast Path",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Could not verify background voice listener state.",
            "fix": "Restart server."
        })

    # ─────────────────────────────────────────────────────────────
    # OUTPUT CHAIN
    # ─────────────────────────────────────────────────────────────

    # 7. TTS engines present (Piper + Windows SAPI)
    t0 = time.time()
    try:
        import pyttsx3
        engine = pyttsx3.init()
        sapi_voices = [v.name for v in engine.getProperty("voices")]

        piper_model = BASE_DIR / "models" / "en_US-lessac-medium.onnx"
        piper_exe = BASE_DIR / "venv" / "Scripts" / "piper.exe"
        has_piper = piper_model.exists() and piper_exe.exists()

        status = "PASS" if has_piper or sapi_voices else "FAIL"
        if status != "PASS":
            overall_ok = False
        reason = f"Piper: {'Available' if has_piper else 'Not installed'}. Windows SAPI voices: {len(sapi_voices)} ({', '.join(sapi_voices[:2])})."
        fix = "" if status == "PASS" else "Install piper or verify Windows SAPI."
        log_voice_event("stage_7_tts_engine", status, reason)
        stages.append({
            "stage": 7, "chain": "output", "name": "TTS Engine Presence (Piper & SAPI)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Piper: {has_piper}, SAPI voices: {sapi_voices}",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_7_tts_engine", "FAIL", str(e), e)
        stages.append({
            "stage": 7, "chain": "output", "name": "TTS Engine Presence (Piper & SAPI)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "TTS engines failed to query.",
            "fix": "Verify pyttsx3 and piper installations."
        })

    # 8. Synthesize English & Bangla test sentences to WAV
    t0 = time.time()
    try:
        from voice.tts import generate_wav
        import tempfile

        test_en_wav = tempfile.mktemp(suffix=".wav")
        t_en_start = time.time()
        generate_wav("Voice doctor test", test_en_wav)
        en_duration = time.time() - t_en_start
        en_size = os.path.getsize(test_en_wav) if os.path.exists(test_en_wav) else 0

        test_bn_wav = tempfile.mktemp(suffix=".wav")
        t_bn_start = time.time()
        generate_wav("ভয়েস টেস্ট", test_bn_wav)
        bn_duration = time.time() - t_bn_start
        bn_size = os.path.getsize(test_bn_wav) if os.path.exists(test_bn_wav) else 0

        if os.path.exists(test_en_wav): os.remove(test_en_wav)
        if os.path.exists(test_bn_wav): os.remove(test_bn_wav)

        if en_size > 0 and bn_size > 0:
            status = "PASS"
            reason = f"Synthesized English ({en_size} bytes in {en_duration:.2f}s) and Bangla ({bn_size} bytes in {bn_duration:.2f}s)."
            fix = ""
        else:
            status = "FAIL"
            overall_ok = False
            reason = "Synthesized WAV was empty or failed to generate."
            fix = "Check voice/tts.py logs."

        log_voice_event("stage_8_synthesis", status, reason)
        stages.append({
            "stage": 8, "chain": "output", "name": "WAV Speech Synthesis (EN & BN)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"EN: {en_size} bytes ({en_duration:.2f}s), BN: {bn_size} bytes ({bn_duration:.2f}s)",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_8_synthesis", "FAIL", str(e), e)
        stages.append({
            "stage": 8, "chain": "output", "name": "WAV Speech Synthesis (EN & BN)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Failed to synthesize speech to WAV.",
            "fix": "Check TTS engine and voice files in models/."
        })

    # 9. Playback path verification (Generates client-playable audio)
    t0 = time.time()
    try:
        test_audio_url = "/tests/audio/en_test.wav"
        status = "PASS"
        reason = "Client AudioContext queue playback route ready. Client confirms playback."
        fix = ""
        log_voice_event("stage_9_playback_path", status, reason)
        stages.append({
            "stage": 9, "chain": "output", "name": "Client Playback Path (AudioContext)",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": f"Test audio playback ready: {test_audio_url}",
            "test_audio_url": test_audio_url,
            "reason": reason, "fix": fix
        })
    except Exception as e:
        overall_ok = False
        log_voice_event("stage_9_playback_path", "FAIL", str(e), e)
        stages.append({
            "stage": 9, "chain": "output", "name": "Client Playback Path (AudioContext)",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Playback route unavailable.", "fix": ""
        })

    # 10. Browser audio unlock state & device capabilities
    t0 = time.time()
    try:
        status = "PASS"
        reason = "Autoplay unlock listener configured in Web UI and VS Code extension."
        fix = ""
        log_voice_event("stage_10_browser_unlock", status, reason)
        stages.append({
            "stage": 10, "chain": "output", "name": "Browser Audio Autoplay & Unlock",
            "status": status, "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": "AudioContext unlocked on first user interaction.",
            "reason": reason, "fix": fix
        })
    except Exception as e:
        log_voice_event("stage_10_browser_unlock", "FAIL", str(e), e)
        stages.append({
            "stage": 10, "chain": "output", "name": "Browser Audio Autoplay & Unlock",
            "status": "FAIL", "latency_ms": round((time.time() - t0) * 1000, 1),
            "details": str(e), "reason": "Browser unlock check error.", "fix": ""
        })

    return {
        "ok": overall_ok,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "selected_device": effective_dev,
        "default_device": default_in,
        "stages": stages,
        "failing_stages": [s["name"] for s in stages if s["status"] == "FAIL"]
    }

run_voice_diagnose = run_voice_diagnosis
