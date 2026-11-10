"""
actions/visual_grounding_action.py — Multimodal Visual Screen Grounding & OS Click Action for NEO.

Auto-discovered by core/action_loader.py. Enables Gemini Live and the Assistant to visually
locate buttons, menus, inputs, or text on the desktop and interact with them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from core.neo_visual_grounding import visual_grounding
from core.neo_brain import brain

_BASE_DIR = Path(__file__).resolve().parent.parent


def visual_screen_grounding(parameters: dict, **kwargs) -> str:
    """Handler for visual grounding and desktop interaction."""
    action = str(parameters.get("action", "locate")).strip().lower()
    query = str(parameters.get("query", "")).strip()
    fmt = str(parameters.get("format", "mermaid")).strip().lower()

    if action == "reverse_engineer":
        img, _ = visual_grounding.capture_screen()
        if not img:
            return "Failed to capture screen frame for reverse engineering."
        result = visual_grounding.reverse_engineer_visual(img, target_format=fmt)
        return result

    if not query:
        return "Error: 'query' parameter is required to locate or click a UI element on screen."

    # Ground element on active display
    elem = visual_grounding.ground_target_on_screen(query, highlight=True)
    if not elem:
        return f"Could not locate UI element '{query}' on active display."

    cx, cy = elem.center
    brain.episodic.log_event("VISUAL_GROUNDED", f"Located '{elem.label}' on screen at ({cx}, {cy})")

    if action in ("click", "double_click", "right_click"):
        is_dbl = action == "double_click"
        is_right = action == "right_click"
        ok = visual_grounding.click_element(elem, double_click=is_dbl, right_click=is_right)
        action_verb = "Double-clicked" if is_dbl else ("Right-clicked" if is_right else "Clicked")
        if ok:
            return f"Successfully {action_verb.lower()} '{elem.label}' at screen coordinates ({cx}, {cy})."
        else:
            return f"Located '{elem.label}' at ({cx}, {cy}) but click execution failed."

    return (
        f"Located '{elem.label}' ({elem.element_type}) on display at ({cx}, {cy}) "
        f"with confidence {elem.confidence:.2f}. Visual highlight badge displayed."
    )


TOOL = {
    "name": "visual_screen_grounding",
    "description": (
        "Multimodal visual screen grounding and desktop interaction for NEO. "
        "Allows finding any button, link, icon, menu item, or text on the monitor display. "
        "Can locate and visually highlight the element with a macOS accent border, or move "
        "the cursor smoothly and click it. Also reverse-engineers on-screen UI into Mermaid or PyQt."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "One of: 'locate' (find & highlight), 'click' (find & click), 'double_click', 'right_click', or 'reverse_engineer'.",
            },
            "query": {
                "type": "STRING",
                "description": "The visual element name or text to find on screen (e.g. 'Submit button', 'Settings gear', 'Terminal tab').",
            },
            "format": {
                "type": "STRING",
                "description": "Target format for 'reverse_engineer': 'mermaid', 'pyqt', or 'schema'.",
            },
        },
        "required": ["action"],
    },
    "handler": visual_screen_grounding,
}
