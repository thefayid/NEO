"""
Desk Presence & Sentry Protocol for F.R.I.D.A.Y.
Monitors user presence at the desk via webcam.
- Greets on return ("Welcome back, Boss.")
- Warns and auto-locks workstation after prolonged absence when security mode is active.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

from core import outcome

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_config(key: str, val) -> None:
    try:
        cfg = _load_config()
        cfg[key] = val
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Presence] ⚠️ Could not save config: {e}")


class PresenceMonitor:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._face_cascade = None
        self._player = None

        # Settings
        cfg = _load_config()
        self.auto_lock = bool(cfg.get("presence_auto_lock", False))
        self.away_timeout = int(cfg.get("presence_away_timeout", 20))   # 20s responsive absence lock
        self.greet_enabled = bool(cfg.get("presence_greet_enabled", True))

        # State tracking
        self.is_present = True
        self._last_seen_time = time.monotonic()
        self._last_greet_time = 0.0
        self._locked = False
        self._consecutive_faces = 0
        self._consecutive_empty = 0

    def _init_cascade(self):
        if self._face_cascade is None and _CV2_OK:
            cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if os.path.exists(cascade_path):
                self._face_cascade = cv2.CascadeClassifier(cascade_path)

    def start(self, player=None, speak=None) -> str:
        with self._lock:
            if not _CV2_OK:
                return "OpenCV (cv2) is not installed."
            self._init_cascade()
            if self._face_cascade is None:
                return "Haar cascade for face detection could not be loaded."
            if player:
                self._player = player
            if speak:
                self._speak_fn = speak
            if self._running:
                return "Presence detection is already active."

            self._running = True
            self._last_seen_time = time.monotonic()
            self._locked = False
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="PresenceSentryThread")
            self._thread.start()
            _save_config("presence_detection_enabled", True)
            return "Presence Sentry activated. Monitoring desk presence, Boss."

    def stop(self) -> str:
        with self._lock:
            if not self._running:
                return "Presence detection is not running."
            self._running = False
            _save_config("presence_detection_enabled", False)
            return "Presence Sentry deactivated."

    def is_active(self) -> bool:
        return self._running

    def status(self) -> str:
        st = "ACTIVE" if self._running else "INACTIVE"
        state_txt = "Boss Present" if self.is_present else "Boss Away"
        lock_txt = "Enabled" if self.auto_lock else "Disabled"
        return f"Presence Sentry: {st} | Status: {state_txt} | Auto-lock: {lock_txt} (timeout: {self.away_timeout}s)"

    def _get_return_briefing(self) -> str:
        """Fetch quick executive summary: unread VIP emails, active reminders, and system alerts."""
        items = []
        try:
            from actions.reminder import get_pending_reminders_count
            rc = get_pending_reminders_count()
            if rc > 0:
                items.append(f"{rc} active reminder{'s' if rc > 1 else ''}")
        except Exception:
            pass

        try:
            from actions.executive_briefing import _get_active_reminders_summary
            rems = _get_active_reminders_summary()
            if rems and not items:
                items.append(f"{len(rems)} pending reminder{'s' if len(rems) > 1 else ''}")
        except Exception:
            pass

        try:
            from actions.executive_briefing import _triage_emails
            email_info = _triage_emails()
            vip_count = email_info.get("vip_unread", 0)
            if vip_count > 0:
                items.append(f"{vip_count} unread VIP email{'s' if vip_count > 1 else ''}")
        except Exception:
            pass

        if items:
            return " You have " + " and ".join(items) + "."
        return " All systems nominal and horizon is clear."

    def _speak(self, text: str):
        spoken = False
        if hasattr(self, "_speak_fn") and callable(self._speak_fn):
            try:
                self._speak_fn(text)
                spoken = True
            except Exception:
                pass
        if not spoken and self._player and hasattr(self._player, "speak"):
            try:
                self._player.speak(text)
                spoken = True
            except Exception:
                pass
        print(f"[Presence] 🗣️ {text}")

    def _log(self, text: str):
        if self._player and hasattr(self._player, "write_log"):
            try:
                self._player.write_log(f"SYS: {text}")
            except Exception:
                pass
        print(f"[Presence] {text}")

    def _monitor_loop(self):
        from core.camera_service import get_camera_service
        cam_srv = get_camera_service()
        cam_srv.register_consumer("presence_sentry")
        print("[Presence] 👁️ Sentry thread started with Shared Camera Service")

        try:
            while self._running:
                ok, frame = cam_srv.get_frame(timeout=2.0)
                if not ok or frame is None:
                    time.sleep(1.0)
                    continue

                try:
                    small = cv2.resize(frame, (320, 240))
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    gray = cv2.equalizeHist(gray)

                    faces = self._face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.18,
                        minNeighbors=4,
                        minSize=(30, 30),
                    )

                    now = time.monotonic()
                    has_face = len(faces) > 0

                    if has_face:
                        self._consecutive_faces += 1
                        self._consecutive_empty = 0
                        self._last_seen_time = now

                        # Transition: AWAY -> PRESENT (2 consecutive positive checks)
                        if not self.is_present and self._consecutive_faces >= 2:
                            self.is_present = True
                            self._locked = False
                            self._log("👤 Boss detected at workstation.")
                            # Wake up assistant
                            if self._player and hasattr(self._player, "_awake"):
                                self._player._awake = True
                            if self._player and hasattr(self._player, "ui") and hasattr(self._player.ui, "set_state"):
                                self._player.ui.set_state("LISTENING")

                            if self.greet_enabled and (now - self._last_greet_time > 60):
                                self._last_greet_time = now
                                summary = self._get_return_briefing()
                                greeting = f"Welcome back, Boss.{summary}"
                                self._speak(greeting)
                                if self._player and hasattr(self._player, "ui") and hasattr(self._player.ui, "show_content"):
                                    self._player.ui.show_content("PRESENCE // EXECUTIVE RETURN BRIEFING", greeting)
                    else:
                        self._consecutive_empty += 1
                        self._consecutive_faces = 0

                        # Check absence timeout
                        if self.is_present and (now - self._last_seen_time > self.away_timeout):
                            self.is_present = False
                            # Auto-silence assistant when away
                            if self._player and hasattr(self._player, "sleep"):
                                self._player.sleep(reason="Boss away from desk")
                            self._log(f"⚠️ Boss absent from workstation for > {self.away_timeout}s.")
                            if self.auto_lock and not self._locked:
                                self._locked = True
                                self._speak("Workstation unattended. Engaging security lock.")
                                time.sleep(1.5)
                                if platform.system() == "Windows":
                                    try:
                                        ctypes.windll.user32.LockWorkStation()
                                    except Exception as e:
                                        print(f"[Presence] LockWorkStation error: {e}")
                except Exception as e:
                    print(f"[Presence] Loop error: {e}")

                time.sleep(1.5)
        finally:
            cam_srv.unregister_consumer("presence_sentry")
            print("[Presence] 👁️ Sentry thread stopped.")


# Singleton instance
_monitor = PresenceMonitor()


def presence_sentry(parameters: dict, player=None, speak=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "status").lower().strip()

    if action in ("enable", "start", "on"):
        return _monitor.start(player, speak)
    elif action in ("disable", "stop", "off"):
        return _monitor.stop()
    elif action in ("status", "check"):
        return _monitor.status()
    elif action in ("set_lock", "lock_on_absence", "auto_lock", "enable_lock"):
        enabled = params.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() not in ("false", "0", "disable", "off")
        else:
            enabled = bool(enabled)
        _monitor.auto_lock = enabled
        _save_config("presence_auto_lock", enabled)
        if enabled and not _monitor._running:
            _monitor.start(player, speak)
        st = "enabled (20s absence trigger)" if enabled else "disabled"
        return f"Auto-lock workstation on absence is now {st}, Boss. Monitoring is engaged."
    else:
        return f"Unknown action: '{action}'. Available: enable, disable, status, set_lock."


def init_presence_on_boot(player=None) -> None:
    """Auto-start presence sentry if enabled in config."""
    cfg = _load_config()
    if False:  # Camera access strictly on-demand per user instruction
        _monitor.start(player)


TOOL = {
    "name": "presence_sentry",
    "description": (
        "Controls desk presence detection and workstation security. "
        "Monitors when Boss sits down at the desk to greet them ('Welcome back, Boss'), "
        "and automatically locks the PC when Boss steps away for over 60 seconds."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "enable | disable | status | set_lock (default: status)"
            },
            "enabled": {
                "type": "BOOLEAN",
                "description": "When action is set_lock: true to auto-lock when away, false to only greet."
            }
        },
        "required": ["action"]
    },
    "handler": presence_sentry,
}
