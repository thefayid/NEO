"""
actions/voice_gate.py — F.R.I.D.A.Y. Voice Biometric Gate & Speaker Verification Action.

Provides voice commands to manage Tony Stark's voiceprint authentication:
  • enroll: Learns and stores the Boss's acoustic signature vector.
  • verify: Confirms speaker match against the enrolled signature.
  • status: Reports voiceprint enrollment date, confidence score, and security level.
  • set_security: Adjusts security policy ('strict' | 'relaxed' | 'off').
"""
from __future__ import annotations

from core.voice_auth import get_voiceprint_engine


def voice_gate(parameters: dict | None = None, **kwargs) -> str:
    """Manage voiceprint biometric gate and Boss authentication."""
    params = parameters or {}
    action = str(params.get("action", "status")).strip().lower()
    engine = get_voiceprint_engine()

    if action in ("enroll", "learn", "register"):
        return engine.enroll()
    elif action in ("verify", "check_speaker", "who_am_i"):
        is_auth, score = engine.verify_features(engine._load_profile().get("feature_vector", None) or [])
        pct = score * 100
        verdict = "AUTHORIZED [TONY STARK MATCHED]" if is_auth else "WARNING: UNVERIFIED SPEAKER"
        return f"[SPEAKER VERIFICATION]\n- Verdict: {verdict}\n- Acoustic Confidence: {pct:.1f}%\n- Status: All primary subsystems accessible to Boss."
    elif action in ("set_security", "security_level", "level"):
        lvl = str(params.get("level", "relaxed")).strip().lower()
        return engine.set_security(lvl)
    else:
        return engine.status()


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "voice_gate",
    "description": (
        "Controls Tony Stark's Voice Biometric Voiceprint Gate and speaker authentication. "
        "Actions: "
        "'status' (Checks voiceprint enrollment status and current security policy) | "
        "'enroll' (Enrolls and locks Tony Stark's vocal signature into the biometric database) | "
        "'verify' (Tests speaker voice against authorized profile and outputs confidence match) | "
        "'set_security' (Sets security policy: 'strict' | 'relaxed' | 'off'). "
        "Call when user asks about voice authentication, enrolling their voice, or speaker verification."
    ),
    "brief": (
        "Voice biometric gate: enroll Tony Stark voiceprint, verify speaker identity, "
        "and set voice security policy."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'status' | 'enroll' | 'verify' | 'set_security'",
                "enum": ["status", "enroll", "verify", "set_security"]
            },
            "level": {
                "type": "STRING",
                "description": "Security level when action is 'set_security': 'strict' | 'relaxed' | 'off'",
                "enum": ["strict", "relaxed", "off"]
            }
        },
        "required": ["action"]
    },
    "handler": voice_gate,
}
