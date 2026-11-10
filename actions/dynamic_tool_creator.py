"""
actions/dynamic_tool_creator.py — Dynamic Self-Tooling & Meta-Plugin Synthesizer Action for NEO.

Auto-discovered by core/action_loader.py. Allows Gemini Live and the Assistant to synthesize
and hot-register new Python capabilities at runtime without restarting the application.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from core.neo_self_tooling import synthesizer
from core.neo_brain import brain

_BASE_DIR = Path(__file__).resolve().parent.parent


def synthesize_custom_tool(parameters: dict, **kwargs) -> str:
    """Handler for runtime tool synthesis and listing."""
    action_type = str(parameters.get("action_type", "synthesize")).strip().lower()
    tool_name = str(parameters.get("tool_name", "")).strip()
    description = str(parameters.get("description", "")).strip()
    code_body = str(parameters.get("code_body", "")).strip()

    if action_type == "list":
        tools = synthesizer.list_synthesized_tools()
        if not tools:
            return "No dynamically synthesized tools registered yet."
        summary = [f"• {t['name']}: {t['description']}" for t in tools]
        return "Active Synthesized Capabilities:\n" + "\n".join(summary)

    if not tool_name or not code_body:
        return "Error: 'tool_name' and 'code_body' are required to synthesize a tool."

    desc = description or f"Dynamically synthesized tool for {tool_name}"
    ok, msg = synthesizer.synthesize_tool(tool_name, desc, code_body)
    if ok:
        brain.episodic.log_event("TOOL_SYNTHESIZED", f"Synthesized capability: {tool_name}")
        brain.graph.upsert_entity(tool_name, "TOOL", attributes={"description": desc})
        brain.graph.add_relation("NEO", tool_name, "OWNS_TOOL")
        return f"Success: {msg} The capability is now hot-loaded and available for execution."
    else:
        return f"Synthesis Failed: {msg}"


TOOL = {
    "name": "synthesize_custom_tool",
    "description": (
        "Dynamically creates, verifies via AST and sandbox, and hot-registers a new Python tool "
        "at runtime. Use when a requested task requires an API or calculation function that "
        "NEO does not currently possess. The new capability is saved, loaded into the action "
        "registry, and immediately callable without restarting NEO."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action_type": {
                "type": "STRING",
                "description": "Either 'synthesize' to create a new tool, or 'list' to show active synthesized tools.",
            },
            "tool_name": {
                "type": "STRING",
                "description": "Unique valid Python identifier for the tool (e.g. 'convert_currency').",
            },
            "description": {
                "type": "STRING",
                "description": "Explanation of what the tool accomplishes and how it should be used.",
            },
            "code_body": {
                "type": "STRING",
                "description": "Executable Python code with a function matching the tool_name or returning the result.",
            },
        },
        "required": ["action_type"],
    },
    "handler": synthesize_custom_tool,
}
