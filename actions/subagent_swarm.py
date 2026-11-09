"""
actions/subagent_swarm.py — F.R.I.D.A.Y. Autonomous Subagent Swarm & Task Delegation (Feature 4).

Enables F.R.I.D.A.Y. to delegate complex, multi-step parallel background tasks:
  • spawn_agent: Dispatches a dedicated worker subagent (web_researcher, code_reviewer, data_analyst, doc_writer) with specialized prompts.
  • list_agents: Shows all active/completed background tasks and their current execution state.
  • get_results: Retrieves completed deliverables without interrupting or locking the live voice session.
"""
from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import uuid
from typing import Optional

from core import gemini, outcome

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5, thread_name_prefix="SubagentWorker")
_TASK_REGISTRY: dict[str, dict] = {}
_LOCK = threading.Lock()


def _run_worker_task(task_id: str, role: str, instruction: str) -> None:
    """Executes the subagent task in the background using Gemini."""
    with _LOCK:
        if task_id in _TASK_REGISTRY:
            _TASK_REGISTRY[task_id]["status"] = "RUNNING"
            _TASK_REGISTRY[task_id]["started_at"] = time.strftime("%H:%M:%S")

    system_prompts = {
        "web_researcher": (
            "You are an elite research agent for Tony Stark. Synthesize deep facts, verify dates, "
            "and output an executive summary with bulleted actionable findings."
        ),
        "code_reviewer": (
            "You are an expert senior security & systems architect. Review this codebase/snippet "
            "for concurrency bugs, memory leaks, performance traps, and provide exact diff recommendations."
        ),
        "data_analyst": (
            "You are a quantitative intelligence analyst. Extract key metrics, trends, statistical "
            "outliers, and structured summaries from the data."
        ),
        "doc_writer": (
            "You are an executive technical writer. Create polished, clean Markdown documentation, "
            "API reference, or user briefings."
        ),
    }

    sp = system_prompts.get(role, "You are a specialized autonomous background agent for F.R.I.D.A.Y.")
    full_prompt = f"{sp}\n\nTask:\n{instruction}"

    try:
        resp = gemini.text(full_prompt, tier=gemini.FAST, timeout_ms=45000)
        output = resp if resp else "Agent completed task with empty response."
        status = "COMPLETED"
    except Exception as e:
        output = f"Subagent error: {e}"
        status = "FAILED"

    with _LOCK:
        if task_id in _TASK_REGISTRY:
            _TASK_REGISTRY[task_id]["status"] = status
            _TASK_REGISTRY[task_id]["output"] = output
            _TASK_REGISTRY[task_id]["finished_at"] = time.strftime("%H:%M:%S")
            _notify_ui(list(_TASK_REGISTRY.values()))


_CACHED_PLAYER = None


def _notify_ui(tasks: list[dict]):
    if _CACHED_PLAYER and hasattr(_CACHED_PLAYER, "update_swarm_cards"):
        try:
            _CACHED_PLAYER.update_swarm_cards(tasks)
        except Exception:
            pass


def spawn_subagent(role: str, instruction: str, player=None) -> str:
    """Spawn a background agent worker."""
    global _CACHED_PLAYER
    if player:
        _CACHED_PLAYER = player

    task_id = f"swarm-{uuid.uuid4().hex[:6]}"
    with _LOCK:
        _TASK_REGISTRY[task_id] = {
            "id": task_id,
            "role": role,
            "instruction": instruction[:120] + ("..." if len(instruction) > 120 else ""),
            "status": "QUEUED",
            "output": None,
            "created_at": time.strftime("%H:%M:%S"),
        }
        _notify_ui(list(_TASK_REGISTRY.values()))

    _EXECUTOR.submit(_run_worker_task, task_id, role, instruction)
    return (
        f"[SWARM AGENT DEPLOYED]\n"
        f"• Task ID: {task_id}\n"
        f"• Agent Unit: {role.upper()}\n"
        f"• Status: Dispatched in background. You can continue speaking while it processes."
    )


def list_subagents() -> str:
    """List status of all background worker tasks."""
    with _LOCK:
        if not _TASK_REGISTRY:
            return "[SWARM REGISTRY]\nNo active background agents running."

        lines = ["[SWARM AGENT REGISTRY]"]
        for tid, t in _TASK_REGISTRY.items():
            status_symbol = "●" if t["status"] == "RUNNING" else ("✓" if t["status"] == "COMPLETED" else "✗")
            lines.append(f"{status_symbol} [{tid}] ({t['role']}) {t['status']} — \"{t['instruction']}\"")
        return "\n".join(lines)


def get_agent_results(task_id: str) -> str:
    """Retrieve the deliverable from a finished agent."""
    with _LOCK:
        task = _TASK_REGISTRY.get(task_id)
        if not task:
            return f"No subagent found with ID '{task_id}'."
        if task["status"] == "RUNNING" or task["status"] == "QUEUED":
            return f"Agent '{task_id}' is still active ({task['status']}). Awaiting deliverable."
        return f"[SWARM DELIVERABLE — {task_id.upper()}]\n{task['output']}"


def subagent_swarm(parameters: dict | None = None, **kwargs) -> str:
    """Main dispatch for Stark Subagent Swarm."""
    params = parameters or {}
    action = str(params.get("action", "list")).strip().lower()
    player = kwargs.get("player")

    if action in ("spawn", "delegate", "start", "run"):
        role = str(params.get("role", "web_researcher")).strip().lower()
        instruction = str(params.get("instruction", "")).strip()
        if not instruction:
            return "Please specify an instruction or task description for the agent."
        return spawn_subagent(role, instruction, player=player)
    elif action in ("results", "get", "fetch", "result"):
        task_id = str(params.get("task_id", "")).strip().lower()
        return get_agent_results(task_id)
    else:
        return list_subagents()


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "subagent_swarm",
    "description": (
        "Stark Subagent Swarm & Autonomous Task Delegation. "
        "Allows F.R.I.D.A.Y. to delegate heavy reasoning, background web research, code reviews, "
        "or report drafting to parallel background worker agents without locking speech. "
        "Actions: "
        "'spawn' (Deploy background subagent with 'role' and 'instruction') | "
        "'list' (Show status of all background worker agents) | "
        "'results' (Fetch finished work for a given 'task_id'). "
        "Roles: 'web_researcher', 'code_reviewer', 'data_analyst', 'doc_writer'. "
        "Call when user asks to delegate a task, run background analysis, or check subagent progress."
    ),
    "brief": "Autonomous subagent swarm: spawn parallel worker agents, list status, and retrieve results.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'spawn' | 'list' | 'results'",
                "enum": ["spawn", "list", "results"],
            },
            "role": {
                "type": "STRING",
                "description": "Subagent role: 'web_researcher' | 'code_reviewer' | 'data_analyst' | 'doc_writer'",
                "enum": ["web_researcher", "code_reviewer", "data_analyst", "doc_writer"],
            },
            "instruction": {
                "type": "STRING",
                "description": "The detailed task or research prompt for the subagent.",
            },
            "task_id": {
                "type": "STRING",
                "description": "The ID of the task to retrieve results for (e.g. 'swarm-a1b2c3').",
            },
        },
    },
    "handler": subagent_swarm,
}
