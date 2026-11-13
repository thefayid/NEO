"""
actions/task_scope_action.py — Task Scope Sentinel Action for NEO.

Auto-discovered by core/action_loader.py. Exposes task scope locking, expansion upon
user permission, inspection, and scope resetting upon task completion.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core.neo_scope_sentinel import scope_sentinel


def manage_task_scope(parameters: dict, **kwargs) -> str:
    """Handler for NEO Task Scope operations."""
    operation = str(parameters.get("operation", "get_scope")).strip().lower()

    if operation == "lock_scope":
        task_name = str(parameters.get("task_name", "task")).strip()
        allowed_apps = parameters.get("allowed_apps", [])
        allowed_folders = parameters.get("allowed_folders", [])
        allowed_websites = parameters.get("allowed_websites", [])
        allowed_actions = parameters.get("allowed_actions", [])

        scope = scope_sentinel.lock_scope(
            task_name=task_name,
            allowed_apps=allowed_apps,
            allowed_folders=allowed_folders,
            allowed_websites=allowed_websites,
            allowed_actions=allowed_actions,
        )
        return (
            f"status=done action=lock_scope verified=true task_name='{task_name}'\n"
            f"Allowed Apps: {scope['allowed_apps'] or 'None'}\n"
            f"Allowed Folders: {scope['allowed_folders'] or 'None'}\n"
            f"Allowed Websites: {scope['allowed_websites'] or 'None'}\n"
            f"Allowed Actions: {scope['allowed_actions'] or 'All actions'}\n"
            f"Boundary Locked: Anything outside this scope is strictly forbidden without user permission."
        )

    elif operation == "expand_scope":
        allowed_apps = parameters.get("allowed_apps", [])
        allowed_folders = parameters.get("allowed_folders", [])
        allowed_websites = parameters.get("allowed_websites", [])
        allowed_actions = parameters.get("allowed_actions", [])

        scope = scope_sentinel.expand_scope(
            allowed_apps=allowed_apps,
            allowed_folders=allowed_folders,
            allowed_websites=allowed_websites,
            allowed_actions=allowed_actions,
        )
        return (
            f"status=done action=expand_scope verified=true task_name='{scope['task_name']}'\n"
            f"Updated Allowed Apps: {scope['allowed_apps']}\n"
            f"Updated Allowed Folders: {scope['allowed_folders']}\n"
            f"Updated Allowed Websites: {scope['allowed_websites']}\n"
            f"Updated Allowed Actions: {scope['allowed_actions']}"
        )

    elif operation == "reset_scope":
        scope_sentinel.reset_scope()
        return "status=done action=reset_scope verified=true message='Task scope unlocked and reset.'"

    elif operation == "get_scope":
        scope = scope_sentinel.get_scope()
        if not scope.get("is_locked"):
            return "status=done is_locked=false message='No task scope is currently locked.'"
        return (
            f"status=done is_locked=true task='{scope['task_name']}'\n"
            f"Allowed Apps: {scope['allowed_apps']}\n"
            f"Allowed Folders: {scope['allowed_folders']}\n"
            f"Allowed Websites: {scope['allowed_websites']}\n"
            f"Allowed Actions: {scope['allowed_actions']}"
        )

    else:
        return (
            f"status=failed error='Unknown operation: {operation}'. "
            f"Valid operations: lock_scope, expand_scope, get_scope, reset_scope."
        )


TOOL = {
    "name": "task_scope",
    "description": (
        "Locks, expands, inspects, or resets the execution boundary for a task. "
        "At the start of each task, call 'lock_scope' to declare allowed apps, folders, websites, and actions (all others forbidden). "
        "Call 'expand_scope' only when the user explicitly grants permission to access additional resources. "
        "Call 'reset_scope' when the task ends."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'lock_scope', 'expand_scope', 'get_scope', 'reset_scope'.",
            },
            "task_name": {
                "type": "STRING",
                "description": "Name or brief identifier for the task.",
            },
            "allowed_apps": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of allowed applications (e.g. ['notepad', 'chrome']).",
            },
            "allowed_folders": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of allowed folders/directories.",
            },
            "allowed_websites": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of allowed website domains or URLs.",
            },
            "allowed_actions": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of allowed tools or action verbs.",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_task_scope,
}

