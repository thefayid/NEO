"""
core/neo_ambient_sensor.py — Ambient Nervous System for NEO.

Continuous sensory ingestion across the host operating system:
1. Foreground Application & Active Window Context (VS Code, Terminal, Browser, etc.).
2. Terminal & Developer Process Error Watcher (Tracebacks, build failures, crash dumps).
3. Clipboard & Link Observer (GitHub repos, PyPI commands, code snippets, stack traces).
4. Workspace & Git Sentinel (Uncommitted edits, dirty branches, modified count).
5. Calendar & Circadian Clock (Upcoming meetings, Night Owl focus state).
6. System Telemetry & Vitals (RAM saturation, CPU load, battery status).
7. User Activity & Focus State Machine (ACTIVE_TYPING, FOCUSED_IDLE, AWAY).
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import psutil

_BASE_DIR = Path(__file__).resolve().parent.parent


class UserFocusState(Enum):
    ACTIVE_TYPING = "ACTIVE_TYPING"  # Interacted in last 10s (DND for voice)
    FOCUSED_IDLE  = "FOCUSED_IDLE"   # Idle 10s - 3m (Prime for smart chips / toasts)
    AWAY          = "AWAY"           # Idle > 3m


class NEOAmbientSensor(QObject):
    """
    Continuous sensory scanner that builds a live ambient snapshot of the user's workspace.
    """
    telemetry_updated = pyqtSignal(dict)
    error_detected = pyqtSignal(str, str)      # error_type, details
    clipboard_detected = pyqtSignal(str, str)  # content_type, text
    meeting_imminent = pyqtSignal(str, int)    # event_title, minutes_until

    def __init__(self, sample_interval_ms: int = 3500, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._sample_interval_ms = sample_interval_ms
        self._is_running = False
        self._lock = threading.Lock()

        # Telemetry State
        self._last_user_activity = time.time()
        self._last_clipboard_text = ""
        self._last_snapshot: Dict[str, Any] = {}
        self._recent_errors: List[Dict[str, Any]] = []

        # Win32 Helpers
        self._is_windows = sys.platform.startswith("win")

        # Timer for polling
        self._timer = QTimer(self)
        self._timer.setInterval(self._sample_interval_ms)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        """Starts ambient sensory sampling."""
        if not self._is_running:
            self._is_running = True
            self._timer.start()
            # Perform initial synchronous scan
            self._on_tick()

    def stop(self) -> None:
        """Stops ambient sensory sampling."""
        self._is_running = False
        self._timer.stop()

    def record_user_input(self) -> None:
        """Called whenever the user types or clicks inside the UI."""
        self._last_user_activity = time.time()

    def get_focus_state(self) -> UserFocusState:
        """Returns the current user attention / focus state."""
        idle_secs = time.time() - self._last_user_activity
        if idle_secs < 10.0:
            return UserFocusState.ACTIVE_TYPING
        elif idle_secs < 180.0:
            return UserFocusState.FOCUSED_IDLE
        return UserFocusState.AWAY

    def get_latest_snapshot(self) -> Dict[str, Any]:
        """Returns the latest ambient sensory snapshot."""
        with self._lock:
            return dict(self._last_snapshot)

    # ─────────────────────────────────────────────────────────────────────────
    # Sampling Routine
    # ─────────────────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        """Background tick sampling all OS sensors in a worker thread."""
        def _worker():
            try:
                snap = self._collect_snapshot()
                with self._lock:
                    self._last_snapshot = snap
                self.telemetry_updated.emit(snap)
            except Exception as e:
                pass

        threading.Thread(target=_worker, daemon=True, name="neo-ambient-sampler").start()

    def _collect_snapshot(self) -> Dict[str, Any]:
        """Collects full multi-sensor ambient state."""
        foreground = self._get_foreground_window()
        vitals = self._get_system_vitals()
        git_state = self._get_git_state()
        agenda = self._get_upcoming_agenda()
        clipboard = self._check_clipboard()
        focus_state = self.get_focus_state()

        return {
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%I:%M %p"),
            "focus_state": focus_state.value,
            "idle_seconds": round(time.time() - self._last_user_activity, 1),
            "foreground": foreground,
            "vitals": vitals,
            "git": git_state,
            "agenda": agenda,
            "clipboard": clipboard,
            "recent_errors": list(self._recent_errors[-3:]),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Foreground Window & App Detection
    # ─────────────────────────────────────────────────────────────────────────

    def _get_foreground_window(self) -> Dict[str, Any]:
        """Detects the foreground active window title and process name."""
        if not self._is_windows:
            return {"app_name": "unknown", "title": "", "pid": 0}

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return {"app_name": "desktop", "title": "Desktop", "pid": 0}

            # Window Title
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value or ""

            # Process ID & Name
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = "unknown"
            try:
                p = psutil.Process(pid.value)
                proc_name = p.name()
            except Exception:
                pass

            # Classify IDE / Terminal / Browser
            app_category = "other"
            proc_lower = proc_name.lower()
            if any(term in proc_lower for term in ("code", "pycharm", "cursor", "devenv")):
                app_category = "ide"
            elif any(term in proc_lower for term in ("terminal", "powershell", "cmd", "bash", "wt")):
                app_category = "terminal"
            elif any(term in proc_lower for term in ("chrome", "msedge", "firefox", "brave")):
                app_category = "browser"

            # Check if title indicates build error or failure
            self._inspect_window_title_for_errors(title, proc_name)

            return {
                "app_name": proc_name,
                "title": title,
                "pid": pid.value,
                "category": app_category,
            }
        except Exception:
            return {"app_name": "unknown", "title": "", "pid": 0, "category": "other"}

    def _inspect_window_title_for_errors(self, title: str, proc_name: str) -> None:
        """Checks for terminal/build error keywords in foreground window title."""
        title_lower = title.lower()
        error_keywords = ("failed", "error", "traceback", "exception", "crashed")
        for kw in error_keywords:
            if kw in title_lower:
                err_record = {
                    "source": proc_name,
                    "keyword": kw,
                    "title": title[:80],
                    "timestamp": time.time(),
                }
                self._recent_errors.append(err_record)
                self.error_detected.emit(kw.upper(), title[:80])
                break

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Clipboard & Link Observer
    # ─────────────────────────────────────────────────────────────────────────

    def _check_clipboard(self) -> Dict[str, Any]:
        """Inspects clipboard content without stealing OS focus."""
        if not self._is_windows:
            return {"type": "none", "content": ""}

        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                else:
                    text = ""
            finally:
                win32clipboard.CloseClipboard()

            text = (text or "").strip()
            if not text or text == self._last_clipboard_text:
                return {"type": "unchanged", "content": ""}

            self._last_clipboard_text = text
            content_type = "plain_text"

            if text.startswith("https://github.com/") or text.startswith("git@github.com:"):
                content_type = "github_repo"
            elif text.startswith("https://") or text.startswith("http://"):
                content_type = "url"
            elif "Traceback (most recent call last)" in text or "Error:" in text:
                content_type = "stack_trace"
                self._recent_errors.append({
                    "source": "clipboard",
                    "keyword": "traceback",
                    "title": text.splitlines()[-1][:80] if text.splitlines() else "Traceback",
                    "timestamp": time.time(),
                })
                self.error_detected.emit("STACK_TRACE", text[:120])
            elif text.startswith("pip install ") or text.startswith("npm i ") or text.startswith("npm install "):
                content_type = "package_install"
            elif text.startswith("{") and text.endswith("}"):
                content_type = "json"

            if content_type != "plain_text":
                self.clipboard_detected.emit(content_type, text[:150])

            return {
                "type": content_type,
                "content": text[:200],
                "char_count": len(text),
            }
        except Exception:
            return {"type": "none", "content": ""}

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Workspace & Git Sentinel
    # ─────────────────────────────────────────────────────────────────────────

    def _get_git_state(self) -> Dict[str, Any]:
        """Checks uncommitted files and branch status in active project workspace."""
        proj_dir = _BASE_DIR
        try:
            p_file = _BASE_DIR / "memory" / "projects.json"
            if p_file.exists():
                with open(p_file, "r", encoding="utf-8") as f:
                    p_data = json.load(f)
                    act_id = p_data.get("active_project_id")
                    for p in p_data.get("projects", []):
                        if p.get("id") == act_id:
                            cand = Path(p.get("path", ""))
                            if cand.exists():
                                proj_dir = cand
                            break
        except Exception:
            pass

        branch = "main"
        modified_files: List[str] = []
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                capture_output=True, text=True, timeout=1.8, cwd=proj_dir,
            )
            lines = res.stdout.strip().splitlines()
            if lines:
                branch = lines[0].replace("## ", "").split("...")[0].strip()
                for l in lines[1:]:
                    if l.strip():
                        modified_files.append(l[3:].strip())
        except Exception:
            pass

        return {
            "project_path": str(proj_dir),
            "branch": branch,
            "dirty": len(modified_files) > 0,
            "modified_count": len(modified_files),
            "modified_sample": modified_files[:4],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Calendar & Agenda Sentinel
    # ─────────────────────────────────────────────────────────────────────────

    def _get_upcoming_agenda(self) -> List[Dict[str, Any]]:
        """Detects events scheduled today within the next 45 minutes."""
        agenda_file = _BASE_DIR / "memory" / "agenda.json"
        upcoming: List[Dict[str, Any]] = []
        if not agenda_file.exists():
            return upcoming

        try:
            with open(agenda_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = data.get("events", [])
            today_str = datetime.now().strftime("%Y-%m-%d")
            now = datetime.now()
            now_mins = now.hour * 60 + now.minute

            for ev in events:
                if ev.get("date") == today_str:
                    st = ev.get("start_time", "")
                    if st:
                        try:
                            parts = [int(p) for p in st.split(":")[:2]]
                            ev_mins = parts[0] * 60 + parts[1]
                            diff = ev_mins - now_mins
                            if 0 <= diff <= 45:
                                upcoming.append({
                                    "title": ev.get("title", "Event"),
                                    "start_time": st,
                                    "minutes_until": diff,
                                })
                                if diff <= 15:
                                    self.meeting_imminent.emit(ev.get("title", "Event"), diff)
                        except Exception:
                            pass
        except Exception:
            pass

        return upcoming

    # ─────────────────────────────────────────────────────────────────────────
    # 5. System Vitals & Pressure
    # ─────────────────────────────────────────────────────────────────────────

    def _get_system_vitals(self) -> Dict[str, Any]:
        """Returns CPU, RAM, Disk, and Battery pressure."""
        try:
            ram = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            batt = psutil.sensors_battery()
            battery_pct = batt.percent if batt else 100.0
            power_plugged = batt.power_plugged if batt else True

            return {
                "ram_percent": round(ram.percent, 1),
                "cpu_percent": round(cpu, 1),
                "disk_percent": round(disk.percent, 1),
                "battery_percent": round(battery_pct, 1),
                "power_plugged": power_plugged,
                "ram_critical": ram.percent >= 90.0,
                "cpu_critical": cpu >= 88.0,
                "battery_low": (battery_pct <= 20.0 and not power_plugged),
            }
        except Exception:
            return {
                "ram_percent": 0.0,
                "cpu_percent": 0.0,
                "disk_percent": 0.0,
                "battery_percent": 100.0,
                "power_plugged": True,
                "ram_critical": False,
                "cpu_critical": False,
                "battery_low": False,
            }


# Global Singleton Sensor
ambient_sensor = NEOAmbientSensor()
