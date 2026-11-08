"""
actions/ergonomic_sentinel.py — F.R.I.D.A.Y. Ergonomic Sentinel & Health Watchdog.

Keeps Tony Stark in peak physical & cognitive condition:
  • 20-20-20 Eye Protection: Timed reminders every 20 minutes to prevent digital eye strain.
  • Hydration Sentinel: Paces water intake every 45 minutes and logs hydration counts.
  • Posture Sentinel: Tracks unbroken sitting duration and uses webcam vision to detect
    slumping or leaning too close to the screen.
  • Telemetry Status: Reports total desk hours, breaks taken, and hydration levels today.
"""
from __future__ import annotations

import datetime
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

_BASE_DIR = Path(__file__).resolve().parent.parent
_ERGO_CONFIG_FILE = _BASE_DIR / "config" / "ergonomics.json"


def _load_ergo_data() -> dict:
    today_str = datetime.date.today().isoformat()
    default_data = {
        "enabled": True,
        "hydration_interval_minutes": 45,
        "eye_rest_interval_minutes": 20,
        "sitting_break_minutes": 90,
        "today_date": today_str,
        "water_glasses": 0,
        "breaks_taken": 0,
        "eye_rests_completed": 0,
        "total_active_minutes": 0,
    }
    if _ERGO_CONFIG_FILE.exists():
        try:
            data = json.loads(_ERGO_CONFIG_FILE.read_text(encoding="utf-8"))
            if data.get("today_date") != today_str:
                data["today_date"] = today_str
                data["water_glasses"] = 0
                data["breaks_taken"] = 0
                data["eye_rests_completed"] = 0
                data["total_active_minutes"] = 0
            return data
        except Exception as e:
            print(f"[Ergonomic] Warning loading config: {e}")
    return default_data


def _save_ergo_data(data: dict) -> None:
    try:
        _ERGO_CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Ergonomic] Warning saving config: {e}")


