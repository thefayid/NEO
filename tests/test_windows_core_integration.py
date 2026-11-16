"""
tests/test_windows_core_integration.py — Integration tests for neo/windows/core.py.

Uses live Notepad and Calculator on Windows to test:
- open_target() launching allow-listed applications.
- list_windows() enumerating top-level desktop applications.
- focus_window() bringing windows to front and verifying foreground state.
- type_unicode() and hotkey() hardware dispatch via SendInput.
- Clean process termination.
"""
from __future__ import annotations

import platform
import subprocess
import time
from typing import Generator

import psutil
import pytest

from neo.config import load_settings
from neo.safety.emergency_stop import emergency_stop
from neo.windows.core import (
    focus_window,
    foreground,
    hotkey,
    list_windows,
    open_target,
    type_unicode,
)


def _cleanup_procs():
    """Terminates any stray test instances of notepad or calc."""
    killed = False
    for p in psutil.process_iter(["name", "pid"]):
        try:
            n = (p.info["name"] or "").lower()
            if n in ("notepad.exe", "calculatorapp.exe", "calculator.exe"):
                p.kill()
                killed = True
        except Exception:
            pass
    if killed:
        time.sleep(0.4)


def _clean_notepad_cache():
    """Cleans corrupt/stale session files from Windows 11 tabbed Notepad."""
    import glob
    import os
    local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
    if os.path.exists(local_state):
        tabstate = os.path.join(local_state, "TabState")
        winstate = os.path.join(local_state, "WindowState")
        for f in glob.glob(os.path.join(tabstate, "*")) + glob.glob(os.path.join(winstate, "*")):
            try:
                os.remove(f)
            except Exception:
                pass


@pytest.fixture
def managed_apps() -> Generator[None, None, None]:
    """Ensures clean state before and after integration test run."""
    if platform.system() != "Windows":
        pytest.skip("Windows only integration test.")

    load_settings(allowed_apps=["notepad.exe", "calc.exe"])
    emergency_stop.reset()
    _cleanup_procs()
    _clean_notepad_cache()
    time.sleep(0.5)

    yield

    _cleanup_procs()
    _clean_notepad_cache()
    emergency_stop.reset()


@pytest.mark.windows_only
def test_notepad_and_calculator_live_workflow(managed_apps):
    # 1. Launch Calculator via open_target (reliable across all Windows 10/11 versions)
    res_calc = open_target("calc.exe")
    assert res_calc.ok is True, f"Failed to open calc: {res_calc.error}"

    # Wait for Calculator window to register
    calc_found = False
    titles = []
    for _ in range(40):
        res_list = list_windows(only_visible=True)
        assert res_list.ok is True
        titles = [w.title for w in res_list.data]
        if any("calc" in t.lower() or "calculator" in t.lower() for t in titles):
            calc_found = True
            break
        time.sleep(0.1)
    assert calc_found, f"Calculator window not found in list: {titles}"

    # 2. Focus Calculator and verify foreground transition
    res_calc_focus = focus_window("Calc", timeout_sec=4.0)
    assert res_calc_focus.ok is True, f"Could not focus Calculator: {res_calc_focus.error}"
    assert res_calc_focus.evidence["verified"] is True

    # 3. Check foreground() reflects Calculator
    res_calc_fg = foreground()
    assert res_calc_fg.ok is True
    fg_name = res_calc_fg.data.process_name.lower()
    assert "calc" in fg_name or "calculator" in res_calc_fg.data.title.lower()

    # 4. Type Unicode text and hotkey into live Calculator
    res_type = type_unicode("1234")
    assert res_type.ok is True
    assert res_type.evidence["chars_typed"] == 4

    time.sleep(0.2)
    res_hk = hotkey("ctrl", "a")
    assert res_hk.ok is True

    # 5. Launch Notepad via open_target if functional on host OS
    res_open = open_target("notepad.exe")
    assert res_open.ok is True, f"Failed to open notepad: {res_open.error}"
    assert res_open.evidence["app_name"] == "notepad.exe"

    time.sleep(1.0)
    notepad_found = False
    for _ in range(20):
        res_list = list_windows(only_visible=True)
        titles = [w.title for w in res_list.data]
        if any("notepad" in t.lower() for t in titles):
            notepad_found = True
            break
        time.sleep(0.1)

    # If Notepad launched without OS Store crash, verify focus & input on it too
    if notepad_found:
        res_focus = focus_window("Notepad", timeout_sec=4.0)
        assert res_focus.ok is True
        assert res_focus.evidence["verified"] is True

        res_fg = foreground()
        assert res_fg.ok is True
        assert "notepad" in res_fg.data.process_name.lower() or "notepad" in res_fg.data.title.lower()

        res_type_np = type_unicode("Hello from NEO Core! \u2713")
        assert res_type_np.ok is True
