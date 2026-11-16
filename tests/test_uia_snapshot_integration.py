"""
tests/test_uia_snapshot_integration.py — Live integration tests for UIA snapshot.

Tests against live Windows applications (Calculator, Settings, Notepad):
- Full accessibility tree snapshotting into numbered elements.
- Element attribute extraction: id, control_type, name, automation_id, enabled, value, bounding_rect.
- Region filtering and control type whitelist filtering.
- Capacity capping (max_elements) and truncation flag.
- Live stale-ID rejection when sequential snapshots are taken.
"""
from __future__ import annotations

import platform
import time
from typing import Generator

import psutil
import pytest

from neo.config import load_settings
from neo.safety.emergency_stop import emergency_stop
from neo.windows.core import (
    ensure_desktop_attached,
    focus_window,
    list_windows,
    open_target,
)
from neo.windows.uia_snapshot import (
    SnapshotRegistry,
    StaleSnapshotError,
    UIASnapshot,
    get_active_registry,
    snapshot,
)


@pytest.fixture(autouse=True)
def setup_windows_env() -> Generator[None, None, None]:
    if platform.system() != "Windows":
        pytest.skip("Windows-only integration tests.")
    load_settings(allowed_apps=["calc.exe", "notepad.exe"])
    emergency_stop.reset()
    ensure_desktop_attached()
    yield
    emergency_stop.reset()


def _ensure_calculator_running() -> int:
    """Ensures Calculator is running and returns its live, verified HWND."""
    import ctypes
    user32 = ctypes.windll.user32

    calc_hwnd = None
    res_list = list_windows(only_visible=True)
    # Prefer the ApplicationFrameHost window on Windows 10/11 which hosts the XAML accessibility tree
    for w in res_list.data:
        if "calc" in w.title.lower() and "frame" in w.process_name.lower():
            if user32.IsWindow(w.hwnd) and user32.IsWindowVisible(w.hwnd):
                calc_hwnd = w.hwnd
                break

    if not calc_hwnd:
        for w in res_list.data:
            if "calc" in w.title.lower() or "calc" in w.process_name.lower():
                if user32.IsWindow(w.hwnd) and user32.IsWindowVisible(w.hwnd):
                    calc_hwnd = w.hwnd
                    break

    if not calc_hwnd:
        open_target("calc.exe")
        time.sleep(1.2)
        for _ in range(40):
            res_list = list_windows(only_visible=True)
            for w in res_list.data:
                if "calc" in w.title.lower() and "frame" in w.process_name.lower():
                    if user32.IsWindow(w.hwnd) and user32.IsWindowVisible(w.hwnd):
                        calc_hwnd = w.hwnd
                        break
            if calc_hwnd:
                break
            time.sleep(0.1)

    assert calc_hwnd is not None, "Calculator could not be launched or found."
    focus_window("Calculator", timeout_sec=3.0)
    time.sleep(0.3)
    return calc_hwnd


@pytest.mark.windows_only
def test_snapshot_calculator_live():
    """Verifies UIA snapshot on live Calculator produces a numbered, complete element list."""
    calc_hwnd = _ensure_calculator_running()

    snap = snapshot(calc_hwnd, timeout_sec=5.0)

    assert isinstance(snap, UIASnapshot)
    assert snap.hwnd == calc_hwnd
    assert len(snap.elements) >= 15, f"Expected >= 15 elements in Calculator, found {len(snap.elements)}"
    assert snap.is_sparse is False

    # Verify numbered IDs: 1, 2, 3 ... N
    expected_ids = list(range(1, len(snap.elements) + 1))
    actual_ids = [e.id for e in snap.elements]
    assert actual_ids == expected_ids

    # Verify attributes on elements
    button_found = False
    for elem in snap.elements:
        assert elem.snapshot_id == snap.snapshot_id
        assert elem.control_type != ""
        assert len(elem.bounding_rect) == 4
        l, t, r, b = elem.bounding_rect
        assert r > l and b > t, f"Invalid rect: {elem.bounding_rect}"
        if elem.control_type == "Button":
            button_found = True

    assert button_found is True, "Expected at least one Button control in Calculator."


