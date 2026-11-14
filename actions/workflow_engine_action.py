"""
actions/workflow_engine_action.py — Deterministic Workflow Engine Action for NEO.

Provides single-command execution of multi-step workstation routines:
- Run built-in routines: 'dev_workspace', 'focus_mode', 'system_tuneup', 'meeting_prep'.
- List available automated routines.
- Create and persist custom multi-step automation routines.
"""
from __future__ import annotations

from typing import Any, Dict
from core.neo_workflow_engine import workflow_engine
from core import outcome

TOOL = {
    "name": "workflow_engine",
    "description": (
        "Execute multi-step deterministic workstation routines and macros with zero LLM latency. "
        "Use this tool when the user says 'set up my dev workspace', 'start focus mode', "
        "'tune up the system', 'run routine X', or wants to automate recurring workstation setups."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'execute_routine' to run a routine, 'list_routines' to see available, 'create_routine' to register a new one.",
                "enum": ["execute_routine", "list_routines", "create_routine"]
            },
            "routine_name": {
                "type": "STRING",
                "description": "Name of the routine (e.g. 'dev_workspace', 'focus_mode', 'system_tuneup', 'meeting_prep')."
            },
            "description": {
                "type": "STRING",
                "description": "Description when creating a new routine."
            },
            "steps": {
                "type": "ARRAY",
                "description": "List of step dictionaries [{'tool': 'os_control', 'params': {...}}] for create_routine.",
                "items": {"type": "OBJECT"}
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = (params.get("action") or "list_routines").strip().lower()

    if action == "execute_routine":
        r_name = params.get("routine_name") or ""
        if not r_name:
            return outcome.failed("workflow_engine", "No routine name specified.")
        
        res = workflow_engine.execute_routine(r_name, player=player)
        if not res.get("success"):
            return outcome.failed("workflow_engine", res.get("message"))

        return outcome.done(
            "workflow_engine",
            routine=res.get("routine"),
            steps_executed=res.get("steps_count"),
            elapsed_seconds=res.get("elapsed_seconds"),
            message=res.get("message")
        )

    elif action == "list_routines":
        routines = workflow_engine.list_routines()
        names = [f"{r['name']} ({r['steps_count']} steps): {r['description']}" for r in routines]
        return outcome.done("workflow_engine", count=len(routines), routines=names)

    elif action == "create_routine":
        r_name = params.get("routine_name") or ""
        desc = params.get("description") or "Custom user routine"
        steps = params.get("steps") or []
        if not r_name or not steps:
            return outcome.failed("workflow_engine", "Both 'routine_name' and 'steps' are required to create a routine.")

        ok = workflow_engine.register_routine(r_name, desc, steps)
        if ok:
            return outcome.done("workflow_engine", created=r_name, steps=len(steps), message=f"Routine '{r_name}' registered successfully.")
        return outcome.failed("workflow_engine", f"Failed registering routine '{r_name}'.")

    return outcome.failed("workflow_engine", f"Unknown action '{action}'.")
