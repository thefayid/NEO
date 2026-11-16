"""
tests/test_actions_unit.py — Unit tests for neo/windows/actions.py.

Verifies:
- Whitelist and parameter validation with Pydantic (clear errors for LLM).
- Settle polling helper logic (success and timeout).
- Stale snapshot ID and non-existent element ID handling.
- Mandatory warning when action has no observable effect on UI state.
- Verification logic for matching and mismatching readback.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from neo.windows.actions import (
    ACTION_WHITELIST,
    ActionRequest,
    ActionResult,
    execute_action,
    wait_for_ui_settle,
)
from neo.windows.uia_snapshot import (
    SnapshotRegistry,
    UIAElement,
    UIASnapshot,
)


def test_whitelist_validation():
    """Verifies that unknown actions are strictly rejected with an informative error message."""
    # Unknown action
    res = execute_action({"action": "self_destruct"})
    assert res.ok is False
    assert res.verified == "false"
    assert "Unknown action 'self_destruct'" in res.warning
    assert "whitelist" in res.warning

    # Valid whitelisted actions construct cleanly
    for act in ACTION_WHITELIST:
        payload = {"action": act}
        if act in ("type", "set_text"):
            payload["text"] = "sample text"
        elif act == "press_key":
            payload["key"] = "enter"
        elif act == "hotkey":
            payload["keys"] = ["ctrl", "c"]
        elif act in ("open", "focus"):
            payload["target"] = "calc.exe"

        req = ActionRequest(**payload)
        assert req.action == act


def test_parameter_requirements_validation():
    """Verifies that each action enforces its required parameters."""
    # type missing text
    res = execute_action({"action": "type"})
    assert res.ok is False
    assert "requires the 'text' parameter" in res.warning

    # press_key missing key
    res = execute_action({"action": "press_key"})
    assert res.ok is False
    assert "requires the 'key' parameter" in res.warning

    # hotkey missing keys
    res = execute_action({"action": "hotkey"})
    assert res.ok is False
    assert "requires a non-empty list of 'keys'" in res.warning

    # open missing target
    res = execute_action({"action": "open"})
    assert res.ok is False
    assert "requires 'target'" in res.warning

    # element_id without snapshot_id
    res = execute_action({"action": "click", "element_id": 5})
    assert res.ok is False
    assert "requires accompanying 'snapshot_id'" in res.warning


def test_stale_and_nonexistent_element_ids():
    """Verifies that stale or non-existent element IDs return clear, readable errors for the LLM."""
    reg = SnapshotRegistry()

    # 1. Action with obsolete/unknown snapshot_id
    res_stale = execute_action(
        {"action": "click", "snapshot_id": "snap_expired_999", "element_id": 1},
        registry=reg,
    )
    assert res_stale.ok is False
    assert res_stale.verified == "false"
    assert "StaleElementError" in res_stale.warning
    assert "take a fresh snapshot" in res_stale.warning

    # 2. Register a snapshot, but query non-existent element ID
    elem1 = UIAElement(
        id=1,
        snapshot_id="snap_active_1",
        control_type="Button",
        name="Submit",
        automation_id="btnSubmit",
        enabled=True,
        value=None,
        bounding_rect=(10, 10, 100, 50),
    )
    snap = UIASnapshot(
        snapshot_id="snap_active_1",
        hwnd=9999,
        window_title="Active Form",
        elements=[elem1],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=1,
        duration_ms=5.0,
    )
    reg.register(snap, {1: MagicMock()})

    res_missing = execute_action(
        {"action": "click", "snapshot_id": "snap_active_1", "element_id": 999},
        registry=reg,
    )
    assert res_missing.ok is False
    assert res_missing.verified == "false"
    assert "ElementNotFoundError" in res_missing.warning
    assert "Element ID 999 not found" in res_missing.warning


def test_action_with_no_observable_effect_returns_warning():
    """
    CRITICAL RULE: An action with no observable effect must return a warning,
    NEVER plain success.
    """
    reg = SnapshotRegistry()
    mock_wrapper = MagicMock()
    mock_wrapper.is_password.return_value = False
    mock_elem_info = MagicMock()
    mock_elem_info.element.CurrentIsPassword = 0
    mock_elem_info.element.GetCurrentPropertyValue.return_value = 0
    mock_elem_info.control_type = "Text"
    mock_elem_info.name = "Static Label"
    mock_elem_info.automation_id = "lblStatic"
    mock_wrapper.element_info = mock_elem_info
    del mock_wrapper.iface_invoke  # No invoke pattern
    del mock_wrapper.iface_toggle
    del mock_wrapper.iface_selection_item
    del mock_wrapper.iface_value
    del mock_wrapper.iface_range_value
    mock_wrapper.window_text.return_value = "Static Label"

    elem = UIAElement(
        id=1,
        snapshot_id="snap_static",
        control_type="Text",
        name="Static Label",
        automation_id="lblStatic",
        enabled=True,
        value=None,
        bounding_rect=(100, 100, 200, 130),
    )
    snap = UIASnapshot(
        snapshot_id="snap_static",
        hwnd=5555,
        window_title="Static App",
        elements=[elem],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=1,
        duration_ms=5.0,
    )
    reg.register(snap, {1: mock_wrapper})

    with patch("neo.windows.actions.click_coords") as mock_click, \
         patch("neo.windows.actions.foreground") as mock_fg:
        from neo.windows.core import WindowInfo, WindowsResult
        mock_click.return_value = WindowsResult(ok=True, evidence={"coords": (150, 115)})
        mock_fg.return_value = WindowsResult(
            ok=True,
            data=WindowInfo(hwnd=5555, title="Static App", process_name="test.exe", pid=100),
        )

        res = execute_action(
            {"action": "click", "snapshot_id": "snap_static", "element_id": 1, "settle_timeout": 0.2},
            registry=reg,
        )

        assert res.ok is True
        assert res.verified != "true"
        assert res.warning is not None
        assert "no observable effect" in res.warning.lower()


def test_wait_for_ui_settle():
    """Verifies dynamic settle polling terminates quickly upon change and times out properly."""
    # Condition met on 3rd poll
    call_count = 0
    def condition_met():
        nonlocal call_count
        call_count += 1
        return {"data": "ready"} if call_count >= 3 else None

    settled, res = wait_for_ui_settle(condition_met, timeout_sec=1.0, poll_interval=0.01, debounce_sec=0.01)
    assert settled is True
    assert res == {"data": "ready"}
    assert call_count >= 3

    # Condition never met -> times out
    settled_to, res_to = wait_for_ui_settle(lambda: None, timeout_sec=0.1, poll_interval=0.02, debounce_sec=0)
    assert settled_to is False
    assert res_to is None


def test_action_safety_gating_and_hard_stops():
    """Verifies risky actions trigger confirmation gate and hard stops block execution."""
    from neo.safety import get_confirmation_gate

    gate = get_confirmation_gate()

    # 1. Hard stop test (element name contains 'Pay Now')
    mock_elem = UIAElement(
        snapshot_id="snap_hardstop",
        id=99,
        control_type="Button",
        name="Pay Now $500",
        automation_id="btnPay",
        enabled=True,
        value=None,
        bounding_rect=(10, 10, 50, 50),
    )
    reg = SnapshotRegistry()
    reg.register(
        UIASnapshot(
            snapshot_id="snap_hardstop",
            hwnd=123,
            window_title="Checkout",
            elements=[mock_elem],
            is_sparse=False,
            timestamp=12345.0,
            total_elements_scanned=1,
            duration_ms=10.0,
        ),
        {99: MagicMock()},
    )

    res_hardstop = execute_action(
        {"action": "click", "snapshot_id": "snap_hardstop", "element_id": 99},
        registry=reg,
    )
    assert res_hardstop.ok is False
    assert res_hardstop.verified == "false"
    assert "HardStopRequiredError" in (res_hardstop.warning or "")
    assert res_hardstop.evidence.get("hard_stop") is True

    # 2. Risky action test - Denied
    gate.set_handler(lambda assessment: (False, "User declined dangerous format command"))
    res_denied = execute_action(
        {"action": "type", "text": "format c: /fs:NTFS"},
        registry=reg,
    )
    assert res_denied.ok is False
    assert res_denied.verified == "false"
    assert "ConfirmationDeniedError" in (res_denied.warning or "")
    assert res_denied.evidence.get("denied") is True

    # Reset handler
    gate.set_handler(None)

