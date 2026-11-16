"""
tests/test_actions_integration.py — Live integration tests for neo/windows/actions.py.

Verifies against live Windows applications (Calculator, Settings, Notepad):
- Click a Calculator number button and verify the display updates with real evidence.
- Type/set_text and read back text from an input control.
- Deliberate wrong element ID and stale snapshot ID handling.
- Mandatory warning when an action has no observable effect.
"""
from __future__ import annotations

import platform
import time
from typing import Generator

import pytest

from neo.config import load_settings
from neo.safety.emergency_stop import emergency_stop
from neo.windows.actions import execute_action
from neo.windows.core import (
    ensure_desktop_attached,
    focus_window,
    list_windows,
    open_target,
)
from neo.windows.uia_snapshot import get_active_registry, snapshot


@pytest.fixture(autouse=True)
def setup_windows_env() -> Generator[None, None, None]:
    if platform.system() != "Windows":
        pytest.skip("Windows only integration tests.")
    load_settings(allowed_apps=["calc.exe", "notepad.exe"])
    emergency_stop.reset()
    ensure_desktop_attached()
    yield
    emergency_stop.reset()


def _ensure_calc_active() -> None:
    """Ensures Calculator is running, focused, and cleared."""
    res_list = list_windows(only_visible=True)
    calc_hwnd = None
    for w in res_list.data:
        if "calc" in w.title.lower() and "frame" in w.process_name.lower():
            calc_hwnd = w.hwnd
            break

    if not calc_hwnd:
        open_target("calc.exe")
        time.sleep(1.2)

    focus_window("Calculator", timeout_sec=3.0)
    time.sleep(0.3)


@pytest.mark.windows_only
def test_click_calculator_button_and_check_display():
    """Clicks a Calculator button ('5') and empirically verifies the display updates."""
    _ensure_calc_active()

    # Clear Calculator by pressing Escape
    execute_action({"action": "press_key", "key": "escape"})
    time.sleep(0.2)

    # Take fresh snapshot
    snap = snapshot("Calculator", timeout_sec=4.0)
    assert len(snap.elements) > 0

    # Locate button '5'
    btn_5 = None
    for elem in snap.elements:
        if elem.automation_id == "num5Button" or elem.name in ("Five", "5"):
            btn_5 = elem
            break
    assert btn_5 is not None, "Button '5' not found in Calculator snapshot."

    # Locate display element
    disp_elem = None
    for elem in snap.elements:
        if elem.automation_id == "CalculatorResults" or "display" in elem.name.lower():
            disp_elem = elem
            break
    assert disp_elem is not None, "Display element not found in Calculator snapshot."

    # Click button '5'
    res = execute_action({
        "action": "click",
        "snapshot_id": snap.snapshot_id,
        "element_id": btn_5.id,
        "settle_timeout": 1.5,
    })

    assert res.ok is True, f"Click failed: {res.warning}"

    # Read back display value
    snap_after = snapshot("Calculator", timeout_sec=4.0)
    disp_after = None
    for elem in snap_after.elements:
        if elem.automation_id == "CalculatorResults" or "display" in elem.name.lower():
            disp_after = elem
            break

    assert disp_after is not None
    # In Windows 11 Calculator, disp_after.name is 'Display is 5'
    assert "5" in disp_after.name, f"Expected display to contain '5', found '{disp_after.name}'"


@pytest.mark.windows_only
def test_type_then_read_back_live():
    """Types text into an input control and reads it back to verify equality."""
    # Attempt on Settings Search Box
    import subprocess
    subprocess.Popen(["cmd.exe", "/c", "start", "ms-settings:"])
    time.sleep(1.5)
    focus_window("Settings", timeout_sec=4.0)
    time.sleep(0.5)

    snap = snapshot("Settings", timeout_sec=4.0)
    search_edit = None
    for elem in snap.elements:
        if elem.control_type == "Edit" or "search" in elem.automation_id.lower() or "search" in elem.name.lower():
            search_edit = elem
            break

    if not search_edit:
        pytest.skip("No accessible Edit control found in Settings on host OS.")

    test_query = "Sound"
    # Use set_text
    res_set = execute_action({
        "action": "set_text",
        "snapshot_id": snap.snapshot_id,
        "element_id": search_edit.id,
        "text": test_query,
        "settle_timeout": 1.5,
    })

    assert res_set.ok is True, f"set_text failed: {res_set.warning}"

    # Read back value via read action
    res_read = execute_action({
        "action": "read",
        "snapshot_id": snap.snapshot_id,
        "element_id": search_edit.id,
    })

    assert res_read.ok is True
    assert res_read.verified == "true"
    read_val = str(res_read.data or res_read.evidence.get("value") or res_read.evidence.get("name") or "")
    assert test_query.lower() in read_val.lower()


@pytest.mark.windows_only
def test_deliberate_wrong_id_action_live():
    """Verifies that attempting an action with an invalid or stale ID returns ok=False with a clear error."""
    _ensure_calc_active()
    snap = snapshot("Calculator")

    # 1. Deliberate non-existent element ID
    res_wrong_id = execute_action({
        "action": "click",
        "snapshot_id": snap.snapshot_id,
        "element_id": 88888,
    })
    assert res_wrong_id.ok is False
    assert res_wrong_id.verified == "false"
    assert "ElementNotFoundError" in res_wrong_id.warning
    assert "88888" in res_wrong_id.warning

    # 2. Deliberate stale / non-existent snapshot ID
    res_wrong_snap = execute_action({
        "action": "click",
        "snapshot_id": "snap_bogus_snapshot_000",
        "element_id": 1,
    })
    assert res_wrong_snap.ok is False
    assert res_wrong_snap.verified == "false"
    assert "StaleElementError" in res_wrong_snap.warning


@pytest.mark.windows_only
def test_action_that_changes_nothing_live():
    """
    Verifies that executing a click on an element that produces no state change
    returns a warning, NEVER plain success.
    """
    _ensure_calc_active()
    snap = snapshot("Calculator")

    # Clicking on the Display text box itself produces no state delta
    disp_elem = None
    for elem in snap.elements:
        if elem.automation_id == "CalculatorResults" or "display" in elem.name.lower():
            disp_elem = elem
            break

    assert disp_elem is not None

    res = execute_action({
        "action": "click",
        "snapshot_id": snap.snapshot_id,
        "element_id": disp_elem.id,
        "settle_timeout": 0.5,
    })

    # Action executed without error, but produced no observable UI change
    assert res.ok is True
    assert res.verified != "true"
    assert res.warning is not None
    assert "warning" in res.to_dict()
    assert len(res.warning) > 0
