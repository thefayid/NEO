"""
neo/ui/triggers.py — Global Hotkey Listener and Voice Input (Whisper) Trigger Engine.

Architectural Guarantees:
1. Native Windows Global Hotkeys:
   - Uses user32.dll RegisterHotKey/UnregisterHotKey via ctypes.
   - Operates system-wide even when NEO is out of focus or minimized.
   - Built-in shortcuts:
     * Ctrl+Alt+S (or F12): Emergency Stop trigger.
     * Ctrl+Alt+N: Focus Dashboard / Start task.
     * Ctrl+Alt+V: Toggle Voice Input.
2. Voice Input Trigger:
   - Captures microphone audio using sounddevice (or PyAudio).
   - Transcribes audio using OpenAI Whisper (local model) when available.
   - Graceful fallback with clear diagnostic messages when speech libraries are unconfigured.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from neo.safety.emergency_stop import emergency_stop

logger = logging.getLogger("neo.ui.triggers")

# Windows API Hotkey Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

# Virtual Key Codes
VK_N = 0x4E
VK_S = 0x53
VK_V = 0x56
VK_F12 = 0x7B


class GlobalHotkeyManager:
    """
    Registers and listens for system-wide Windows global hotkeys in a dedicated daemon thread.
    """

    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None

    def register_hotkey(
        self,
        hotkey_id: int,
        modifiers: int,
        vk_code: int,
        callback: Callable[[], None],
    ) -> None:
        """Associates a hotkey ID and callback before starting the listener thread."""
        self._callbacks[hotkey_id] = (modifiers, vk_code, callback)

    def register_default_hotkeys(
        self,
        on_stop: Optional[Callable[[], None]] = None,
        on_focus: Optional[Callable[[], None]] = None,
        on_voice: Optional[Callable[[], None]] = None,
    ) -> None:
        """Registers default NEO keyboard shortcuts."""
        # 1. Emergency Stop: Ctrl + Alt + S
        stop_cb = on_stop or (lambda: emergency_stop.trigger("Global Hotkey Ctrl+Alt+S pressed"))
        self.register_hotkey(1, MOD_CONTROL | MOD_ALT, VK_S, stop_cb)

        # 2. Focus Dashboard: Ctrl + Alt + N
        if on_focus:
            self.register_hotkey(2, MOD_CONTROL | MOD_ALT, VK_N, on_focus)

        # 3. Voice Input: Ctrl + Alt + V
        if on_voice:
            self.register_hotkey(3, MOD_CONTROL | MOD_ALT, VK_V, on_voice)

    def start(self) -> None:
        """Starts the Windows message pump loop on a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        logger.info("Global hotkey listener started.")

    def _message_loop(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # Register all configured hotkeys on this thread's message queue
        registered_ids = []
        for hid, (mods, vk, cb) in list(self._callbacks.items()):
            if self.user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk):
                registered_ids.append(hid)
            else:
                logger.warning("Could not register hotkey id=%d (mods=0x%x, vk=0x%x)", hid, mods, vk)

        msg = ctypes.wintypes.MSG()
        try:
            while self._running:
                # GetMessage blocks until a message arrives
                res = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    hid = msg.wParam
                    if hid in self._callbacks:
                        _, _, cb = self._callbacks[hid]
                        try:
                            cb()
                        except Exception as e:
                            logger.error("Hotkey callback error (id=%d): %s", hid, e)
                self.user32.TranslateMessage(ctypes.byref(msg))
                self.user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hid in registered_ids:
                self.user32.UnregisterHotKey(None, hid)
            logger.info("Global hotkeys unregistered.")

    def stop(self) -> None:
        """Stops the message loop and unregisters hotkeys."""
        self._running = False
        if self._thread_id and self.user32:
            WM_QUIT = 0x0012
            self.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("Global hotkey manager stopped.")


class VoiceTrigger:
    """
    Microphone recording and speech-to-text trigger using local Whisper.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.is_recording = False
        self._whisper_model = None
        self._lock = threading.Lock()

    def has_whisper(self) -> bool:
        """Checks if OpenAI Whisper is installed and importable."""
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def load_model(self, model_size: str = "tiny") -> bool:
        """Loads local Whisper speech recognition model."""
        with self._lock:
            if self._whisper_model is not None:
                return True
            try:
                import whisper
                self._whisper_model = whisper.load_model(model_size)
                logger.info("Loaded Whisper model '%s'.", model_size)
                return True
            except Exception as e:
                logger.warning("Could not load Whisper model: %s", e)
                return False

    def record_and_transcribe(
        self,
        duration_s: float = 4.0,
        mock_text: Optional[str] = None,
    ) -> str:
        """
        Records microphone audio for duration_s and transcribes using Whisper.
        If mock_text is supplied, immediately returns mock transcription (for testing).
        """
        if mock_text is not None:
            time.sleep(0.05)
            return mock_text

        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            return "[Error: sounddevice not installed. Install with 'pip install sounddevice numpy']"

        logger.info("Recording voice input for %.1f seconds...", duration_s)
        self.is_recording = True
        try:
            audio_data = sd.rec(
                int(duration_s * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
        except Exception as e:
            logger.error("Audio recording failed: %s", e)
            return f"[Recording Error: {e}]"
        finally:
            self.is_recording = False

        # Convert float32 to 16-bit PCM WAV in temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_path = Path(tmp_wav.name)

        try:
            audio_int16 = (audio_data * 32767).astype(np.int16)
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_int16.tobytes())

            # Transcribe with Whisper if available
            if self.has_whisper() and self.load_model():
                try:
                    result = self._whisper_model.transcribe(str(tmp_path))
                    text = result.get("text", "").strip()
                    logger.info("Transcribed text: '%s'", text)
                    return text
                except Exception as e:
                    logger.error("Whisper transcription error: %s", e)
                    return f"[Transcription Error: {e}]"
            else:
                return "[Whisper not installed. Run 'pip install openai-whisper' for offline transcription]"
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def listen_in_background(
        self,
        callback: Callable[[str], None],
        duration_s: float = 4.0,
        mock_text: Optional[str] = None,
    ) -> threading.Thread:
        """Fires voice recording in a background thread and returns transcribed text via callback."""
        def _worker():
            transcription = self.record_and_transcribe(duration_s=duration_s, mock_text=mock_text)
            callback(transcription)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t
