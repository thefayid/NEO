"""
tests/test_ocr_and_gestures.py — End-to-end verification for Hand Gestures & Multimodal OCR.
"""
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image, ImageDraw
import io
import cv2
import numpy as np
from core import gemini
from actions.gesture_control import _gesture_ctl

def test_ocr_pipeline():
    print("\n--- 1. Testing Multimodal OCR Pipeline ---")
    img = Image.new("RGB", (350, 120), color=(10, 15, 25))
    draw = ImageDraw.Draw(img)
    draw.text((20, 45), "MARK-LVI DEEP OCR VERIFIED", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b = buf.getvalue()

    prompt = "Extract all text visible in this image (OCR). Return only the extracted text."
    result = gemini.multimodal(prompt, img_b, mime="image/png")
    print(f"OCR Extracted Output: '{result.strip()}'")
    assert "MARK-LVI" in result or "DEEP OCR" in result or "VERIFIED" in result, f"OCR failed to extract text: {result}"
    print("✓ Multimodal OCR Pipeline passed!")

def test_hand_gestures():
    print("\n--- 2. Testing Hand Gestures & Neural Recognizer ---")
    model_path = BASE_DIR / "models" / "gesture_recognizer.task"
    assert model_path.exists(), f"Google model {model_path} missing!"
    print(f"✓ Model verified at {model_path} ({model_path.stat().st_size} bytes)")

    # Test controller start
    msg = _gesture_ctl.start()
    print(f"Gesture start result: {msg}")
    assert _gesture_ctl.is_active(), "Gesture controller should be active"

    # Simulate palm trigger and check last gesture
    _gesture_ctl._trigger_palm()
    last_gest, last_t = _gesture_ctl.get_last_gesture()
    assert "Open Palm" in last_gest, f"Expected Open Palm, got: {last_gest}"
    print(f"✓ Palm trigger telemetry verified: '{last_gest}'")

    # Reset trigger time cooldown for unit test
    _gesture_ctl._last_trigger_time = 0.0

    # Simulate swipe trigger
    _gesture_ctl._trigger_swipe("right")
    last_gest, _ = _gesture_ctl.get_last_gesture()
    assert "Swipe Right" in last_gest, f"Expected Swipe Right, got: {last_gest}"
    print(f"✓ Swipe trigger telemetry verified: '{last_gest}'")

    # Stop controller
    stop_msg = _gesture_ctl.stop()
    assert not _gesture_ctl.is_active(), "Gesture controller should be stopped"
    print(f"✓ Gesture controller stopped cleanly: {stop_msg}")

def test_vision_studio_ui():
    print("\n--- 3. Testing NeoVisionSpatialStudio UI Hooks ---")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from core.neo_vision_studio import NeoVisionSpatialStudio
    studio = NeoVisionSpatialStudio()

    assert hasattr(studio, "screen_ocr_btn")
    assert hasattr(studio, "snap_ocr_btn")
    assert hasattr(studio, "copy_ocr_btn")
    assert hasattr(studio, "gesture_toggle_btn")

    # Test toggle gesture button
    studio._toggle_gestures() # enable
    assert _gesture_ctl.is_active()
    assert "Disable" in studio.gesture_toggle_btn.text()
    studio._toggle_gestures() # disable
    assert not _gesture_ctl.is_active()
    assert "Enable" in studio.gesture_toggle_btn.text()
    print("✓ NeoVisionSpatialStudio UI buttons and gesture toggle verified!")

if __name__ == "__main__":
    test_ocr_pipeline()
    test_hand_gestures()
    test_vision_studio_ui()
    print("\n🎉 ALL HAND GESTURE & OCR TESTS PASSED WITH 100% SUCCESS!")
