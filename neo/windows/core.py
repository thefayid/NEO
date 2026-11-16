"""
neo/windows/core.py — Native Windows OS Interaction & Input Controller.

Implements Level 1 (Direct APIs/COM) and Level 4 (Keyboard/Mouse via SendInput):
- Per-monitor v2 DPI awareness set at startup.
- foreground() -> WindowInfo (hwnd, title, process_name, pid).
- list_windows() and focus_window(title_regex) with empirical focus verification.
- Hardware keyboard and mouse input using Win32 SendInput (ctypes) with Unicode text,
  hotkeys, scrolling, and coordinate conversion helpers.
- open_target(): strictly allow-listed applications, http(s) URLs, and non-executable
  files in allowed folders.
- Detection of elevated processes and secure desktop windows (UAC, Windows Sign-in),
  raising/returning typed BlockedError.
- Every function returns a typed WindowsResult. Zero bare print statements.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import psutil

from neo.config import get_settings
from neo.safety.emergency_stop import emergency_stop

logger = logging.getLogger("neo.windows.core")

# ─────────────────────────────────────────────────────────────────────────────
# Win32 Constants & Typed Results
# ─────────────────────────────────────────────────────────────────────────────
_IS_WINDOWS = platform.system() == "Windows"

# ShowWindow Constants
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9

# SendInput Types
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Mouse Flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Keyboard Flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Virtual Screen Metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Blocked Executable Extensions
DISALLOWED_FILE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf",
    ".scr", ".msi", ".com", ".pif", ".reg", ".hta", ".cpl",
}

# Known Secure Desktop & UAC Executables
SECURE_DESKTOP_PROCESSES = {
    "consent.exe",
    "logonui.exe",
    "credentialuibroker.exe",
    "lockapp.exe",
}


class BlockedError(RuntimeError):
    """Raised when an operation targets an elevated window or secure desktop (UAC, sign-in)."""
    def __init__(self, message: str, evidence: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.evidence = evidence or {}


@dataclass
class WindowInfo:
    """Detailed metadata for a top-level OS window."""
    hwnd: int
    title: str
    process_name: str
    pid: int
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (left, top, right, bottom)
    is_minimized: bool = False
    is_elevated_or_secure: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "process_name": self.process_name,
            "pid": self.pid,
            "rect": self.rect,
            "is_minimized": self.is_minimized,
            "is_elevated_or_secure": self.is_elevated_or_secure,
        }


@dataclass
class WindowsResult:
    """Strictly typed outcome for all Windows automation functions."""
    ok: bool
    error: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d_val = self.data.to_dict() if hasattr(self.data, "to_dict") else self.data
        return {
            "ok": self.ok,
            "error": self.error,
            "evidence": self.evidence,
            "data": d_val,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SendInput Native Structs (64-bit alignment verified)
# ─────────────────────────────────────────────────────────────────────────────
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Virtual Key Mapping
# ─────────────────────────────────────────────────────────────────────────────
VK_MAP: Dict[str, int] = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "esc": 0x1B,
    "escape": 0x1B,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "super": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


# ─────────────────────────────────────────────────────────────────────────────
# DPI Awareness & Desktop Station Setup
# ─────────────────────────────────────────────────────────────────────────────
def init_dpi_awareness() -> bool:
    """Sets per-monitor v2 DPI awareness for pixel-perfect screen coordinates."""
    if not _IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            logger.debug("DPI awareness set to Per-Monitor v2.")
            return True
    except Exception as e:
        logger.debug("SetProcessDpiAwarenessContext failed: %s", e)

    try:
        shcore = ctypes.windll.shcore
        if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE = 2
            logger.debug("DPI awareness set via shcore.")
            return True
    except Exception as e:
        logger.debug("shcore SetProcessDpiAwareness failed: %s", e)

    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            logger.debug("DPI awareness set via user32 fallback.")
            return True
    except Exception as e:
        logger.debug("user32 SetProcessDPIAware failed: %s", e)

    return False


# Initialize DPI awareness immediately upon module loading
init_dpi_awareness()


def ensure_desktop_attached() -> bool:
    """Attaches thread to interactive desktop WinSta0\\Default so window enumeration works."""
    if not _IS_WINDOWS:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
                return True
    except Exception as e:
        logger.debug("Could not attach to WinSta0\\Default: %s", e)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Security & Privilege Verification
# ─────────────────────────────────────────────────────────────────────────────
def check_secure_desktop() -> Tuple[bool, str]:
    """
    Checks if a Windows secure desktop (UAC consent, lock screen, or sign-in) is active.
    Returns (is_secure: bool, description: str).
    """
    if not _IS_WINDOWS:
        return False, "Non-Windows OS"
    try:
        user32 = ctypes.windll.user32
        # OpenInputDesktop fails with ERROR_ACCESS_DENIED (5) when on secure desktop
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if not hdesk:
            err = ctypes.get_last_error()
            if err == 5:
                return True, "Secure Desktop Active (Access Denied / UAC Prompt)"
            return False, f"OpenInputDesktop returned code {err}"

        try:
            buf = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            user32.GetUserObjectInformationW(hdesk, 2, buf, 256, ctypes.byref(needed))  # UOI_NAME = 2
            desk_name = buf.value.strip().lower()
            if desk_name in ("winlogon", "screendvr_desktop"):
                return True, f"Secure Desktop Active ({desk_name})"
        finally:
            user32.CloseDesktop(hdesk)
    except Exception as e:
        logger.debug("check_secure_desktop failed: %s", e)

    return False, "Standard User Desktop"


def is_process_elevated(pid: int) -> Tuple[bool, str]:
    """
    Checks if the process associated with PID is running elevated.
    Returns (is_elevated: bool, reason: str).
    """
    if not _IS_WINDOWS or pid <= 4:
        return (True, "System Process") if pid <= 4 else (False, "Non-Windows OS")
    try:
        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(0x1000, False, pid)
        if not h_proc:
            err = kernel32.GetLastError()
            if err == 5:  # Access Denied
                return True, "Access denied to process handle (Elevated Administrator Process)"
            return False, f"OpenProcess failed with error {err}"

        try:
            h_token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(h_proc, 0x0008, ctypes.byref(h_token)):  # TOKEN_QUERY = 0x0008
                return False, "Could not open process token"
            try:
                class TOKEN_ELEVATION(ctypes.Structure):
                    _fields_ = [("TokenIsElevated", wintypes.DWORD)]

                elev = TOKEN_ELEVATION()
                ret_len = wintypes.DWORD()
                if advapi32.GetTokenInformation(h_token, 20, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret_len)):  # TokenElevation = 20
                    if bool(elev.TokenIsElevated):
                        return True, "Process is running with elevated administrator token"
                return False, "Standard user process token"
            finally:
                kernel32.CloseHandle(h_token)
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception as e:
        logger.debug("is_process_elevated exception for PID %s: %s", pid, e)
        return False, str(e)


def detect_blocked_window(hwnd: int) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Detects if the target window is elevated or on a secure desktop.
    Returns (blocked: bool, reason: str, evidence: dict).
    """
    evidence: Dict[str, Any] = {"hwnd": hwnd}
    is_sec, sec_reason = check_secure_desktop()
    if is_sec:
        evidence["secure_desktop"] = sec_reason
        return True, sec_reason, evidence

    if not hwnd or not _IS_WINDOWS:
        return False, "Window handle invalid or non-Windows", evidence

    try:
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        evidence["pid"] = pid_val

        pname = ""
        try:
            pname = psutil.Process(pid_val).name().lower()
            evidence["process_name"] = pname
        except Exception:
            pass

        if pname in SECURE_DESKTOP_PROCESSES:
            reason = f"Window belongs to secure OS process '{pname}'"
            evidence["blocked_process"] = pname
            return True, reason, evidence

        is_elev, elev_reason = is_process_elevated(pid_val)
        evidence["token_elevation"] = is_elev
        evidence["elevation_reason"] = elev_reason
        if is_elev:
            return True, f"Target process {pid_val} ({pname}) is elevated: {elev_reason}", evidence

    except Exception as e:
        logger.debug("detect_blocked_window error on HWND %s: %s", hwnd, e)

    return False, "Window is standard and non-elevated", evidence


