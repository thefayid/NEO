"""
actions/swarm_war_room_action.py — Autonomous Swarm War Room Action for NEO.

Auto-discovered by core/action_loader.py. Exposes 4-agent collaborative consensus
(Architect, Coder, Critic, DevOps) to Gemini Live and the Voice Assistant.
"""
from __future__ import annotations

from typing import Dict, Any, Optional
from core.neo_central_coordinator import central_core
from core.neo_swarm_war_room import swarm_war_room


def run_swarm_war_room(parameters: dict, **kwargs) -> str:
    """Handler for Swarm War Room missions."""
    action_type = str(parameters.get("action_type", "dispatch")).strip().lower()
    objective = str(parameters.get("objective", "")).strip()
    mission_id = str(parameters.get("mission_id", "")).strip()

    if action_type == "list":
        missions = central_core.get_swarm_missions()
        if not missions:
            return "No active or recent Swarm War Room missions found."
        lines = [
            f"• [{m['mission_id'][:8]}] State: {m['state']} — Objective: {m['objective'][:60]}"
            for m in missions[-5:]
        ]
        return "Recent Swarm Missions:\n" + "\n".join(lines)

    if action_type == "status":
        if not mission_id:
            missions = central_core.get_swarm_missions()
            if not missions:
                return "No active Swarm mission to check."
            m = missions[-1]
        else:
            m_obj = swarm_war_room.get_mission(mission_id)
            m = m_obj.to_dict() if m_obj else None

        if not m:
            return f"Swarm mission '{mission_id}' not found."

        deliv_count = len(m.get("deliverables", []))
        return (
            f"Swarm Mission [{m['mission_id'][:8]}]\n"
            f"State: {m['state']}\n"
            f"Objective: {m['objective']}\n"
            f"Deliverables generated: {deliv_count}\n"
            f"Summary: {m.get('final_summary', 'In progress...')}"
        )

    if not objective:
        return "Error: 'objective' is required to dispatch a Swarm War Room mission."

    mid = central_core.dispatch_swarm_mission(objective)
    return (
        f"Swarm War Room Mission [{mid[:8]}] launched successfully. "
        f"Architect, Coder, Critic, and DevOps lanes are now actively synthesizing."
    )


TOOL = {
    "name": "run_swarm_war_room",
    "description": (
        "Dispatches an autonomous 4-agent Swarm War Room mission (Architect, Coder, Critic, DevOps). "
        "Use when the user wants comprehensive multi-perspective engineering, system design, "
        "thorough review, or collaborative code generation."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "objective": {
                "type": "STRING",
                "description": "The complex engineering specification or mission objective for the swarm.",
            },
            "action_type": {
                "type": "STRING",
                "description": "'dispatch' to launch a mission, 'status' to check progress, or 'list' to view recent missions.",
            },
            "mission_id": {
                "type": "STRING",
                "description": "Optional mission ID when checking status.",
            },
        },
        "required": ["objective"],
    },
    "handler": run_swarm_war_room,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
