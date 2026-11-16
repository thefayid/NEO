"""
tests/test_windows_core_unit.py — Unit tests with mocks for neo/windows/core.py.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neo.config import load_settings
from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.windows.core import (
    BlockedError,
    WindowInfo,
    WindowsResult,
    click_coords,
    detect_blocked_window,
    focus_window,
    foreground,
    get_virtual_screen_bounds,
    hotkey,
    normalized_to_pixel_coords,
    open_target,
    pixel_to_normalized_coords,
    pixels_to_sendinput_coords,
    scroll,
    type_unicode,
)


@pytest.fixture(autouse=True)
def ensure_unstopped():
    emergency_stop.reset()
    yield
    emergency_stop.reset()


# ── 1. Coordinate Conversions ────────────────────────────────────────────────
def test_coordinate_conversions():
    with patch("neo.windows.core.get_virtual_screen_bounds", return_value=(0, 0, 1920, 1080)):
        # Pixels to normalized [0, 65535]
        sx, sy = pixels_to_sendinput_coords(960, 540)
        assert 32000 <= sx <= 33000
        assert 32000 <= sy <= 33000

        # Normalized float [0.0, 1.0] to pixels
        px, py = normalized_to_pixel_coords(0.5, 0.5)
        assert px == 960
        assert py == 540

        # Pixels to normalized float [0.0, 1.0]
        nx, ny = pixel_to_normalized_coords(960, 540)
        assert nx == 0.5
        assert ny == 0.5


# ── 2. open_target Security Gates ───────────────────────────────────────────
def test_open_target_rejects_empty():
    res = open_target("")
    assert res.ok is False
    assert "No target specified" in (res.error or "")


def test_open_target_http_https_urls():
    with patch("os.startfile") as mock_start:
        res = open_target("https://www.google.com")
        assert res.ok is True
        assert res.evidence["scheme"] == "https"
        mock_start.assert_called_once_with("https://www.google.com")

        res_http = open_target("http://example.com")
        assert res_http.ok is True
        assert res_http.evidence["scheme"] == "http"


def test_open_target_blocks_dangerous_uri_schemes():
    with patch("os.startfile"):
        res_file = open_target("file:///C:/Windows/System32/calc.exe")
        assert res_file.ok is False
        assert "Blocked URI scheme 'file:'" in (res_file.error or "")

        res_js = open_target("javascript:alert(1)")
        assert res_js.ok is False
        assert "Blocked URI scheme 'javascript:'" in (res_js.error or "")


def test_open_target_allowed_application():
    load_settings(allowed_apps=["notepad.exe", "calc.exe"])
    with patch("ctypes.windll.shell32.ShellExecuteW", return_value=42):
        res = open_target("notepad.exe")
        assert res.ok is True
        assert res.evidence["app_name"] == "notepad.exe"
        assert res.evidence["shell_execute_status"] == 42


def test_open_target_blocks_disallowed_application():
    load_settings(allowed_apps=["notepad.exe"])
    res = open_target("unauthorized_tool.exe")
    assert res.ok is False
    assert "not an allowed application" in (res.error or "")


def test_open_target_allowed_folder_file(tmp_path: Path):
    safe_folder = tmp_path / "safe_data"
    safe_folder.mkdir()
    text_file = safe_folder / "report.txt"
    text_file.write_text("Safe content", encoding="utf-8")

    load_settings(allowed_folders=[str(safe_folder)])

    with patch("os.startfile") as mock_start:
        res = open_target(str(text_file))
        assert res.ok is True
        assert res.evidence["type"] == "allowed_file"
        mock_start.assert_called_once_with(str(text_file.resolve()))


def test_open_target_blocks_executable_file_in_allowed_folder(tmp_path: Path):
    safe_folder = tmp_path / "safe_data"
    safe_folder.mkdir()
    script_file = safe_folder / "payload.bat"
    script_file.write_text("@echo off\necho hi", encoding="utf-8")

    load_settings(allowed_folders=[str(safe_folder)])

    with patch("os.startfile"):
        res = open_target(str(script_file))
        assert res.ok is False
        assert "Blocked execution of file with executable extension" in (res.error or "")


def test_open_target_blocks_file_outside_allowed_folder(tmp_path: Path):
    safe_folder = tmp_path / "safe_data"
    safe_folder.mkdir()
    outside_folder = tmp_path / "outside"
    outside_folder.mkdir()
    secret_file = outside_folder / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")

    load_settings(allowed_folders=[str(safe_folder)])

    res = open_target(str(secret_file))
    assert res.ok is False
    assert "Access denied: file 'secret.txt' is outside configured allowed_folders" in (res.error or "")


# ── 3. Elevated and Secure Desktop Detection ─────────────────────────────────
def test_detect_blocked_window_uac_consent():
    with patch("neo.windows.core.check_secure_desktop", return_value=(True, "Secure Desktop Active (UAC)")):
        is_blocked, reason, evidence = detect_blocked_window(12345)
        assert is_blocked is True
        assert "UAC" in reason


def test_detect_blocked_window_elevated_process():
    with patch("neo.windows.core.check_secure_desktop", return_value=(False, "")):
        with patch("neo.windows.core.is_process_elevated", return_value=(True, "Elevated Administrator Process")):
            is_blocked, reason, evidence = detect_blocked_window(54321)
            assert is_blocked is True
            assert "elevated" in reason.lower()


def test_focus_window_raises_blocked_error_on_elevated():
    mock_win = WindowInfo(
        hwnd=9999,
        title="Admin Terminal",
        process_name="cmd.exe",
        pid=1111,
    )
    with patch("neo.windows.core.list_windows", return_value=WindowsResult(ok=True, data=[mock_win])):
        with patch("neo.windows.core.detect_blocked_window", return_value=(True, "Administrator Process", {"pid": 1111})):
            with pytest.raises(BlockedError, match="Cannot focus elevated/secure window"):
                focus_window("Admin Terminal")


# ── 4. Emergency Stop Guard Verification ─────────────────────────────────────
def test_emergency_stop_blocks_all_actions():
    emergency_stop.trigger(reason="Test Stop")

    with pytest.raises(EmergencyStopTriggeredError):
        foreground()

    with pytest.raises(EmergencyStopTriggeredError):
        click_coords(100, 100)

    with pytest.raises(EmergencyStopTriggeredError):
        type_unicode("test")

    with pytest.raises(EmergencyStopTriggeredError):
        hotkey("ctrl", "c")

    with pytest.raises(EmergencyStopTriggeredError):
        scroll(3)

    with pytest.raises(EmergencyStopTriggeredError):
        open_target("https://google.com")
