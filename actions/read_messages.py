"""
actions/read_messages.py — Dedicated Multimodal Chat Reader & Transcriber for WhatsApp & Telegram.

Enables NEO to seamlessly raise, focus, and read live incoming messages, unread chats,
and conversation histories on WhatsApp and Telegram directly from the desktop screen
without hallucination.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def read_messages(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Direct handler for reading, opening, and transcribing WhatsApp and Telegram chats.
    """
    params = parameters or {}
    receiver = str(params.get("receiver") or params.get("contact") or params.get("name") or "").strip()
    platform = str(params.get("platform") or "whatsapp").strip().lower()

    from actions.send_message import send_message as _dispatch_send_message

    sub_params = {
        "action": "read_messages",
        "receiver": receiver,
        "platform": platform,
    }
    return _dispatch_send_message(
        sub_params,
        response=response,
        player=player,
        session_memory=session_memory,
    )


TOOL = {
    "name": "read_messages",
    "description": (
        "Reads, opens, inspects, or transcribes incoming and recent chat messages from WhatsApp or Telegram on screen. "
        "Call this whenever the user says: "
        "'Take the chat of Vias in WhatsApp', "
        "'Open the chat of Vihas on WhatsApp', "
        "'Read messages from Vihas on WhatsApp', "
        "'Check WhatsApp from Rahul', "
        "'What did Vihas send on WhatsApp?', "
        "'Check my WhatsApp', "
        "'Check my Telegram messages', "
        "'Any new messages from Alex'. "
        "Supports contact names (e.g. 'Vias', 'Rahul') or phone numbers. "
        "NEO has complete desktop vision capability to read WhatsApp and Telegram chats directly on screen."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {
                "type": "STRING",
                "description": "Contact name (e.g. 'Vias', 'Rahul') or phone number to read chat from. Leave empty to inspect active/recent chat.",
            },
            "platform": {
                "type": "STRING",
                "description": "'whatsapp' (default) or 'telegram'",
            },
        },
        "required": [],
    },
    "handler": read_messages,
}
