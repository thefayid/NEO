"""
core/sfx.py — Stark Sound Effects Engine for F.R.I.D.A.Y.

Synthesizes and plays subtle MCU-style metallic audio chimes:
  • confirm: Crisp two-tone harmonic metallic chime on task completion.
  • protocol: Low resonant harmonic arc-reactor pulse on protocol triggers.
  • alert: Bright rising tactical ping on wake / attention.
  • media: Melodic resonant acoustic chime on media/Spotify control.
  • error: Damped dual-tone tactical alert on errors or boundaries.

Features:
  - Zero-latency non-blocking asynchronous audio playback via Windows waveOut (winsound).
  - 0% CPU consumption during playback, never blocks event loops or audio input streams.
  - Automatically synthesizes pristine 44.1 kHz 16-bit PCM harmonic waveforms if assets are absent.
"""
from __future__ import annotations

import json
import math
import os
import platform
import threading
import wave
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import winsound
    _WINSOUND_OK = True
except ImportError:
    _WINSOUND_OK = False

_OS = platform.system()
_BASE_DIR = Path(__file__).resolve().parent.parent
_SFX_DIR = _BASE_DIR / "assets" / "sfx"
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"


def _is_sfx_enabled() -> bool:
    try:
        cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("stark_sfx_enabled", True))
    except Exception:
        return True


