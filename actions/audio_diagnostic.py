"""
actions/audio_diagnostic.py — Microphone Diagnostics and Telemetry Tool for NEO.

Provides deep real-time acoustic analysis of audio inputs, tests microphone signal levels,
detects silent/dead devices, and verifies speech capture health.
Can be executed as a tool or directly via: `python -m actions.audio_diagnostic`.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

from core import audio_devices
from memory.config_manager import (
    get_input_device,
    save_input_device,
    get_turn_tuning,
    get_proactive_audio_enabled,
    save_turn_tuning,
    save_proactive_audio_enabled,
)


def run_audio_diagnostics(duration_s: float = 1.0) -> Dict[str, Any]:
    """Probes all input microphones, measures live RMS and peak signal, and diagnoses acoustic health."""
    if sd is None:
        return {"status": "error", "message": "sounddevice library is not available"}

    current_device_name = get_input_device()
    turn_tuning = get_turn_tuning()
    proactive_audio = get_proactive_audio_enabled()

    results: List[Dict[str, Any]] = []
    default_dev_idx = sd.default.device[0]

    all_devs = sd.query_devices()
    host_apis = sd.query_hostapis()

    # Find unique working input devices
    seen_names = set()
    for idx, d in enumerate(all_devs):
        if d.get("max_input_channels", 0) <= 0:
            continue
        dev_name = d.get("name", f"Device {idx}")
        api_name = host_apis[d["hostapi"]]["name"] if d["hostapi"] < len(host_apis) else "Unknown"

        # Check only 1 per name to avoid redundant API duplicates
        clean_name = dev_name.strip()
        if (clean_name, api_name) in seen_names:
            continue
        seen_names.add((clean_name, api_name))

        # Sample test audio
        try:
            sample_rate = 16000
            n_samples = int(sample_rate * duration_s)
            rec = sd.rec(n_samples, samplerate=sample_rate, channels=1, dtype="int16", device=idx)
            sd.wait()
            data = rec.astype(np.float64)
            rms = float(np.sqrt(np.mean(data * data)))
            peak = int(np.max(np.abs(rec)))

            if peak == 0 or rms < 5.0:
                health = "SILENT_OR_DEAD"
            elif rms < 50.0:
                health = "LOW_GAIN"
            elif peak > 30000:
                health = "CLIPPING"
            else:
                health = "OPTIMAL"

            results.append({
                "index": idx,
                "name": dev_name,
                "host_api": api_name,
                "rms": round(rms, 1),
                "peak": peak,
                "health": health,
                "is_system_default": (idx == default_dev_idx),
                "is_current_neo_device": (clean_name == current_device_name or (current_device_name == "" and idx == default_dev_idx)),
            })
        except Exception as e:
            # Skip devices that fail opening at 16kHz
            continue

    # Overall Diagnosis
    issues = []
    if proactive_audio:
        issues.append("Proactive audio is enabled, which may cause Gemini to ignore conversational queries.")
    if turn_tuning.get("enabled", False) and turn_tuning.get("silence_ms", 550) < 400:
        issues.append(f"Turn tuning silence cutoff is very short ({turn_tuning.get('silence_ms')}ms) and may cut speech mid-sentence.")

    return {
        "status": "success",
        "current_device": current_device_name or f"System Default (Index {default_dev_idx})",
        "turn_tuning": turn_tuning,
        "proactive_audio": proactive_audio,
        "devices": results,
        "issues": issues,
    }


def manage_audio_diagnostic(parameters: dict, **kwargs) -> str:
    """Action handler for NEO voice and microphone diagnostics."""
    operation = str(parameters.get("operation", "diagnose")).strip().lower()

    if operation in ("diagnose", "test", "check"):
        diag = run_audio_diagnostics(duration_s=1.0)
        lines = [
            "=== NEO AUDIO & MICROPHONE DIAGNOSTICS ===",
            f"Configured Input Device : {diag['current_device']}",
            f"Proactive Audio Filter  : {'ENABLED (May drop queries)' if diag['proactive_audio'] else 'DISABLED (Optimal)'}",
            f"Turn Tuning VAD Cutoff  : {'ENABLED (' + str(diag['turn_tuning'].get('silence_ms')) + 'ms)' if diag['turn_tuning'].get('enabled') else 'DISABLED (Using robust server default)'}",
            "",
            "Available Microphones & Signal Health:",
        ]
        for dev in diag["devices"]:
            current_tag = " [ACTIVE NEO MIC]" if dev["is_current_neo_device"] else ""
            default_tag = " [SYS DEFAULT]" if dev["is_system_default"] else ""
            lines.append(
                f"- #{dev['index']:02d}: {dev['name']} ({dev['host_api']}){current_tag}{default_tag}\n"
                f"   Level: RMS {dev['rms']} | Peak {dev['peak']} | Status: {dev['health']}"
            )

        if diag["issues"]:
            lines.append("\n⚠️ Detected Issues:")
            for issue in diag["issues"]:
                lines.append(f"  • {issue}")
        else:
            lines.append("\n✅ All acoustic pipeline settings are optimal.")

        return "\n".join(lines)

    elif operation == "set_device":
        device_name = str(parameters.get("device_name", "")).strip()
        save_input_device(device_name)
        label = device_name if device_name else "System Default"
        return f"status=success action=set_device device='{label}'"

    elif operation == "optimize_settings":
        save_proactive_audio_enabled(False)
        save_turn_tuning({
            "enabled": False,
            "silence_ms": 750,
            "prefix_ms": 150,
            "end_sensitivity": "low",
            "start_sensitivity": "high",
        })
        return "status=success action=optimize_settings message='Audio pipeline optimized: proactive audio disabled, natural turn tuning set.'"

    return f"status=failed error='Unknown operation: {operation}'. Valid operations: diagnose, set_device, optimize_settings."


TOOL = {
    "name": "audio_diagnostic",
    "description": (
        "Diagnoses and tests NEO's microphone and voice capture system. "
        "Use 'operation'='diagnose' to measure acoustic levels, detect silent or low-gain microphones, and identify turn-cutting issues. "
        "Use 'operation'='optimize_settings' to apply recommended acoustic and speech recognition defaults."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'diagnose' (test mics and signal levels), 'set_device', 'optimize_settings'.",
            },
            "device_name": {
                "type": "STRING",
                "description": "Device name for 'set_device' (or empty string for system default).",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_audio_diagnostic,
}


if __name__ == "__main__":
    print(manage_audio_diagnostic({"operation": "diagnose"}))
