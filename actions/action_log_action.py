"""
actions/action_log_action.py — Action Audit Log Tool for NEO.

Auto-discovered by core/action_loader.py. Exposes structured audit log inspection,
"show log", and strictly factual "what did you do?" queries based only on verified log entries.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core.neo_action_logger import action_logger


def manage_action_log(parameters: dict, **kwargs) -> str:
    """Handler for NEO Structured Action Audit Log operations."""
    operation = str(parameters.get("operation", "show_log")).strip().lower()

    if operation == "show_log":
        n = int(parameters.get("n", 10))
        return action_logger.format_last_entries(n)

    elif operation in ("what_did_you_do", "query"):
        limit = int(parameters.get("limit", 10))
        return action_logger.answer_what_did_you_do(limit=limit)

    elif operation == "record":
        tool_called = str(parameters.get("tool_called", "")).strip()
        params = parameters.get("parameters", {})
        result = str(parameters.get("result", "")).strip()
        step = parameters.get("step")
        evidence = parameters.get("evidence")
        verified = parameters.get("verified")

        if not tool_called:
            return "status=failed error='tool_called is required to log an action.'"

        entry = action_logger.record_action(
            tool_called=tool_called,
            parameters=params,
            result=result,
            step=step,
            evidence=evidence,
            verified=verified,
        )
        return f"status=done action=log_recorded entry='{entry.to_line()}'"

    else:
        return (
            f"status=failed error='Unknown operation: {operation}'. "
            f"Valid operations: show_log, what_did_you_do, record."
        )


TOOL = {
    "name": "action_log",
    "description": (
        "Inspects or manages NEO's Structured Action Audit Log. "
        "Use 'operation'='show_log' when the user requests 'show log' or wants to see the last N logged actions. "
        "Use 'operation'='what_did_you_do' when the user asks 'what did you do?' to answer STRICTLY from the log, never from memory or inference."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'show_log' (print last N entries), 'what_did_you_do' (report strictly from log), or 'record'.",
            },
            "n": {
                "type": "INTEGER",
                "description": "Number of log entries to print (defaults to 10).",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Max entries to summarize for 'what_did_you_do'.",
            },
            "tool_called": {
                "type": "STRING",
                "description": "Tool name for 'record'.",
            },
            "parameters": {
                "type": "OBJECT",
                "description": "Parameters for 'record'.",
            },
            "result": {
                "type": "STRING",
                "description": "Tool output/result for 'record'.",
            },
            "evidence": {
                "type": "STRING",
                "description": "Screenshot ID or output proof for 'record'.",
            },
            "verified": {
                "type": "STRING",
                "description": "'yes' or 'no' for 'record'.",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_action_log,
}