@pytest.mark.windows_only
def test_snapshot_settings_live():
    """Verifies UIA snapshot against Windows Settings application."""
    res_list = list_windows(only_visible=True)
    settings_hwnd = None
    for w in res_list.data:
        if "setting" in w.title.lower() and "frame" in w.process_name.lower():
            settings_hwnd = w.hwnd
            break

    if not settings_hwnd:
        # Fallback to any settings window
        for w in res_list.data:
            if "setting" in w.title.lower():
                settings_hwnd = w.hwnd
                break

    if not settings_hwnd:
        pytest.skip("Settings window not currently active on desktop.")

    focus_window("Settings")
    time.sleep(0.5)

    snap = snapshot(settings_hwnd, max_elements=50, timeout_sec=5.0)
    assert snap.hwnd == settings_hwnd
    assert len(snap.elements) > 0
    assert snap.elements[0].id == 1


@pytest.mark.windows_only
def test_snapshot_notepad_live():
    """Verifies UIA snapshot against Notepad if functional on host OS."""
    open_target("notepad.exe")
    time.sleep(1.0)

    res_list = list_windows(only_visible=True)
    np_hwnd = None
    for w in res_list.data:
        if "notepad" in w.title.lower() or "notepad" in w.process_name.lower():
            np_hwnd = w.hwnd
            break

    if not np_hwnd:
        pytest.skip("Notepad window did not open (Store package issue on host OS).")

    focus_window("Notepad")
    time.sleep(0.3)
    snap = snapshot(np_hwnd, timeout_sec=4.0)
    assert snap.hwnd == np_hwnd
    assert len(snap.elements) > 0


@pytest.mark.windows_only
def test_snapshot_filtering_and_capping():
    """Verifies control type whitelist, region bounding box, and max_elements cap."""
    calc_hwnd = _ensure_calculator_running()

    # 1. Filter by control_types=['Button']
    snap_buttons = snapshot(calc_hwnd, control_types=["Button"])
    assert len(snap_buttons.elements) > 0
    for elem in snap_buttons.elements:
        assert elem.control_type == "Button"

    # 2. Capping with max_elements=5
    snap_capped = snapshot(calc_hwnd, max_elements=5)
    assert len(snap_capped.elements) == 5
    assert snap_capped.truncated is True

    # 3. Filter by region
    full_snap = snapshot(calc_hwnd)
    if full_snap.elements:
        # Take region of first 3 elements
        e0 = full_snap.elements[0]
        region = (e0.bounding_rect[0] - 5, e0.bounding_rect[1] - 5,
                  e0.bounding_rect[2] + 5, e0.bounding_rect[3] + 5)
        snap_reg = snapshot(calc_hwnd, region=region)
        assert len(snap_reg.elements) > 0
        for e in snap_reg.elements:
            l, t, r, b = e.bounding_rect
            # Check intersection
            assert not (r <= region[0] or l >= region[2] or b <= region[1] or t >= region[3])


@pytest.mark.windows_only
def test_live_stale_id_rejection():
    """Verifies registry rejects stale element IDs when a new snapshot supersedes."""
    calc_hwnd = _ensure_calculator_running()
    reg = get_active_registry()

    snap1 = snapshot(calc_hwnd, registry=reg)
    snap1_id = snap1.snapshot_id
    assert len(snap1.elements) > 0

    # Resolve element #1 on active snapshot 1
    elem, wrapper = reg.resolve(snap1_id, 1)
    assert elem.id == 1
    assert wrapper is not None

    # Take snapshot 2 (supersedes snapshot 1)
    time.sleep(0.1)
    snap2 = snapshot(calc_hwnd, registry=reg)
    snap2_id = snap2.snapshot_id
    assert snap2_id != snap1_id

    # Trying to resolve element #1 using snap1_id must fail with StaleSnapshotError
    with pytest.raises(StaleSnapshotError) as exc_info:
        reg.resolve(snap1_id, 1)
    assert f"Rejected stale element ID 1 from snapshot '{snap1_id}'" in str(exc_info.value)

    # Resolving on snap2_id succeeds
    elem2, wrapper2 = reg.resolve(snap2_id, 1)
    assert elem2.id == 1
    assert wrapper2 is not None