class ErgonomicSentinel:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._player = None
        self._speak_fn = None
        
        self.start_time = time.monotonic()
        self.last_eye_reminder = time.monotonic()
        self.last_hydration_reminder = time.monotonic()
        self.last_break_reminder = time.monotonic()
        self.face_cascade = None

    def _init_cascade(self):
        if self.face_cascade is None and _CV2_OK:
            cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if os.path.exists(cascade_path):
                self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def start(self, player=None, speak=None) -> str:
        with self._lock:
            if player:
                self._player = player
            if speak:
                self._speak_fn = speak

            data = _load_ergo_data()
            data["enabled"] = True
            _save_ergo_data(data)

            if self._running:
                return "Ergonomic Sentinel is already active and monitoring posture & hydration, Boss."

            self._running = True
            self.start_time = time.monotonic()
            self.last_eye_reminder = time.monotonic()
            self.last_hydration_reminder = time.monotonic()
            self.last_break_reminder = time.monotonic()

            self._thread = threading.Thread(target=self._sentinel_loop, daemon=True, name="ErgonomicSentinelThread")
            self._thread.start()
            return "Ergonomic Sentinel armed, Boss. Eye protection (20-20-20), hydration pacing, and posture watchdog are online."

    def stop(self) -> str:
        with self._lock:
            if not self._running:
                return "Ergonomic Sentinel is already offline."
            self._running = False
            data = _load_ergo_data()
            data["enabled"] = False
            _save_ergo_data(data)
            return "Ergonomic Sentinel stood down, Boss."

    def _notify(self, message: str) -> None:
        """Send notification via speak or player or console."""
        print(f"[Ergonomic Sentinel] [HEALTH] {message}")
        if self._player and hasattr(self._player, "say"):
            try:
                self._player.say(message)
                return
            except Exception:
                pass
        if self._speak_fn and callable(self._speak_fn):
            try:
                self._speak_fn(message)
            except Exception:
                pass

    def _sentinel_loop(self) -> None:
        while self._running:
            time.sleep(30.0)  # Check every 30 seconds
            if not self._running:
                break

            now = time.monotonic()
            data = _load_ergo_data()

            # Eye protection check (20-20-20 rule)
            eye_interval = int(data.get("eye_rest_interval_minutes", 20)) * 60
            if (now - self.last_eye_reminder) >= eye_interval:
                self.last_eye_reminder = now
                data["eye_rests_completed"] = data.get("eye_rests_completed", 0) + 1
                _save_ergo_data(data)
                self._notify("Boss, 20-20-20 eye rest alert: shift your gaze 20 feet away for 20 seconds to relieve ocular strain.")

            # Hydration check
            hydro_interval = int(data.get("hydration_interval_minutes", 45)) * 60
            if (now - self.last_hydration_reminder) >= hydro_interval:
                self.last_hydration_reminder = now
                self._notify("Hydration checkpoint, Boss. Take a drink of water to maintain peak cognitive focus.")

            # Break check (90 minutes continuous)
            break_interval = int(data.get("sitting_break_minutes", 90)) * 60
            if (now - self.last_break_reminder) >= break_interval:
                self.last_break_reminder = now
                data["breaks_taken"] = data.get("breaks_taken", 0) + 1
                _save_ergo_data(data)
                self._notify("Boss, you have maintained uninterrupted focus for 90 minutes. Stand up, stretch your spine, and recalibrate.")

    def check_posture_vision(self) -> str:
        """Capture a webcam snapshot and assess distance/slump."""
        if not _CV2_OK:
            return "OpenCV not available for visual posture detection."
        self._init_cascade()
        if not self.face_cascade:
            return "Visual posture model could not be initialized."

        try:
            from actions.screen_processor import _capture_camera
            img_b, _ = _capture_camera()
            import numpy as np
            nparr = np.frombuffer(img_b, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                return "Could not capture camera frame for posture check."

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))

            if len(faces) == 0:
                return "Visual Posture Check: No face detected. Ensure your face is centered in the camera view, Boss."

            # Evaluate primary face size and position
            (x, y, w, h) = faces[0]
            f_h, f_w = frame.shape[:2]
            width_ratio = w / f_w
            y_center = (y + h / 2) / f_h

            verdict = []
            if width_ratio > 0.45:
                verdict.append("[WARNING] Leaning too close to the screen (forward head posture detected). Please sit back.")
            elif width_ratio < 0.15:
                verdict.append("[WARNING] Seated relatively far from optimal screen focus.")
            else:
                verdict.append("[NOMINAL] Optimal screen distance maintained.")

            if y_center > 0.65:
                verdict.append("[WARNING] Head position is dropped low -- likely slumping shoulders.")
            elif y_center < 0.25:
                verdict.append("[WARNING] Camera angled too low or neck tilted upward.")
            else:
                verdict.append("[NOMINAL] Vertical spinal alignment looks nominal.")

            return "[VISUAL POSTURE ASSESSMENT]\n" + "\n".join(verdict) + "\nDiagnosis: Posture calibrated, Boss."
        except Exception as e:
            return f"Posture inspection note: {e}"

    def status(self) -> str:
        data = _load_ergo_data()
        elapsed_mins = int((time.monotonic() - self.start_time) // 60)
        glasses = data.get("water_glasses", 0)
        breaks = data.get("breaks_taken", 0)
        eye_rests = data.get("eye_rests_completed", 0)
        status_str = "ACTIVE [ONLINE]" if self._running else "STANDBY [OFFLINE]"

        return (
            f"[ERGONOMIC SENTINEL TELEMETRY]\n"
            f"- Status: {status_str}\n"
            f"- Active Session Duration: {elapsed_mins} minutes\n"
            f"- Hydration Log: {glasses} glasses logged today\n"
            f"- Eye Rest Cycles (20-20-20): {eye_rests} completed\n"
            f"- Posture & Movement Breaks: {breaks} taken\n"
            f"- Health Recommendation: Maintain lumbar support and hydrate regularly, Boss."
        )

    def log_water(self) -> str:
        data = _load_ergo_data()
        data["water_glasses"] = data.get("water_glasses", 0) + 1
        _save_ergo_data(data)
        count = data["water_glasses"]
        return f"Hydration recorded, Boss. Total for today: {count} glass{'es' if count > 1 else ''}. Keep it up."


_sentinel = ErgonomicSentinel()


def ergonomic_sentinel(parameters: dict | None = None, player=None, speak=None, **kwargs) -> str:
    """Entry point for ergonomic sentinel."""
    params = parameters or {}
    action = str(params.get("action", "status")).strip().lower()

    if action in ("enable", "start", "activate", "on"):
        return _sentinel.start(player=player, speak=speak)
    elif action in ("disable", "stop", "deactivate", "off"):
        return _sentinel.stop()
    elif action in ("check", "check_posture", "posture", "camera"):
        return _sentinel.check_posture_vision()
    elif action in ("log_water", "water", "drink"):
        return _sentinel.log_water()
    else:
        return _sentinel.status()


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "ergonomic_sentinel",
    "description": (
        "Controls Tony Stark's health, posture, and ergonomic sentinel. "
        "Actions: "
        "'status' (Reports desk time, breaks, hydration, and eye strain status) | "
        "'enable' (Arms 20-20-20 eye strain protection, hydration alerts, and posture check) | "
        "'disable' (Stands down health sentinel) | "
        "'check_posture' (Uses camera to visually analyze head tilt, screen distance, and spine slumping) | "
        "'log_water' (Logs a glass of water to your daily hydration tracker). "
        "Call when user asks about posture, hydration, breaks, or says 'I drank water'."
    ),
    "brief": (
        "Ergonomic health sentinel: posture monitoring via webcam, 20-20-20 eye strain "
        "protection, hydration reminders, and desk uptime tracking."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'status' | 'enable' | 'disable' | 'check_posture' | 'log_water'",
                "enum": ["status", "enable", "disable", "check_posture", "log_water"]
            }
        },
        "required": ["action"]
    },
    "handler": ergonomic_sentinel,
}
