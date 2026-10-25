"""
JARVIS Always-On Voice Listener & Speech Detection Engine
=========================================================
- SoundDevice persistent stream + WebRTC VAD (int16, 16kHz mono, 30ms frames).
- Energy gating before VAD (< 1% CPU during idle listening).
- Automatic speech detection: records until ~1.0s silence cutoff.
- Minimum speech duration 0.5s filter.
- Hallucination and false-trigger filters (no_speech_prob > 0.6, avg_logprob, blacklist).
- Half-duplex speech gating (mutes during JARVIS TTS, allows 'stop'/'thamo' interrupts).
- Modes: 'off', 'always', 'push'.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import numpy as np

try:
    import webrtcvad
    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    WEBRTC_VAD_AVAILABLE = False

from voice.stt import SAMPLE_RATE, CHANNELS, save_wav, transcribe_audio_file_full
from voice.wake_word import contains_wake_word, extract_command, remove_wake_word
from voice.tts import is_speaking, stop_tts, is_in_tts_cooldown, is_acoustic_echo

logger = logging.getLogger("jarvis.voice.listener")

# Frame constants (webrtcvad requires 10, 20, or 30 ms frames at 16kHz)
FRAME_DURATION_MS = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples = 960 bytes for 16-bit
SILENCE_TIMEOUT_SEC = 1.0
MIN_SPEECH_DURATION_SEC = 0.5
MAX_RECORD_SEC = 25.0

# Hallucination blacklist for common Whisper artifacts on silence/noise
HALLUCINATION_BLACKLIST = {
    "you", "thank you", "thank you.", "thank you!", "thanks for watching", "thanks for watching.",
    "subtitles by", "subtitles", "bye", "bye bye", "bye.", "see you next time",
    "thank you so much", "so", "the", "a", "i'm sorry", "amara", "shunechi",
    "আমরা", "শুনেছি", "ধন্যবাদ", "ধন্যবাদ।", "সাবস্ক্রাইব", "বিদায়", "বিদায়।",
}

INTERRUPT_KEYWORDS = {
    "stop", "thamo", "থামো", "chup", "চুপ", "wait", "cancel", "অপেক্ষা", "থেমে যাও", "pause", "quiet"
}

QUICK_SINGLE_WORD_COMMANDS = {
    "stop", "wait", "cancel", "pause", "status", "weather", "help", "time",
    "থামো", "চুপ", "বাতিল", "সাহায্য"
}

# Input device blacklist: strictly reject loopback / speaker / system stereo inputs
LOOPBACK_KEYWORDS = (
    "stereo mix",
    "wave out",
    "what u hear",
    "loopback",
    "pc speaker",
    "sound mapper",
    "primary sound capture",
    "line out",
    "speaker",
    "output",
)


def is_loopback_device(name: str) -> bool:
    nl = (name or "").lower()
    return any(k in nl for k in LOOPBACK_KEYWORDS)


def resolve_physical_input_device(requested_device: Optional[int] = None) -> Optional[int]:
    """Resolves and returns a real physical microphone device index, strictly avoiding loopback/stereo mix/speaker devices."""
    try:
        import sounddevice as sd
        devs = sd.query_devices()
    except Exception as e:
        logger.warning(f"Error querying audio devices: {e}")
        return None

    # If requested_device is explicitly provided and is a valid physical mic, honor it
    if requested_device is not None and 0 <= requested_device < len(devs):
        dev = devs[requested_device]
        if dev.get("max_input_channels", 0) > 0 and not is_loopback_device(dev.get("name", "")):
            return requested_device
        logger.warning(
            f"Device #{requested_device} ('{dev.get('name')}') is a loopback or invalid input device! "
            f"Auto-resolving to physical microphone."
        )

    physical_candidates = []
    for idx, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            name = d.get("name", "")
            if not is_loopback_device(name):
                nl = name.lower()
                score = 0
                if "microphone array" in nl or "mic array" in nl:
                    score = 100
                elif "microphone" in nl or "mic" in nl:
                    score = 80
                elif "headset" in nl or "headphone" in nl:
                    score = 70
                else:
                    score = 10
                physical_candidates.append((score, idx, name))

    if not physical_candidates:
        logger.warning("No physical microphone candidate found without loopback keyword.")
        return None

    # Check if system default is in physical candidates list
    try:
        def_in = sd.default.device[0] if hasattr(sd, "default") and sd.default.device else -1
        for score, idx, name in physical_candidates:
            if idx == def_in:
                return idx
    except Exception:
        pass

    physical_candidates.sort(key=lambda x: x[0], reverse=True)
    best_idx = physical_candidates[0][1]
    return best_idx


def play_chime():
    """Subtle futuristic 2-tone chime on Windows."""
    def _chime():
        try:
            import winsound
            winsound.Beep(1760, 90)   # A6
            winsound.Beep(2637, 130)  # E7
        except Exception:
            pass
    threading.Thread(target=_chime, daemon=True).start()


class WakeWordListener:
    def __init__(self, on_command: Optional[Callable[[str], None]] = None):
        self.mode = os.getenv("JARVIS_VOICE_MODE", "always")  # "always", "off", "push"
        self.device_index: Optional[int] = resolve_physical_input_device(None)
        self.language: str = "auto"  # "auto", "bn", "en"
        self.sensitivity: str = "medium"  # "low", "medium", "high"
        self.speak_replies: bool = True
        self.is_running = False
        self.on_command = on_command
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.status = "idle"  # "idle", "listening", "hearing", "thinking", "speaking"

    def update_settings(
        self,
        mode: Optional[str] = None,
        device: Optional[int] = None,
        language: Optional[str] = None,
        sensitivity: Optional[str] = None,
        speak_replies: Optional[bool] = None,
    ) -> dict:
        if mode is not None:
            clean_mode = str(mode).strip().lower()
            if clean_mode in ("always", "off", "push"):
                self.mode = clean_mode
                if clean_mode in ("always", "push"):
                    self.start()
                else:
                    self.stop()
        if device is not None:
            self.device_index = resolve_physical_input_device(device if device >= 0 else None)
        if language is not None and language in ("auto", "bn", "en"):
            self.language = language
        if sensitivity is not None and sensitivity in ("low", "medium", "high"):
            self.sensitivity = sensitivity
        if speak_replies is not None:
            self.speak_replies = bool(speak_replies)

        return self.get_settings()

    def get_settings(self) -> dict:
        return {
            "mode": self.mode,
            "device": self.device_index,
            "language": self.language,
            "sensitivity": self.sensitivity,
            "speak_replies": self.speak_replies,
            "status": self.status,
            "running": self.is_running,
        }

    def set_mode(self, mode: str) -> str:
        clean_mode = str(mode or "").strip().lower()
        if clean_mode not in ("off", "push", "always"):
            clean_mode = "always"

        logger.info(f"Setting voice mode to '{clean_mode}' (current: '{self.mode}')")
        self.mode = clean_mode

        if clean_mode in ("always", "push"):
            self.start()
        else:
            self.stop()

        return self.mode

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_listener, daemon=True, name="WakeWordListener")
        self._thread.start()
        logger.info("Always-on voice listener thread started.")

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self.status = "idle"
        logger.info("Always-on voice listener stopped.")

    def _get_sensitivity_params(self):
        """Returns (vad_mode, base_energy_threshold_rms) calibrated for laptop mics."""
        if self.sensitivity == "high":
            vad_mode = 1
            base_threshold = 12.0
        elif self.sensitivity == "low":
            vad_mode = 3
            base_threshold = 36.0
        else:  # medium
            vad_mode = 2
            base_threshold = 20.0
        return vad_mode, base_threshold

    def _run_listener(self):
        import sounddevice as sd

        logger.info(f"Always-on VAD listener active. Sensitivity: {self.sensitivity}")

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=200)

        def audio_callback(indata, frames, time_info, status):
            if not self._stop_event.is_set():
                try:
                    audio_queue.put_nowait(bytes(indata))
                except queue.Full:
                    pass

        # Rolling pre-speech buffer (keeps last ~300 ms = 10 frames)
        pre_speech_ring = deque(maxlen=10)
        utterance_frames: list[bytes] = []
        started_speech = False
        silence_start: Optional[float] = None
        speech_start_time: Optional[float] = None
        noise_floor = 15.0

        vad = webrtcvad.Vad(2) if WEBRTC_VAD_AVAILABLE else None

        while not self._stop_event.is_set():
            if self.mode != "always":
                self.status = "off"
                time.sleep(0.5)
                continue

            vad_mode, energy_threshold = self._get_sensitivity_params()
            if vad and vad_mode != 2:
                try:
                    vad.set_mode(vad_mode)
                except Exception:
                    pass

            self.status = "listening"

            try:
                resolved_in_device = resolve_physical_input_device(self.device_index)
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=FRAME_SIZE,
                    device=resolved_in_device,
                    callback=audio_callback,
                ):
                    logger.info(f"Persistent audio InputStream opened on device #{resolved_in_device}. Running 0.5s ambient noise calibration...")
                    calib_frames = []
                    calib_start = time.time()
                    while len(calib_frames) < 16 and (time.time() - calib_start < 1.0) and not self._stop_event.is_set():
                        try:
                            cf = audio_queue.get(timeout=0.08)
                            calib_frames.append(cf)
                        except queue.Empty:
                            continue

                    if calib_frames:
                        calib_arr = np.frombuffer(b"".join(calib_frames), dtype=np.int16).astype(np.float32)
                        measured_floor = float(np.sqrt(np.mean(calib_arr ** 2)))
                        noise_floor = max(measured_floor, 12.0)
                        logger.info(f"Ambient noise calibration complete: baseline {noise_floor:.1f} RMS (threshold: {max(energy_threshold * 1.15, noise_floor * 1.45):.1f})")

                    was_in_tts_gating = False
                    while not self._stop_event.is_set() and self.mode == "always":
                        # Check TTS playback and reverberation cooldown
                        if is_speaking() or is_in_tts_cooldown():
                            was_in_tts_gating = True
                            if started_speech or utterance_frames:
                                logger.debug("TTS active or cooldown: dropping speech buffer to prevent self-trigger")
                                started_speech = False
                                utterance_frames.clear()
                                silence_start = None
                                speech_start_time = None
                            pre_speech_ring.clear()

                            # Drain any buffered frames accumulated in audio_queue
                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break

                            self.status = "speaking"
                            time.sleep(0.04)
                            continue

                        # When exiting TTS gating, purge residual audio frames before listening
                        if was_in_tts_gating:
                            was_in_tts_gating = False
                            pre_speech_ring.clear()
                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            self.status = "listening"

                        try:
                            frame_bytes = audio_queue.get(timeout=0.1)
                        except queue.Empty:
                            continue

                        # Compute frame RMS energy
                        frame_arr = np.frombuffer(frame_bytes, dtype=np.int16)
                        rms = float(np.sqrt(np.mean(frame_arr.astype(np.float32) ** 2)))

                        # Adaptive ambient noise floor tracking during non-speech
                        if not started_speech:
                            noise_floor = 0.96 * noise_floor + 0.04 * max(rms, 5.0)

                        dynamic_threshold = max(energy_threshold * 1.15, noise_floor * 1.45)

                        # Energy gating before VAD (bypass VAD on ambient silence/hum)
                        is_speech_frame = False
                        if rms >= dynamic_threshold:
                            if vad is not None:
                                try:
                                    is_speech_frame = vad.is_speech(frame_bytes, SAMPLE_RATE)
                                except Exception:
                                    is_speech_frame = True
                            else:
                                is_speech_frame = True

                        if is_speech_frame:
                            if not started_speech:
                                started_speech = True
                                speech_start_time = time.time()
                                silence_start = None
                                self.status = "hearing"
                                utterance_frames = list(pre_speech_ring)
                            utterance_frames.append(frame_bytes)
                            silence_start = None
                        else:
                            if not started_speech:
                                pre_speech_ring.append(frame_bytes)
                            else:
                                utterance_frames.append(frame_bytes)
                                if silence_start is None:
                                    silence_start = time.time()
                                elif time.time() - silence_start >= SILENCE_TIMEOUT_SEC or (
                                    speech_start_time and time.time() - speech_start_time >= MAX_RECORD_SEC
                                ):
                                    # Speech completed
                                    self._process_utterance(utterance_frames)
                                    # Reset
                                    utterance_frames = []
                                    started_speech = False
                                    silence_start = None
                                    speech_start_time = None
                                    pre_speech_ring.clear()
                                    self.status = "listening"

            except Exception as stream_err:
                logger.error(f"InputStream error: {stream_err}. Reopening in 1.5s...")
                time.sleep(1.5)

    def _process_utterance(self, frames: list[bytes]):
        """Processes collected audio frames after speech endpoint detection."""
        if not frames:
            return

        speech_duration = len(frames) * (FRAME_DURATION_MS / 1000.0)
        if speech_duration < MIN_SPEECH_DURATION_SEC:
            logger.debug(f"Audio discarded: duration {speech_duration:.2f}s < {MIN_SPEECH_DURATION_SEC}s")
            return

        self.status = "thinking"
        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        wav_path = save_wav(audio_data, SAMPLE_RATE)

        try:
            lang_param = None if self.language == "auto" else self.language
            trans_res = transcribe_audio_file_full(wav_path, language=lang_param)
            
            if trans_res.get("discarded") or not trans_res.get("text"):
                logger.debug(f"Audio discarded: {trans_res.get('discard_reason', 'low confidence/empty')}")
                return

            raw_text = trans_res["text"].strip()
            detected_lang = trans_res.get("language") or "en"
            no_speech_prob = trans_res.get("no_speech_prob", 0.0)
            avg_logprob = trans_res.get("avg_logprob", 0.0)

            text_clean = raw_text.strip()
            text_lower = text_clean.lower().strip(".,!? ")

            # ── 1. Half-Duplex Speech Gating ──────────────────────────────────
            # If JARVIS is currently speaking TTS or in cooldown, mute regular speech but allow interruption
            if is_speaking() or is_in_tts_cooldown():
                words = text_lower.split()
                has_interrupt = any(w in INTERRUPT_KEYWORDS for w in words) or (text_lower in INTERRUPT_KEYWORDS)
                if has_interrupt:
                    logger.info(f"Half-duplex: interruption word detected ('{text_clean}') -> cancelling TTS!")
                    stop_tts()
                    play_chime()
                else:
                    logger.info(f"Half-duplex: ignoring voice during TTS playback/cooldown ('{text_clean}')")
                return

            # ── 2. Acoustic Echo & Self-Trigger Prevention ────────────────────
            if is_acoustic_echo(text_clean) or is_acoustic_echo(raw_text):
                logger.warning(f"Acoustic feedback echo detected ('{text_clean}') - discarding self-trigger!")
                return

            # ── 3. False-trigger and Hallucination Control ─────────────────────
            # Post-transcription blacklist check
            if text_lower in HALLUCINATION_BLACKLIST or text_clean in HALLUCINATION_BLACKLIST:
                logger.debug(f"Discarding blacklisted hallucination: '{text_clean}'")
                return

            # ── 3. Wake Word Clean-up (Wake word not required in always-mode) ──
            cmd = text_clean
            if contains_wake_word(text_clean):
                play_chime()
                extracted = extract_command(text_clean)
                cmd = extracted if extracted else remove_wake_word(text_clean)
                cmd = cmd.strip() if cmd else text_clean
            else:
                play_chime()

            logger.info(f"Accepted voice command ({detected_lang}): '{cmd}'")

            if self.on_command and cmd:
                self.status = "speaking"
                # Dispatch on background thread to prevent blocking audio stream
                def _dispatch(c=cmd, l=detected_lang):
                    try:
                        import inspect
                        sig = inspect.signature(self.on_command)
                        if len(sig.parameters) >= 2:
                            self.on_command(c, l)
                        else:
                            self.on_command(c)
                    except Exception as err:
                        logger.error(f"Error executing voice command: {err}", exc_info=True)
                threading.Thread(target=_dispatch, daemon=True).start()

        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass


# Singleton instance
_listener_instance: Optional[WakeWordListener] = None

def get_voice_listener() -> WakeWordListener:
    global _listener_instance
    if _listener_instance is None:
        _listener_instance = WakeWordListener()
    return _listener_instance