# ─────────────────────────────────────────────────────────────────────────────
# Window Inspection & Focus Management
# ─────────────────────────────────────────────────────────────────────────────
def _get_window_info(hwnd: int) -> WindowInfo:
    """Constructs a WindowInfo dataclass for a given window handle."""
    if not hwnd or not _IS_WINDOWS:
        return WindowInfo(hwnd=0, title="", process_name="", pid=0)

    user32 = ctypes.windll.user32
    # Title
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    title = buf.value.strip()

    # PID and Process Name
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value
    pname = ""
    try:
        pname = psutil.Process(pid_val).name()
    except Exception:
        pname = "unknown"

    # Rect
    rect = (0, 0, 0, 0)
    try:
        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
        r = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            rect = (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass

    # Minimized state
    is_min = bool(user32.IsIconic(hwnd))

    # Elevated / secure check
    is_blocked, _, _ = detect_blocked_window(hwnd)

    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process_name=pname,
        pid=pid_val,
        rect=rect,
        is_minimized=is_min,
        is_elevated_or_secure=is_blocked,
    )


def foreground() -> WindowsResult:
    """
    Returns the currently active foreground window details.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="foreground() requires Windows OS.")

    ensure_desktop_attached()
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return WindowsResult(
            ok=True,
            error=None,
            evidence={"foreground_hwnd": 0},
            data=WindowInfo(hwnd=0, title="", process_name="", pid=0),
        )

    info = _get_window_info(hwnd)
    return WindowsResult(
        ok=True,
        error=None,
        evidence={"foreground_hwnd": hwnd, "title": info.title, "pid": info.pid},
        data=info,
    )


def list_windows(only_visible: bool = True) -> WindowsResult:
    """
    Lists all top-level desktop windows matching visibility criteria.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="list_windows() requires Windows OS.")

    ensure_desktop_attached()
    user32 = ctypes.windll.user32
    windows: List[WindowInfo] = []

    def _enum_proc(hwnd: int, lParam: Any) -> bool:
        if only_visible and not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            info = _get_window_info(hwnd)
            windows.append(info)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)

    return WindowsResult(
        ok=True,
        error=None,
        evidence={"window_count": len(windows)},
        data=windows,
    )


