"""
neo/vision/diff.py — Fast OpenCV Image Difference Engine.

Architectural Guarantees:
1. Fast local computer vision diff via OpenCV (cv2).
2. Calculates exact changed pixel counts, percentage of visual change, and bounding regions.
3. Groups adjacent pixel modifications using morphological dilation into coherent UI change boxes.
4. Filters sub-pixel noise and rendering artifacts below configurable contour thresholds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("neo.vision.diff")


@dataclass
class ImageDiffResult:
    """Detailed result of an image difference comparison."""
    has_changed: bool
    changed_pixel_count: int
    changed_percentage: float
    changed_regions: List[Tuple[int, int, int, int]] = field(default_factory=list)
    enclosing_bbox: Optional[Tuple[int, int, int, int]] = None
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_changed": self.has_changed,
            "changed_pixel_count": self.changed_pixel_count,
            "changed_percentage": round(self.changed_percentage, 4),
            "changed_regions": [
                {"x": r[0], "y": r[1], "w": r[2], "h": r[3]}
                for r in self.changed_regions
            ],
            "enclosing_bbox": (
                {"x": self.enclosing_bbox[0], "y": self.enclosing_bbox[1], "w": self.enclosing_bbox[2], "h": self.enclosing_bbox[3]}
                if self.enclosing_bbox else None
            ),
            "width": self.width,
            "height": self.height,
        }


def _to_cv2_gray(image_input: Union[str, Path, Image.Image, np.ndarray]) -> np.ndarray:
    """Converts image input into a grayscale OpenCV numpy array."""
    if isinstance(image_input, (str, Path)):
        img = cv2.imread(str(image_input))
        if img is None:
            raise FileNotFoundError(f"Could not load image from: {image_input}")
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif isinstance(image_input, Image.Image):
        arr = np.array(image_input)
        if len(arr.shape) == 2:
            return arr
        elif arr.shape[2] == 4:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
        else:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    elif isinstance(image_input, np.ndarray):
        if len(image_input.shape) == 2:
            return image_input
        elif image_input.shape[2] == 4:
            return cv2.cvtColor(image_input, cv2.COLOR_BGRA2GRAY)
        else:
            return cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
    else:
        raise TypeError(f"Unsupported image format: {type(image_input)}")


def diff_images(
    image_a: Union[str, Path, Image.Image, np.ndarray],
    image_b: Union[str, Path, Image.Image, np.ndarray],
    threshold: int = 25,
    min_contour_area: int = 16,
) -> ImageDiffResult:
    """
    Computes visual differences between two images using OpenCV.
    Returns changed regions as bounding boxes (x, y, w, h) and percentage of visual change.
    """
    gray_a = _to_cv2_gray(image_a)
    gray_b = _to_cv2_gray(image_b)

    # Align dimensions if slight mismatch
    if gray_a.shape != gray_b.shape:
        h, w = gray_a.shape[:2]
        gray_b = cv2.resize(gray_b, (w, h), interpolation=cv2.INTER_LINEAR)

    h, w = gray_a.shape[:2]
    total_pixels = max(1, w * h)

    # 1. Absolute pixel difference
    diff = cv2.absdiff(gray_a, gray_b)

    # 2. Binary threshold
    _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    changed_pixels = int(np.count_nonzero(thresh))
    changed_pct = (changed_pixels / float(total_pixels)) * 100.0

    if changed_pixels == 0:
        return ImageDiffResult(
            has_changed=False,
            changed_pixel_count=0,
            changed_percentage=0.0,
            changed_regions=[],
            enclosing_bbox=None,
            width=w,
            height=h,
        )

    # 3. Morphological dilation to group adjacent pixel edits into coherent UI boxes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    dilated = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    dilated = cv2.dilate(dilated, kernel, iterations=1)

    # 4. Find region contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions: List[Tuple[int, int, int, int]] = []
    min_x, min_y, max_x, max_y = w, h, 0, 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_contour_area:
            continue
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        regions.append((rx, ry, rw, rh))

        min_x = min(min_x, rx)
        min_y = min(min_y, ry)
        max_x = max(max_x, rx + rw)
        max_y = max(max_y, ry + rh)

    # Sort regions top-to-bottom, left-to-right
    regions.sort(key=lambda r: (r[1] // 20, r[0]))

    enclosing = None
    if regions:
        enclosing = (min_x, min_y, max_x - min_x, max_y - min_y)

    return ImageDiffResult(
        has_changed=len(regions) > 0 or changed_pixels > min_contour_area,
        changed_pixel_count=changed_pixels,
        changed_percentage=changed_pct,
        changed_regions=regions,
        enclosing_bbox=enclosing,
        width=w,
        height=h,
    )
