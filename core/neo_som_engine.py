"""
core/neo_som_engine.py — Set-of-Marks (SoM) Interactive Visual Grid Engine for NEO.

Eliminates coordinate hallucination across complex desktop applications:
1. Hybrid Mark Extraction:
   - Merges native Windows UI Automation (UIA) accessible controls with OpenCV visual contours.
   - Deduplicates overlapping boxes.
2. High-Contrast Visual Overlay:
   - Draws numbered badge pills ([1], [2], [3], ...) over interactive controls.
   - Saves tagged snapshot to `memory/som_tagged.png`.
3. Discrete Target Registry:
   - Allows model or user to trigger actions with 100% precision by integer ID ("click mark 5").
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
from PIL import Image, ImageDraw, ImageFont

from core.neo_dpi_ocr import dpi_transformer, visual_element_detector
from core.neo_ui_automation import ui_automation

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "memory"
_TAGGED_IMAGE_PATH = _MEMORY_DIR / "som_tagged.png"


@dataclass
class VisualMark:
    mark_id: int
    label: str
    kind: str
    center_logical: Tuple[int, int]
    bbox_logical: Tuple[int, int, int, int]  # (left, top, right, bottom)
    center_physical: Tuple[int, int]
    bbox_physical: Tuple[int, int, int, int]


class SetOfMarksEngine:
    """Generates and resolves numbered Set-of-Marks interactive grids."""

    _instance: Optional["SetOfMarksEngine"] = None

    def __new__(cls) -> "SetOfMarksEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._marks: Dict[int, VisualMark] = {}
            cls._last_tagged_path: Optional[Path] = None
        return cls._instance

    @property
    def active_marks(self) -> Dict[int, VisualMark]:
        return self._marks

    def generate_som_grid(
        self,
        screenshot_path: Optional[str | Path] = None,
        max_marks: int = 40,
    ) -> Tuple[Path, Dict[int, VisualMark]]:
        """
        Takes screenshot or loads image, extracts controls, renders numbered badges, and stores registry.
        """
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        target_path = Path(screenshot_path) if screenshot_path else None

        # If no image path provided, capture active screen
        if not target_path or not target_path.exists():
            import pyautogui
            screenshot = pyautogui.screenshot()
            target_path = _MEMORY_DIR / "som_raw.png"
            screenshot.save(str(target_path))

        pil_img = Image.open(str(target_path)).convert("RGB")
        w_img, h_img = pil_img.size

        # 1. Harvest native UIA controls
        uia_controls = ui_automation.get_interactive_controls(max_items=30, timeout_secs=1.5)

        marks: List[VisualMark] = []
        mark_idx = 1
        occupied_centers: List[Tuple[int, int]] = []

        def _is_too_close(cx: int, cy: int, min_dist: int = 18) -> bool:
            return any(abs(cx - oc[0]) < min_dist and abs(cy - oc[1]) < min_dist for oc in occupied_centers)

        # Process native UIA first
        for c in uia_controls:
            if not c.is_plausible or not c.name:
                continue
            l, t, r, b = c.rect
            cx = (l + r) // 2
            cy = (t + b) // 2

            # Convert to physical coordinates for drawing on screenshot
            p_l, p_t = dpi_transformer.logical_to_physical(l, t)
            p_r, p_b = dpi_transformer.logical_to_physical(r, b)
            p_cx, p_cy = (p_l + p_r) // 2, (p_t + p_b) // 2

            if 0 <= p_cx < w_img and 0 <= p_cy < h_img:
                if not _is_too_close(p_cx, p_cy):
                    occupied_centers.append((p_cx, p_cy))
                    marks.append(VisualMark(
                        mark_id=mark_idx,
                        label=c.name,
                        kind=c.control_type,
                        center_logical=(cx, cy),
                        bbox_logical=(l, t, r, b),
                        center_physical=(p_cx, p_cy),
                        bbox_physical=(p_l, p_t, p_r, p_b),
                    ))
                    mark_idx += 1
                    if len(marks) >= max_marks:
                        break

        # 2. Augment with local visual contour elements if marks < max_marks
        if len(marks) < max_marks:
            cv_img = cv2.imread(str(target_path))
            detected = visual_element_detector.detect_elements(cv_img, max_elements=25)
            for d in detected:
                p_cx, p_cy = (d.bbox_physical[0] + d.bbox_physical[2]) // 2, (d.bbox_physical[1] + d.bbox_physical[3]) // 2
                if not _is_too_close(p_cx, p_cy, min_dist=24):
                    occupied_centers.append((p_cx, p_cy))
                    marks.append(VisualMark(
                        mark_id=mark_idx,
                        label=f"{d.kind}_{mark_idx}",
                        kind=d.kind,
                        center_logical=d.center_logical,
                        bbox_logical=d.bbox_logical,
                        center_physical=(p_cx, p_cy),
                        bbox_physical=d.bbox_physical,
                    ))
                    mark_idx += 1
                    if len(marks) >= max_marks:
                        break

        # 3. Draw high-contrast translucent pills on PIL image
        draw = ImageDraw.Draw(pil_img, "RGBA")
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            font = ImageFont.load_default()

        for m in marks:
            px, py = m.center_physical
            # Pill text
            pill_text = f"[{m.mark_id}]"
            # Pill bounding box
            pw, ph = 26, 18
            pill_l = max(0, px - pw // 2)
            pill_t = max(0, py - ph // 2)
            pill_r = min(w_img, pill_l + pw)
            pill_b = min(h_img, pill_t + ph)

            # Draw translucent neon amber background with solid white text
            draw.rounded_rectangle(
                [(pill_l, pill_t), (pill_r, pill_b)],
                radius=4,
                fill=(245, 158, 11, 235),
                outline=(0, 0, 0, 255),
                width=1
            )
            draw.text((pill_l + 3, pill_t + 1), pill_text, fill=(0, 0, 0), font=font)

        pil_img.save(str(_TAGGED_IMAGE_PATH), "PNG")
        self._last_tagged_path = _TAGGED_IMAGE_PATH
        self._marks = {m.mark_id: m for m in marks}

        return _TAGGED_IMAGE_PATH, self._marks

    def click_mark(self, mark_id: int) -> Tuple[bool, str]:
        """Executes a click at the logical center of the specified mark ID."""
        mark = self._marks.get(mark_id)
        if not mark:
            return False, f"Mark [{mark_id}] not found in current Set-of-Marks grid. Available: {list(self._marks.keys())}"

        lx, ly = mark.center_logical
        try:
            import pyautogui
            pyautogui.click(lx, ly)
            return True, f"Clicked Mark [{mark_id}] ({mark.kind}: '{mark.label}') at exact logical coordinates ({lx}, {ly})."
        except Exception as e:
            return False, f"Failed clicking mark [{mark_id}]: {e}"

    def list_marks_summary(self) -> List[str]:
        """Returns concise metadata for active marks."""
        return [
            f"[{m.mark_id}] {m.kind} '{m.label}' @ ({m.center_logical[0]}, {m.center_logical[1]})"
            for m in self._marks.values()
        ]


# Global Singleton accessor
som_engine = SetOfMarksEngine()
