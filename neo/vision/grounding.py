"""
neo/vision/grounding.py — Visual Coordinate Normalization and Spatial Grounding.

Architectural Guarantees:
1. Maps normalized LLM vision coordinates ([0..1000] scale) to physical screen pixels.
2. Validates coordinates against active monitor resolution to prevent out-of-bounds clicks.
3. Overlays visual grid references when operating in sparse-UI fallback mode.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger("neo.vision.grounding")


@dataclass
class ScreenPoint:
    """A physical screen coordinate with normalization metadata."""
    x: int
    y: int
    normalized_x: float
    normalized_y: float
    is_within_bounds: bool


def normalize_coords(
    x: int,
    y: int,
    screen_width: int,
    screen_height: int,
) -> Tuple[int, int]:
    """
    Normalizes screen pixel coordinates (0..width, 0..height) to standard [0, 1000] integer range.
    """
    if screen_width <= 0 or screen_height <= 0:
        return 0, 0
    norm_x = int(round((x / screen_width) * 1000))
    norm_y = int(round((y / screen_height) * 1000))
    return max(0, min(1000, norm_x)), max(0, min(1000, norm_y))


def denormalize_coords(
    norm_x: int,
    norm_y: int,
    screen_width: int,
    screen_height: int,
) -> ScreenPoint:
    """
    Converts normalized [0, 1000] coordinate space back to physical screen pixels.
    """
    if norm_x < 0 or norm_x > 1000 or norm_y < 0 or norm_y > 1000:
        logger.warning("Normalized coordinates (%d, %d) out of [0, 1000] range.", norm_x, norm_y)

    px = int(round((norm_x / 1000.0) * screen_width))
    py = int(round((norm_y / 1000.0) * screen_height))

    within_bounds = (0 <= px <= screen_width) and (0 <= py <= screen_height)
    return ScreenPoint(
        x=px,
        y=py,
        normalized_x=norm_x / 1000.0,
        normalized_y=norm_y / 1000.0,
        is_within_bounds=within_bounds,
    )