def _generate_wav(filepath: Path, wave_func, duration: float = 0.4, sr: int = 44100) -> None:
    """Generate and write a normalized 16-bit PCM WAV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    raw = wave_func(t)
    # Normalize with safe headroom
    max_val = np.max(np.abs(raw))
    if max_val > 0:
        raw = (raw / max_val) * 0.75
    pcm = (raw * 32767).astype(np.int16)

    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def ensure_sfx_assets() -> None:
    """Synthesize all default Stark audio chimes if not already present."""
    _SFX_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Confirm: Two-tone resonant metallic chime (C6: 1046Hz + C7: 2093Hz + G7 shimmer)
    confirm_path = _SFX_DIR / "confirm.wav"
    if not confirm_path.exists():
        def _confirm_wave(t):
            env = np.exp(-t * 9.5)
            return (
                0.60 * np.sin(2 * np.pi * 1046.5 * t) +
                0.30 * np.sin(2 * np.pi * 2093.0 * t) +
                0.10 * np.sin(2 * np.pi * 3135.9 * t)
            ) * env
        _generate_wav(confirm_path, _confirm_wave, duration=0.35)

    # 2. Protocol: Low resonant tactical arc-reactor pulse (A4: 440Hz -> E5: 659Hz swell)
    protocol_path = _SFX_DIR / "protocol.wav"
    if not protocol_path.exists():
        def _protocol_wave(t):
            env = np.exp(-t * 6.0)
            freq = 440.0 + (659.2 - 440.0) * (t / 0.45)
            return (
                0.65 * np.sin(2 * np.pi * freq * t) +
                0.25 * np.sin(2 * np.pi * (freq * 2.0) * t) +
                0.10 * np.sin(2 * np.pi * 880.0 * t)
            ) * env
        _generate_wav(protocol_path, _protocol_wave, duration=0.45)

    # 3. Alert: Bright rising tactical ping (D5: 587Hz -> D6: 1174Hz harmonic sweep)
    alert_path = _SFX_DIR / "alert.wav"
    if not alert_path.exists():
        def _alert_wave(t):
            env = np.exp(-t * 11.0)
            freq = 587.3 + (1174.6 - 587.3) * (t / 0.30)
            return (
                0.70 * np.sin(2 * np.pi * freq * t) +
                0.30 * np.sin(2 * np.pi * (freq * 1.5) * t)
            ) * env
        _generate_wav(alert_path, _alert_wave, duration=0.30)

    # 4. Media: Smooth melodic metallic chime (F6: 1396Hz + A6: 1760Hz + C7: 2093Hz triad)
    media_path = _SFX_DIR / "media.wav"
    if not media_path.exists():
        def _media_wave(t):
            env = np.exp(-t * 8.0)
            return (
                0.45 * np.sin(2 * np.pi * 1396.9 * t) +
                0.35 * np.sin(2 * np.pi * 1760.0 * t) +
                0.20 * np.sin(2 * np.pi * 2093.0 * t)
            ) * env
        _generate_wav(media_path, _media_wave, duration=0.40)

    # 5. Error: Low damped tactical warning (E3: 164Hz + B3: 246Hz damped dual-pulse)
    error_path = _SFX_DIR / "error.wav"
    if not error_path.exists():
        def _error_wave(t):
            env = np.exp(-t * 14.0)
            return (
                0.60 * np.sin(2 * np.pi * 164.8 * t) +
                0.40 * np.sin(2 * np.pi * 246.9 * t)
            ) * env
        _generate_wav(error_path, _error_wave, duration=0.28)

    # 6. HUD Boot / Wake: Iconic Iron Man Mark helmet HUD startup sweep & harmonics
    boot_path = _SFX_DIR / "hud_boot.wav"
    if not boot_path.exists():
        def _boot_wave(t):
            # Upward energetic sweep with twin ringing harmonics (400Hz -> 1800Hz)
            env = np.clip(t / 0.05, 0, 1) * np.exp(-t * 4.5)
            freq = 400.0 + (1850.0 - 400.0) * (t / 0.50) ** 1.3
            return (
                0.55 * np.sin(2 * np.pi * freq * t) +
                0.30 * np.sin(2 * np.pi * (freq * 1.5) * t) +
                0.15 * np.sin(2 * np.pi * 2400.0 * t)
            ) * env
        _generate_wav(boot_path, _boot_wave, duration=0.50)

    # 7. Repulsor / Power Pulse: High-energy resonant beam discharge pulse
    repulsor_path = _SFX_DIR / "repulsor.wav"
    if not repulsor_path.exists():
        def _repulsor_wave(t):
            # Fast pitch drop followed by high-frequency shimmer
            env = np.exp(-t * 7.5)
            freq = 1200.0 * np.exp(-t * 8.0) + 320.0
            shimmer = 0.20 * np.sin(2 * np.pi * 3200.0 * t) * np.exp(-t * 12.0)
            return (0.75 * np.sin(2 * np.pi * freq * t) + shimmer) * env
        _generate_wav(repulsor_path, _repulsor_wave, duration=0.42)

    # 8. Target Lock / Focus: Crisp dual-chirp target lock confirmation
    lock_path = _SFX_DIR / "target_lock.wav"
    if not lock_path.exists():
        def _lock_wave(t):
            # Double chirp ping (880Hz then 1760Hz)
            p1 = (t < 0.12) * np.sin(2 * np.pi * 880.0 * t) * np.exp(-t * 18.0)
            t2 = t - 0.14
            p2 = (t >= 0.14) * np.sin(2 * np.pi * 1760.0 * np.maximum(t2, 0)) * np.exp(-np.maximum(t2, 0) * 16.0)
            return 0.85 * (p1 + p2)
        _generate_wav(lock_path, _lock_wave, duration=0.32)


def play_sfx(sound_name: str) -> None:
    """
    Play a named Stark sound effect asynchronously:
    'confirm', 'protocol', 'alert', 'media', 'error'
    """
    if not _is_sfx_enabled():
        return

    sound_name = sound_name.lower().strip()
    wav_path = _SFX_DIR / f"{sound_name}.wav"
    if not wav_path.exists():
        ensure_sfx_assets()
        if not wav_path.exists():
            return

    if _OS == "Windows" and _WINSOUND_OK:
        try:
            # SND_ASYNC | SND_FILENAME | SND_NODEFAULT
            winsound.PlaySound(str(wav_path), winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            return
        except Exception:
            pass

    # Cross-platform non-blocking fallback
    def _fallback_play():
        try:
            import sounddevice as sd
            import soundfile as sf
            data, fs = sf.read(str(wav_path))
            sd.play(data, fs)
            sd.wait()
        except Exception:
            pass
    threading.Thread(target=_fallback_play, daemon=True, name="SFXFallback").start()


def play_confirm() -> None:
    play_sfx("confirm")


def play_protocol() -> None:
    play_sfx("protocol")


def play_alert() -> None:
    play_sfx("alert")


def play_media() -> None:
    play_sfx("media")


def play_error() -> None:
    play_sfx("error")


def play_hud_boot() -> None:
    play_sfx("hud_boot")


def play_repulsor() -> None:
    play_sfx("repulsor")


def play_target_lock() -> None:
    play_sfx("target_lock")


# Ensure sounds are ready on module load
try:
    ensure_sfx_assets()
except Exception as _e:
    print(f"[SFX] ⚠️ Asset generation error: {_e}")
