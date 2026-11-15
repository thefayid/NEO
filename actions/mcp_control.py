"""
actions/mcp_control.py — Model Context Protocol (MCP) Control & Discovery Action for NEO.

Allows NEO to inspect connected MCP servers, list active external tools, check
diagnostics, and invoke MCP tools.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core import outcome
from core.neo_mcp_bridge import mcp_bridge


def mcp_control(parameters: Dict[str, Any], **kwargs) -> str:
    """Manages Model Context Protocol (MCP) integrations."""
    action = parameters.get("action", "list_servers")

    # Ensure bridge is initialized
    mcp_bridge.initialize()

    if action == "list_servers":
        summary = mcp_bridge.list_servers_summary()
        if not summary:
            return outcome.done(
                "mcp_control",
                message="No MCP servers configured in config/mcp_servers.json.",
                servers=[],
            )

        servers_data = [
            {
                "name": s.name,
                "command": s.command,
                "enabled": s.enabled,
                "connected": s.connected,
                "tool_count": s.tool_count,
                "error": s.error,
            }
            for s in summary
        ]
        return outcome.done(
            "mcp_control",
            total_servers=len(summary),
            connected_servers=sum(1 for s in summary if s.connected),
            servers=servers_data,
        )

    elif action == "list_tools":
        decls = mcp_bridge.get_tool_declarations()
        if not decls:
            return outcome.done(
                "mcp_control",
                message="No active MCP tools currently discovered.",
                tools=[],
            )
        tools_list = [
            {
                "name": d["name"],
                "description": d["description"],
                "brief": d.get("brief", ""),
            }
            for d in decls
        ]
        return outcome.done(
            "mcp_control",
            total_tools=len(tools_list),
            tools=tools_list,
        )

    elif action == "call_tool":
        tool_name = parameters.get("tool_name", "")
        tool_args = parameters.get("tool_args", {})
        if not tool_name:
            return outcome.failed("mcp_control", "Missing 'tool_name' parameter for call_tool.")

        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except Exception:
                tool_args = {}

        result = mcp_bridge.run(tool_name, tool_args)
        return outcome.done("mcp_control", tool=tool_name, result=result)

    elif action == "refresh":
        mcp_bridge.shutdown()
        mcp_bridge.initialize()
        summary = mcp_bridge.list_servers_summary()
        return outcome.done(
            "mcp_control",
            status="refreshed",
            active_servers=sum(1 for s in summary if s.connected),
            total_tools=len(mcp_bridge.get_tool_declarations()),
        )

    return outcome.failed(
        "mcp_control",
        f"Unknown action '{action}'. Supported: list_servers, list_tools, call_tool, refresh.",
    )


TOOL = {
    "name": "mcp_control",
    "description": (
        "Inspect and manage Model Context Protocol (MCP) servers and external tools. "
        "Allows querying connected external databases, cloud services, and developer tools. "
        "Supported actions: 'list_servers', 'list_tools', 'call_tool', 'refresh'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["list_servers", "list_tools", "call_tool", "refresh"],
                "description": "The MCP action to execute. Default is 'list_servers'.",
            },
            "tool_name": {
                "type": "STRING",
                "description": "Name of the MCP tool to execute (required when action='call_tool').",
            },
            "tool_args": {
                "type": "OBJECT",
                "description": "Arguments dictionary to pass to the MCP tool (for action='call_tool').",
            },
        },
        "required": ["action"],
    },
    "handler": mcp_control,
    "tier": "extra",
    "brief": "Inspect and invoke Model Context Protocol (MCP) tools and servers.",
}