def focus_window(title_regex: str, timeout_sec: float = 2.0) -> WindowsResult:
    """
    Brings target window matching title_regex to foreground and VERIFIES focus.
    Handles minimized windows by restoring them first.
    Raises BlockedError if window belongs to an elevated or secure-desktop process.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="focus_window() requires Windows OS.")

    pattern = re.compile(title_regex, re.IGNORECASE)
    res = list_windows(only_visible=True)
    if not res.ok or not res.data:
        return WindowsResult(ok=False, error="No accessible desktop windows found.", evidence={"query": title_regex})

    target: Optional[WindowInfo] = None
    # 1. Prefer explicit window title match
    for win in res.data:
        if pattern.search(win.title):
            target = win
            break

    # 2. Fallback to process name match if no title matched
    if not target:
        for win in res.data:
            if pattern.search(win.process_name):
                target = win
                break

    if not target:
        return WindowsResult(
            ok=False,
            error=f"Window matching '{title_regex}' not found.",
            evidence={"query": title_regex, "scanned_windows": len(res.data)},
        )

    # Security check: Never manipulate elevated or secure-desktop windows
    is_blocked, block_reason, evidence = detect_blocked_window(target.hwnd)
    if is_blocked:
        raise BlockedError(f"Cannot focus elevated/secure window '{target.title}': {block_reason}", evidence=evidence)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = target.hwnd

    # 1. Restore minimized window
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.08)

    # 2. Attach thread input to bypass Windows foreground locks
    cur_thread = kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    if target_thread != cur_thread:
        user32.AttachThreadInput(cur_thread, target_thread, True)
    if fg_thread and fg_thread != cur_thread and fg_thread != target_thread:
        user32.AttachThreadInput(cur_thread, fg_thread, True)

    try:
        # Standard Win32 lock bypass: simulate Alt key press
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
        user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up (KEYEVENTF_KEYUP = 2)

        user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if hasattr(user32, "SwitchToThisWindow"):
            user32.SwitchToThisWindow(hwnd, True)
    finally:
        if target_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, target_thread, False)
        if fg_thread and fg_thread != cur_thread and fg_thread != target_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, False)

    # 3. VERIFY focus afterwards
    start_t = time.perf_counter()
    focused = False
    verified_hwnd = 0

    while time.perf_counter() - start_t < timeout_sec:
        verified_hwnd = user32.GetForegroundWindow()
        if verified_hwnd == hwnd:
            focused = True
            break
        # Sometimes a child or popup dialog of the target receives the foreground
        pid_fg = wintypes.DWORD()
        user32.GetWindowThreadProcessId(verified_hwnd, ctypes.byref(pid_fg))
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(verified_hwnd, buf, 512)
        fg_title = buf.value.strip()

        if pid_fg.value == target.pid:
            # If target has a title, ensure the foreground title belongs to this app
            # (handles multi-app hosts like ApplicationFrameHost where PID is shared)
            if not target.title or target.title.lower() in fg_title.lower() or pattern.search(fg_title):
                focused = True
                break
        time.sleep(0.04)

    updated_info = _get_window_info(hwnd)
    evidence = {
        "target_hwnd": hwnd,
        "verified_foreground_hwnd": verified_hwnd,
        "title": updated_info.title,
        "pid": updated_info.pid,
        "verified": focused,
    }

    if focused:
        return WindowsResult(ok=True, evidence=evidence, data=updated_info)
    return WindowsResult(
        ok=False,
        error=f"Focus requested for '{target.title}' (HWND {hwnd}), but foreground verification failed (active HWND: {verified_hwnd}).",
        evidence=evidence,
        data=updated_info,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Coordinate Conversion Helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_virtual_screen_bounds() -> Tuple[int, int, int, int]:
    """Returns (vx, vy, vw, vh) of the entire virtual multi-monitor desktop."""
    if not _IS_WINDOWS:
        return (0, 0, 1920, 1080)
    user32 = ctypes.windll.user32
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if vw <= 0 or vh <= 0:
        vw = user32.GetSystemMetrics(0) or 1920
        vh = user32.GetSystemMetrics(1) or 1080
        vx, vy = 0, 0
    return vx, vy, vw, vh


def pixels_to_sendinput_coords(x: int, y: int) -> Tuple[int, int]:
    """
    Converts absolute screen pixels to SendInput normalized virtual screen
    coordinates in range [0, 65535].
    """
    vx, vy, vw, vh = get_virtual_screen_bounds()
    norm_x = int(((x - vx) * 65536) / vw)
    norm_y = int(((y - vy) * 65536) / vh)
    return max(0, min(65535, norm_x)), max(0, min(65535, norm_y))


def normalized_to_pixel_coords(nx: float, ny: float) -> Tuple[int, int]:
    """Converts normalized floats [0.0, 1.0] to physical screen pixels."""
    vx, vy, vw, vh = get_virtual_screen_bounds()
    px = int(vx + (nx * vw))
    py = int(vy + (ny * vh))
    return px, py


def pixel_to_normalized_coords(px: int, py: int) -> Tuple[float, float]:
    """Converts physical screen pixels to normalized floats [0.0, 1.0]."""
    vx, vy, vw, vh = get_virtual_screen_bounds()
    nx = (px - vx) / float(vw)
    ny = (py - vy) / float(vh)
    return round(max(0.0, min(1.0, nx)), 5), round(max(0.0, min(1.0, ny)), 5)


# ─────────────────────────────────────────────────────────────────────────────
# Hardware Input via SendInput (ctypes)
# ─────────────────────────────────────────────────────────────────────────────
def _send_inputs(inputs: List[INPUT]) -> bool:
    """Dispatches a list of INPUT structures via user32.SendInput."""
    if not _IS_WINDOWS or not inputs:
        return False
    emergency_stop.check_stop()
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    cb_size = ctypes.sizeof(INPUT)
    sent = ctypes.windll.user32.SendInput(n, arr, cb_size)
    return sent == n


def click_coords(
    x: int,
    y: int,
    button: str = "left",
    clicks: int = 1,
) -> WindowsResult:
    """
    Moves mouse and clicks at specified physical pixel coordinates using SendInput.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="click_coords() requires Windows OS.")

    btn = button.strip().lower()
    if btn == "left":
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    elif btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        return WindowsResult(ok=False, error=f"Invalid mouse button '{button}'. Use 'left', 'right', or 'middle'.")

    # 1. Position cursor
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.02)

    norm_x, norm_y = pixels_to_sendinput_coords(x, y)
    inputs: List[INPUT] = []

    for _ in range(clicks):
        # Mouse Down
        down_inp = INPUT()
        down_inp.type = INPUT_MOUSE
        down_inp.u.mi.dx = norm_x
        down_inp.u.mi.dy = norm_y
        down_inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | down_flag
        inputs.append(down_inp)

        # Mouse Up
        up_inp = INPUT()
        up_inp.type = INPUT_MOUSE
        up_inp.u.mi.dx = norm_x
        up_inp.u.mi.dy = norm_y
        up_inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | up_flag
        inputs.append(up_inp)

    ok = _send_inputs(inputs)
    evidence = {
        "x": x,
        "y": y,
        "button": btn,
        "clicks": clicks,
        "send_input_success": ok,
    }
    if ok:
        return WindowsResult(ok=True, evidence=evidence)
    return WindowsResult(ok=False, error="SendInput failed to dispatch mouse clicks.", evidence=evidence)


