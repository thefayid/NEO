"""
actions/autonomous_goal.py — Autonomous Computer-Use & Multi-Step Agentic Loop Action for NEO.

Auto-discovered by core/action_loader.py. Exposes autonomous computer task execution
to the Gemini Live Engine, Spotlight, and Voice assistant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from core.neo_agentic_loop import goal_engine, GoalStatus
from core.neo_brain import brain

_BASE_DIR = Path(__file__).resolve().parent.parent


def execute_autonomous_goal(parameters: dict, **kwargs) -> str:
    """Handler for autonomous goal execution and status checking."""
    instruction = str(parameters.get("instruction", "")).strip()
    operation = str(parameters.get("operation", "start")).strip().lower()
    goal_id = str(parameters.get("goal_id", "")).strip()

    if operation == "status":
        if not goal_id:
            return "Error: 'goal_id' is required to check status."
        goal = goal_engine.get_goal(goal_id)
        if not goal:
            return f"Goal '{goal_id}' not found."
        steps_summary = [
            f"Step {s.step_id} [{s.status.value}]: {s.title}"
            for s in goal.steps
        ]
        return (
            f"Goal ID: {goal.goal_id}\n"
            f"Status: {goal.status.value}\n"
            f"Prompt: {goal.prompt}\n"
            f"Steps:\n" + "\n".join(steps_summary)
        )

    if not instruction:
        return "Error: 'instruction' parameter is required to start an autonomous goal."

    # Record in working memory and episodic log
    brain.working.set_active_goal(instruction)
    brain.episodic.log_event("GOAL_DISPATCHED", f"Autonomous goal launched: {instruction}")

    # Submit to agentic engine
    gid = goal_engine.submit_goal(instruction)
    goal = goal_engine.get_goal(gid)

    num_steps = len(goal.steps) if goal else 0
    return (
        f"Autonomous Goal [{gid[:8]}] initiated successfully. "
        f"Plan compiled with {num_steps} atomic execution steps. "
        f"NEO will perform steps, self-correct any errors, and report completion."
    )


TOOL = {
    "name": "execute_autonomous_goal",
    "description": (
        "Launches an autonomous multi-step computer task or goal loop for NEO. "
        "Use when an instruction requires several steps like inspecting files, running terminal "
        "commands, analyzing errors, writing code, or verifying tests. "
        "The autonomous agentic loop executes each step, diagnoses failures (e.g. missing modules), "
        "and auto-corrects before retrying."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "instruction": {
                "type": "STRING",
                "description": "The complex task or objective for NEO to achieve autonomously.",
            },
            "operation": {
                "type": "STRING",
                "description": "Either 'start' to launch a new autonomous goal, or 'status' to check an existing one.",
            },
            "goal_id": {
                "type": "STRING",
                "description": "Optional goal ID when querying status.",
            },
        },
        "required": ["instruction"],
    },
    "handler": execute_autonomous_goal,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
