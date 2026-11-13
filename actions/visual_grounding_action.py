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
from core import outcome

_BASE_DIR = Path(__file__).resolve().parent.parent


def visual_screen_grounding(parameters: dict, **kwargs) -> str:
    """Handler for visual grounding and desktop interaction."""
    action = str(parameters.get("action", "locate")).strip().lower()
    query = str(parameters.get("query", "")).strip()
    fmt = str(parameters.get("format", "mermaid")).strip().lower()

    if action == "reverse_engineer":
        img, _ = visual_grounding.capture_screen()
        if not img:
            return outcome.failed("visual_screen_grounding", "Failed to capture screen frame for reverse engineering.")
        result = visual_grounding.reverse_engineer_visual(img, target_format=fmt)
        return outcome.done("visual_screen_grounding", format=fmt, result=result)

    if not query:
        return outcome.failed("visual_screen_grounding", "Error: 'query' parameter is required to locate or click a UI element on screen.")

    # Ground element on active display (highlight is sent via safe Qt signal)
    elem = visual_grounding.ground_target_on_screen(query, highlight=True)
    if not elem:
        return outcome.failed("visual_screen_grounding", f"Could not locate UI element '{query}' on active display.")

    cx, cy = elem.center
    brain.episodic.log_event("VISUAL_GROUNDED", f"Located '{elem.label}' on screen at ({cx}, {cy})")

    if action in ("click", "double_click", "right_click"):
        is_dbl = action == "double_click"
        is_right = action == "right_click"
        ok = visual_grounding.click_element(elem, double_click=is_dbl, right_click=is_right, verify=True)
        action_verb = "Double-clicked" if is_dbl else ("Right-clicked" if is_right else "Clicked")
        if ok:
            method_str = "uia" if elem.confidence >= 1.0 else ("som" if elem.confidence >= 0.98 else "vision")
            return outcome.done(
                "visual_screen_grounding",
                action=action,
                label=elem.label,
                x=cx,
                y=cy,
                verified=True,
                method=method_str,
            )
        else:
            return outcome.failed("visual_screen_grounding", f"Located '{elem.label}' at ({cx}, {cy}) but click execution failed.")

    method_str = "uia" if elem.confidence >= 1.0 else ("som" if elem.confidence >= 0.98 else "vision")
    return outcome.done(
        "visual_screen_grounding",
        action="locate",
        label=elem.label,
        type=elem.element_type,
        x=cx,
        y=cy,
        confidence=round(elem.confidence, 2),
        method=method_str,
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
