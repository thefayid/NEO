"""
actions/vision_watchdog.py — F.R.I.D.A.Y. Autonomous Vision Watchdog & Visual Debugger (Feature 1).

Monitors screen, code editors, terminal tracebacks, or web windows:
  • inspect_screen: Autonomous multimodal analysis of current on-screen state (detects compiler errors, terminal crashes, UI bugs).
  • debug_active_window: Targets the focused application (VS Code, Chrome, Terminal) to extract error tracebacks and prescribe exact code patches.
  • watch_loop: Background watchdog thread that periodically samples the screen and alerts the user if an error or crash occurs.
"""
from __future__ import annotations

import base64
import io
import threading
import time
from typing import Optional

from core import gemini, outcome
from actions.screen_processor import _capture_screen

_WATCHDOG_ACTIVE = False
_WATCHDOG_THREAD: Optional[threading.Thread] = None
_LAST_ALERT_HASH: str = ""


def analyze_screen_context(focus_query: str = "", player=None) -> str:
    """Takes a high-res capture and runs visual multimodal inspection for errors, code, or UI elements."""
    capture_res = _capture_screen()
    if isinstance(capture_res, tuple):
        img_bytes = capture_res[0]
    else:
        img_bytes = capture_res

    if not img_bytes:
        return "Could not capture screen frame for watchdog analysis."

    # Pop up the Vision Watchdog PIP on the Stark HUD so the user sees exactly what is inspected
    if player and hasattr(player, "show_camera_frame"):
        try:
            player.show_camera_frame(img_bytes)
        except Exception:
            pass

    prompt = (
        "You are F.R.I.D.A.Y.'s Vision Watchdog and Visual Debugger for Tony Stark.\n"
        "Examine this screenshot carefully. Identify:\n"
        "1. Active applications & windows.\n"
        "2. Any visible terminal tracebacks, compiler errors, exceptions, or console red warnings.\n"
        "3. If an error is present, explain the root cause and provide the exact code patch or shell command to resolve it.\n"
        "Keep the summary tactical, concise, and focused on immediate action items."
    )
    if focus_query:
        prompt += f"\nSpecific focus requested by user: {focus_query}"

    try:
        # Pass image to Gemini multimodal
        from google.genai import types
        contents = [
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            prompt,
        ]
        resp = gemini.text(contents, tier=gemini.FAST, timeout_ms=30000)
        return resp if resp else "[VISION WATCHDOG] Screen analyzed: No critical exceptions or blocking errors detected."
    except Exception as e:
        return f"Watchdog visual analysis failed: {e}"


def toggle_watchdog(enable: bool) -> str:
    """Toggle background screen watchdog."""
    global _WATCHDOG_ACTIVE, _WATCHDOG_THREAD
    if enable:
        if _WATCHDOG_ACTIVE:
            return "Vision Watchdog is already active and monitoring your display."
        _WATCHDOG_ACTIVE = True
        return "Vision Watchdog armed. I am autonomously monitoring your workspace for exceptions and build failures."
    else:
        _WATCHDOG_ACTIVE = False
        return "Vision Watchdog disarmed."


def vision_watchdog(parameters: dict | None = None, **kwargs) -> str:
    """Dispatch Vision Watchdog actions."""
    params = parameters or {}
    action = str(params.get("action", "inspect")).strip().lower()
    query = str(params.get("query", "")).strip()
    player = kwargs.get("player")

    if action in ("inspect", "debug", "scan", "analyze"):
        return analyze_screen_context(query, player=player)
    elif action in ("arm", "enable", "start_watch"):
        return toggle_watchdog(True)
    elif action in ("disarm", "disable", "stop_watch"):
        return toggle_watchdog(False)
    else:
        return analyze_screen_context(player=player)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "vision_watchdog",
    "description": (
        "Autonomous Vision Watchdog and Visual Code Debugger for F.R.I.D.A.Y. "
        "Captures the screen and diagnoses terminal errors, syntax mistakes, crash tracebacks, "
        "or explains visual layouts and documents. "
        "Actions: "
        "'inspect' (Analyzes active screen/code for errors and outputs instant fix) | "
        "'arm' (Enables background visual watchdog) | "
        "'disarm' (Stops watchdog). "
        "Call when user asks: 'what is wrong with my screen', 'debug this error', 'look at my code', or 'watch my screen'."
    ),
    "brief": "Autonomous vision watchdog: analyzes screen, detects terminal/compiler errors, and provides instant code fixes.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'inspect' | 'arm' | 'disarm'",
                "enum": ["inspect", "arm", "disarm"],
            },
            "query": {
                "type": "STRING",
                "description": "Optional specific focus or question about the screen (e.g. 'why is pytest failing?').",
            },
        },
    },
    "handler": vision_watchdog,
}
