"""
Thread-safe shared camera service for F.R.I.D.A.Y.
Multiplexes the hardware webcam across concurrent vision workers:
- Stark Air Gesture Control (~25 FPS)
- Desk Presence Sentry (~1 FPS)
- Screen Processor camera capture / preview
Prevents Windows DirectShow device collisions where opening cv2.VideoCapture() in two threads fails.
"""
from __future__ import annotations

import io
import json
import os
import platform
import threading
import time
from pathlib import Path
from typing import Optional, Set

import numpy as np

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

try:
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


class CameraService:
    _instance: Optional[CameraService] = None
    _init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CameraService:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = CameraService()
            return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._consumers: Set[str] = set()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_time: float = 0.0
        self._frame_cond = threading.Condition(self._lock)

        self._grace_timer: Optional[threading.Timer] = None

    def _get_backend(self) -> int:
        if not _CV2_OK:
            return 0
        if platform.system() == "Windows":
            return cv2.CAP_DSHOW
        if platform.system() == "Darwin":
            return cv2.CAP_AVFOUNDATION
        return cv2.CAP_ANY

    def _get_cam_index(self) -> int:
        return int(_load_config().get("camera_index", 0))

    def register_consumer(self, consumer_id: str) -> bool:
        """Register a continuous consumer (e.g. 'gestures', 'sentry'). Starts the camera worker if not running."""
        with self._lock:
            if not _CV2_OK:
                return False
            if self._grace_timer:
                self._grace_timer.cancel()
                self._grace_timer = None

            self._consumers.add(consumer_id)
            if not self._running:
                self._running = True
                self._worker_thread = threading.Thread(
                    target=self._capture_loop, daemon=True, name="SharedCameraWorker"
                )
                self._worker_thread.start()
            return True

    def unregister_consumer(self, consumer_id: str) -> None:
        """Unregister a consumer. Automatically schedules camera release if no active consumers remain."""
        with self._lock:
            self._consumers.discard(consumer_id)
            if not self._consumers and self._running:
                # Schedule camera release after 6s grace period
                if self._grace_timer:
                    self._grace_timer.cancel()
                self._grace_timer = threading.Timer(6.0, self._stop_internal)
                self._grace_timer.daemon = True
                self._grace_timer.start()

    def _stop_internal(self):
        with self._lock:
            if not self._consumers and self._running:
                self._running = False
                print("[CameraService] 💤 No active consumers. Hardware camera released.")

    def get_frame(self, timeout: float = 0.5) -> tuple[bool, Optional[np.ndarray]]:
        """Thread-safe read of the most recent frame."""
        with self._frame_cond:
            if self._latest_frame is not None:
                return True, self._latest_frame.copy()
            # Wait for first frame if worker just started
            if self._running:
                self._frame_cond.wait(timeout)
                if self._latest_frame is not None:
                    return True, self._latest_frame.copy()
        return False, None

    def snapshot(self) -> tuple[bytes, str]:
        """Capture a single JPEG snapshot. Uses live running feed if active, or does a clean single shot."""
        if not _CV2_OK:
            raise RuntimeError("OpenCV (cv2) is not installed.")

        # If running, grab directly from shared worker
        ok, frame = self.get_frame(timeout=1.0)
        if ok and frame is not None:
            return self._encode_jpeg(frame)

        # Otherwise do a fast one-off capture
        with self._lock:
            idx = self._get_cam_index()
            backend = self._get_backend()
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                raise RuntimeError(f"Camera index {idx} could not be opened.")
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                raise RuntimeError("Camera returned no frame.")
            return self._encode_jpeg(frame)

    def _encode_jpeg(self, frame: np.ndarray) -> tuple[bytes, str]:
        if _PIL_OK:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = PIL.Image.fromarray(rgb)
            img.thumbnail((1280, 720), PIL.Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            return buf.getvalue(), "image/jpeg"
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        return buf.tobytes(), "image/jpeg"

    def _capture_loop(self):
        idx = self._get_cam_index()
        backend = self._get_backend()
        print(f"[CameraService] 📷 Hardware camera opened on index {idx} ({backend})")

        self._cap = cv2.VideoCapture(idx, backend)
        if not self._cap.isOpened():
            print(f"[CameraService] ⚠️ Could not open camera {idx}")
            with self._lock:
                self._running = False
            return

        # Fast warm-up
        for _ in range(4):
            self._cap.read()

        while self._running:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._frame_cond:
                    self._latest_frame = frame
                    self._latest_time = time.monotonic()
                    self._frame_cond.notify_all()
            time.sleep(0.033)  # ~30 FPS

        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._frame_cond:
            self._latest_frame = None
            self._frame_cond.notify_all()
        print("[CameraService] 📷 Camera thread stopped.")


def get_camera_service() -> CameraService:
    return CameraService.get_instance()
