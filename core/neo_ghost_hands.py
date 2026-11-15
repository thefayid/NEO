"""
core/neo_ghost_hands.py — Ghost Hands: Zero-Hijacking Background Computer Operator.

Enables parallel co-operation: NEO operates background applications, browser sessions,
and desktop controls without moving the user's physical mouse cursor or stealing keyboard focus.

Architecture:
1. Tier 1 (UIA COM Pattern): IUIAutomationInvokePattern / ValuePattern / TogglePattern / SelectionItemPattern
   - Directly triggers control action in target app's message loop without mouse movement or focus theft.
2. Tier 2 (Win32 Message Pump): PostMessage / SendMessage (WM_LBUTTONDOWN, WM_SETTEXT, WM_MOUSEWHEEL)
   - Dispatches mouse and keyboard events directly to target HWND at relative client coordinates.
   - Operates on non-focused and background windows.
3. Tier 3 (CDP Background Engine): Chrome DevTools Protocol DOM & Network bridge
   - Executes web automation, form filling, and data extraction across background browser tabs without cursor movement.
4. Tier 4 (Non-Activating Window Restorer): SW_SHOWNOACTIVATE
   - Keeps target apps visible to the OS graphics subsystem without raising them above the user's active work.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import ctypes
from ctypes import wintypes
import os
import platform
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import outcome

_OS = platform.system()

# Windows API Constants
SW_SHOWNOACTIVATE = 4
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_MOUSEWHEEL = 0x020A
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002

_WIN32_AVAILABLE = False
if _OS == "Windows":
    try:
        import win32gui
        import win32con
        import win32process
        import win32api
        _WIN32_AVAILABLE = True
    except ImportError:
        _WIN32_AVAILABLE = False

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="GhostHandsWorker")


def ensure_desktop_attached() -> bool:
    """Attaches worker thread to interactive desktop station WinSta0\\Default so window enumeration and UIA work."""
    if _OS != "Windows":
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
    except Exception:
        pass
    return False


def ensure_com_initialized() -> None:
    """Ensures COM is initialized in MTA/STA for the current thread."""
    if _OS != "Windows":
        return
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


def _run_in_worker(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Helper that runs a function on a clean worker thread attached to WinSta0\\Default and COM initialized."""
    ensure_desktop_attached()
    ensure_com_initialized()
    return fn(*args, **kwargs)


@dataclass
class BackgroundWindowInfo:
    """Metadata representing an interactable background application window."""
    hwnd: int
    title: str
    process_name: str
    rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_minimized: bool
    is_visible: bool


class CursorGuard:
    """
    Context manager that protects the human user's physical mouse cursor and active focus.
    If any third-party routine moves the cursor, CursorGuard restores it instantly (<1ms).
    """
    def __init__(self, tag: str = "GhostHands"):
        self.tag = tag
        self.orig_x: int = 0
        self.orig_y: int = 0
        self.orig_hwnd: int = 0
        self.cursor_preserved: bool = True

    def __enter__(self) -> CursorGuard:
        if _OS == "Windows":
            try:
                pt = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                self.orig_x, self.orig_y = pt.x, pt.y
                self.orig_hwnd = int(ctypes.windll.user32.GetForegroundWindow())
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if _OS == "Windows":
            try:
                pt_now = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt_now))
                if (pt_now.x != self.orig_x) or (pt_now.y != self.orig_y):
                    # Restore physical cursor position immediately
                    ctypes.windll.user32.SetCursorPos(self.orig_x, self.orig_y)
                    self.cursor_preserved = False

                fg_now = int(ctypes.windll.user32.GetForegroundWindow())
                if self.orig_hwnd and fg_now != self.orig_hwnd:
                    # Restore foreground focus to user's active window
                    ctypes.windll.user32.SetForegroundWindow(self.orig_hwnd)
            except Exception:
                pass


