"""
actions/meeting_copilot.py — Meeting Copilot action for NEO.

Provides autonomous command handling for:
- Starting internal audio meeting recordings (Stereo Mix loopback).
- Stopping and compiling Executive Meeting Minutes.
- Pinning live notes and adding action items.
- Auto-syncing action items into tasks and agenda.
"""
from __future__ import annotations

from typing import Any, Dict
from core.meeting_copilot import meeting_manager
from core import outcome

TOOL = {
    "name": "meeting_copilot",
    "description": (
        "Control NEO Meeting Copilot to record internal PC system audio (Google Meet, Zoom, Teams, Discord, YouTube) "
        "via Stereo Mix/loopback without mic bleed. Automatically extracts decisions, action items, and generates "
        "executive markdown minutes synced to Desktop, Tasks, and Agenda."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "The action: 'start' (begin recording meeting), 'stop' (conclude meeting & compile minutes), 'status' (check duration & counts), 'pin_note' (pin a live decision or note), 'add_action_item' (record a todo).",
                "enum": ["start", "stop", "status", "pin_note", "add_action_item"]
            },
            "topic": {
                "type": "STRING",
                "description": "Optional title or topic of the meeting for 'start' (e.g. 'Sprint Planning', 'Client Demo')."
            },
            "note": {
                "type": "STRING",
                "description": "Note or insight text for 'pin_note'."
            },
            "action_item": {
                "type": "STRING",
                "description": "Action item description for 'add_action_item'."
            },
            "owner": {
                "type": "STRING",
                "description": "Owner for 'add_action_item' (default: Rahman)."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = (params.get("action") or "status").strip().lower()

    if action == "start":
        topic = params.get("topic") or "General Meeting"
        res = meeting_manager.start_meeting(topic=topic)
        if res.get("status") == "already_active":
            return outcome.failed("meeting_copilot", res.get("message"))
        
        if player:
            try:
                player.write_log(f"MEETING COPILOT: 🔴 Recording '{topic}' via internal loopback.")
                if hasattr(player, "show_meeting_badge"):
                    player.show_meeting_badge(True, topic=topic, duration_sec=0)
            except Exception:
                pass

        return outcome.done(
            "meeting_copilot",
            session_id=res.get("session_id"),
            topic=res.get("topic"),
            device=res.get("device"),
            message=f"Meeting recording initiated for '{topic}'. All internal audio is now being captured cleanly."
        )

    elif action == "stop":
        res = meeting_manager.stop_meeting()
        if res.get("status") == "inactive":
            return outcome.failed("meeting_copilot", res.get("message"))

        if player:
            try:
                player.write_log(f"MEETING COPILOT: ⏹️ Meeting '{res.get('topic')}' concluded. Minutes generated on Desktop.")
                if hasattr(player, "show_meeting_badge"):
                    player.show_meeting_badge(False)
            except Exception:
                pass

        return outcome.done(
            "meeting_copilot",
            session_id=res.get("session_id"),
            topic=res.get("topic"),
            duration=res.get("duration"),
            action_items_count=res.get("action_items_count"),
            decisions_count=res.get("decisions_count"),
            desktop_path=res.get("desktop_path"),
            md_path=res.get("md_path"),
            synced_tasks=res.get("synced_tasks", []),
            message=f"Meeting concluded successfully ({res.get('duration')}). Minutes saved to Desktop and action items synced to your task queue."
        )

    elif action == "status":
        st = meeting_manager.get_status()
        if not st.get("active"):
            return outcome.done(
                "meeting_copilot",
                active=False,
                message="No meeting recording in progress, Boss."
            )
        
        if player:
            try:
                if hasattr(player, "show_meeting_badge"):
                    player.show_meeting_badge(True, topic=st.get("topic", ""), duration_sec=st.get("duration_sec", 0))
            except Exception:
                pass

        return outcome.done(
            "meeting_copilot",
            active=True,
            session_id=st.get("session_id"),
            topic=st.get("topic"),
            duration=st.get("duration"),
            notes_count=st.get("notes_count"),
            action_items_count=st.get("action_items_count"),
            decisions_count=st.get("decisions_count"),
            message=f"Meeting '{st.get('topic')}' has been recording for {st.get('duration')}."
        )

    elif action == "pin_note":
        note_text = params.get("note") or ""
        if not note_text:
            return outcome.failed("meeting_copilot", "No note text provided.")
        
        res = meeting_manager.pin_note(note_text)
        if res.get("status") == "inactive":
            return outcome.failed("meeting_copilot", res.get("message"))

        if player:
            try:
                player.write_log(f"MEETING COPILOT: 📌 Pinned note: '{note_text[:50]}'")
            except Exception:
                pass

        return outcome.done("meeting_copilot", note=note_text, time=res.get("entry", {}).get("time"))

    elif action == "add_action_item":
        item_text = params.get("action_item") or ""
        if not item_text:
            return outcome.failed("meeting_copilot", "No action item text provided.")
        
        owner = params.get("owner") or "Rahman"
        res = meeting_manager.add_action_item(item_text, owner=owner)
        if res.get("status") == "inactive":
            return outcome.failed("meeting_copilot", res.get("message"))

        if player:
            try:
                player.write_log(f"MEETING COPILOT: 📋 Added action item: '{item_text}' ({owner})")
            except Exception:
                pass

        return outcome.done("meeting_copilot", action_item=item_text, owner=owner)

    return outcome.failed("meeting_copilot", f"Unknown action '{action}'")
