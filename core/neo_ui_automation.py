"""
core/neo_ui_automation.py — Native Windows UI Automation (UIA) Precision Engine.

Provides mathematically exact physical pixel targeting for buttons, inputs, links, tabs,
and menus across desktop applications without coordinate hallucination or vision drift.
Uses Windows UI Automation Core / pywinauto under WinSta0 desktop station.
"""
from __future__ import annotations

import concurrent.futures
import ctypes
from ctypes import wintypes
import os
import platform
import re
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=UserWarning, module="pywinauto")

_OS = platform.system()
_ATTACHED_THREADS = set()
_ATTACH_LOCK = threading.Lock()
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="UIAWorker")


def ensure_com_initialized() -> None:
    """Ensures COM is initialized in MTA/STA for the current thread."""
    if _OS != "Windows":
        return
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


def ensure_desktop_attached() -> bool:
    """Attaches the interactive desktop station so UIA works reliably across worker threads without leaking handles."""
    if _OS != "Windows":
        return False
    tid = threading.get_ident()
    with _ATTACH_LOCK:
        if tid in _ATTACHED_THREADS:
            return True
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
                hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                if hdesk:
                    user32.SetThreadDesktop(hdesk)
                    _ATTACHED_THREADS.add(tid)
                    return True
        except Exception:
            pass
    return False


@dataclass
class UIControl:
    """Represents a discrete, exact native UI control from the OS accessibility tree."""
    name: str
    control_type: str
    rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    center: Tuple[int, int]          # (cx, cy)
    handle: int
    automation_id: str = ""
    is_enabled: bool = True
    is_visible: bool = True

    @property
    def width(self) -> int:
        return max(0, self.rect[2] - self.rect[0])

    @property
    def height(self) -> int:
        return max(0, self.rect[3] - self.rect[1])

    @property
    def area(self) -> int:
        return self.width * self.height


