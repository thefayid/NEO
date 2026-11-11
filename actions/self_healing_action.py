"""
actions/self_healing_action.py — Self-Healing Codebase Action for NEO.

Auto-discovered by core/action_loader.py. Exposes AST syntax auditing, automated auto-fixes,
and conventional git commit generation to Gemini Live and the Voice Assistant.
"""
from __future__ import annotations

from typing import Dict, Any, Optional
from core.neo_central_coordinator import central_core


def self_healing_codebase(parameters: dict, **kwargs) -> str:
    """Handler for self-healing workspace and git operations."""
    operation = str(parameters.get("operation", "audit")).strip().lower()
    commit_message = str(parameters.get("commit_message", "")).strip()

    if operation == "audit":
        res = central_core.run_workspace_self_healing()
        scanned = res.get("files_scanned", 0)
        errors = res.get("errors_found", 0)
        if errors == 0:
            return f"Workspace syntax audit clean. Scanned {scanned} Python files — zero syntax errors found."
        
        detail_lines = [
            f"• {e['file']}:{e['line']} — {e['error']}"
            for e in res.get("details", [])[:5]
        ]
        return (
            f"Workspace audit found {errors} syntax error(s) across {scanned} files:\n"
            + "\n".join(detail_lines)
            + "\nSmart auto-fix chips have been queued to the UI."
        )

    if operation == "commit":
        msg = commit_message if commit_message else None
        ok, res_msg = central_core.auto_commit_workspace(message=msg)
        if ok:
            return f"Workspace changes successfully staged and committed:\n{res_msg}"
        return f"Git commit notice: {res_msg}"

    if operation == "suggest_commit":
        msg = central_core.generate_git_commit()
        return f"Suggested Conventional Commit Message:\n{msg}"

    return f"Unknown operation '{operation}'. Supported operations: 'audit', 'commit', 'suggest_commit'."


TOOL = {
    "name": "self_healing_codebase",
    "description": (
        "Audits workspace Python files for syntax errors, generates targeted auto-fix proposals, "
        "or creates conventional git commits from current diffs. "
        "Use when the user asks to check code health, diagnose code errors, or commit workspace changes."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "'audit' to scan syntax across workspace, 'commit' to stage and commit changes, or 'suggest_commit' to draft a conventional commit message.",
            },
            "commit_message": {
                "type": "STRING",
                "description": "Optional custom git commit message. If omitted during 'commit', NEO auto-generates a conventional commit message from active git diff.",
            },
        },
        "required": ["operation"],
    },
    "handler": self_healing_codebase,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
