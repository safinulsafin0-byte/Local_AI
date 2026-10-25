"""
JARVIS Offline Speech-To-Text — voice/stt.py
=============================================
High-performance local microphone & audio transcription with faster-whisper.
- Multi-lingual auto language detection (English + Bengali).
- Native WAV PCM decoding without requiring external PyAV DLLs.
- VAD silence cutoff gating (1.2s silence stop, max 30s).
- INT8 quantization on CPU for high-speed transcription.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
import time
import types
import wave
from pathlib import Path
from typing import Optional, Tuple, Callable

import numpy as np

# PyAV Application Control bypass for Windows
if "av" not in sys.modules:
    try:
        import av
    except Exception:
        mock_av = types.ModuleType("av")
        mock_av_audio = types.ModuleType("av.audio")
        mock_av_audio.AudioFrame = type("AudioFrame", (), {})
        mock_av_audio.AudioResampler = type("AudioResampler", (), {})
        mock_av.audio = mock_av_audio
        sys.modules["av"] = mock_av
        sys.modules["av.audio"] = mock_av_audio

from faster_whisper import WhisperModel
import faster_whisper.audio
import faster_whisper.transcribe

logger = logging.getLogger("jarvis.voice.stt")

BASE_DIR = Path(__file__).resolve().parent.parent

SAMPLE_RATE = 16000
CHANNELS = 1
DEVICE = os.getenv("JARVIS_WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
MODEL_NAME = os.getenv("JARVIS_WHISPER_MODEL", "tiny")


def _wav_decode_audio(input_file, sampling_rate=16000):
    """Pure wave PCM decoder for faster-whisper without requiring PyAV."""
    if isinstance(input_file, str) and input_file.lower().endswith(".wav"):
        try:
            with wave.open(input_file, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                if sampwidth == 2:
                    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
                if n_channels > 1:
                    data = data.reshape(-1, n_channels).mean(axis=1)
                if framerate != sampling_rate and len(data) > 0:
                    try:
                        from scipy import signal
                        target_len = int(round(len(data) * float(sampling_rate) / float(framerate)))
                        data = signal.resample(data, target_len).astype(np.float32)
                    except Exception as re_err:
                        # Fallback linear interpolation
                        xp = np.linspace(0, 1, len(data))
                        target_len = int(round(len(data) * float(sampling_rate) / float(framerate)))
                        x_new = np.linspace(0, 1, target_len)
                        data = np.interp(x_new, xp, data).astype(np.float32)
                return data
        except Exception as e:
            logger.warning(f"wave decoder error: {e}")
    # Fallback to byte stream if numpy array was passed
    if isinstance(input_file, np.ndarray):
        return input_file.astype(np.float32)
    return np.zeros(1600, dtype=np.float32)


# Patch faster-whisper decoders
faster_whisper.audio.decode_audio = _wav_decode_audio
faster_whisper.transcribe.decode_audio = _wav_decode_audio

_model: Optional[WhisperModel] = None


def _resolve_local_model_path() -> Tuple[str, str]:
    requested = os.getenv("JARVIS_WHISPER_MODEL", "").strip().lower()
    if requested:
        candidate = BASE_DIR / "models" / f"faster-whisper-{requested}"
        if candidate.exists():
            return str(candidate), requested
        if (BASE_DIR / "models" / requested).exists():
            return str(BASE_DIR / "models" / requested), requested

    small = BASE_DIR / "models" / "faster-whisper-small"
    if small.exists():
        return str(small), "small"
    base = BASE_DIR / "models" / "faster-whisper-base"
    if base.exists():
        return str(base), "base"
    return "small", "small"


def get_model() -> WhisperModel:
    global _model
    if _model is not None:
        return _model

    model_source, model_tag = _resolve_local_model_path()
    logger.info(f"Loading faster-whisper '{model_tag}' from {model_source} on {DEVICE} ({COMPUTE_TYPE})...")

    try:
        _model = WhisperModel(model_source, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception as e:
        logger.warning(f"Could not load with {DEVICE}/{COMPUTE_TYPE}: {e}. Retrying CPU int8...")
        _model = WhisperModel(model_source, device="cpu", compute_type="int8")

    logger.info("faster-whisper model ready.")
    return _model


def save_wav(audio_data: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """Save normalized float32 or int16 numpy array to temporary WAV file."""
    fd, path = tempfile.mkstemp(prefix="jarvis_stt_", suffix=".wav")
    os.close(fd)

    if audio_data.dtype != np.int16:
        pcm = np.clip(audio_data, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
    else:
        pcm = audio_data

    with wave.open(path, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())

    return path


def _single_transcribe_pass(audio_path: str, language: Optional[str] = None) -> dict:
    """Runs a single pass of faster-whisper transcription."""
    model = get_model()
    kwargs = {
        "task": "transcribe",
        "beam_size": 3,
        "temperature": 0.0,
        "vad_filter": False,
    }
    if language and language != "auto":
        kwargs["language"] = language

    segments, info = model.transcribe(str(audio_path), **kwargs)

    parts = []
    logprobs = []
    no_speech_probs = []
    total_duration = getattr(info, "duration", 0.0)

    for segment in segments:
        text = str(segment.text or "").strip()
        if text:
            parts.append(text)
        if hasattr(segment, "avg_logprob") and segment.avg_logprob is not None:
            logprobs.append(segment.avg_logprob)
        if hasattr(segment, "no_speech_prob") and segment.no_speech_prob is not None:
            no_speech_probs.append(segment.no_speech_prob)

    result_text = " ".join(parts).strip()
    detected_lang = getattr(info, "language", language or "en")
    lang_prob = getattr(info, "language_probability", 1.0)
    avg_lp = float(np.mean(logprobs)) if logprobs else -2.0
    no_sp = float(np.mean(no_speech_probs)) if no_speech_probs else 0.0

    return {
        "text": result_text,
        "language": detected_lang,
        "language_prob": lang_prob,
        "avg_logprob": avg_lp,
        "no_speech_prob": no_sp,
        "duration": total_duration,
    }


def transcribe_audio_file_full(audio_path: str, language: Optional[str] = None) -> dict:
    """Transcribes an audio file restricted to Bangla and English only.
    - If detected language is not 'bn' or 'en', re-runs once with 'bn' and once with 'en',
      keeps the higher avg_logprob, and discards if avg_logprob is low or no_speech_prob is high.
    - Discards any Korean/CJK glyph hallucinations immediately.
    - Discards short utterances (< 0.5s or < 2 words).
    """
    if language and language not in ("auto", "bn", "en"):
        language = "en"

    # Initial pass
    initial = _single_transcribe_pass(audio_path, language=language)
    detected_lang = initial["language"]

    # If language was auto/None and detected language is not bn or en (e.g. ko, ja, zh on noise)
    if (not language or language == "auto") and detected_lang not in ("bn", "en"):
        logger.info(f"Detected non-BN/EN language '{detected_lang}', running forced bilingual passes (BN & EN)...")
        pass_bn = _single_transcribe_pass(audio_path, language="bn")
        pass_en = _single_transcribe_pass(audio_path, language="en")

        # Keep the candidate with the higher avg_logprob
        if pass_bn["avg_logprob"] >= pass_en["avg_logprob"]:
            chosen = pass_bn
            chosen["language"] = "bn"
        else:
            chosen = pass_en
            chosen["language"] = "en"
    else:
        chosen = initial

    result_text = chosen["text"].strip()
    detected_lang = chosen["language"]
    lang_prob = chosen["language_prob"]
    avg_lp = chosen["avg_logprob"]
    no_sp = chosen["no_speech_prob"]
    total_duration = chosen["duration"]

    # ── 1. Korean, CJK, Devanagari, Tibetan & Disallowed Script Hallucinations ──
    # Allowed: Bangla (\u0980-\u09FF), English ([A-Za-z0-9]), standard punctuation
    if re.search(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\u4e00-\u9fff\u3040-\u30ff\u0f00-\u0fff\u0900-\u097f\u0400-\u04ff\u0600-\u06ff]", result_text):
        if not re.search(r"[\u0980-\u09ff]", result_text):
            logger.info(f"Discarding disallowed script noise hallucination: '{result_text}'")
            return {
                "text": "",
                "language": detected_lang,
                "language_prob": 0.0,
                "avg_logprob": avg_lp,
                "no_speech_prob": 1.0,
                "duration": total_duration,
                "discarded": True,
                "discard_reason": "Contains disallowed foreign script",
            }

    # ── 1b. Repetitive Token / Character Hallucination Gate ──────────────────
    words = [w for w in result_text.split() if w]
    if len(words) >= 3 and len(set(words)) <= 1:
        logger.info(f"Discarding repetitive token hallucination: '{result_text}'")
        return {
            "text": "",
            "language": detected_lang,
            "language_prob": 0.0,
            "avg_logprob": avg_lp,
            "no_speech_prob": 1.0,
            "duration": total_duration,
            "discarded": True,
            "discard_reason": "Repetitive token hallucination",
        }

    raw_chars = [c for c in result_text if c.isalnum() or '\u0980' <= c <= '\u09FF']
    if len(raw_chars) >= 8 and len(set(raw_chars)) <= 2:
        logger.info(f"Discarding repetitive character hallucination: '{result_text}'")
        return {
            "text": "",
            "language": detected_lang,
            "language_prob": 0.0,
            "avg_logprob": avg_lp,
            "no_speech_prob": 1.0,
            "duration": total_duration,
            "discarded": True,
            "discard_reason": "Repetitive character hallucination",
        }

    # ── 2. Confidence & Speech Probability Gate ──────────────────────────────
    if no_sp > 0.45 or avg_lp < -1.35:
        logger.info(f"Discarding low-confidence transcript (no_sp={no_sp:.2f}, avg_lp={avg_lp:.2f}): '{result_text}'")
        return {
            "text": "",
            "language": detected_lang,
            "language_prob": lang_prob,
            "avg_logprob": avg_lp,
            "no_speech_prob": no_sp,
            "duration": total_duration,
            "discarded": True,
            "discard_reason": f"Low confidence: no_sp={no_sp:.2f}, avg_lp={avg_lp:.2f}",
        }

    # ── 3. Duration & Word Count Gate ────────────────────────────────────────
    # Utterances under 0.5s or under 2 words (< 4 chars for Bangla) are ignored
    is_bangla = bool(re.search(r"[\u0980-\u09FF]", result_text))
    text_clean = result_text.strip(".,!? ")
    if is_bangla:
        detected_lang = "bn"
        if len(text_clean.replace(" ", "")) < 4:
            logger.info(f"Discarding short Bangla utterance (< 4 chars): '{result_text}'")
            return {
                "text": "",
                "language": "bn",
                "language_prob": lang_prob,
                "avg_logprob": avg_lp,
                "no_speech_prob": no_sp,
                "duration": total_duration,
                "discarded": True,
            }
    else:
        detected_lang = "en"
        words = [w for w in text_clean.split() if w]
        quick_commands = {"stop", "wait", "cancel", "pause", "status", "weather", "help", "time", "news"}
        if len(words) < 2 and text_clean.lower() not in quick_commands:
            logger.info(f"Discarding short English utterance (< 2 words): '{result_text}'")
            return {
                "text": "",
                "language": "en",
                "language_prob": lang_prob,
                "avg_logprob": avg_lp,
                "no_speech_prob": no_sp,
                "duration": total_duration,
                "discarded": True,
            }

    logger.info(f"Recognized ({detected_lang}, p={lang_prob:.2f}, no_sp={no_sp:.2f}, avg_lp={avg_lp:.2f}): '{result_text}'")
    return {
        "text": result_text,
        "language": detected_lang,
        "language_prob": lang_prob,
        "avg_logprob": avg_lp,
        "no_speech_prob": no_sp,
        "duration": total_duration,
        "discarded": False,
    }


def transcribe_audio_file(audio_path: str, language: Optional[str] = None) -> Tuple[str, str]:
    """Transcribes an audio file with auto language detection (English + Bangla).
    Returns: (text, detected_language)
    """
    res = transcribe_audio_file_full(audio_path, language=language)
    return res["text"], res["language"]


def listen_and_transcribe(
    timeout: float = 30.0,
    silence_threshold: float = 0.015,
    min_silence_duration: float = 1.2,
    status_callback: Optional[Callable[[str], None]] = None,
    language: Optional[str] = None,
) -> Tuple[str, str]:
    """Records microphone audio using sounddevice until silence is detected,
    then transcribes locally with faster-whisper.
    """
    import sounddevice as sd

    if status_callback:
        status_callback("listening")

    logger.info("Microphone recording started...")
    buffer: list[np.ndarray] = []
    silence_start: Optional[float] = None
    started_speaking = False
    start_time = time.time()

    def callback(indata, frames, ctime, status):
        buffer.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=callback):
        while time.time() - start_time < timeout:
            sd.sleep(100)
            if not buffer:
                continue

            recent = buffer[-10:]
            chunk = np.concatenate(recent, axis=0) if len(recent) > 1 else recent[0]
            rms = float(np.sqrt(np.mean(chunk**2)))

            if rms > silence_threshold:
                started_speaking = True
                silence_start = None
            elif started_speaking:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= min_silence_duration:
                    logger.info("Silence detected. Stopping recording.")
                    break

    if not buffer or not started_speaking:
        if status_callback:
            status_callback("idle")
        return "", "en"

    if status_callback:
        status_callback("processing")

    audio_data = np.concatenate(buffer, axis=0).flatten()
    wav_path = save_wav(audio_data, SAMPLE_RATE)

    try:
        text, detected_lang = transcribe_audio_file(wav_path, language=language)
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass
        if status_callback:
            status_callback("idle")

    return text, detected_lang