def scroll(
    amount: int = 3,
    direction: str = "down",
    x: Optional[int] = None,
    y: Optional[int] = None,
) -> WindowsResult:
    """
    Dispatches mouse wheel scroll via SendInput.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="scroll() requires Windows OS.")

    if x is not None and y is not None:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.01)

    dir_clean = direction.strip().lower()
    # Windows WHEEL_DELTA = 120 per notch
    delta = (amount * 120) if dir_clean in ("up", "top") else (-amount * 120)

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.mouseData = wintypes.DWORD(delta & 0xFFFFFFFF)
    inp.u.mi.dwFlags = MOUSEEVENTF_WHEEL

    ok = _send_inputs([inp])
    evidence = {"amount": amount, "direction": dir_clean, "wheel_delta": delta}
    if ok:
        return WindowsResult(ok=True, evidence=evidence)
    return WindowsResult(ok=False, error="SendInput failed to dispatch scroll event.", evidence=evidence)


def type_unicode(text: str) -> WindowsResult:
    """
    Dispatches exact Unicode character input via SendInput with KEYEVENTF_UNICODE.
    Bypasses keyboard layouts, IME states, and uppercase/lowercase shift handling.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="type_unicode() requires Windows OS.")
    if not text:
        return WindowsResult(ok=True, evidence={"chars_typed": 0})

    inputs: List[INPUT] = []
    for ch in text:
        code = ord(ch)

        # Key down
        down_inp = INPUT()
        down_inp.type = INPUT_KEYBOARD
        down_inp.u.ki.wVk = 0
        down_inp.u.ki.wScan = code
        down_inp.u.ki.dwFlags = KEYEVENTF_UNICODE
        inputs.append(down_inp)

        # Key up
        up_inp = INPUT()
        up_inp.type = INPUT_KEYBOARD
        up_inp.u.ki.wVk = 0
        up_inp.u.ki.wScan = code
        up_inp.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inputs.append(up_inp)

    ok = _send_inputs(inputs)
    evidence = {
        "chars_typed": len(text),
        "text_sample": text[:30] + ("..." if len(text) > 30 else ""),
    }
    if ok:
        return WindowsResult(ok=True, evidence=evidence)
    return WindowsResult(ok=False, error="SendInput failed to type Unicode characters.", evidence=evidence)


