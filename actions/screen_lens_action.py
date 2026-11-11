"""
actions/screen_lens_action.py — Omnipresent Screen Lens & Multimodal Vision Action for NEO.

Auto-discovered by core/action_loader.py. Exposes instant screen inspection,
debugging, OCR extraction, and visual element grounding to Gemini Live & Voice Assistant.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from PyQt6.QtCore import QTimer
from core.neo_screen_lens import get_screen_lens
from core.neo_central_coordinator import central_core


def screen_lens(parameters: dict, player: Any = None, speak: Any = None, **kwargs) -> str:
    """
    Activates the omnipresent Screen Lens HUD to analyze, debug, OCR, or click on-screen elements.

    Parameters:
      - action: 'inspect' | 'explain' | 'debug' | 'ocr' | 'summarize' | 'click'
      - query: Optional question, target description, or element to click.
    """
    action = str(parameters.get("action", "explain")).strip().lower()
    query = str(parameters.get("query", "")).strip()

    valid_actions = ("inspect", "explain", "debug", "ocr", "summarize", "click")
    if action not in valid_actions:
        action = "explain"

    # Activate Screen Lens on main Qt GUI thread
    def _run_on_gui():
        try:
            lens = get_screen_lens()
            lens.activate_lens()
            lens.execute_action(action, query)
        except Exception as e:
            print(f"[ScreenLensAction] Error invoking lens: {e}")

    QTimer.singleShot(0, _run_on_gui)

    central_core.system_telemetry.emit({
        "event": "screen_lens_invoked",
        "action": action,
        "query": query
    })

    if action == "debug":
        return "Activating Screen Lens to inspect the code error and traceback on screen."
    elif action == "ocr":
        return "Activating Screen Lens to extract and copy visible text and code to your clipboard."
    elif action == "click":
        return f"Activating Screen Lens to locate and interact with '{query or 'target'}'."
    elif action == "summarize":
        return "Activating Screen Lens to summarize the active document or web page."
    else:
        return "Activating Screen Lens. Analyzing what is currently visible on your display."
