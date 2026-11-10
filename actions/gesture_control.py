"""
Stark Air Gesture Control for F.R.I.D.A.Y.
Uses webcam vision to recognize hand gestures:
- Open Palm (✋) held up -> Stop speaking / Pause media (Interrupt)
- Swipe Right / Left -> Switch application tab / window (Ctrl+Tab)
- Fist / Thumbs Up -> Resume / Unmute
"""
from __future__ import annotations

import json
import os
import platform
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

try:
    import pyautogui
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

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
        print(f"[Gesture] ⚠️ Could not save config: {e}")


class GestureController:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._player = None

        # Tracking state
        self._last_trigger_time = 0.0
        self._cooldown = 1.2  # seconds between gesture triggers
        self._prev_centroid_x = None
        self._prev_time = 0.0
        self.last_detected_gesture: str = "STANDBY (No gesture)"
        self.last_detected_time: float = 0.0
        if _PYAUTOGUI_OK:
            try:
                pyautogui.FAILSAFE = False
            except Exception:
                pass

    def start(self, player=None) -> str:
        with self._lock:
            if not _CV2_OK:
                return "OpenCV (cv2) is required for gesture control."
            if player:
                self._player = player
            if self._running:
                return "Gesture control is already active, Boss."

            self._running = True
            self._thread = threading.Thread(target=self._gesture_loop, daemon=True, name="GestureControlThread")
            self._thread.start()
            _save_config("gesture_control_enabled", True)
            return "Stark Air Gesture Control activated. Raised palm pauses, swiping navigates tabs."

    def stop(self) -> str:
        with self._lock:
            if not self._running:
                return "Gesture control is not running."
            self._running = False
            _save_config("gesture_control_enabled", False)
            return "Gesture control deactivated, Boss."

    def is_active(self) -> bool:
        return self._running

    def status(self) -> str:
        st = "ACTIVE" if self._running else "INACTIVE"
        return f"Gesture Control: {st} | Palm = Pause/Mute, Swipe = Switch Tabs"

    def get_last_gesture(self) -> tuple[str, float]:
        with self._lock:
            return self.last_detected_gesture, self.last_detected_time

    def _trigger_palm(self):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
        self.last_detected_gesture = "🖐️ Open Palm (Interrupt / Pause)"
        self.last_detected_time = now
        print("[Gesture] ✋ OPEN PALM DETECTED -> Triggering Interrupt / Pause")
        if self._player:
            if hasattr(self._player, "interrupt"):
                try:
                    self._player.interrupt()
                except Exception:
                    pass
            elif hasattr(self._player, "_do_interrupt"):
                try:
                    self._player._do_interrupt()
                except Exception:
                    pass
            if hasattr(self._player, "write_log"):
                try:
                    self._player.write_log("GESTURE: ✋ Open palm (Interrupt / Pause)")
                except Exception:
                    pass
        if _PYAUTOGUI_OK:
            try:
                pyautogui.press("playpause")
            except Exception:
                pass
        try:
            from core.neo_central_coordinator import central_core
            central_core.trigger_gesture(self.last_detected_gesture)
        except Exception:
            pass

    def _trigger_swipe(self, direction: str):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
        self.last_detected_gesture = f"💨 Swipe {direction.capitalize()} (Switch Tab)"
        self.last_detected_time = now
        print(f"[Gesture] 💨 SWIPE {direction.upper()} DETECTED -> Switching Tab")
        if self._player and hasattr(self._player, "write_log"):
            try:
                lbl = "Next Tab (Ctrl+Tab)" if direction == "right" else "Prev Tab (Ctrl+Shift+Tab)"
                self._player.write_log(f"GESTURE: 💨 Swipe {direction.capitalize()} ({lbl})")
            except Exception:
                pass
        if _PYAUTOGUI_OK:
            try:
                if direction == "right":
                    pyautogui.hotkey("ctrl", "tab")
                else:
                    pyautogui.hotkey("ctrl", "shift", "tab")
            except Exception as e:
                print(f"[Gesture] Hotkey error: {e}")

    def _trigger_fist(self):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
        self.last_detected_gesture = "✊ Fist (Resume / Unmute)"
        self.last_detected_time = now
        print("[Gesture] ✊ FIST / CONFIRM DETECTED -> Unmute / Resume")
        if self._player:
            if hasattr(self._player, "_muted") and self._player._muted:
                try:
                    self._player._set_muted(False)
                except Exception:
                    pass
            if hasattr(self._player, "write_log"):
                try:
                    self._player.write_log("GESTURE: ✊ Fist (Resume / Unmute)")
                except Exception:
                    pass
        if _PYAUTOGUI_OK:
            try:
                pyautogui.press("playpause")
            except Exception:
                pass
        try:
            from core.neo_central_coordinator import central_core
            central_core.trigger_gesture(self.last_detected_gesture)
        except Exception:
            pass

    def _trigger_victory(self):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
        self.last_detected_gesture = "✌️ Peace / Victory (Mute Mic Toggle)"
        self.last_detected_time = now
        print("[Gesture] ✌️ VICTORY / PEACE SIGN DETECTED -> Mute / Unmute Toggle")
        if self._player:
            if hasattr(self._player, "_toggle_mute"):
                try:
                    self._player._toggle_mute()
                except Exception:
                    pass
            if hasattr(self._player, "write_log"):
                try:
                    self._player.write_log("GESTURE: ✌️ Peace Sign (Mute Mic Toggle)")
                except Exception:
                    pass

    def _trigger_point(self):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
        self.last_detected_gesture = "☝️ Point Up (Acknowledge)"
        self.last_detected_time = now
        print("[Gesture] ☝️ POINT UP DETECTED -> Acknowledged")
        if self._player and hasattr(self._player, "write_log"):
            try:
                self._player.write_log("GESTURE: ☝️ Point Up (Acknowledge)")
            except Exception:
                pass

    def _gesture_loop(self):
        from core.camera_service import get_camera_service
        cam_srv = get_camera_service()
        cam_srv.register_consumer("gesture_control")
        print("[Gesture] 🖐️ Gesture detection loop running with Shared Camera Service")

        # 1. Initialize MediaPipe Tasks GestureRecognizer with Google model
        recognizer = None
        try:
            import mediapipe as mp
            model_path = _BASE_DIR / "models" / "gesture_recognizer.task"
            if model_path.exists():
                BaseOptions = mp.tasks.BaseOptions
                GestureRecognizer = mp.tasks.vision.GestureRecognizer
                GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
                VisionRunningMode = mp.tasks.vision.RunningMode

                options = GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=str(model_path.resolve())),
                    running_mode=VisionRunningMode.IMAGE,
                    num_hands=1
                )
                recognizer = GestureRecognizer.create_from_options(options)
                print("[Gesture] 🚀 MediaPipe Neural GestureRecognizer initialized with Google model.")
        except Exception as mp_err:
            print(f"[Gesture] ⚡ MediaPipe Tasks notice: {mp_err}. Using calibrated OpenCV fallback.")

        # 2. Pre-load Face Cascade once for OpenCV fallback
        face_cascade = None
        if _CV2_OK:
            face_cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if os.path.exists(face_cascade_path):
                try:
                    face_cascade = cv2.CascadeClassifier(face_cascade_path)
                except Exception:
                    pass

        try:
            while self._running:
                ok, frame = cam_srv.get_frame(timeout=0.2)
                if not ok or frame is None:
                    time.sleep(0.04)
                    continue

                # Mirror frame horizontally for intuitive interaction
                frame = cv2.flip(frame, 1)
                now = time.monotonic()

                # ── PRIMARY PATH: MediaPipe Neural Gesture Recognition ────────
                if recognizer is not None:
                    try:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                        result = recognizer.recognize(mp_img)

                        # Check recognized gestures
                        if result.gestures and len(result.gestures[0]) > 0:
                            top_g = result.gestures[0][0]
                            g_name = top_g.category_name
                            score = top_g.score

                            if score > 0.40:
                                if g_name == "Open_Palm":
                                    self._trigger_palm()
                                elif g_name == "Closed_Fist":
                                    self._trigger_fist()
                                elif g_name == "Victory":
                                    self._trigger_victory()
                                elif g_name == "Pointing_Up":
                                    self._trigger_point()

                        # Directional Swipes via Landmark 9 (middle knuckle / palm center)
                        if result.hand_landmarks and len(result.hand_landmarks) > 0:
                            cx = result.hand_landmarks[0][9].x
                            if self._prev_centroid_x is not None:
                                dt = now - self._prev_time
                                if 0.04 < dt < 0.45:
                                    dx = (cx - self._prev_centroid_x) / dt
                                    if dx > 1.1:
                                        self._trigger_swipe("right")
                                    elif dx < -1.1:
                                        self._trigger_swipe("left")
                            self._prev_centroid_x = cx
                            self._prev_time = now
                        else:
                            self._prev_centroid_x = None

                        time.sleep(0.035)  # ~28 FPS
                        continue
                    except Exception:
                        pass

                # ── SECONDARY PATH: Calibrated OpenCV Contour & Convexity ─────
                small = cv2.resize(frame, (320, 240))
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)

                # Robust Dual-Space Skin Mask
                mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 130, 75]), np.array([255, 180, 135]))
                mask_hsv = cv2.inRange(hsv, np.array([0, 20, 40]), np.array([30, 255, 255]))
                mask = cv2.bitwise_and(mask_ycrcb, mask_hsv)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
                mask = cv2.dilate(mask, kernel, iterations=1)

                # Mask out face bounding box (do not mask torso or hands)
                if face_cascade is not None:
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.3, 4, minSize=(35, 35))
                    for (fx, fy, fw, fh) in faces:
                        mask[max(0, fy):min(240, fy + fh), max(0, fx):min(320, fx + fw)] = 0

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    max_c = max(contours, key=cv2.contourArea)
                    area = cv2.contourArea(max_c)

                    # Calibrated Area: 1400px - 22000px on 320x240 frame
                    if 1400 < area < 22000:
                        hull = cv2.convexHull(max_c, returnPoints=False)
                        if hull is not None and len(hull) > 3 and len(max_c) > 3:
                            try:
                                defects = cv2.convexityDefects(max_c, hull)
                                finger_count = 0
                                if defects is not None:
                                    for i in range(defects.shape[0]):
                                        s, e, f, d = defects[i, 0]
                                        start = max_c[s][0]
                                        end = max_c[e][0]
                                        far = max_c[f][0]
                                        a = np.linalg.norm(end - start)
                                        b = np.linalg.norm(far - start)
                                        c = np.linalg.norm(end - far)
                                        angle = np.arccos(np.clip((b**2 + c**2 - a**2) / (2 * b * c + 1e-6), -1.0, 1.0))
                                        # Calibrated finger defect depth: > 1000 (~4px) and acute angle (< 95 deg)
                                        if angle <= np.pi * 0.53 and d > 1000:
                                            finger_count += 1

                                # Centroid tracking for directional swipes
                                M = cv2.moments(max_c)
                                if M["m00"] > 0:
                                    cx = float(M["m10"] / M["m00"])
                                    if self._prev_centroid_x is not None:
                                        dt = now - self._prev_time
                                        if 0.05 < dt < 0.40:
                                            dx = (cx - self._prev_centroid_x) / dt
                                            if dx > 110:
                                                self._trigger_swipe("right")
                                            elif dx < -110:
                                                self._trigger_swipe("left")
                                    self._prev_centroid_x = cx
                                    self._prev_time = now

                                # Gesture Classification
                                if finger_count >= 3:
                                    self._trigger_palm()
                                elif finger_count == 0 and 1200 < area < 6500:
                                    self._trigger_fist()
                            except Exception:
                                pass
                else:
                    self._prev_centroid_x = None

                time.sleep(0.04)  # ~25 FPS loop

        except Exception as e:
            print(f"[Gesture] Loop error: {e}")
        finally:
            cam_srv.unregister_consumer("gesture_control")
            print("[Gesture] 🖐️ Gesture detection loop stopped.")


_gesture_ctl = GestureController()


def gesture_control(parameters: dict, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "status").lower().strip()

    if action in ("enable", "start", "on"):
        return _gesture_ctl.start(player)
    elif action in ("disable", "stop", "off"):
        return _gesture_ctl.stop()
    elif action in ("status", "check"):
        return _gesture_ctl.status()
    else:
        return f"Unknown action: '{action}'. Available: enable, disable, status."


def init_gesture_on_boot(player=None) -> None:
    """Auto-start gesture control if enabled in config."""
    cfg = _load_config()
    if cfg.get("gesture_control_enabled", False):
        _gesture_ctl.start(player)


TOOL = {
    "name": "gesture_control",
    "description": (
        "Controls Stark Air Hand Gesture recognition via webcam. "
        "Allows Boss to control the desktop without touching mouse or keyboard: "
        "Open Palm (✋) held up pauses speech or media, Swipe Right/Left switches tabs."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "enable | disable | status (default: status)"
            }
        },
        "required": ["action"]
    },
    "handler": gesture_control,
}