def hotkey(*keys: str) -> WindowsResult:
    """
    Dispatches key combination using virtual key codes via SendInput.
    Presses modifiers in order, taps final key, releases modifiers in reverse.
    """
    emergency_stop.check_stop()
    if not _IS_WINDOWS:
        return WindowsResult(ok=False, error="hotkey() requires Windows OS.")

    if not keys:
        return WindowsResult(ok=False, error="No keys specified for hotkey.")

    # Flatten any "ctrl+c" string representations
    parsed_keys: List[str] = []
    for k in keys:
        for sub in str(k).split("+"):
            sub_c = sub.strip().lower()
            if sub_c:
                parsed_keys.append(sub_c)

    vk_codes: List[int] = []
    for k in parsed_keys:
        if k in VK_MAP:
            vk_codes.append(VK_MAP[k])
        elif len(k) == 1:
            vk_codes.append(ord(k.upper()))
        else:
            return WindowsResult(ok=False, error=f"Unrecognized hotkey component: '{k}'")

    inputs: List[INPUT] = []

    # Down sequence
    for vk in vk_codes:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = 0
        inp.u.ki.dwFlags = 0
        inputs.append(inp)

    # Up sequence (reverse)
    for vk in reversed(vk_codes):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = 0
        inp.u.ki.dwFlags = KEYEVENTF_KEYUP
        inputs.append(inp)

    ok = _send_inputs(inputs)
    evidence = {"hotkey": "+".join(parsed_keys), "vk_codes": vk_codes}
    if ok:
        return WindowsResult(ok=True, evidence=evidence)
    return WindowsResult(ok=False, error=f"SendInput failed for hotkey '{'+'.join(parsed_keys)}'.", evidence=evidence)


