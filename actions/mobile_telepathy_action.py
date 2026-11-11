"""
actions/mobile_telepathy_action.py — Cross-Device Mobile Telepathy Action for NEO.

Auto-discovered by core/action_loader.py. Exposes remote pushes and desktop screenshot
transmissions to Gemini Live and the Voice Assistant.
"""
from __future__ import annotations

from typing import Dict, Any, Optional
from core.neo_central_coordinator import central_core
from core.neo_mobile_telepathy import mobile_telepathy


def mobile_telepathy_command(parameters: dict, **kwargs) -> str:
    """Handler for Mobile Telepathy operations."""
    operation = str(parameters.get("operation", "send_push")).strip().lower()
    message = str(parameters.get("message", "")).strip()
    title = str(parameters.get("title", "NEO Executive Companion")).strip()
    urgency = float(parameters.get("urgency", 0.5))

    if operation == "check_paired":
        details = mobile_telepathy.get_paired_details()
        if details["paired"]:
            return f"Mobile Telepathy is paired with {details['user_name']} (Chat ID: {details['chat_id']})."
        return "Mobile Telepathy is currently unpaired. Configure telegram credentials in config/telegram.json."

    if operation == "send_screen":
        caption = message or "🖥️ Desktop Screen Snapshot from NEO"
        ok = central_core.capture_and_send_mobile_screen(caption=caption)
        if ok:
            return f"High-resolution desktop screenshot dispatched to your mobile companion."
        return "Failed to send screen snapshot to mobile companion (check pairing)."

    # Default: send_push
    if not message:
        return "Error: 'message' is required to send a mobile push notification."

    ok = central_core.send_mobile_push(title=title, message=message, urgency=urgency)
    if ok:
        return f"Mobile notification dispatched: '{title} — {message}'"
    return "Notification queued/dispatched via active fallback channel."


TOOL = {
    "name": "mobile_telepathy_command",
    "description": (
        "Sends mobile push notifications or real-time desktop screen captures to the user's phone. "
        "Use when the user asks to send an alert, summary, reminder, or screen image to their mobile device."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "'send_push' to send text alert, 'send_screen' to capture and send desktop screen, or 'check_paired' to verify mobile pairing.",
            },
            "message": {
                "type": "STRING",
                "description": "The message body to send, or the screenshot caption.",
            },
            "title": {
                "type": "STRING",
                "description": "Optional title for the notification.",
            },
            "urgency": {
                "type": "NUMBER",
                "description": "Urgency from 0.0 (low) to 1.0 (critical alert).",
            },
        },
        "required": ["operation"],
    },
    "handler": mobile_telepathy_command,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
