"""
actions/time_capsule_action.py — Visual Screen History & Time Capsule Search Action for NEO.

Allows NEO to recall past screen contents, active windows, and visual activity.
"""
from __future__ import annotations

from typing import Any, Dict

from core import outcome
from core.neo_visual_time_capsule import visual_time_capsule


def time_capsule_action(parameters: Dict[str, Any], **kwargs) -> str:
    """Queries or logs the visual time capsule."""
    action = parameters.get("action", "search")

    if action == "search":
        query = parameters.get("query", "").strip()
        limit = int(parameters.get("limit", 6))
        hours = float(parameters.get("hours", 24))
        since_seconds = hours * 3600.0

        matches = visual_time_capsule.search_history(query, limit=limit, since_seconds=since_seconds)
        if not matches:
            return outcome.done(
                "time_capsule",
                message=f"No visual history matching '{query}' found in the last {hours} hours.",
                matches=[],
            )

        data = [
            {
                "time": m.formatted_time,
                "app": m.app_name,
                "window": m.window_title,
                "ocr_snippet": m.ocr_snippet,
                "monitor": m.display_index,
            }
            for m in matches
        ]
        return outcome.done(
            "time_capsule",
            query=query,
            total_matches=len(matches),
            matches=data,
        )

    elif action == "timeline":
        limit = int(parameters.get("limit", 10))
        timeline = visual_time_capsule.get_timeline(limit=limit)
        data = [
            f"[{t.formatted_time}] {t.app_name}: '{t.window_title}' (Monitor {t.display_index})"
            for t in timeline
        ]
        return outcome.done(
            "time_capsule",
            total=len(timeline),
            timeline=data,
        )

    elif action == "record":
        app = parameters.get("app_name", "Unknown")
        title = parameters.get("window_title", "Untitled")
        ocr = parameters.get("ocr_snippet", "")
        mon = int(parameters.get("display_index", 1))
        row_id = visual_time_capsule.record_frame(app, title, ocr, display_index=mon)
        return outcome.done("time_capsule", status="recorded", entry_id=row_id)

    return outcome.failed(
        "time_capsule",
        f"Unknown action '{action}'. Supported: search, timeline, record.",
    )


TOOL = {
    "name": "time_capsule",
    "description": (
        "Search or inspect visual desktop history and past screen contents. "
        "Use when the user asks what they were looking at, searches for a past error code, "
        "or asks about previous work: 'what was on my screen 20 minutes ago?', 'search history for postgres'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["search", "timeline", "record"],
                "description": "Action to perform: 'search' (default), 'timeline', or 'record'.",
            },
            "query": {
                "type": "STRING",
                "description": "Search keyword or text fragment to find in past screen history.",
            },
            "hours": {
                "type": "NUMBER",
                "description": "Look back window in hours (default 24).",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Max results to return (default 6).",
            },
        },
        "required": [],
    },
    "handler": time_capsule_action,
    "tier": "extra",
    "brief": "Search past desktop screens, active windows, and visual OCR history.",
}