# ─────────────────────────────────────────────────────────────────────────────
# Security-Gated Target Launching (open_target)
# ─────────────────────────────────────────────────────────────────────────────
def open_target(target: str) -> WindowsResult:
    """
    Opens target while strictly enforcing security boundaries:
    1. HTTP / HTTPS URLs: Launched using the system default browser.
       Any other URI scheme (file://, javascript:, shell:) is blocked.
    2. Applications: Executables must be explicitly listed in settings.allowed_apps.
    3. Files: Must reside inside settings.allowed_folders and must NOT have an executable extension.
    """
    emergency_stop.check_stop()
    target_clean = (target or "").strip().strip('"').strip("'")
    if not target_clean:
        return WindowsResult(ok=False, error="No target specified for open_target.")

    settings = get_settings()

    # ── 1. HTTP / HTTPS URL Handling ─────────────────────────────────────────
    # Distinguish Windows drive letters (e.g. C:\path) from URI schemes (http://)
    is_win_drive = len(target_clean) >= 2 and target_clean[1] == ":" and target_clean[0].isalpha()
    parsed = urlparse(target_clean) if not is_win_drive else None

    if parsed and parsed.scheme and len(parsed.scheme) > 1:
        if parsed.scheme.lower() in ("http", "https"):
            try:
                # Safe launch via Windows shell association
                os.startfile(target_clean)
                return WindowsResult(
                    ok=True,
                    evidence={"type": "url", "target": target_clean, "scheme": parsed.scheme.lower()},
                )
            except Exception as e:
                return WindowsResult(ok=False, error=f"Could not open URL: {e}", evidence={"target": target_clean})
        else:
            return WindowsResult(
                ok=False,
                error=f"Blocked URI scheme '{parsed.scheme}:'. Only http and https URLs are permitted.",
                evidence={"target": target_clean, "blocked_scheme": parsed.scheme},
            )

    # ── 2. Allow-listed Application Launching ─────────────────────────────────
    p = Path(target_clean)
    target_name = p.name.lower()
    allowed_apps_lower = [a.lower() for a in settings.allowed_apps]

    if target_name in allowed_apps_lower or target_clean.lower() in allowed_apps_lower:
        try:
            if _IS_WINDOWS:
                # ShellExecuteW properly activates Windows 10/11 packaged and Win32 applications with interactive GUI
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", target_clean, None, None, SW_SHOWNORMAL)
                if res > 32:  # Greater than 32 indicates success in Win32 ShellExecute
                    return WindowsResult(
                        ok=True,
                        evidence={
                            "type": "allowed_app",
                            "app_name": target_name,
                            "target": target_clean,
                            "shell_execute_status": res,
                        },
                    )

            # Fallback for non-Windows or direct binary execution
            resolved_binary = target_clean
            if not p.is_absolute():
                import shutil
                which_p = shutil.which(target_clean)
                if which_p:
                    resolved_binary = which_p

            proc = subprocess.Popen(
                [resolved_binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return WindowsResult(
                ok=True,
                evidence={
                    "type": "allowed_app",
                    "app_name": target_name,
                    "binary": resolved_binary,
                    "pid": proc.pid,
                },
            )
        except Exception as e:
            return WindowsResult(
                ok=False,
                error=f"Failed to launch allowed app '{target_clean}': {e}",
                evidence={"app": target_clean},
            )

    # ── 3. Files in Allowed Folders (Non-Executables Only) ────────────────────
    target_path = p.resolve()
    if target_path.exists() and target_path.is_file():
        # Check disallowed executable extensions
        ext = target_path.suffix.lower()
        if ext in DISALLOWED_FILE_EXTENSIONS:
            return WindowsResult(
                ok=False,
                error=f"Blocked execution of file with executable extension '{ext}'. Only non-executable documents are permitted.",
                evidence={"path": str(target_path), "extension": ext},
            )

        # Check path resides within an allowed folder
        is_in_allowed_folder = False
        matching_root = ""
        for folder_str in settings.allowed_folders:
            folder_path = Path(folder_str).resolve()
            try:
                if target_path == folder_path or target_path.is_relative_to(folder_path):
                    is_in_allowed_folder = True
                    matching_root = str(folder_path)
                    break
            except Exception:
                pass

        if not is_in_allowed_folder:
            return WindowsResult(
                ok=False,
                error=f"Access denied: file '{target_path.name}' is outside configured allowed_folders.",
                evidence={"path": str(target_path), "allowed_folders": settings.allowed_folders},
            )

        try:
            os.startfile(str(target_path))
            return WindowsResult(
                ok=True,
                evidence={
                    "type": "allowed_file",
                    "path": str(target_path),
                    "allowed_folder": matching_root,
                },
            )
        except Exception as e:
            return WindowsResult(
                ok=False,
                error=f"Could not open file '{target_path.name}': {e}",
                evidence={"path": str(target_path)},
            )

    # If neither an allowed URL, app, nor existing file
    return WindowsResult(
        ok=False,
        error=f"Target '{target_clean}' is not an allowed application, valid http(s) URL, or accessible non-executable file.",
        evidence={"target": target_clean, "allowed_apps_sample": settings.allowed_apps[:5]},
    )
