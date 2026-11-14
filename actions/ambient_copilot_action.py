"""
actions/ambient_copilot_action.py — Self-describing action for NEO Ambient Live Copilot.

Enables NEO to access the ambient copilot memory, inspect recent stack traces and errors,
and autonomously propose/apply developer bug fixes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.ambient_copilot import copilot_engine, AmbientCopilotClassifier, ContentKind
from core import outcome

_BASE_DIR = Path(__file__).resolve().parent.parent

TOOL = {
    "name": "ambient_copilot",
    "description": (
        "Inspect recent runtime errors, stack traces, and ambient developer context captured by NEO's Ambient Copilot. "
        "Use this tool when the user says 'what was that error?', 'fix the recent crash', 'analyze the stack trace', "
        "or asks about errors occurring in active terminals or scripts."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "The action: 'get_recent_error' (latest crash/traceback), 'list_errors' (recent log), 'analyze_text' (classify custom text snippet), 'clear_errors'.",
                "enum": ["get_recent_error", "list_errors", "analyze_text", "clear_errors"]
            },
            "text": {
                "type": "STRING",
                "description": "Optional snippet of error or code to analyze when action is 'analyze_text'."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = (params.get("action") or "get_recent_error").strip().lower()

    if action == "get_recent_error":
        err = copilot_engine.get_latest_error()
        if not err:
            return outcome.done("ambient_copilot", found=False, message="No active runtime errors or stack traces detected recently, Boss.")
        
        loc = f" at {err.get('file')}:{err.get('line')}" if err.get("file") else ""
        res_text = (
            f"Latest Intercepted Error: {err.get('error_type')}{loc}\n"
            f"Time: {err.get('time_str')}\n"
            f"Summary: {err.get('title')}\n"
            f"Snippet:\n{err.get('raw_text', '')[:600]}"
        )
        if player:
            try:
                player.write_log(f"COPILOT: ⚠️ {err.get('title')}")
            except Exception:
                pass
        return outcome.done("ambient_copilot", found=True, error_type=err.get("error_type"), file=err.get("file"), line=err.get("line"), details=res_text)

    elif action == "list_errors":
        errors = copilot_engine.get_recent_errors(limit=5)
        if not errors:
            return outcome.done("ambient_copilot", count=0, message="No recent errors logged.")
        
        lines = [f"Found {len(errors)} recent error(s):"]
        for idx, e in enumerate(errors, 1):
            lines.append(f"{idx}. [{e.get('time_str')}] {e.get('title')}")
        return outcome.done("ambient_copilot", count=len(errors), errors=lines)

    elif action == "analyze_text":
        text = params.get("text", "")
        if not text:
            return outcome.failed("ambient_copilot", "No text provided to analyze.")
        
        analysis = AmbientCopilotClassifier.classify(text)
        action_names = [a[0] for a in analysis.actions]
        return outcome.done(
            "ambient_copilot",
            kind=analysis.kind.value,
            title=analysis.title,
            badge=analysis.badge_label,
            suggested_actions=action_names,
            preview=analysis.preview_text
        )

    elif action == "clear_errors":
        copilot_engine.clear_errors()
        return outcome.done("ambient_copilot", message="Cleared recent error log buffer.")

    return outcome.failed("ambient_copilot", f"Unknown action '{action}'")
