"""
Screen & webcam capture for NEO vision.

Provides the two capture entry points main.py uses — `_capture_screen()` and
`_capture_camera()` — plus their helpers (compression, camera auto-detection,
config access). main.py grabs a frame here on demand, then injects it into the
main Gemini Live session; there is no separate vision session here.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

from core.lazyimport import LazyModule, installed

# OpenCV is 224 ms and is only ever touched by the webcam path — see
# core/lazyimport.py. Screen capture, which is what this action does on almost
# every call, never reaches it. numpy above stays eager: main.py already
# imports it for audio, so it is in memory before this file is read.
_CV2 = installed("cv2")

cv2 = LazyModule("cv2")

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL
    import PIL.Image
    import PIL.ImageGrab
    _PIL = True
except ImportError:
    _PIL = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q    = 82


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] Image compress note: {e}")
        return img_bytes, f"image/{source_format.lower()}"


def _get_active_window_rect() -> dict | None:
    """Return bounding rect of the currently focused foreground window on Windows."""
    try:
        import platform
        if platform.system() != "Windows":
            return None
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        w, h = right - left, bottom - top
        if w > 120 and h > 120:
            return {"left": left, "top": top, "width": w, "height": h}
    except Exception:
        pass
    return None


def _capture_screen(target_mode: str = "full") -> tuple[bytes, str]:
    # 1. High-speed MSS capture (direct raw RGB bytes -> PIL Image, eliminating PNG encode/decode roundtrip)
    if _MSS:
        try:
            with mss.mss() as sct:
                target = None
                if target_mode in ("active", "window", "focused"):
                    win_rect = _get_active_window_rect()
                    if win_rect:
                        target = win_rect
                if target is None:
                    monitors = sct.monitors
                    target = monitors[1] if len(monitors) > 1 else monitors[0]

                shot = sct.grab(target)
                if _PIL:
                    img = PIL.Image.frombytes("RGB", shot.size, shot.rgb)
                    img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
                    return buf.getvalue(), "image/jpeg"
                png = mss.tools.to_png(shot.rgb, shot.size)
                return _compress(png, "PNG")
        except Exception as e:
            print(f"[Vision] mss capture note ({e}), trying fallback")

    # 2. Resilient PIL ImageGrab fallback
    if _PIL:
        try:
            bbox = None
            if target_mode in ("active", "window", "focused"):
                win_rect = _get_active_window_rect()
                if win_rect:
                    bbox = (
                        win_rect["left"],
                        win_rect["top"],
                        win_rect["left"] + win_rect["width"],
                        win_rect["top"] + win_rect["height"]
                    )
            img = PIL.ImageGrab.grab(bbox=bbox, all_screens=True)
            img = img.convert("RGB")
            img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
            return buf.getvalue(), "image/jpeg"
        except Exception as e:
            print(f"[Vision] ImageGrab note: {e}")

    # 3. Graceful fallback image if screen is locked or inaccessible
    if _PIL:
        try:
            fallback = PIL.Image.new("RGB", (640, 360), color=(15, 18, 24))
            buf = io.BytesIO()
            fallback.save(buf, format="JPEG", quality=75)
            return buf.getvalue(), "image/jpeg"
        except Exception:
            pass

    raise RuntimeError("Desktop screen capture failed (screen may be locked or session restricted).")


def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    try:
        from core.camera_service import get_camera_service
        return get_camera_service().snapshot()
    except Exception as _e:
        print(f"[Vision] CameraService snapshot fallback ({_e})")

    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(8):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"
