"""
tests/test_tools.py — Unit and integration tests for neo.tools and system info.
"""
from __future__ import annotations

import time
import pytest

from neo.safety import get_confirmation_gate
from neo.tools import (
    RiskLevel,
    ToolDefinition,
    ToolRegistry,
    clipboard_get,
    clipboard_set,
    get_battery,
    get_current_datetime,
    get_disk,
    get_network,
    get_running_apps,
    get_tool_registry,
)


def test_tool_registry_schemas_and_listing():
    reg = get_tool_registry()
    tools = reg.list_tools()
    assert len(tools) >= 7

    tool_names = {t["name"] for t in tools}
    assert "get_current_datetime" in tool_names
    assert "get_battery" in tool_names
    assert "get_disk" in tool_names
    assert "get_network" in tool_names
    assert "get_running_apps" in tool_names
    assert "clipboard_get" in tool_names
    assert "clipboard_set" in tool_names

    # Check JSON schema structure
    for t in tools:
        assert "description" in t
        assert "parameters" in t
        assert t["parameters"]["type"] == "object"
        assert "risk_level" in t


def test_current_datetime_tool():
    res = get_current_datetime()
    assert res.ok is True
    assert res.source == "system.datetime"
    assert res.timestamp > 0
    assert "local_iso" in res.data
    assert "utc_iso" in res.data
    assert "timezone" in res.data


def test_battery_tool():
    res = get_battery()
    assert res.ok is True
    assert res.source == "system.battery"
    assert res.timestamp > 0
    assert "percent" in res.data
    assert "power_plugged" in res.data


def test_disk_tool():
    res = get_disk(path="C:\\")
    assert res.ok is True
    assert res.source == "system.disk"
    assert res.timestamp > 0
    assert res.data["total_gb"] > 0
    assert res.data["free_gb"] >= 0


def test_network_tool():
    res = get_network()
    assert res.ok is True
    assert res.source == "system.network"
    assert res.timestamp > 0
    assert "hostname" in res.data
    assert "primary_ip" in res.data


def test_running_apps_tool():
    res = get_running_apps()
    assert res.ok is True
    assert res.source == "system.running_apps"
    assert res.timestamp > 0
    assert "apps" in res.data
    assert isinstance(res.data["apps"], list)


def test_clipboard_round_trip():
    """
    Sets Unicode text in the Windows clipboard and reads it back,
    empirically verifying text integrity, timestamp, and source attribution.
    """
    secret_text = f"NEO Clipboard Roundtrip Test {time.time()}"

    set_res = clipboard_set(secret_text)
    assert set_res.ok is True
    assert set_res.source == "system.clipboard"
    assert set_res.evidence.get("verified") is True

    get_res = clipboard_get()
    assert get_res.ok is True
    assert get_res.source == "system.clipboard"
    assert get_res.data == secret_text


def test_tool_registry_high_risk_execution_gating():
    """Verifies that high-risk registered tools evaluate ConfirmationGate before dispatch."""
    reg = ToolRegistry()

    invoked = False
    def dangerous_action(target: str) -> str:
        nonlocal invoked
        invoked = True
        return f"Executed on {target}"

    reg.register(
        ToolDefinition(
            name="format_partition",
            description="High risk disk format",
            parameters_schema={"type": "object", "properties": {"target": {"type": "string"}}},
            risk_level=RiskLevel.HIGH,
            handler=dangerous_action,
        )
    )

    gate = get_confirmation_gate()

    # 1. Deny
    gate.set_handler(lambda *args: (False, "Declined dangerous tool"))
    res_denied = reg.execute("format_partition", {"target": "D:\\"})
    assert res_denied.ok is False
    assert "denied by confirmation gate" in res_denied.error
    assert invoked is False

    # 2. Approve
    gate.set_handler(lambda *args: (True, "Approved by admin"))
    res_approved = reg.execute("format_partition", {"target": "D:\\"})
    assert res_approved.ok is True
    assert res_approved.data == "Executed on D:\\"
    assert invoked is True

    gate.set_handler(None)
