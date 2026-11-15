"""
actions/ghost_hands.py — Ghost Hands: Zero-Hijacking Background Computer Operator.

Enables parallel co-operation: operates background applications, browser windows,
and desktop controls without moving the user's physical mouse cursor or stealing keyboard focus.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
from core import outcome
from core.neo_ghost_hands import ghost_hands

TOOL = {
    "name": "ghost_hands",
    "description": (
        "Zero-hijacking background computer operator. Operates background applications, "
        "browser windows, forms, and desktop controls in parallel WITHOUT moving the user's "
        "physical mouse cursor and WITHOUT stealing keyboard focus. "
        "Use this when the user is actively working (coding, typing, viewing a call) and wants "
        "NEO to click buttons, fill forms, or operate an app in the background."
    ),
    "brief": (
        "Operates background apps without moving the user's mouse cursor: click, type, scroll, read, or pipeline."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'click' | 'type' | 'scroll' | 'read' | 'list_windows' | 'pipeline' | 'status'",
                "enum": ["click", "type", "scroll", "read", "list_windows", "pipeline", "status"]
            },
            "target": {
                "type": "STRING",
                "description": "UI element name, button text, or input description (e.g. 'Search', 'Submit', 'Save', 'Close', 'Username')."
            },
            "app_name": {
                "type": "STRING",
                "description": "Target application name or window title (e.g. 'Chrome', 'Notepad', 'Spotify', 'Settings', 'Calculator')."
            },
            "text": {
                "type": "STRING",
                "description": "Text to type into the target background input field (for action='type')."
            },
            "direction": {
                "type": "STRING",
                "description": "'down' (default) or 'up' for action='scroll'."
            },
            "amount": {
                "type": "INTEGER",
                "description": "Number of scroll notches (default: 3)."
            },
            "double_click": {
                "type": "BOOLEAN",
                "description": "Whether to double click."
            },
            "right_click": {
                "type": "BOOLEAN",
                "description": "Whether to right click."
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Whether to clear the input field before typing."
            },
            "steps": {
                "type": "ARRAY",
                "description": "Array of step dicts for multi-step background pipeline execution."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = str(params.get("action") or "status").strip().lower()
    target = str(params.get("target") or params.get("query") or params.get("description") or "").strip()
    app_name = str(params.get("app_name") or params.get("app") or params.get("window") or "").strip()
    text = str(params.get("text") or "")
    double_click = bool(params.get("double_click", False))
    right_click = bool(params.get("right_click", False))
    clear_first = bool(params.get("clear_first", True))

    # 1. Status Check
    if action == "status":
        available = ghost_hands.is_available
        bg_windows = ghost_hands.list_background_windows(max_windows=10)
        return outcome.done(
            "ghost_hands",
            available=available,
            windows_detected=len(bg_windows),
            sample_windows=[w.title for w in bg_windows[:5]],
        )

    # 2. List Background Windows
    if action in ("list_windows", "windows"):
        windows = ghost_hands.list_background_windows(max_windows=20)
        summary = [
            f"{w.title} ({w.process_name or 'win32'}, hwnd={w.hwnd}, min={w.is_minimized})"
            for w in windows
        ]
        return outcome.done(
            "ghost_hands",
            total_windows=len(windows),
            windows=summary,
        )

    # 3. Ghost Click (Zero Cursor Movement)
    if action in ("click", "click_element"):
        if not target:
            return outcome.failed("ghost_hands", "target is required for ghost_click", action="click")

        res = ghost_hands.ghost_click(
            target=target,
            app_or_title=app_name or None,
            double_click=double_click,
            right_click=right_click,
        )
        if res.get("status") == outcome.DONE:
            return outcome.done(
                "ghost_hands",
                subaction="click",
                target=target,
                method=res.get("method"),
                window=res.get("window"),
                cursor_preserved=res.get("cursor_preserved", True),
            )
        return outcome.failed(
            "ghost_hands",
            res.get("reason", f"Could not click '{target}' in background"),
            action="click",
            target=target,
            window=res.get("window"),
        )

    # 4. Ghost Type (Zero Keyboard Hijack)
    if action in ("type", "type_into_element"):
        if not target:
            return outcome.failed("ghost_hands", "target is required for ghost_type", action="type")

        res = ghost_hands.ghost_type(
            target=target,
            text=text,
            app_or_title=app_name or None,
            clear_first=clear_first,
        )
        if res.get("status") == outcome.DONE:
            return outcome.done(
                "ghost_hands",
                subaction="type",
                target=target,
                method=res.get("method"),
                window=res.get("window"),
                chars_typed=res.get("chars_typed", len(text)),
                cursor_preserved=res.get("cursor_preserved", True),
            )
        return outcome.failed(
            "ghost_hands",
            res.get("reason", f"Could not type into '{target}' in background"),
            action="type",
            target=target,
            window=res.get("window"),
        )

    # 5. Ghost Scroll
    if action == "scroll":
        direction = str(params.get("direction", "down")).strip().lower()
        amount = int(params.get("amount", 3))
        res = ghost_hands.ghost_scroll(
            direction=direction,
            amount=amount,
            app_or_title=app_name or None,
        )
        if res.get("status") == outcome.DONE:
            return outcome.done(
                "ghost_hands",
                subaction="scroll",
                direction=direction,
                amount=amount,
                window=res.get("window"),
                cursor_preserved=res.get("cursor_preserved", True),
            )
        return outcome.failed(
            "ghost_hands",
            res.get("reason", "Failed to scroll background window"),
            action="scroll",
            window=res.get("window"),
        )

    # 6. Ghost Read
    if action == "read":
        res = ghost_hands.ghost_read(
            target=target or None,
            app_or_title=app_name or None,
        )
        if res.get("status") == outcome.DONE:
            return outcome.done(
                "ghost_hands",
                subaction="read",
                window=res.get("window"),
                extracted_text=res.get("extracted_text"),
                controls=res.get("controls", []),
            )
        return outcome.failed(
            "ghost_hands",
            res.get("reason", "Failed to read background window"),
            action="read",
        )

    # 7. Ghost Pipeline (Multi-Step Routine)
    if action == "pipeline":
        steps = params.get("steps") or []
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except Exception:
                steps = []
        if not steps or not isinstance(steps, list):
            return outcome.failed("ghost_hands", "steps array is required for pipeline action", action="pipeline")

        res = ghost_hands.ghost_pipeline(steps=steps, app_or_title=app_name or None)
        if res.get("status") == outcome.DONE:
            return outcome.done(
                "ghost_hands",
                subaction="pipeline",
                total_steps=res.get("total_steps"),
                results_count=len(res.get("results", [])),
            )
        return outcome.failed(
            "ghost_hands",
            f"Pipeline failed at step {res.get('failed_at_step')}: {res.get('reason')}",
            action="pipeline",
        )

    return outcome.failed("ghost_hands", f"Unknown action: '{action}'", action=action)
