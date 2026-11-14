"""
actions/computer_operator_action.py — Autonomous Computer-Operator Action for NEO.

Provides autonomous computer-use execution:
- Deconstructs user goals into verified stages.
- Executes iterative Look -> Check -> Plan -> Act cycles.
- Verifies state transitions before claiming success.
- Automatically yields to user on security/payment gates.
"""
from __future__ import annotations

import json
from typing import Any, Dict
from core.neo_computer_operator import computer_operator_registry
from core import outcome

TOOL = {
    "name": "computer_operator",
    "description": (
        "Operates the computer autonomously to achieve a user goal: searches apps, navigates controls, "
        "types text, clicks buttons, and verifies each action against screen state changes. "
        "Follows strict Truth Rules: never guesses or chains blind actions. Pauses for user on payments, "
        "OTPs, and security checks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'start' to launch an autonomous operator loop, 'step' to execute a single turn, 'status' to inspect.",
                "enum": ["start", "step", "status"]
            },
            "goal": {
                "type": "STRING",
                "description": "The exact goal to achieve (e.g. 'Open Notepad and type release notes', 'Find audio settings')."
            },
            "max_turns": {
                "type": "INTEGER",
                "description": "Maximum autonomous turns to execute (default: 8)."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    act = (params.get("action") or "start").strip().lower()

    if act == "start":
        goal = params.get("goal") or ""
        if not goal:
            return outcome.failed("computer_operator", "No goal specified.")
        
        session = computer_operator_registry.create_session(goal)
        max_turns = int(params.get("max_turns") or 8)
        
        if player:
            try:
                player.write_log(f"OPERATOR: 🤖 Launching computer-operator loop for '{goal}' ({len(session.stages)} stages).")
            except Exception:
                pass

        turns = session.run_autonomous_loop(max_turns=max_turns)
        last_turn = turns[-1] if turns else {}

        if player:
            try:
                player.write_log(f"OPERATOR: Finished {len(turns)} turns. Status: {last_turn.get('action')}")
            except Exception:
                pass

        return outcome.done(
            "computer_operator",
            session_id=session.session_id,
            turns_executed=len(turns),
            final_stage=last_turn.get("current_stage"),
            final_action=last_turn.get("action"),
            observation_summary=last_turn.get("observation", "")[:200],
            message=f"Operator concluded {len(turns)} turns. Final action: '{last_turn.get('action')}'. Plan: '{last_turn.get('plan')}'"
        )

    elif act == "step":
        session = computer_operator_registry.get_active()
        if not session:
            return outcome.failed("computer_operator", "No active computer-operator session.")
        
        turn = session.step()
        return outcome.done(
            "computer_operator",
            turn=turn.get("turn_index", 1),
            stage=turn.get("current_stage"),
            action=turn.get("action"),
            plan=turn.get("plan"),
            last_result=turn.get("last_action_result")
        )

    elif act == "status":
        session = computer_operator_registry.get_active()
        if not session:
            return outcome.done("computer_operator", active=False, message="No active operator session.")
        
        return outcome.done(
            "computer_operator",
            active=not session.concluded,
            session_id=session.session_id,
            goal=session.goal,
            current_stage_idx=session.current_stage_idx,
            total_stages=len(session.stages),
            turns_executed=len(session.turns)
        )

    return outcome.failed("computer_operator", f"Unknown action '{act}'.")