class WindowsUIAutomationEngine:
    """
    Direct interface to Windows UI Automation tree for 0-drift pixel targeting.
    """
    _INTERACTIVE_TYPES = {
        "Button", "Edit", "Hyperlink", "MenuItem", "TabItem",
        "CheckBox", "RadioButton", "ComboBox", "ListItem", "TreeItem",
        "SplitButton", "ToolBar", "AppBar", "Thumb", "Custom"
    }

    def __init__(self):
        self._available = False
        if _OS == "Windows":
            try:
                import pywinauto
                self._available = True
            except ImportError:
                self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def get_foreground_handle(self) -> int:
        """Returns the Win32 HWND of the currently active foreground window, or top visible application."""
        if _OS != "Windows":
            return 0
        ensure_desktop_attached()
        try:
            user32 = ctypes.windll.user32
            fore = int(user32.GetForegroundWindow())
            if fore:
                return fore

            # Fallback: find top-most visible application window on the desktop
            hwnd = user32.GetTopWindow(0)
            while hwnd:
                if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                    r = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                    w = r.right - r.left
                    h = r.bottom - r.top
                    if w > 300 and h > 200:
                        cls = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls, 256)
                        if cls.value not in ("Progman", "WorkerW", "Shell_TrayWnd"):
                            return int(hwnd)
                hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT
        except Exception:
            pass
        return 0

    def get_foreground_title(self) -> str:
        """Returns the window title of the current foreground window."""
        hwnd = self.get_foreground_handle()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value

    def get_top_windows(self, max_windows: int = 5) -> List[Tuple[int, str]]:
        """Enumerates top visible application windows (HWND, title)."""
        if _OS != "Windows":
            return []
        ensure_desktop_attached()
        results: List[Tuple[int, str]] = []
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetTopWindow(0)
            while hwnd and len(results) < max_windows:
                if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                    r = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                    w = r.right - r.left
                    h = r.bottom - r.top
                    if w > 250 and h > 150:
                        cls = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls, 256)
                        if cls.value not in ("Progman", "WorkerW", "Shell_TrayWnd"):
                            tbuf = ctypes.create_unicode_buffer(512)
                            user32.GetWindowTextW(hwnd, tbuf, 512)
                            title = tbuf.value.strip()
                            if title:
                                results.append((int(hwnd), title))
                hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT
        except Exception:
            pass
        return results

    def _extract_controls_sync(self, target_hwnd: int, max_items: int) -> List[UIControl]:
        """Internal synchronous extractor with COM initialization."""
        ensure_com_initialized()
        ensure_desktop_attached()

        controls: List[UIControl] = []
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=target_hwnd)
            win = app.window(handle=target_hwnd)

            # First priority: Fast scan of top-level children
            immediate_elements = []
            try:
                immediate_elements = win.children()
            except Exception:
                pass

            # If immediate children available, also get second-level descendants
            candidates = list(immediate_elements)
            for child in immediate_elements[:15]:
                try:
                    sub = child.children()
                    candidates.extend(sub)
                    if len(candidates) >= (max_items * 2):
                        break
                except Exception:
                    continue

            for elem in candidates:
                try:
                    c_type = str(getattr(elem.element_info, "control_type", "") or "")
                    if c_type not in self._INTERACTIVE_TYPES:
                        continue

                    rect = elem.rectangle()
                    w = rect.width()
                    h = rect.height()
                    if w < 6 or h < 6 or rect.left < -500 or rect.top < -500:
                        continue

                    name = str(getattr(elem.element_info, "name", "") or "").strip()
                    auto_id = str(getattr(elem.element_info, "automation_id", "") or "").strip()

                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2

                    ctrl = UIControl(
                        name=name,
                        control_type=c_type,
                        rect=(rect.left, rect.top, rect.right, rect.bottom),
                        center=(cx, cy),
                        handle=target_hwnd,
                        automation_id=auto_id,
                        is_enabled=bool(getattr(elem.element_info, "enabled", True)),
                        is_visible=bool(getattr(elem.element_info, "visible", True)),
                    )
                    controls.append(ctrl)
                    if len(controls) >= max_items:
                        break
                except Exception:
                    continue
        except Exception:
            pass

        return controls

    def get_interactive_controls(self, hwnd: int = 0, max_items: int = 80, timeout_secs: float = 2.0) -> List[UIControl]:
        """
        Extracts interactive UI controls from the target window with a hard timeout to prevent freezes.
        """
        if not self._available or _OS != "Windows":
            return []

        target_hwnd = hwnd or self.get_foreground_handle()
        if not target_hwnd:
            return []

        # Run with strict timeout
        future = _EXECUTOR.submit(self._extract_controls_sync, target_hwnd, max_items)
        try:
            return future.result(timeout=timeout_secs)
        except concurrent.futures.TimeoutError:
            print(f"[UIA] ⚠️ get_interactive_controls timed out after {timeout_secs}s on hwnd={target_hwnd}")
            return []
        except Exception as e:
            return []

    def find_control(self, query: str, hwnd: int = 0, search_all_windows: bool = True) -> Optional[UIControl]:
        """
        Finds a control matching query with high precision and zero freeze risk.
        """
        q = (query or "").strip().lower()
        if not q:
            return None

        primary_hwnd = hwnd or self.get_foreground_handle()
        target_hwnds = [primary_hwnd] if primary_hwnd else [0]

        if search_all_windows:
            top_windows = self.get_top_windows(max_windows=3)
            for h, _ in top_windows:
                if h not in target_hwnds:
                    target_hwnds.append(h)

        q_tokens = set(re.findall(r"[a-z0-9]+", q))

        for target_h in target_hwnds:
            controls = self.get_interactive_controls(hwnd=target_h, timeout_secs=1.5)
            if not controls:
                continue

            # 1. Exact Name / Automation ID Match
            for c in controls:
                c_name = c.name.lower()
                c_id = c.automation_id.lower()
                if c_name == q or c_id == q:
                    return c

            # If single-character or very short query, do NOT do fuzzy match
            if len(q) <= 2:
                continue

            # 2. Direct Substring Match
            for c in controls:
                c_name = c.name.lower()
                if (q in c_name) or (len(c_name) > 3 and c_name in q):
                    return c

            # 3. Token Overlap Score
            best_ctrl: Optional[UIControl] = None
            best_score = 0
            for c in controls:
                c_tokens = set(re.findall(r"[a-z0-9]+", c.name.lower()))
                c_tokens.add(c.control_type.lower())
                overlap = len(q_tokens & c_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_ctrl = c

            if best_ctrl and best_score >= 1:
                return best_ctrl

        return None

    def click_control_by_name(
        self,
        query: str,
        hwnd: int = 0,
        double_click: bool = False,
        right_click: bool = False,
    ) -> Tuple[bool, str, Tuple[int, int]]:
        """
        Finds the exact control by name and clicks its physical center with 0-drift precision.
        Returns: (success: bool, detail: str, center: (cx, cy))
        """
        ctrl = self.find_control(query, hwnd=hwnd)
        if not ctrl:
            return False, f"Control '{query}' not found in active window UIA tree.", (0, 0)

        cx, cy = ctrl.center
        try:
            # Ensure window is foreground
            if ctrl.handle and _OS == "Windows":
                try:
                    ctypes.windll.user32.SetForegroundWindow(ctrl.handle)
                    time.sleep(0.04)
                except Exception:
                    pass

            # Native OS click
            import pyautogui
            if double_click:
                pyautogui.doubleClick(cx, cy)
                action_verb = "Double-clicked"
            elif right_click:
                pyautogui.rightClick(cx, cy)
                action_verb = "Right-clicked"
            else:
                pyautogui.click(cx, cy)
                action_verb = "Clicked"

            return True, f"{action_verb} {ctrl.control_type} '{ctrl.name}' at exact physical coordinates ({cx}, {cy}).", (cx, cy)
        except Exception as e:
            return False, f"Failed clicking control '{ctrl.name}': {e}", (cx, cy)


# Singleton Instance
ui_automation = WindowsUIAutomationEngine()
