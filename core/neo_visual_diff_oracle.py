"""
core/neo_visual_diff_oracle.py — Visual Diff Oracle & Adaptive Settle Watchdog for NEO.

Provides perceptual before/after verification and intelligent dynamic waiting:
1. Visual Diff Oracle:
   - Takes localized screen patch before a click and compares it after the click using OpenCV absdiff.
   - Diagnoses whether an action was accepted or ignored by the OS/target application.
2. Adaptive Settle Watchdog:
   - Replaces hardcoded blind sleeps with adaptive settling.
   - Monitors localized screen regions; returns as soon as animations or page spinners complete.
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

import cv2
import numpy as np

from core.neo_dpi_ocr import dpi_transformer


class VisualDiffOracle:
    """Perceptual screen verification engine."""

    _instance: Optional["VisualDiffOracle"] = None

    def __new__(cls) -> "VisualDiffOracle":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def capture_screen_patch(self, logical_x: int, logical_y: int, radius: int = 40) -> np.ndarray:
        """Captures a localized screen patch centered around logical (lx, ly)."""
        import pyautogui
        # Convert to physical bounding box for screen capture
        px, py = dpi_transformer.logical_to_physical(logical_x, logical_y)
        p_radius = int(radius * dpi_transformer.scale_factor)

        l = max(0, px - p_radius)
        t = max(0, py - p_radius)
        w = max(1, p_radius * 2)
        h = max(1, p_radius * 2)

        try:
            screenshot = pyautogui.screenshot(region=(l, t, w, h))
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception:
            return np.zeros((h, w, 3), dtype=np.uint8)

    def capture_fullscreen(self) -> np.ndarray:
        """Captures active screen as an OpenCV BGR image."""
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception:
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def compute_visual_diff(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        Calculates normalized perceptual difference percentage between two images (0.0 = identical, 1.0 = completely different).
        """
        if img1 is None or img2 is None:
            return 1.0
        if img1.shape != img2.shape:
            # Resize img2 to match img1
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if len(img1.shape) == 3 else img1
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if len(img2.shape) == 3 else img2

        diff = cv2.absdiff(gray1, gray2)
        _, thresh = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        non_zero = cv2.countNonZero(thresh)
        total_pixels = gray1.shape[0] * gray1.shape[1]

        return round(float(non_zero) / float(total_pixels), 4)

    def verify_action_registered(
        self,
        before_patch: np.ndarray,
        logical_x: int,
        logical_y: int,
        radius: int = 40,
        settle_delay_sec: float = 0.2,
        min_diff_threshold: float = 0.012,
    ) -> Tuple[bool, float]:
        """
        Takes after-patch and verifies whether the clicked region experienced state change.
        Returns: (registered: bool, diff_percentage: float)
        """
        time.sleep(settle_delay_sec)
        after_patch = self.capture_screen_patch(logical_x, logical_y, radius=radius)
        diff = self.compute_visual_diff(before_patch, after_patch)
        return (diff >= min_diff_threshold), diff

    def wait_until_settled(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        max_wait_sec: float = 3.5,
        check_interval_sec: float = 0.15,
        settle_threshold: float = 0.005,
    ) -> bool:
        """
        Smart adaptive wait: monitors screen activity (spinners, loading animations, dialog pop-ins).
        Returns True as soon as the screen is stable for 2 consecutive intervals, or False on timeout.
        """
        import pyautogui

        def _grab():
            if region:
                return np.array(pyautogui.screenshot(region=region))
            return np.array(pyautogui.screenshot())

        start_t = time.time()
        prev_frame = _grab()
        consecutive_stable = 0

        while (time.time() - start_t) < max_wait_sec:
            time.sleep(check_interval_sec)
            curr_frame = _grab()
            diff = self.compute_visual_diff(prev_frame, curr_frame)
            if diff <= settle_threshold:
                consecutive_stable += 1
                if consecutive_stable >= 2:
                    return True
            else:
                consecutive_stable = 0
            prev_frame = curr_frame

        return False


# Global Singleton accessor
diff_oracle = VisualDiffOracle()
