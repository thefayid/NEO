"""
actions/skill_library_action.py — Reusable Skill Library & Failure Lessons Tool Action for NEO.

Auto-discovered by core/action_loader.py. Exposes routine storage, fuzzy routine lookup,
and failure lesson recording directly to NEO.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core.neo_skill_library import skill_library


def manage_skill_library(parameters: dict, **kwargs) -> str:
    """Handler for NEO Skill Library and Failure Lessons operations."""
    operation = str(parameters.get("operation", "")).strip().lower()

    if operation == "save_routine":
        name = str(parameters.get("name", "")).strip()
        goal = str(parameters.get("goal", "")).strip()
        preconditions = parameters.get("preconditions", [])
        steps = parameters.get("steps", [])
        ready_signals = parameters.get("ready_signals", [])

        if not goal:
            return "status=failed error='Goal is required to save a verified routine.'"

        routine = skill_library.save_routine(
            name=name,
            goal=goal,
            preconditions=preconditions,
            steps=steps,
            ready_signals=ready_signals,
        )
        return (
            f"status=done action=save_routine name='{routine['name']}' "
            f"steps_count={len(routine['steps'])} verified=true"
        )

    elif operation == "find_routine":
        goal = str(parameters.get("goal", "") or parameters.get("query", "")).strip()
        if not goal:
            return "status=failed error='Goal or query is required to search for a routine.'"

        matched = skill_library.find_matching_routine(goal)
        if not matched:
            return f"status=not_found message='No matching routine found for: {goal}'"

        steps_str = "\n".join(f"  {idx+1}. {s}" for idx, s in enumerate(matched.get("steps", [])))
        signals_str = "\n".join(f"  • {sig}" for sig in matched.get("ready_signals", []))
        prec_str = ", ".join(matched.get("preconditions", [])) or "None"

        return (
            f"status=done action=find_routine verified=true\n"
            f"Found Matching Routine: '{matched['name']}'\n"
            f"Goal: {matched['goal']}\n"
            f"Preconditions: {prec_str}\n"
            f"Verified Steps (replay and verify each):\n{steps_str}\n"
            f"Ready-Signals to Poll:\n{signals_str}"
        )

    elif operation == "list_routines":
        routines = skill_library.list_routines()
        if not routines:
            return "status=done message='Skill library has no saved routines yet.'"

        items = [f"• {r['name']} (Goal: {r['goal']}, Steps: {len(r['steps'])})" for r in routines]
        return f"status=done count={len(routines)}\n" + "\n".join(items)

    elif operation == "record_lesson":
        situation = str(parameters.get("situation", "")).strip()
        what_went_wrong = str(parameters.get("what_went_wrong", "")).strip()
        rule_to_prevent = str(parameters.get("rule_to_prevent", "")).strip()

        if not situation or not what_went_wrong or not rule_to_prevent:
            return "status=failed error='situation, what_went_wrong, and rule_to_prevent are all required.'"

        lesson = skill_library.record_lesson(
            situation=situation,
            what_went_wrong=what_went_wrong,
            rule_to_prevent=rule_to_prevent,
        )
        return (
            f"status=done action=record_lesson verified=true "
            f"message='Lesson recorded and added to session start recall.'"
        )

    elif operation == "get_lessons":
        lessons = skill_library.get_lessons()
        if not lessons:
            return "status=done message='No failure lessons recorded yet.'"

        lines = [
            f"{idx+1}. Situation: {l['situation']} | Wrong: {l['what_went_wrong']} | Rule: {l['rule_to_prevent']}"
            for idx, l in enumerate(lessons)
        ]
        return f"status=done count={len(lessons)}\n" + "\n".join(lines)

    else:
        return (
            f"status=failed error='Unknown operation: {operation}'. "
            f"Valid operations: save_routine, find_routine, list_routines, record_lesson, get_lessons."
        )


TOOL = {
    "name": "skill_library",
    "description": (
        "Manages NEO's Reusable Skill Library and Failure Lessons. "
        "Use 'save_routine' after any successfully verified task to persist: goal, preconditions, verified steps, and ready-signals. "
        "Use 'find_routine' before starting a task to check if a matching routine exists to replay (verify each step). "
        "Use 'record_lesson' after any failure to record: Situation, what went wrong, and the rule to prevent it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'save_routine', 'find_routine', 'list_routines', 'record_lesson', 'get_lessons'.",
            },
            "name": {
                "type": "STRING",
                "description": "Identifier or name for the routine (e.g. 'open_youtube_music_chrome', 'git_pull_repo').",
            },
            "goal": {
                "type": "STRING",
                "description": "High-level goal or task intent of the routine.",
            },
            "preconditions": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "List of preconditions required before executing the routine.",
            },
            "steps": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Exact list of verified steps executed in the routine.",
            },
            "ready_signals": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Ready-signals to wait/poll for between steps (window titles, element visible, etc.).",
            },
            "situation": {
                "type": "STRING",
                "description": "For 'record_lesson': The task or situation in which the failure occurred.",
            },
            "what_went_wrong": {
                "type": "STRING",
                "description": "For 'record_lesson': Description of the failure or error.",
            },
            "rule_to_prevent": {
                "type": "STRING",
                "description": "For 'record_lesson': The strict preventative rule to ensure it never happens again.",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_skill_library,
}

