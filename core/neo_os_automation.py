"""
core/neo_os_automation.py — Native OS & Shell Direct Automation Engine for NEO.

Provides sub-millisecond, deterministic desktop and system control:
1. Window Grid & Workspace Layout Manager:
   - Work-area aware snapping (Left, Right, Quadrants, Maximize, Minimize, Restore, Center).
   - Side-by-side (50/50) and dual-window tiling without mouse dragging.
   - Robust foreground switching using Win32 AttachThreadInput (prevents focus loss).
2. Process & Port Watchdog:
   - Zero-delay process termination by name or PID.
   - Port inspection and auto-kill for developer port conflicts (e.g. 3000, 8080, 5000).
   - Real-time hardware health metrics (CPU, Memory, Battery, Disk).
3. Direct Desktop & File Utilities:
   - Shell-level directory opening, folder creation, and recycle bin purging.
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

_OS = platform.system()


class WindowManager:
    """Deterministic Win32/OS window geometry, layout, and focus controller."""

    # ShowWindow commands
    SW_HIDE = 0
    SW_NORMAL = 1
    SW_SHOWMINIMIZED = 2
    SW_MAXIMIZE = 3
    SW_SHOWNOACTIVATE = 4
    SW_SHOW = 5
    SW_MINIMIZE = 6
    SW_SHOWMINNOACTIVE = 7
    SW_SHOWNA = 8
    SW_RESTORE = 9

    def get_work_area(self) -> Tuple[int, int, int, int]:
        """Returns the usable desktop area (left, top, right, bottom) excluding the Windows taskbar."""
        if _OS == "Windows":
            try:
                rect = wintypes.RECT()
                # SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    return (rect.left, rect.top, rect.right, rect.bottom)
            except Exception:
                pass
        # Fallback to full screen resolution
        try:
            import pyautogui
            w, h = pyautogui.size()
            return (0, 0, w, h)
        except Exception:
            return (0, 0, 1920, 1080)

    def list_windows(self, only_visible: bool = True) -> List[Dict[str, Any]]:
        """Lists active top-level windows with their HWND, title, process, and bounding rectangle."""
        if _OS != "Windows":
            return []

        results: List[Dict[str, Any]] = []
        user32 = ctypes.windll.user32

        def enum_proc(hwnd, _lparam):
            if only_visible and not user32.IsWindowVisible(hwnd):
                return True
            if user32.IsIconic(hwnd) and only_visible:
                pass  # include minimized windows if visible flag allows

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0 and only_visible:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            # Filter out hidden tooltips, background shell windows
            if only_visible:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                cls_name = cls_buf.value
                if cls_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
                    return True

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # Process PID
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = ""
            try:
                p = psutil.Process(pid.value)
                proc_name = p.name()
            except Exception:
                pass

            if title or not only_visible:
                results.append({
                    "hwnd": int(hwnd),
                    "title": title,
                    "process_name": proc_name,
                    "pid": int(pid.value),
                    "rect": (rect.left, rect.top, rect.right, rect.bottom),
                    "width": w,
                    "height": h,
                    "is_minimized": bool(user32.IsIconic(hwnd)),
                })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
        return results

    def get_foreground_window(self) -> Optional[Dict[str, Any]]:
        """Gets metadata for the window currently holding user focus."""
        if _OS != "Windows":
            return None
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None

        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = ""
        try:
            p = psutil.Process(pid.value)
            proc_name = p.name()
        except Exception:
            pass

        return {
            "hwnd": int(hwnd),
            "title": buf.value.strip(),
            "process_name": proc_name,
            "pid": int(pid.value),
            "rect": (rect.left, rect.top, rect.right, rect.bottom),
        }

    def focus_window(self, title_or_process: str) -> bool:
        """Reliably brings target window to front and assigns focus using Win32 AttachThreadInput."""
        if _OS != "Windows":
            return False

        q = title_or_process.strip().lower()
        windows = self.list_windows(only_visible=True)
        target = None
        for w in windows:
            if q in w["title"].lower() or q in w["process_name"].lower():
                target = w
                break

        if not target:
            return False

        hwnd = target["hwnd"]
        user32 = ctypes.windll.user32
        fore_hwnd = user32.GetForegroundWindow()

        try:
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)

            if fore_tid != target_tid:
                user32.AttachThreadInput(fore_tid, target_tid, True)

            user32.ShowWindow(hwnd, self.SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

            if fore_tid != target_tid:
                user32.AttachThreadInput(fore_tid, target_tid, False)
            return True
        except Exception as e:
            print(f"[WindowManager] Focus error: {e}")
            return False

    def snap_active_window(self, position: str, hwnd: Optional[int] = None) -> bool:
        """
        Snaps the active (or specified) window to precise screen regions based on desktop work area.
        Positions: 'left', 'right', 'top', 'bottom', 'top_left', 'top_right',
                   'bottom_left', 'bottom_right', 'center', 'maximize', 'minimize', 'restore'
        """
        if _OS != "Windows":
            return False

        target_hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()
        if not target_hwnd:
            return False

        user32 = ctypes.windll.user32
        pos = position.strip().lower()

        # Handle simple states first
        if pos == "maximize":
            user32.ShowWindow(target_hwnd, self.SW_MAXIMIZE)
            return True
        if pos == "minimize":
            user32.ShowWindow(target_hwnd, self.SW_MINIMIZE)
            return True
        if pos == "restore":
            user32.ShowWindow(target_hwnd, self.SW_RESTORE)
            return True

        # Ensure window is restored before calculating coordinates
        user32.ShowWindow(target_hwnd, self.SW_RESTORE)

        l, t, r, b = self.get_work_area()
        work_w = r - l
        work_h = b - t
        half_w = work_w // 2
        half_h = work_h // 2

        new_x, new_y, new_w, new_h = l, t, work_w, work_h

        if pos == "left":
            new_x, new_y, new_w, new_h = l, t, half_w, work_h
        elif pos == "right":
            new_x, new_y, new_w, new_h = l + half_w, t, half_w, work_h
        elif pos == "top":
            new_x, new_y, new_w, new_h = l, t, work_w, half_h
        elif pos == "bottom":
            new_x, new_y, new_w, new_h = l, t + half_h, work_w, half_h
        elif pos == "top_left":
            new_x, new_y, new_w, new_h = l, t, half_w, half_h
        elif pos == "top_right":
            new_x, new_y, new_w, new_h = l + half_w, t, half_w, half_h
        elif pos == "bottom_left":
            new_x, new_y, new_w, new_h = l, t + half_h, half_w, half_h
        elif pos == "bottom_right":
            new_x, new_y, new_w, new_h = l + half_w, t + half_h, half_w, half_h
        elif pos == "center":
            target_w = int(work_w * 0.75)
            target_h = int(work_h * 0.8)
            new_x = l + (work_w - target_w) // 2
            new_y = t + (work_h - target_h) // 2
            new_w = target_w
            new_h = target_h
        else:
            return False

        # Apply geometry: SWP_NOZORDER = 0x0004
        user32.MoveWindow(target_hwnd, new_x, new_y, new_w, new_h, True)
        return True

    def tile_two_windows(self, mode: str = "side_by_side") -> bool:
        """
        Tiles the top two foreground application windows side-by-side or stacked top-and-bottom.
        """
        if _OS != "Windows":
            return False

        windows = [w for w in self.list_windows(only_visible=True) if w["width"] > 200 and w["height"] > 200]
        if len(windows) < 2:
            return False

        w1 = windows[0]["hwnd"]
        w2 = windows[1]["hwnd"]

        l, t, r, b = self.get_work_area()
        work_w = r - l
        work_h = b - t
        user32 = ctypes.windll.user32

        user32.ShowWindow(w1, self.SW_RESTORE)
        user32.ShowWindow(w2, self.SW_RESTORE)

        if mode == "stacked":
            half_h = work_h // 2
            user32.MoveWindow(w1, l, t, work_w, half_h, True)
            user32.MoveWindow(w2, l, t + half_h, work_w, half_h, True)
        else:  # side_by_side
            half_w = work_w // 2
            user32.MoveWindow(w1, l, t, half_w, work_h, True)
            user32.MoveWindow(w2, l + half_w, t, half_w, work_h, True)

        return True

    def close_window(self, title_or_process: str) -> bool:
        """Sends WM_CLOSE gracefully to the target window."""
        if _OS != "Windows":
            return False
        q = title_or_process.strip().lower()
        windows = self.list_windows(only_visible=True)
        for w in windows:
            if q in w["title"].lower() or q in w["process_name"].lower():
                # WM_CLOSE = 0x0010
                ctypes.windll.user32.PostMessageW(w["hwnd"], 0x0010, 0, 0)
                return True
        return False


class SystemResourceManager:
    """Deterministic process, hardware health, port, and shell cleanup controller."""

    def get_health(self) -> Dict[str, Any]:
        """Gathers real hardware metrics with 0 lag."""
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        battery = psutil.sensors_battery()

        return {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_gb": round((mem.total - mem.available) / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
            "battery_percent": round(battery.percent) if battery else None,
            "power_plugged": battery.power_plugged if battery else True,
        }

    def kill_process(self, target: str | int, force: bool = True) -> Dict[str, Any]:
        """Kills an unresponsive or unwanted process by PID or name."""
        killed = []
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            pid = int(target)
            try:
                p = psutil.Process(pid)
                name = p.name()
                if force:
                    p.kill()
                else:
                    p.terminate()
                return {"success": True, "killed": [f"{name} (PID {pid})"]}
            except Exception as e:
                return {"success": False, "error": str(e)}

        target_name = str(target).strip().lower()
        if not target_name.endswith(".exe") and _OS == "Windows":
            target_name_exe = f"{target_name}.exe"
        else:
            target_name_exe = target_name

        for p in psutil.process_iter(["pid", "name"]):
            try:
                p_name = p.info["name"].lower()
                if p_name == target_name or p_name == target_name_exe or target_name in p_name:
                    pid = p.info["pid"]
                    if force:
                        p.kill()
                    else:
                        p.terminate()
                    killed.append(f"{p.info['name']} (PID {pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {
            "success": len(killed) > 0,
            "killed": killed,
            "message": f"Killed {len(killed)} process(es)." if killed else f"No process matching '{target}' found."
        }

    def find_process_by_port(self, port: int) -> Optional[Dict[str, Any]]:
        """Finds which application/PID is listening on a given network port."""
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port:
                pid = conn.pid
                if pid:
                    try:
                        p = psutil.Process(pid)
                        return {
                            "port": port,
                            "pid": pid,
                            "name": p.name(),
                            "status": conn.status,
                            "cmdline": " ".join(p.cmdline()[:3]),
                        }
                    except Exception:
                        return {"port": port, "pid": pid, "name": "Unknown", "status": conn.status}
        return None

    def kill_process_by_port(self, port: int) -> bool:
        """Kills whichever process is holding a port, freeing it for development servers."""
        info = self.find_process_by_port(port)
        if info and info.get("pid"):
            res = self.kill_process(info["pid"], force=True)
            return res.get("success", False)
        return False

    def empty_recycle_bin(self) -> bool:
        """Cleans Windows Recycle Bin cleanly without dialog popups."""
        if _OS == "Windows":
            try:
                # Use powershell Clear-RecycleBin for 100% reliable execution across win10/11
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if _OS == "Windows" else 0,
                    timeout=5
                )
                return True
            except Exception:
                pass
        return False

    def open_explorer_path(self, path_str: str) -> bool:
        """Opens native file explorer to the specified folder or highlights a file."""
        p = Path(path_str).expanduser().resolve()
        if not p.exists():
            return False

        if _OS == "Windows":
            try:
                if p.is_file():
                    subprocess.Popen(f'explorer.exe /select,"{p}"', shell=True)
                else:
                    subprocess.Popen(f'explorer.exe "{p}"', shell=True)
                return True
            except Exception:
                return False
        elif _OS == "Darwin":
            subprocess.Popen(["open", str(p)])
            return True
        else:
            subprocess.Popen(["xdg-open", str(p)])
            return True

    def create_desktop_folder(self, folder_name: str) -> str:
        """Creates a clean folder directly on user's Desktop."""
        desktop = Path.home() / "Desktop"
        clean_name = folder_name.strip() or "New_Folder"
        target = desktop / clean_name
        target.mkdir(parents=True, exist_ok=True)
        return str(target)


# Global Singleton accessors
window_manager = WindowManager()
resource_manager = SystemResourceManager()
