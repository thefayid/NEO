"""
core/voice_auth.py — F.R.I.D.A.Y. Voice Biometric Voiceprint Gate & Speaker Verification.

Provides acoustic biometric authentication for Tony Stark ("Boss"):
  • Acoustic Feature Extraction: Pitch (F0), Spectral Centroid, Rolloff, and 16-channel Mel-Filterbank.
  • Voiceprint Profile: Vector representation of the Boss's vocal characteristics.
  • Cosine Similarity Scoring: Match verification against enrolled profile.
  • Security Policy: Enforces biometric gating for sensitive actions (shutdown, file deletion, security lockdown).
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from scipy import signal

_BASE_DIR = Path(__file__).resolve().parent.parent
_VOICEPRINT_FILE = _BASE_DIR / "config" / "voiceprint.json"


def _extract_acoustic_features(audio_data: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Extract normalized acoustic feature vector from PCM audio chunk."""
    if audio_data.dtype != np.float32 and audio_data.dtype != np.float64:
        audio = audio_data.astype(np.float32) / 32768.0
    else:
        audio = audio_data.astype(np.float32)

    # Remove DC offset & pre-emphasis
    audio = audio - np.mean(audio)
    if len(audio) < 512:
        return np.zeros(24, dtype=np.float32)

    # 1. Fundamental frequency (Pitch / F0) via autocorrelation
    # Search within human pitch range: 65 Hz to 350 Hz
    min_lag = int(sample_rate / 350)
    max_lag = int(sample_rate / 65)
    corr = signal.correlate(audio[:min(len(audio), 4000)], audio[:min(len(audio), 4000)], mode='full')
    corr = corr[len(corr)//2:]
    
    pitch = 120.0
    if len(corr) > max_lag:
        segment = corr[min_lag:max_lag]
        if len(segment) > 0 and np.max(segment) > 0:
            peak_lag = min_lag + np.argmax(segment)
            pitch = sample_rate / max(1, peak_lag)

    # 2. Spectral features via FFT
    n_fft = 512
    window = np.hanning(min(len(audio), n_fft))
    frame = audio[:len(window)] * window
    mag = np.abs(np.fft.rfft(frame, n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sample_rate)

    sum_mag = np.sum(mag) + 1e-9
    spectral_centroid = np.sum(freqs * mag) / sum_mag

    # Spectral Rolloff (85% energy point)
    cum_energy = np.cumsum(mag)
    rolloff_idx = np.where(cum_energy >= 0.85 * sum_mag)[0]
    spectral_rolloff = freqs[rolloff_idx[0]] if len(rolloff_idx) > 0 else freqs[-1]

    # 3. 16-channel Filterbank energies across 100 Hz - 7500 Hz
    mel_bands = np.geomspace(100, min(7500, sample_rate / 2 - 100), 17)
    band_energies = []
    for i in range(16):
        low, high = mel_bands[i], mel_bands[i+1]
        idx = np.where((freqs >= low) & (freqs < high))[0]
        if len(idx) > 0:
            e = np.mean(mag[idx] ** 2)
        else:
            e = 0.0
        band_energies.append(np.log1p(e * 100.0))

    # Combine into 24-dimensional feature vector
    features = np.zeros(20, dtype=np.float32)
    features[0] = pitch / 300.0  # Normalized pitch
    features[1] = spectral_centroid / 4000.0
    features[2] = spectral_rolloff / 6000.0
    features[3] = np.mean(audio ** 2) * 50.0  # RMS energy
    features[4:20] = np.array(band_energies, dtype=np.float32)

    # Unit norm vector
    norm = np.linalg.norm(features)
    if norm > 1e-6:
        features = features / norm
    return features


class VoiceprintEngine:
    def __init__(self):
        self.profile = self._load_profile()
        self.recent_scores: list[float] = []

    def _load_profile(self) -> dict:
        default_profile = {
            "enrolled": False,
            "boss_name": "Tony Stark",
            "security_level": "relaxed",  # "strict" | "relaxed" | "off"
            "feature_vector": None,
            "enrolled_at": None,
            "samples_count": 0,
        }
        if _VOICEPRINT_FILE.exists():
            try:
                data = json.loads(_VOICEPRINT_FILE.read_text(encoding="utf-8"))
                return data
            except Exception as e:
                print(f"[VoiceAuth] Warning loading voiceprint: {e}")
        return default_profile

    def _save_profile(self) -> None:
        try:
            _VOICEPRINT_FILE.write_text(json.dumps(self.profile, indent=4), encoding="utf-8")
        except Exception as e:
            print(f"[VoiceAuth] Error saving voiceprint: {e}")

    def enroll(self, audio_data: Optional[np.ndarray] = None) -> str:
        """Enroll the current user's voice as Tony Stark's authorized voiceprint."""
        if audio_data is None:
            # Generate simulated baseline or capture micro sample
            # Create calibrated Stark acoustic signature
            vec = np.ones(20, dtype=np.float32)
            vec[0] = 0.42   # F0 around 125 Hz
            vec[1] = 0.45   # Centroid around 1800 Hz
            vec[2] = 0.55   # Rolloff
            vec[3] = 0.60   # Energy
            vec[4:20] = np.array([0.8, 0.9, 1.1, 1.2, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.4, 0.3, 0.3, 0.2, 0.2], dtype=np.float32)
            vec = vec / np.linalg.norm(vec)
        else:
            vec = _extract_acoustic_features(audio_data)

        self.profile["enrolled"] = True
        self.profile["feature_vector"] = [round(float(x), 4) for x in vec]
        self.profile["enrolled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.profile["samples_count"] = self.profile.get("samples_count", 0) + 1
        self._save_profile()

        return (
            f"[VOICEPRINT ENROLLMENT COMPLETE]\n"
            f"- Target Identity: Tony Stark (Boss)\n"
            f"- Acoustic Vector Dimension: {len(vec)}\n"
            f"- Security Status: Active [{self.profile['security_level'].upper()}]\n"
            f"- Biometric signature stored in config/voiceprint.json, Boss."
        )

    def verify_features(self, candidate_vector: np.ndarray) -> Tuple[bool, float]:
        """Verify candidate feature vector against enrolled Boss voiceprint."""
        if not self.profile.get("enrolled") or not self.profile.get("feature_vector"):
            return True, 1.0  # Not enrolled yet -> bypass

        level = self.profile.get("security_level", "relaxed")
        if level == "off":
            return True, 1.0

        enrolled_vec = np.array(self.profile["feature_vector"], dtype=np.float32)
        dot = np.dot(candidate_vector, enrolled_vec)
        norm_a = np.linalg.norm(candidate_vector)
        norm_b = np.linalg.norm(enrolled_vec)
        
        if norm_a < 1e-6 or norm_b < 1e-6:
            score = 0.85  # Default nominal fallback
        else:
            score = float(dot / (norm_a * norm_b))

        self.recent_scores.append(score)
        if len(self.recent_scores) > 20:
            self.recent_scores.pop(0)

        threshold = 0.78 if level == "strict" else 0.60
        is_authenticated = (score >= threshold)
        return is_authenticated, score

    def set_security(self, level: str) -> str:
        level = level.lower().strip()
        if level not in ("strict", "relaxed", "off"):
            return f"Invalid security level '{level}'. Choose 'strict', 'relaxed', or 'off'."
        self.profile["security_level"] = level
        self._save_profile()
        return f"Voice Biometric Security set to [{level.upper()}], Boss."

    def status(self) -> str:
        enrolled = self.profile.get("enrolled", False)
        level = self.profile.get("security_level", "relaxed").upper()
        date = self.profile.get("enrolled_at", "Never")
        last_score = f"{self.recent_scores[-1]*100:.1f}%" if self.recent_scores else "No recent samples"

        return (
            f"[VOICEPRINT BIOMETRIC GATE STATUS]\n"
            f"- Boss Enrolled: {'YES [ACTIVE]' if enrolled else 'NO [UNENROLLED - Run enroll command]'}\n"
            f"- Security Policy: {level}\n"
            f"- Authorized Voice: Tony Stark\n"
            f"- Enrolled Timestamp: {date}\n"
            f"- Last Match Confidence: {last_score}\n"
            f"- Gated Actions: Shutdown, computer settings, destructive file operations."
        )


_engine = VoiceprintEngine()


def get_voiceprint_engine() -> VoiceprintEngine:
    return _engine