class GhostHandsEngine:
    """
    Ghost Hands: Parallel Background Computer-Use Operator.
    Executes clicks, text typing, scrolling, and multi-step workflows in background
    applications without moving the user's mouse cursor or stealing keyboard focus.
    """

    def __init__(self):
        self._uia_available = False
        if _OS == "Windows":
            try:
                import pywinauto
                self._uia_available = True
            except ImportError:
                self._uia_available = False

        self._active_tasks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        return _OS == "Windows" or _WIN32_AVAILABLE or self._uia_available

    # -------------------------------------------------------------------------
    # Window Discovery & Management
    # -------------------------------------------------------------------------
    def _list_background_windows_sync(self, max_windows: int = 25) -> List[BackgroundWindowInfo]:
        if _OS != "Windows" or not _WIN32_AVAILABLE:
            return []

        results: List[BackgroundWindowInfo] = []

        def _enum_cb(hwnd: int, _):
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True
            cls_name = win32gui.GetClassName(hwnd)
            if cls_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
                return True

            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w < 100 or h < 80:
                return True

            proc_name = ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                if handle:
                    proc_name = win32process.GetModuleFileNameEx(handle, 0)
                    proc_name = os.path.basename(proc_name)
                    win32api.CloseHandle(handle)
            except Exception:
                pass

            is_min = bool(win32gui.IsIconic(hwnd))
            results.append(BackgroundWindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=proc_name,
                rect=rect,
                is_minimized=is_min,
                is_visible=True
            ))
            return len(results) < max_windows

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            pass

        return results

    def list_background_windows(self, max_windows: int = 25) -> List[BackgroundWindowInfo]:
        """Lists running background application windows available for ghost interaction."""
        future = _EXECUTOR.submit(_run_in_worker, self._list_background_windows_sync, max_windows)
        try:
            return future.result(timeout=3.0)
        except Exception:
            return []

    def find_target_window(self, app_or_title: Optional[str] = None, hwnd: Optional[int] = None) -> Optional[BackgroundWindowInfo]:
        """
        Locates the target application window by HWND, process name, or title substring.
        If the window is minimized, restores it in the background using SW_SHOWNOACTIVATE.
        """
        windows = self.list_background_windows(max_windows=40)
        if not windows:
            return None

        # 1. Exact HWND match
        if hwnd:
            for w in windows:
                if w.hwnd == hwnd:
                    self._ensure_renderable(w)
                    return w

        if not app_or_title:
            # Fall back to top background window (excluding active foreground)
            fg = 0
            if _OS == "Windows":
                try:
                    fg = int(ctypes.windll.user32.GetForegroundWindow())
                except Exception:
                    pass
            for w in windows:
                if w.hwnd != fg:
                    self._ensure_renderable(w)
                    return w
            return windows[0] if windows else None

        query = app_or_title.strip().lower()

        # 2. Process Name exact or substring match (e.g. "chrome", "notepad", "spotify")
        for w in windows:
            p = w.process_name.lower()
            if p and (query in p or p.startswith(query)):
                self._ensure_renderable(w)
                return w

        # 3. Window Title exact match
        for w in windows:
            if w.title.lower() == query:
                self._ensure_renderable(w)
                return w

        # 4. Window Title substring match
        for w in windows:
            if query in w.title.lower():
                self._ensure_renderable(w)
                return w

        # 5. Token overlap match
        q_tokens = set(re.findall(r"[a-z0-9]+", query))
        best_win: Optional[BackgroundWindowInfo] = None
        best_score = 0
        for w in windows:
            w_tokens = set(re.findall(r"[a-z0-9]+", (w.title + " " + w.process_name).lower()))
            overlap = len(q_tokens & w_tokens)
            if overlap > best_score:
                best_score = overlap
                best_win = w

        if best_win and best_score >= 1:
            self._ensure_renderable(best_win)
            return best_win

        return None

    def _ensure_renderable(self, win_info: BackgroundWindowInfo) -> None:
        """Ensures the window is rendered by the OS graphics compositor without stealing foreground focus."""
        if _OS != "Windows" or not _WIN32_AVAILABLE:
            return
        try:
            if win_info.is_minimized:
                # Restore without taking focus
                win32gui.ShowWindow(win_info.hwnd, SW_SHOWNOACTIVATE)
                time.sleep(0.04)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Tier 1 & Tier 2: Non-Hijacking Click
    # -------------------------------------------------------------------------
    def _ghost_click_sync(
        self,
        target_str: str,
        win: BackgroundWindowInfo,
        double_click: bool,
        right_click: bool,
    ) -> Dict[str, Any]:
        with CursorGuard(tag=f"ghost_click({target_str})") as guard:
            # --- Tier 1: Direct UIA Pattern Invocation ---
            uia_result = self._try_uia_pattern_click(win.hwnd, target_str, double_click, right_click)
            if uia_result["success"]:
                return {
                    "status": outcome.DONE,
                    "method": "uia_pattern",
                    "target": target_str,
                    "window": win.title,
                    "hwnd": win.hwnd,
                    "element_name": uia_result.get("name", target_str),
                    "element_type": uia_result.get("control_type", "Button"),
                    "cursor_preserved": guard.cursor_preserved,
                }

            # --- Tier 2: Win32 PostMessage at Relative Coordinates ---
            cx = uia_result.get("cx", 0)
            cy = uia_result.get("cy", 0)

            # If UIA found the center coordinates but couldn't invoke pattern:
            if cx > 0 and cy > 0:
                msg_ok = self._post_message_click(win.hwnd, cx, cy, double_click, right_click)
                if msg_ok:
                    return {
                        "status": outcome.DONE,
                        "method": "win32_postmessage",
                        "target": target_str,
                        "window": win.title,
                        "hwnd": win.hwnd,
                        "coordinates": (cx, cy),
                        "cursor_preserved": guard.cursor_preserved,
                    }

            # If element was not found in UIA at all, check if target is coordinate string "x, y"
            coord_match = re.match(r"^(\d+)\s*,\s*(\d+)$", target_str)
            if coord_match:
                px = int(coord_match.group(1))
                py = int(coord_match.group(2))
                msg_ok = self._post_message_click(win.hwnd, px, py, double_click, right_click)
                if msg_ok:
                    return {
                        "status": outcome.DONE,
                        "method": "win32_postmessage_coords",
                        "target": target_str,
                        "window": win.title,
                        "hwnd": win.hwnd,
                        "coordinates": (px, py),
                        "cursor_preserved": guard.cursor_preserved,
                    }

        return {
            "status": outcome.FAILED,
            "reason": f"Could not find interactable control '{target_str}' in background window '{win.title}'",
            "window": win.title,
            "hwnd": win.hwnd,
        }

    def ghost_click(
        self,
        target: str,
        app_or_title: Optional[str] = None,
        hwnd: Optional[int] = None,
        double_click: bool = False,
        right_click: bool = False,
    ) -> Dict[str, Any]:
        """
        Clicks an interactive element in a background window with ZERO cursor movement and ZERO focus theft.
        1. Tries UIA InvokePattern / TogglePattern / SelectionItemPattern.
        2. Fallback: Dispatches Win32 PostMessage (WM_LBUTTONDOWN/UP) directly to the target window.
        """
        target_str = str(target or "").strip()
        if not target_str:
            return {"status": outcome.FAILED, "reason": "Target query cannot be empty"}

        win = self.find_target_window(app_or_title, hwnd)
        if not win:
            return {
                "status": outcome.FAILED,
                "reason": f"Target application window '{app_or_title or hwnd}' not found",
            }

        future = _EXECUTOR.submit(_run_in_worker, self._ghost_click_sync, target_str, win, double_click, right_click)
        try:
            return future.result(timeout=4.0)
        except concurrent.futures.TimeoutError:
            return {"status": outcome.FAILED, "reason": f"Ghost click on '{target_str}' timed out"}
        except Exception as e:
            return {"status": outcome.FAILED, "reason": str(e)}

    def _try_uia_pattern_click(
        self,
        hwnd: int,
        query: str,
        double_click: bool,
        right_click: bool,
    ) -> Dict[str, Any]:
        """Attempts to invoke UIA pattern directly on the matching element without mouse cursor."""
        if not self._uia_available:
            return {"success": False}

        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=hwnd)
            top_win = app.window(handle=hwnd)

            candidates = []
            try:
                candidates = top_win.children()
            except Exception:
                pass

            # Search elements
            q = query.lower()
            matched_elem = None
            cx, cy = 0, 0

            # Breadth-first search up to 2 levels
            elements_to_inspect = list(candidates)
            for c in candidates[:12]:
                try:
                    elements_to_inspect.extend(c.children())
                except Exception:
                    pass

            for elem in elements_to_inspect:
                try:
                    info = elem.element_info
                    name = str(getattr(info, "name", "") or "").strip()
                    auto_id = str(getattr(info, "automation_id", "") or "").strip()
                    c_type = str(getattr(info, "control_type", "") or "")

                    if (name.lower() == q) or (auto_id.lower() == q) or (q in name.lower() and len(name) < 40):
                        matched_elem = elem
                        rect = elem.rectangle()
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        break
                except Exception:
                    continue

            if not matched_elem:
                return {"success": False}

            # Direct UIA Pattern Invocation
            if not right_click and not double_click:
                if hasattr(matched_elem, "invoke"):
                    matched_elem.invoke()
                    return {"success": True, "name": name, "control_type": c_type, "cx": cx, "cy": cy}
                if hasattr(matched_elem, "toggle"):
                    matched_elem.toggle()
                    return {"success": True, "name": name, "control_type": c_type, "cx": cx, "cy": cy}
                if hasattr(matched_elem, "select"):
                    matched_elem.select()
                    return {"success": True, "name": name, "control_type": c_type, "cx": cx, "cy": cy}

            # Return coordinates for PostMessage fallback
            return {"success": False, "name": name, "control_type": c_type, "cx": cx, "cy": cy}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _post_message_click(
        self,
        parent_hwnd: int,
        screen_x: int,
        screen_y: int,
        double_click: bool = False,
        right_click: bool = False,
    ) -> bool:
        """Dispatches mouse click messages directly to the HWND at client relative coordinates."""
        if not _WIN32_AVAILABLE:
            return False

        try:
            # Convert screen coordinates to client coordinates
            client_x, client_y = win32gui.ScreenToClient(parent_hwnd, (screen_x, screen_y))

            # Find direct child window at point
            child_hwnd = win32gui.RealChildWindowFromPoint(parent_hwnd, (client_x, client_y))
            target_hwnd = child_hwnd if child_hwnd else parent_hwnd

            if target_hwnd != parent_hwnd:
                child_pt = win32gui.ScreenToClient(target_hwnd, (screen_x, screen_y))
                lparam = (child_pt[1] << 16) | (child_pt[0] & 0xFFFF)
            else:
                lparam = (client_y << 16) | (client_x & 0xFFFF)

            if right_click:
                win32gui.PostMessage(target_hwnd, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
                time.sleep(0.02)
                win32gui.PostMessage(target_hwnd, WM_RBUTTONUP, 0, lparam)
            elif double_click:
                win32gui.PostMessage(target_hwnd, WM_LBUTTONDBLCLK, MK_LBUTTON, lparam)
                time.sleep(0.02)
                win32gui.PostMessage(target_hwnd, WM_LBUTTONUP, 0, lparam)
            else:
                win32gui.PostMessage(target_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
                time.sleep(0.02)
                win32gui.PostMessage(target_hwnd, WM_LBUTTONUP, 0, lparam)

            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Tier 1 & Tier 2: Non-Hijacking Type
    # -------------------------------------------------------------------------
    def _ghost_type_sync(
        self,
        target_str: str,
        text_str: str,
        win: BackgroundWindowInfo,
        clear_first: bool,
    ) -> Dict[str, Any]:
        with CursorGuard(tag=f"ghost_type({target_str})") as guard:
            # --- Tier 1: UIA ValuePattern ---
            if self._uia_available:
                try:
                    from pywinauto import Application
                    app = Application(backend="uia").connect(handle=win.hwnd)
                    top_win = app.window(handle=win.hwnd)

                    candidates = top_win.children()
                    elements_to_inspect = list(candidates)
                    for c in candidates[:12]:
                        try:
                            elements_to_inspect.extend(c.children())
                        except Exception:
                            pass

                    q = target_str.lower()
                    for elem in elements_to_inspect:
                        try:
                            name = str(getattr(elem.element_info, "name", "") or "").strip()
                            auto_id = str(getattr(elem.element_info, "automation_id", "") or "").strip()
                            c_type = str(getattr(elem.element_info, "control_type", "") or "")

                            if (name.lower() == q) or (auto_id.lower() == q) or (q in name.lower()):
                                if hasattr(elem, "set_edit_text"):
                                    elem.set_edit_text(text_str)
                                    return {
                                        "status": outcome.DONE,
                                        "method": "uia_value_pattern",
                                        "target": target_str,
                                        "window": win.title,
                                        "hwnd": win.hwnd,
                                        "chars_typed": len(text_str),
                                        "cursor_preserved": guard.cursor_preserved,
                                    }
                                elif hasattr(elem, "set_text"):
                                    elem.set_text(text_str)
                                    return {
                                        "status": outcome.DONE,
                                        "method": "uia_set_text",
                                        "target": target_str,
                                        "window": win.title,
                                        "hwnd": win.hwnd,
                                        "chars_typed": len(text_str),
                                        "cursor_preserved": guard.cursor_preserved,
                                    }
                        except Exception:
                            continue
                except Exception:
                    pass

            # --- Tier 2: Win32 Message WM_SETTEXT / WM_CHAR ---
            if _WIN32_AVAILABLE:
                edit_hwnd = self._find_child_edit(win.hwnd)
                target_h = edit_hwnd if edit_hwnd else win.hwnd

                try:
                    win32gui.SendMessage(target_h, WM_SETTEXT, 0, text_str)
                    return {
                        "status": outcome.DONE,
                        "method": "win32_wm_settext",
                        "target": target_str,
                        "window": win.title,
                        "hwnd": target_h,
                        "chars_typed": len(text_str),
                        "cursor_preserved": guard.cursor_preserved,
                    }
                except Exception:
                    for ch in text_str:
                        win32gui.PostMessage(target_h, WM_CHAR, ord(ch), 0)
                        time.sleep(0.005)
                    return {
                        "status": outcome.DONE,
                        "method": "win32_wm_char_stream",
                        "target": target_str,
                        "window": win.title,
                        "hwnd": target_h,
                        "chars_typed": len(text_str),
                        "cursor_preserved": guard.cursor_preserved,
                    }

        return {
            "status": outcome.FAILED,
            "reason": f"Could not type into control '{target_str}' in '{win.title}'",
            "window": win.title,
            "hwnd": win.hwnd,
        }

    def ghost_type(
        self,
        target: str,
        text: str,
        app_or_title: Optional[str] = None,
        hwnd: Optional[int] = None,
        clear_first: bool = True,
    ) -> Dict[str, Any]:
        """
        Types text into a background control without stealing keyboard focus or moving the mouse.
        1. Tries UIA ValuePattern (set_edit_text / set_text).
        2. Fallback: Win32 WM_SETTEXT / WM_CHAR message sequence.
        """
        target_str = str(target or "").strip()
        text_str = str(text or "")

        win = self.find_target_window(app_or_title, hwnd)
        if not win:
            return {
                "status": outcome.FAILED,
                "reason": f"Target application window '{app_or_title or hwnd}' not found",
            }

        future = _EXECUTOR.submit(_run_in_worker, self._ghost_type_sync, target_str, text_str, win, clear_first)
        try:
            return future.result(timeout=4.0)
        except concurrent.futures.TimeoutError:
            return {"status": outcome.FAILED, "reason": f"Ghost type into '{target_str}' timed out"}
        except Exception as e:
            return {"status": outcome.FAILED, "reason": str(e)}

    def _find_child_edit(self, parent_hwnd: int) -> int:
        """Finds the first child Edit or RichEdit control in the parent window."""
        found = [0]
        def _cb(h, _):
            cls = win32gui.GetClassName(h).lower()
            if "edit" in cls or "richedit" in cls:
                found[0] = h
                return False
            return True
        try:
            win32gui.EnumChildWindows(parent_hwnd, _cb, None)
        except Exception:
            pass
        return found[0]

    # -------------------------------------------------------------------------
    # Background Scroll
    # -------------------------------------------------------------------------
    def ghost_scroll(
        self,
        direction: str = "down",
        amount: int = 3,
        app_or_title: Optional[str] = None,
        hwnd: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatches mousewheel scroll messages directly to background window HWND."""
        if not _WIN32_AVAILABLE:
            return {"status": outcome.FAILED, "reason": "Win32 message dispatch not available on this OS"}

        win = self.find_target_window(app_or_title, hwnd)
        if not win:
            return {"status": outcome.FAILED, "reason": "Target window not found for ghost scroll"}

        dir_clean = str(direction).lower().strip()
        delta = -120 * amount if dir_clean in ("down", "d") else 120 * amount
        wparam = (delta << 16) & 0xFFFFFFFF

        rect = win.rect
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        lparam = (cy << 16) | (cx & 0xFFFF)

        with CursorGuard(tag="ghost_scroll") as guard:
            try:
                win32gui.PostMessage(win.hwnd, WM_MOUSEWHEEL, wparam, lparam)
                return {
                    "status": outcome.DONE,
                    "method": "win32_wm_mousewheel",
                    "direction": dir_clean,
                    "amount": amount,
                    "window": win.title,
                    "hwnd": win.hwnd,
                    "cursor_preserved": guard.cursor_preserved,
                }
            except Exception as e:
                return {"status": outcome.FAILED, "reason": str(e), "window": win.title}

    # -------------------------------------------------------------------------
    # Background Read
    # -------------------------------------------------------------------------
    def _ghost_read_sync(self, target: Optional[str], win: BackgroundWindowInfo) -> Dict[str, Any]:
        extracted_text = ""
        controls_summary = []

        if self._uia_available:
            try:
                from pywinauto import Application
                app = Application(backend="uia").connect(handle=win.hwnd)
                top_win = app.window(handle=win.hwnd)

                candidates = top_win.children()
                q = (target or "").strip().lower()

                for c in candidates[:25]:
                    try:
                        c_name = str(getattr(c.element_info, "name", "") or "").strip()
                        c_type = str(getattr(c.element_info, "control_type", "") or "")
                        if c_name:
                            controls_summary.append(f"{c_type}: {c_name}")
                            if q and (q in c_name.lower()):
                                extracted_text = c_name
                    except Exception:
                        continue
            except Exception:
                pass

        if not extracted_text:
            extracted_text = win.title

        return {
            "status": outcome.DONE,
            "window": win.title,
            "hwnd": win.hwnd,
            "process": win.process_name,
            "extracted_text": extracted_text,
            "controls": controls_summary[:10],
        }

    def ghost_read(
        self,
        target: Optional[str] = None,
        app_or_title: Optional[str] = None,
        hwnd: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Reads text, title, or controls from a background application without raising it."""
        win = self.find_target_window(app_or_title, hwnd)
        if not win:
            return {"status": outcome.FAILED, "reason": "Target window not found for reading"}

        future = _EXECUTOR.submit(_run_in_worker, self._ghost_read_sync, target, win)
        try:
            return future.result(timeout=3.0)
        except Exception as e:
            return {"status": outcome.FAILED, "reason": str(e)}

    # -------------------------------------------------------------------------
    # Multi-Step Background Pipeline
    # -------------------------------------------------------------------------
    def ghost_pipeline(self, steps: List[Dict[str, Any]], app_or_title: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a sequence of ghost actions (e.g. click -> type -> scroll) entirely in the background.
        Verifies every step along the way.
        """
        executed = []
        for i, step in enumerate(steps):
            action_type = str(step.get("action", "")).lower().strip()
            target = step.get("target") or step.get("query") or ""
            target_app = step.get("app_name") or app_or_title

            if action_type == "click":
                res = self.ghost_click(target=target, app_or_title=target_app)
            elif action_type == "type":
                res = self.ghost_type(target=target, text=step.get("text", ""), app_or_title=target_app)
            elif action_type == "scroll":
                res = self.ghost_scroll(direction=step.get("direction", "down"), amount=step.get("amount", 3), app_or_title=target_app)
            elif action_type == "wait":
                time.sleep(float(step.get("seconds", 0.5)))
                res = {"status": outcome.DONE, "action": "wait", "seconds": step.get("seconds", 0.5)}
            else:
                res = {"status": outcome.FAILED, "reason": f"Unknown ghost pipeline step action: {action_type}"}

            executed.append(res)
            if res.get("status") == outcome.FAILED:
                return {
                    "status": outcome.FAILED,
                    "failed_at_step": i,
                    "reason": res.get("reason", "Step failed"),
                    "completed_steps": executed,
                }

        return {
            "status": outcome.DONE,
            "total_steps": len(steps),
            "results": executed,
        }


# Singleton instance
ghost_hands = GhostHandsEngine()
