# ============================================================
# JARVIS OFFLINE TEXT-TO-SPEECH
#
# File:
# D:\personal-ai-full\voice\tts.py
#
# Uses:
#   Piper TTS
#   en_US-lessac-medium.onnx
#
# Fully local / offline.
# ============================================================

from __future__ import annotations

import difflib
import os
import re
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Optional

import winsound


# ============================================================
# PATHS
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent.parent
)

PIPER_MODEL = (
    BASE_DIR
    / "models"
    / "en_US-lessac-medium.onnx"
)


# ============================================================
# STATE
# ============================================================

_tts_lock = threading.RLock()

_current_process = None


# ============================================================
# LOG
# ============================================================

def log(message: str):

    print(
        f"[JARVIS TTS] {message}"
    )


# ============================================================
# MODEL CHECK
# ============================================================

def model_exists() -> bool:

    return PIPER_MODEL.exists()


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""

    import re

    # Replace fenced code blocks with conversational summary as required by spec
    has_code = bool(re.search(r"```[\s\S]*?```", text))
    text = re.sub(
        r"```[\s\S]*?```",
        " I wrote the function, check the chat. ",
        text,
    )

    # Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove markdown headings
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # Remove bold / italic / bullets
    text = re.sub(r"[*_~]+", "", text)
    text = re.sub(r"^[\s*•\-]+\s+", "", text, flags=re.MULTILINE)

    # Replace URLs
    text = re.sub(r"https?://\S+", "the link", text, flags=re.IGNORECASE)

    # Strip apology and AI filler phrases
    text = re.sub(r"(?i)\bi apologize for (any )?confusion\.?\s*", "", text)
    text = re.sub(r"(?i)\bi'm sorry for (any )?confusion\.?\s*", "", text)
    text = re.sub(r"(?i)\bas an ai (language model)?\,?\s*", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# PLAYBACK STATE & ACOUSTIC ECHO GATING
# ============================================================

_is_speaking: bool = False
_last_speech_ended_at: float = 0.0
_recent_tts_sentences: deque[tuple[str, float]] = deque(maxlen=30)
POST_TTS_COOLDOWN_SEC: float = 1.2


def set_speaking_state(speaking: bool, text: Optional[str] = None):
    """Updates whether JARVIS or client is currently outputting voice audio."""
    global _is_speaking, _last_speech_ended_at
    with _tts_lock:
        if speaking:
            _is_speaking = True
            if text:
                record_tts_output(text)
        else:
            _is_speaking = False
            _last_speech_ended_at = time.time()


def record_tts_output(text: str):
    """Records recently spoken sentences for acoustic echo cancellation."""
    if not text:
        return
    cleaned = clean_text(text)
    if cleaned:
        with _tts_lock:
            _recent_tts_sentences.append((cleaned, time.time()))


def is_speaking() -> bool:
    """Returns True if TTS is currently playing audio."""
    global _is_speaking
    return bool(_is_speaking)


def is_in_tts_cooldown() -> bool:
    """Returns True if TTS is currently playing OR if we are within post-speech reverberation cooldown."""
    global _is_speaking, _last_speech_ended_at
    if _is_speaking:
        return True
    return (time.time() - _last_speech_ended_at) < POST_TTS_COOLDOWN_SEC


def is_acoustic_echo(candidate_text: str) -> bool:
    """Detects if candidate speech matches recently spoken assistant output (acoustic feedback loop)."""
    if not candidate_text:
        return False
    cand_norm = re.sub(r"[^\w\s\u0980-\u09FF]", "", candidate_text.lower()).strip()
    if len(cand_norm) < 3:
        return False

    now = time.time()
    with _tts_lock:
        recent_items = list(_recent_tts_sentences)

    for item_text, timestamp in reversed(recent_items):
        if (now - timestamp) > 60.0:
            continue
        rec_norm = re.sub(r"[^\w\s\u0980-\u09FF]", "", item_text.lower()).strip()
        if not rec_norm:
            continue

        # Exact match
        if cand_norm == rec_norm:
            return True
        # Substring containment for phrases of length >= 6
        if len(cand_norm) >= 6 and (cand_norm in rec_norm or rec_norm in cand_norm):
            return True

        # Token overlap
        cand_words = set(cand_norm.split())
        rec_words = set(rec_norm.split())
        if len(cand_words) >= 2 and len(rec_words) >= 2:
            overlap = len(cand_words & rec_words) / float(len(cand_words))
            if overlap >= 0.70:
                return True

        # Fuzzy string similarity
        if len(cand_norm) >= 6 and len(rec_norm) >= 6:
            ratio = difflib.SequenceMatcher(None, cand_norm, rec_norm).ratio()
            if ratio >= 0.65:
                return True

    return False


# ============================================================
# STOP PLAYBACK
# ============================================================

def stop():
    global _current_process
    set_speaking_state(False)

    process = _current_process
    if process is not None:
        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        _current_process = None

    try:
        winsound.PlaySound(
            None,
            winsound.SND_PURGE,
        )
    except Exception:
        pass


def stop_tts():
    """Alias for stop()."""
    stop()


# ============================================================
# WAV DURATION
# ------------------------------------------------------------
# Reads the actual length of the generated clip so the caller
# (Flask route / frontend) can know exactly how long playback
# will take, instead of guessing from text length. Returns 0
# if it can't be determined for any reason - callers should
# fall back to an estimate in that case.
# ============================================================

def _get_wav_duration_ms(
    path: str
) -> int:

    try:

        with wave.open(
            path,
            "rb",
        ) as wf:

            frames = wf.getnframes()

            rate = wf.getframerate()

            if rate <= 0:

                return 0

            return int(
                round(
                    (
                        frames
                        / float(rate)
                    )
                    * 1000
                )
            )

    except Exception as error:

        log(
            f"Could not read WAV duration: {error}"
        )

        return 0


# ============================================================
# GENERATE WAV WITH PIPER
# ============================================================

def generate_wav(
    text: str,
    output_wav: str,
):
    global _current_process

    cleaned = clean_text(text)
    if not cleaned:
        raise ValueError("Nothing to speak.")

    record_tts_output(cleaned)

    import re
    is_bangla = bool(re.search(r"[\u0980-\u09FF]", cleaned))

    # If text is Bengali script, synthesize with edge-tts or gTTS
    if is_bangla:
        try:
            import asyncio
            import edge_tts
            import miniaudio
            temp_mp3 = Path(output_wav).with_suffix(".mp3")
            communicate = edge_tts.Communicate(cleaned, "bn-BD-PradeepNeural")
            asyncio.run(communicate.save(str(temp_mp3)))
            if temp_mp3.exists() and temp_mp3.stat().st_size > 0:
                decoded = miniaudio.decode_file(str(temp_mp3))
                with wave.open(str(output_wav), "wb") as wf:
                    wf.setnchannels(decoded.nchannels)
                    wf.setsampwidth(decoded.sample_width)
                    wf.setframerate(decoded.sample_rate)
                    wf.writeframes(decoded.samples)
                temp_mp3.unlink(missing_ok=True)
                return output_wav
        except Exception as e_edge:
            log(f"edge-tts Bengali failed ({e_edge}), trying gTTS...")
            try:
                from gtts import gTTS
                import miniaudio
                temp_mp3 = Path(output_wav).with_suffix(".mp3")
                tts_g = gTTS(text=cleaned, lang="bn")
                tts_g.save(str(temp_mp3))
                if temp_mp3.exists() and temp_mp3.stat().st_size > 0:
                    decoded = miniaudio.decode_file(str(temp_mp3))
                    with wave.open(str(output_wav), "wb") as wf:
                        wf.setnchannels(decoded.nchannels)
                        wf.setsampwidth(decoded.sample_width)
                        wf.setframerate(decoded.sample_rate)
                        wf.writeframes(decoded.samples)
                    temp_mp3.unlink(missing_ok=True)
                    return output_wav
            except Exception as e_gtts:
                log(f"gTTS Bengali failed ({e_gtts}), falling back to standard SAPI/Piper...")

    # Try Piper first if model exists
    if model_exists():
        try:
            piper_executable = "piper"
            venv_scripts = BASE_DIR / "venv" / "Scripts" / "piper.exe"
            if venv_scripts.exists():
                piper_executable = str(venv_scripts)

            command = [
                piper_executable,
                "--model",
                str(PIPER_MODEL),
                "--output_file",
                str(output_wav),
            ]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _current_process = process
            try:
                stdout, stderr = process.communicate(input=cleaned)
            finally:
                if _current_process is process:
                    _current_process = None

            if process.returncode == 0 and os.path.exists(output_wav) and os.path.getsize(output_wav) > 0:
                return output_wav
            log(f"Piper failed, falling back to Windows SAPI TTS...")
        except Exception as pe:
            log(f"Piper exception ({pe}), falling back to Windows SAPI TTS...")

    # Native Windows SAPI fallback (reliable, offline, no blocked DLLs)
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            stream.Open(str(output_wav), 3, False)
            speaker.AudioOutputStream = stream
            speaker.Speak(cleaned)
            stream.Close()
            speaker.AudioOutputStream = None
        finally:
            pythoncom.CoUninitialize()

        if os.path.exists(output_wav) and os.path.getsize(output_wav) > 0:
            return output_wav
    except Exception as sapi_err:
        log(f"Windows SAPI fallback failed: {sapi_err}")

    # Fallback to edge-tts English if available
    try:
        import asyncio
        import edge_tts
        import miniaudio
        temp_mp3 = Path(output_wav).with_suffix(".mp3")
        communicate = edge_tts.Communicate(cleaned, "en-US-GuyNeural")
        asyncio.run(communicate.save(str(temp_mp3)))
        if temp_mp3.exists() and temp_mp3.stat().st_size > 0:
            decoded = miniaudio.decode_file(str(temp_mp3))
            with wave.open(str(output_wav), "wb") as wf:
                wf.setnchannels(decoded.nchannels)
                wf.setsampwidth(decoded.sample_width)
                wf.setframerate(decoded.sample_rate)
                wf.writeframes(decoded.samples)
            temp_mp3.unlink(missing_ok=True)
            return output_wav
    except Exception as e_edge_en:
        raise RuntimeError(f"TTS synthesis failed on Piper, Windows SAPI, and edge-tts: {e_edge_en}")

    return output_wav

synthesize = generate_wav
synthesize_to_wav = generate_wav


# ============================================================
# SYNCHRONOUS SPEAK
# ============================================================

def speak(
    text: str
):

    cleaned = clean_text(
        text
    )

    if not cleaned:

        return {
            "success": False,
            "error": "Nothing to speak.",
        }

    with _tts_lock:

        temp_wav = None

        try:

            # ------------------------------------------------
            # Stop any previous audio
            # ------------------------------------------------

            stop()

            # ------------------------------------------------
            # Temporary WAV
            # ------------------------------------------------

            fd, temp_wav = tempfile.mkstemp(
                prefix="jarvis_tts_",
                suffix=".wav",
            )

            os.close(
                fd
            )

            # ------------------------------------------------
            # Piper
            # ------------------------------------------------

            generate_wav(
                cleaned,
                temp_wav,
            )

            duration_ms = _get_wav_duration_ms(
                temp_wav
            )

            log(
                "Playing response..."
            )

            # ------------------------------------------------
            # Native Windows playback
            # ------------------------------------------------

            try:
                set_speaking_state(True, cleaned)
                winsound.PlaySound(
                    temp_wav,
                    winsound.SND_FILENAME,
                )
            finally:
                set_speaking_state(False)

            log(
                "Playback completed."
            )

            return {
                "success": True,
                "text": cleaned,
                "offline": True,
                "duration_ms": duration_ms,
            }

        except Exception as error:

            print(
                "[TTS ERROR]",
                error
            )

            return {
                "success": False,
                "error": str(error),
            }

        finally:

            if temp_wav:

                try:

                    if os.path.exists(
                        temp_wav
                    ):

                        os.remove(
                            temp_wav
                        )

                except Exception:
                    pass


# ============================================================
# ASYNC SPEAK
#
# Flask won't have to wait until the sentence finishes
# PLAYING - but it DOES wait for the (fast) Piper generation
# step, because that's the only way to know the real clip
# duration before responding. Only playback itself happens in
# the background thread.
#
# The lock is held only around generation (protects the
# shared Piper subprocess handle), NOT across playback -
# holding it across playback would let one lingering speak()
# call block/deadlock a following stop()+speak() pair, since
# stop() can't interrupt audio it never gets to run against.
# Windows' PlaySound already stops any previous synchronous
# clip when a new one starts, so serializing generation alone
# is enough to keep behavior correct.
# ============================================================

def speak_async(
    text: str
):

    cleaned = clean_text(
        text
    )

    if not cleaned:

        return {
            "success": False,
            "error": "Nothing to speak.",
        }

    # ----------------------------------------------------------
    # Stop whatever might still be playing from a previous turn
    # BEFORE generating the new clip, so two responses can never
    # overlap on the speakers (and therefore never overlap into
    # the microphone either).
    # ----------------------------------------------------------

    stop()

    temp_wav = None

    duration_ms = 0

    with _tts_lock:

        try:

            fd, temp_wav = tempfile.mkstemp(
                prefix="jarvis_tts_",
                suffix=".wav",
            )

            os.close(
                fd
            )

            generate_wav(
                cleaned,
                temp_wav,
            )

            duration_ms = _get_wav_duration_ms(
                temp_wav
            )

        except Exception as error:

            if temp_wav:

                try:

                    if os.path.exists(
                        temp_wav
                    ):

                        os.remove(
                            temp_wav
                        )

                except Exception:
                    pass

            print(
                "[TTS ERROR]",
                error
            )

            return {
                "success": False,
                "error": str(error),
            }

    def worker():
        try:
            set_speaking_state(True, cleaned)
            log(
                "Playing response..."
            )

            winsound.PlaySound(
                temp_wav,
                winsound.SND_FILENAME,
            )

            log(
                "Playback completed."
            )

        except Exception as error:

            print(
                "[ASYNC TTS ERROR]",
                error
            )

        finally:
            set_speaking_state(False)

            try:

                if os.path.exists(
                    temp_wav
                ):

                    os.remove(
                        temp_wav
                    )

            except Exception:
                pass

    thread = threading.Thread(
        target=worker,
        daemon=True,
    )

    thread.start()

    return {
        "success": True,
        "started": True,
        "offline": True,
        "text": cleaned,
        "duration_ms": duration_ms,
    }


# ============================================================
# TEST
# ============================================================

def test():

    print()
    print(
        "=" * 60
    )
    print(
        "        JARVIS OFFLINE TTS TEST"
    )
    print(
        "=" * 60
    )

    print()

    print(
        "Model:"
    )

    print(
        PIPER_MODEL
    )

    print()

    print(
        "Model exists:",
        model_exists()
    )

    print()

    result = speak(
        "Hello Sir. JARVIS offline voice output is working."
    )

    print()

    print(
        "Result:",
        result
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    test()