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

    def _trigger_palm(self):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
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

    def _trigger_swipe(self, direction: str):
        now = time.monotonic()
        if now - self._last_trigger_time < self._cooldown:
            return
        self._last_trigger_time = now
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

    def _gesture_loop(self):
        from core.camera_service import get_camera_service
        cam_srv = get_camera_service()
        cam_srv.register_consumer("gesture_control")
        print("[Gesture] 🖐️ Gesture detection loop running with Shared Camera Service")

        try:
            # Try loading MediaPipe if installed
            mp_hands = None
            hands = None
            try:
                import mediapipe as mp
                mp_hands = mp.solutions.hands
                hands = mp_hands.Hands(
                    static_image_mode=False,
                    max_num_hands=1,
                    model_complexity=0,
                    min_detection_confidence=0.6,
                    min_tracking_confidence=0.55,
                )
                print("[Gesture] 🚀 MediaPipe Hands neural engine initialized (model_complexity=0).")
            except Exception:
                print("[Gesture] ⚡ Using OpenCV contour convexity engine.")

            while self._running:
                ok, frame = cam_srv.get_frame(timeout=0.2)
                if not ok or frame is None:
                    time.sleep(0.04)
                    continue

                # Mirror frame for intuitive gesture direction
                frame = cv2.flip(frame, 1)
                now = time.monotonic()

                if hands is not None:
                    # ── Ultra-fast Neural MediaPipe Landmark Engine (<2% CPU) ──
                    small = cv2.resize(frame, (480, 270))
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    results = hands.process(rgb)

                    if results.multi_hand_landmarks:
                        for hand_landmarks in results.multi_hand_landmarks:
                            lm = hand_landmarks.landmark
                            # Count extended fingers
                            extended = 0
                            for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
                                if lm[tip].y < lm[pip].y:
                                    extended += 1
                            if abs(lm[4].x - lm[2].x) > 0.05:
                                extended += 1

                            cx = lm[9].x  # Palm center x (normalized 0.0 - 1.0)

                            # Directional swipe detection
                            if self._prev_centroid_x is not None:
                                dt = now - self._prev_time
                                dist = cx - self._prev_centroid_x
                                if 0.03 < dt < 0.35 and abs(dist) > 0.10:
                                    dx = dist / dt
                                    if dx > 1.5:
                                        self._trigger_swipe("right")
                                    elif dx < -1.5:
                                        self._trigger_swipe("left")

                            self._prev_centroid_x = cx
                            self._prev_time = now

                            # Palm vs Fist
                            if extended >= 4:
                                self._trigger_palm()
                            elif extended == 0:
                                self._trigger_fist()
                    else:
                        self._prev_centroid_x = None

                else:
                    # ── OpenCV Fast Contour & Convexity Defect Engine ──
                    small = cv2.resize(frame, (320, 240))
                    ycrcb = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
                    # Skin color mask
                    mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
                    mask = cv2.GaussianBlur(mask, (5, 5), 0)

                    # Black out face & neck region so head/face movement NEVER triggers hand gestures
                    face_cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                    if os.path.exists(face_cascade_path):
                        face_cascade = cv2.CascadeClassifier(face_cascade_path)
                        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        faces = face_cascade.detectMultiScale(gray, 1.25, 4, minSize=(35, 35))
                        for (fx, fy, fw, fh) in faces:
                            pad_w, pad_h = int(fw * 0.2), int(fh * 0.35)
                            x0 = max(0, fx - pad_w)
                            y0 = max(0, fy - pad_h)
                            x1 = min(320, fx + fw + pad_w)
                            y1 = min(240, fy + fh + pad_h * 2)
                            mask[y0:y1, x0:x1] = 0

                    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        max_c = max(contours, key=cv2.contourArea)
                        area = cv2.contourArea(max_c)
                        # Require a deliberate, sizable hand contour (exclude small skin patches or noise)
                        if area > 6500:
                            hull = cv2.convexHull(max_c, returnPoints=False)
                            if hull is not None and len(hull) > 3 and len(max_c) > 3:
                                try:
                                    defects = cv2.convexityDefects(max_c, hull)
                                    if defects is not None:
                                        finger_count = 0
                                        for i in range(defects.shape[0]):
                                            s, e, f, d = defects[i, 0]
                                            start = max_c[s][0]
                                            end = max_c[e][0]
                                            far = max_c[f][0]
                                            a = np.linalg.norm(end - start)
                                            b = np.linalg.norm(far - start)
                                            c = np.linalg.norm(end - far)
                                            angle = np.arccos(np.clip((b**2 + c**2 - a**2) / (2 * b * c + 1e-6), -1.0, 1.0))
                                            if angle <= np.pi / 2.2 and d > 3500:
                                                finger_count += 1

                                        M = cv2.moments(max_c)
                                        if M["m00"] > 0:
                                            cx = float(M["m10"] / M["m00"])
                                            if self._prev_centroid_x is not None:
                                                dt = now - self._prev_time
                                                if 0.06 < dt < 0.35:
                                                    dx = (cx - self._prev_centroid_x) / dt
                                                    # Only fast, deliberate swipes across the screen
                                                    if dx > 260:
                                                        self._trigger_swipe("right")
                                                    elif dx < -260:
                                                        self._trigger_swipe("left")
                                            self._prev_centroid_x = cx
                                            self._prev_time = now

                                        if finger_count >= 4:
                                            self._trigger_palm()
                                        elif finger_count == 0 and area > 8000:
                                            self._trigger_fist()
                                except Exception:
                                    pass

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
    if False:  # Camera access strictly on-demand per user instruction
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
