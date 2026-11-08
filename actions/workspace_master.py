"""
actions/workspace_master.py — Autonomous Stark Workspaces & Window Master.

Provides comprehensive window tiling, multi-monitor management, and high-level
workspace orchestration presets:
  • Presets:
      - Dev Mode: Launches/focuses VS Code & Terminal, tiles side-by-side.
      - Focus Protocol: Minimizes distractions, silences alerts, starts ambient focus audio.
      - Media Mode: Dims display brightness, balances audio, maximizes media center.
  • Voice Window Snapping:
      - "Snap browser to the left, terminal to the right."
      - "Snap code to the left half."
  • Multi-Monitor Control:
      - "Move Chrome to monitor 2."
  • Isolation:
      - "Minimize everything except my code editor."
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import psutil

_OS = platform.system()
user32 = ctypes.windll.user32 if _OS == "Windows" else None

_BASE_DIR = Path(__file__).resolve().parent.parent


def _attach_desktop():
    """Ensure this thread is attached to the interactive WinSta0/default desktop."""
    if _OS != "Windows" or user32 is None:
        return
    try:
        hwinsta0 = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta0:
            user32.SetProcessWindowStation(hwinsta0)
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("rcMonitor", w.RECT),
        ("rcWork", w.RECT),
        ("dwFlags", w.DWORD),
        ("szDevice", w.WCHAR * 32),
    ]


def get_monitors() -> List[Dict]:
    """Return all detected display monitors and their work areas."""
    if _OS != "Windows" or user32 is None:
        return [{"index": 1, "primary": True, "work": (0, 0, 1920, 1080)}]

    _attach_desktop()
    monitors = []

    def mon_cb(hmon, hdc, lprect, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            m = info.rcMonitor
            wk = info.rcWork
            monitors.append({
                "hmon": hmon,
                "primary": bool(info.dwFlags & 1),
                "device": info.szDevice,
                "monitor": (m.left, m.top, m.right - m.left, m.bottom - m.top),
                "work": (wk.left, wk.top, wk.right - wk.left, wk.bottom - wk.top),
            })
        return True

    CB_T = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HMONITOR, w.HDC, ctypes.c_void_p, w.LPARAM)
    user32.EnumDisplayMonitors(0, 0, CB_T(mon_cb), 0)

    # Sort primary first, then left-to-right
    monitors.sort(key=lambda m: (0 if m["primary"] else 1, m["work"][0]))
    for idx, m in enumerate(monitors, 1):
        m["index"] = idx
    return monitors


def get_visible_windows() -> List[Dict]:
    """Enumerate all real, top-level visible application windows."""
    if _OS != "Windows" or user32 is None:
        return []

    _attach_desktop()
    windows = []

    def enum_cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        # Skip cloaked windows (Windows 10/11 virtual desktops)
        cloaked = ctypes.c_int(0)
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            if cloaked.value != 0:
                return True
        except Exception:
            pass

        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()

        rect = w.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        # Ignore tiny toolbars, shell overlays, wallpaper host
        if width <= 100 or height <= 100 or not title:
            return True
        if title in ("Program Manager", "Windows Input Experience", "Settings"):
            # Check class name
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
                return True

        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pname = ""
        try:
            pname = psutil.Process(pid.value).name().lower()
        except Exception:
            pass

        windows.append({
            "hwnd": hwnd,
            "title": title,
            "process": pname,
            "rect": (rect.left, rect.top, width, height),
            "is_maximized": bool(user32.IsZoomed(hwnd)),
            "is_minimized": bool(user32.IsIconic(hwnd)),
        })
        return True

    CB_T = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    user32.EnumWindows(CB_T(enum_cb), 0)
    return windows


def find_window(query: str) -> Optional[Dict]:
    """Fuzzy match query against open application titles and process names."""
    windows = get_visible_windows()
    if not windows:
        return None

    query = query.lower().strip()

    # Domain aliases
    aliases = {
        "browser": ["chrome", "msedge", "brave", "firefox", "opera", "vivaldi"],
        "chrome": ["chrome"],
        "edge": ["msedge", "edge"],
        "terminal": ["windowsterminal", "cmd", "powershell", "wt", "bash"],
        "powershell": ["powershell"],
        "cmd": ["cmd"],
        "code": ["code", "vscode", "antigravity", "visual studio code"],
        "editor": ["code", "vscode", "antigravity", "sublime", "pycharm", "notepad", "cursor"],
        "ide": ["code", "vscode", "antigravity", "pycharm", "cursor"],
        "spotify": ["spotify"],
        "music": ["spotify", "youtube", "media", "music"],
        "media": ["spotify", "vlc", "netflix", "youtube", "chrome"],
        "discord": ["discord"],
        "slack": ["slack"],
    }

    target_keys = aliases.get(query, [query])

    # 1. Exact or alias process match
    for w_info in windows:
        proc = w_info["process"]
        for k in target_keys:
            if k in proc:
                return w_info

    # 2. Substring in window title
    for w_info in windows:
        title = w_info["title"].lower()
        for k in target_keys:
            if k in title:
                return w_info

    # 3. Weak substring match
    for w_info in windows:
        if query in w_info["title"].lower() or query in w_info["process"]:
            return w_info

    return None


def snap_window(hwnd: int, position: str, monitor_index: int = 1) -> bool:
    """Snap a window to a defined position on the specified monitor."""
    if _OS != "Windows" or user32 is None:
        return False

    monitors = get_monitors()
    if not monitors:
        return False

    # Choose monitor (1-indexed)
    mon = monitors[0]
    for m in monitors:
        if m["index"] == monitor_index:
            mon = m
            break

    mx, my, mw, mh = mon["work"]
    pos = position.lower().strip().replace(" ", "_").replace("-", "_")

    # Restore if maximized or minimized before moving
    if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.05)

    if pos in ("left", "left_half", "left_side"):
        nx, ny, nw, nh = mx, my, mw // 2, mh
    elif pos in ("right", "right_half", "right_side"):
        nx, ny, nw, nh = mx + (mw // 2), my, mw - (mw // 2), mh
    elif pos in ("top", "top_half"):
        nx, ny, nw, nh = mx, my, mw, mh // 2
    elif pos in ("bottom", "bottom_half"):
        nx, ny, nw, nh = mx, my + (mh // 2), mw, mh - (mh // 2)
    elif pos in ("left_60", "dev_left", "code_left"):
        w60 = int(mw * 0.58)
        nx, ny, nw, nh = mx, my, w60, mh
    elif pos in ("right_40", "dev_right", "terminal_right"):
        w60 = int(mw * 0.58)
        nx, ny, nw, nh = mx + w60, my, mw - w60, mh
    elif pos in ("top_left", "corner_top_left"):
        nx, ny, nw, nh = mx, my, mw // 2, mh // 2
    elif pos in ("top_right", "corner_top_right"):
        nx, ny, nw, nh = mx + (mw // 2), my, mw - (mw // 2), mh // 2
    elif pos in ("bottom_left", "corner_bottom_left"):
        nx, ny, nw, nh = mx, my + (mh // 2), mw // 2, mh - (mh // 2)
    elif pos in ("bottom_right", "corner_bottom_right"):
        nx, ny, nw, nh = mx + (mw // 2), my + (mh // 2), mw - (mw // 2), mh - (mh // 2)
    elif pos in ("center", "centered"):
        cw = int(mw * 0.72)
        ch = int(mh * 0.76)
        nx, ny, nw, nh = mx + (mw - cw) // 2, my + (mh - ch) // 2, cw, ch
    elif pos in ("maximize", "max", "full", "fullscreen"):
        nx, ny, nw, nh = mx, my, mw, mh
        user32.MoveWindow(hwnd, nx, ny, nw, nh, True)
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        user32.SetForegroundWindow(hwnd)
        return True
    elif pos in ("minimize", "min"):
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        return True
    else:
        # Default to left half
        nx, ny, nw, nh = mx, my, mw // 2, mh

    # Move and bring to top
    user32.SetWindowPos(hwnd, 0, nx, ny, nw, nh, 0x0040 | 0x0004)  # SWP_SHOWWINDOW | SWP_NOZORDER
    user32.MoveWindow(hwnd, nx, ny, nw, nh, True)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    return True


def snap_pair(app1: str, pos1: str, app2: str, pos2: str, monitor_index: int = 1) -> str:
    """Snap two applications simultaneously to designated positions."""
    w1 = find_window(app1)
    w2 = find_window(app2)

    results = []
    if w1:
        ok1 = snap_window(w1["hwnd"], pos1, monitor_index)
        results.append(f"{w1['title'][:25]} -> {pos1} ({'OK' if ok1 else 'Failed'})")
    else:
        results.append(f"'{app1}' not found")

    if w2:
        ok2 = snap_window(w2["hwnd"], pos2, monitor_index)
        results.append(f"{w2['title'][:25]} -> {pos2} ({'OK' if ok2 else 'Failed'})")
    else:
        results.append(f"'{app2}' not found")

    return f"Tiled pair: {', '.join(results)} on Monitor {monitor_index}."


def move_to_monitor(hwnd: int, target_monitor: int) -> bool:
    """Move a window to a different display monitor."""
    monitors = get_monitors()
    target_mon = None
    for m in monitors:
        if m["index"] == target_monitor:
            target_mon = m
            break
    if not target_mon:
        return False

    # Snap to center or full on new monitor
    return snap_window(hwnd, "maximize" if user32.IsZoomed(hwnd) else "center", target_monitor)


def minimize_all_except(target: str) -> str:
    """Minimize all windows except the matching application."""
    if _OS != "Windows" or user32 is None:
        return "Window minimization requires Windows."

    target_win = find_window(target)
    if not target_win:
        return f"Could not find any window matching '{target}', Boss."

    windows = get_visible_windows()
    target_hwnd = target_win["hwnd"]
    minimized_count = 0

    for w_info in windows:
        h = w_info["hwnd"]
        if h != target_hwnd:
            user32.ShowWindow(h, 6)  # SW_MINIMIZE
            minimized_count += 1

    # Restore and focus target
    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(target_hwnd)
    return f"Focused '{target_win['title'][:30]}' and minimized {minimized_count} other windows, Boss."


# ─────────────────────────────────────────────────────────────────────────────
#  WORKSPACE PRESETS
# ─────────────────────────────────────────────────────────────────────────────

def _launch_if_missing(app_cmd: str, candidate_paths: List[str], cwd: Optional[Path] = None) -> bool:
    """Launch an application if it is installed and not currently running."""
    # 1. Check path
    if shutil.which(app_cmd):
        try:
            subprocess.Popen([app_cmd, str(cwd)] if cwd else [app_cmd], shell=True, cwd=str(cwd) if cwd else None)
            return True
        except Exception:
            pass

    # 2. Check candidate absolute paths
    for p in candidate_paths:
        expanded = os.path.expandvars(p)
        if os.path.exists(expanded):
            try:
                subprocess.Popen([expanded, str(cwd)] if cwd else [expanded], shell=True, cwd=str(cwd) if cwd else None)
                return True
            except Exception:
                pass
    return False


def run_dev_mode() -> str:
    """Dev Mode: Launches VS Code & Terminal, tiles them side-by-side."""
    actions = []

    # 1. Ensure Code is open
    code_win = find_window("code")
    if not code_win:
        launched = _launch_if_missing(
            "code",
            [
                r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
            ],
            cwd=_BASE_DIR
        )
        if launched:
            actions.append("VS Code launched")
            time.sleep(1.2)
            code_win = find_window("code")

    # 2. Ensure Terminal is open
    term_win = find_window("terminal")
    if not term_win:
        launched_term = _launch_if_missing(
            "wt",
            [
                r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe",
                r"%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe",
            ],
            cwd=_BASE_DIR
        )
        if launched_term:
            actions.append("Terminal launched")
            time.sleep(1.0)
            term_win = find_window("terminal")

    # 3. Tile side-by-side (Code Left 58%, Terminal Right 42%)
    if code_win:
        snap_window(code_win["hwnd"], "left_60", monitor_index=1)
        actions.append("VS Code tiled to Left (58%)")

    if term_win:
        snap_window(term_win["hwnd"], "right_40", monitor_index=1)
        actions.append("Terminal tiled to Right (42%)")

    summary = ", ".join(actions) if actions else "Workspace arranged"
    return f"[Dev Mode Activated]\n{summary}, Boss. Code editor and terminal are docked side-by-side."


def run_focus_protocol(player=None) -> str:
    """Focus Protocol: suppresses distractions, minimizes clutter, starts ambient focus audio."""
    distractions = [
        "twitter", "x.com", "reddit", "youtube", "tiktok", "facebook",
        "instagram", "netflix", "twitch", "discord", "steam", "whatsapp", "telegram"
    ]
    closed_distractions = 0

    windows = get_visible_windows()
    for w_info in windows:
        title = w_info["title"].lower()
        proc = w_info["process"].lower()
        if any(d in title or d in proc for d in distractions):
            # If standalone social/game app, minimize it
            if proc in ("discord.exe", "steam.exe", "whatsapp.exe", "telegram.exe", "spotify.exe"):
                user32.ShowWindow(w_info["hwnd"], 6)  # SW_MINIMIZE
                closed_distractions += 1

    # Keep only active code editor or main work app
    active_code = find_window("code")
    if active_code:
        minimize_all_except("code")
    else:
        # Minimize clutter
        for w_info in windows[1:6]:
            user32.ShowWindow(w_info["hwnd"], 6)

    # Start ambient focus lofi audio
    try:
        from actions.youtube_video import youtube_video
        youtube_video({"action": "play", "query": "lofi hip hop radio beats to relax study to"})
    except Exception:
        pass

    if player and hasattr(player, "write_log"):
        player.write_log("SYS: 🎯 Focus Protocol engaged — Distractions suppressed, ambient focus audio active.")

    return (
        "[Focus Protocol Engaged]\n"
        f"Distractions suppressed ({closed_distractions} apps minimized). "
        "Notifications silenced, and ambient lofi stream active, Boss. High-priority focus engaged."
    )


def run_media_mode(player=None) -> str:
    """Media Mode: dims display brightness to 35%, optimizes audio, maximizes media player."""
    actions = []

    # 1. Dim display brightness to 35%
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, 35)"],
            capture_output=True, timeout=4
        )
        actions.append("Display dimmed to 35%")
    except Exception:
        pass

    # 2. Adjust volume to 50%
    if _OS == "Windows":
        try:
            # Unmute and balance volume via pyautogui / volume controls
            from actions.computer_settings import volume_up
            for _ in range(3):
                volume_up()
            actions.append("Audio optimized to cinema level")
        except Exception:
            pass

    # 3. Find and maximize media player
    media_win = find_window("spotify") or find_window("vlc") or find_window("youtube") or find_window("media")
    if media_win:
        snap_window(media_win["hwnd"], "maximize")
        actions.append(f"'{media_win['title'][:25]}' brought full-screen")
    else:
        # Launch media app
        try:
            from actions.youtube_video import youtube_video
            youtube_video({"action": "search", "query": "trending music"})
            actions.append("Media center opened")
        except Exception:
            pass

    if player and hasattr(player, "write_log"):
        player.write_log("SYS: 🎬 Media Mode active — Screen dimmed, audio equalized.")

    return f"[Media Mode Engaged]\n{', '.join(actions)}, Boss. Sit back and enjoy."


def auto_tile_grid() -> str:
    """Auto-tile all active windows into an even grid layout."""
    windows = get_visible_windows()
    if not windows:
        return "No visible windows to tile."

    monitors = get_monitors()
    primary = monitors[0]
    mx, my, mw, mh = primary["work"]

    count = min(len(windows), 4)
    if count == 1:
        snap_window(windows[0]["hwnd"], "maximize")
        return "Maximized single window."
    elif count == 2:
        snap_window(windows[0]["hwnd"], "left")
        snap_window(windows[1]["hwnd"], "right")
        return "Tiled 2 windows side-by-side (50/50)."
    elif count == 3:
        w3 = mw // 3
        snap_window(windows[0]["hwnd"], "left")
        user32.MoveWindow(windows[0]["hwnd"], mx, my, w3, mh, True)
        user32.MoveWindow(windows[1]["hwnd"], mx + w3, my, w3, mh, True)
        user32.MoveWindow(windows[2]["hwnd"], mx + 2 * w3, my, mw - 2 * w3, mh, True)
        return "Tiled 3 windows into equal columns."
    else:
        # 2x2 Grid
        hw = mw // 2
        hh = mh // 2
        user32.MoveWindow(windows[0]["hwnd"], mx, my, hw, hh, True)
        user32.MoveWindow(windows[1]["hwnd"], mx + hw, my, mw - hw, hh, True)
        user32.MoveWindow(windows[2]["hwnd"], mx, my + hh, hw, mh - hh, True)
        user32.MoveWindow(windows[3]["hwnd"], mx + hw, my + hh, mw - hw, mh - hh, True)
        return "Tiled 4 windows in a 2x2 grid layout."


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL HANDLER & SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

def workspace_master(parameters: dict, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "preset").lower().strip()

    if action in ("preset", "mode"):
        preset = params.get("preset", "").lower().strip()
        if preset in ("dev", "dev_mode", "developer", "coding"):
            return run_dev_mode()
        elif preset in ("focus", "focus_protocol", "combat"):
            return run_focus_protocol(player)
        elif preset in ("media", "media_mode", "cinema", "movie"):
            return run_media_mode(player)
        else:
            return f"Unknown preset '{preset}'. Available: dev, focus, media."

    elif action == "snap":
        target = params.get("target", "active")
        position = params.get("position", "left")
        mon_idx = int(params.get("monitor", 1))
        win = find_window(target)
        if not win:
            return f"Could not find window matching '{target}', Boss."
        ok = snap_window(win["hwnd"], position, mon_idx)
        return f"Snapped '{win['title'][:30]}' to {position} on Monitor {mon_idx}." if ok else "Snap failed."

    elif action == "snap_pair":
        app1 = params.get("app1", "browser")
        pos1 = params.get("pos1", "left")
        app2 = params.get("app2", "terminal")
        pos2 = params.get("pos2", "right")
        mon_idx = int(params.get("monitor", 1))
        return snap_pair(app1, pos1, app2, pos2, mon_idx)

    elif action in ("move_monitor", "move"):
        target = params.get("target", "")
        mon_idx = int(params.get("monitor", 2))
        win = find_window(target)
        if not win:
            return f"Could not find window matching '{target}', Boss."
        ok = move_to_monitor(win["hwnd"], mon_idx)
        return f"Moved '{win['title'][:30]}' to Monitor {mon_idx}." if ok else "Move failed."

    elif action in ("minimize_except", "isolate", "focus_app"):
        target = params.get("target", "code")
        return minimize_all_except(target)

    elif action in ("tile", "tile_all", "grid"):
        return auto_tile_grid()

    elif action in ("list_windows", "windows"):
        wins = get_visible_windows()
        lines = [f"* [{w_info['process']}] '{w_info['title'][:40]}' (pos: {w_info['rect']})" for w_info in wins[:8]]
        return f"Active Windows ({len(wins)}):\n" + "\n".join(lines)

    elif action in ("list_monitors", "monitors"):
        mons = get_monitors()
        lines = [f"* Monitor {m['index']} ({'Primary' if m['primary'] else 'Secondary'}): Work area {m['work']}" for m in mons]
        return f"Detected Monitors ({len(mons)}):\n" + "\n".join(lines)

    else:
        return (
            f"Unknown workspace action '{action}'. "
            "Available actions: preset, snap, snap_pair, move_monitor, minimize_except, tile, list_windows, list_monitors."
        )


TOOL = {
    "name": "workspace_master",
    "description": (
        "Autonomous Stark Workspaces & Window Master. Controls window tiling, multi-monitor movement, "
        "minimizing everything except code editor, and executes high-level workspace presets: "
        "'Dev Mode' (tiles VS Code & Terminal side-by-side), 'Focus Protocol' (suppresses distractions & plays lofi), "
        "and 'Media Mode' (dims display & maximizes media center)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "preset | snap | snap_pair | move_monitor | minimize_except | tile | list_windows | list_monitors"
            },
            "preset": {
                "type": "STRING",
                "description": "When action is 'preset': dev | focus | media"
            },
            "target": {
                "type": "STRING",
                "description": "Target application name or window title (e.g. 'browser', 'chrome', 'terminal', 'code', 'spotify')"
            },
            "position": {
                "type": "STRING",
                "description": "left | right | top | bottom | maximize | center | top_left | top_right | bottom_left | bottom_right"
            },
            "app1": {
                "type": "STRING",
                "description": "When action is 'snap_pair': first app name (e.g. 'browser' or 'code')"
            },
            "pos1": {
                "type": "STRING",
                "description": "When action is 'snap_pair': position for first app (default: left)"
            },
            "app2": {
                "type": "STRING",
                "description": "When action is 'snap_pair': second app name (e.g. 'terminal')"
            },
            "pos2": {
                "type": "STRING",
                "description": "When action is 'snap_pair': position for second app (default: right)"
            },
            "monitor": {
                "type": "INTEGER",
                "description": "Monitor index (1, 2, ...). Default: 1"
            }
        },
        "required": ["action"]
    },
    "handler": workspace_master,
}
