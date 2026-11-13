"""
core/neo_set_of_marks.py — Set-of-Marks (SoM) Visual UI Grounding Engine for NEO.

Provides discrete, zero-drift visual element selection. Instead of asking multimodal
models for floating-point coordinates (which drift across scaling & resolutions),
Set-of-Marks tags candidate interactive regions with bright numbered badges [1], [2], [3]...
and has the model choose the discrete tag ID, which maps to exact pre-computed pixel centers.
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import PIL.Image
    import PIL.ImageDraw
    import PIL.ImageFilter
    import PIL.ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from core.neo_ui_automation import ui_automation, UIControl


# High-contrast color palette for visual badges (stands out against light and dark backgrounds)
BADGE_PALETTE = [
    {"bg": (255, 220, 0), "fg": (0, 0, 0)},     # Vivid Yellow
    {"bg": (0, 230, 255), "fg": (0, 0, 0)},     # Electric Cyan
    {"bg": (50, 255, 120), "fg": (0, 0, 0)},    # Neon Green
    {"bg": (255, 60, 140), "fg": (255, 255, 255)}, # Vivid Magenta
    {"bg": (255, 130, 20), "fg": (0, 0, 0)},    # Orange
    {"bg": (170, 80, 255), "fg": (255, 255, 255)}, # Purple
    {"bg": (255, 40, 40), "fg": (255, 255, 255)},  # Crimson Red
    {"bg": (0, 150, 255), "fg": (255, 255, 255)},  # Royal Blue
]


@dataclass
class Mark:
    """Represents a discrete numbered mark tagged on an on-screen element."""
    id: int
    rect: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    center: Tuple[int, int]          # (cx, cy)
    label: str = ""
    control_type: str = "element"
    source: str = "som"              # "uia" or "visual_contour"

    @property
    def width(self) -> int:
        return max(1, self.rect[2] - self.rect[0])

    @property
    def height(self) -> int:
        return max(1, self.rect[3] - self.rect[1])


class SetOfMarksEngine:
    """
    Overlays discrete numbered badges onto screen captures for zero-drift vision selection.
    """

    def __init__(self):
        self._font = None
        if _HAS_PIL:
            try:
                # Try standard Windows / cross-platform sans-serif font
                for font_name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf", "DejaVuSans.ttf"):
                    try:
                        self._font = PIL.ImageFont.truetype(font_name, 12)
                        break
                    except Exception:
                        continue
            except Exception:
                pass
            if self._font is None:
                self._font = PIL.ImageFont.load_default()

    def extract_candidate_regions(
        self,
        image: PIL.Image.Image,
        uia_controls: Optional[List[UIControl]] = None,
        max_marks: int = 60,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Extracts candidate interactive bounding boxes from UIA controls + visual edge contours.
        """
        boxes: List[Tuple[int, int, int, int]] = []
        w, h = image.size

        # 1. First priority: Add exact UIA control bounding boxes
        if uia_controls:
            for c in uia_controls:
                x1, y1, x2, y2 = c.rect
                # Clamp to image bounds
                x1 = max(0, min(w - 1, x1))
                y1 = max(0, min(h - 1, y1))
                x2 = max(x1 + 6, min(w, x2))
                y2 = max(y1 + 6, min(h, y2))
                if (x2 - x1) >= 8 and (y2 - y1) >= 8:
                    boxes.append((x1, y1, x2, y2))

        # 2. If UIA returned fewer than 15 candidate controls (e.g. web canvas, video, game),
        # extract candidate UI boxes using adaptive contrast downsampling
        if len(boxes) < 15:
            try:
                # Downsample for fast contour detection
                scale = 4
                small = image.resize((w // scale, h // scale), PIL.Image.Resampling.BILINEAR)
                gray = small.convert("L")
                edges = gray.filter(PIL.ImageFilter.FIND_EDGES)
                # Binarize edges
                threshold = 30
                binary = edges.point(lambda p: 255 if p > threshold else 0)

                # Segment into candidate grid tiles with active edge energy
                tile_w = max(12, small.width // 18)
                tile_h = max(10, small.height // 18)

                for ty in range(0, small.height - tile_h, tile_h):
                    for tx in range(0, small.width - tile_w, tile_w):
                        box_small = (tx, ty, tx + tile_w, ty + tile_h)
                        crop = binary.crop(box_small)
                        # Count active edge pixels
                        active_pixels = sum(1 for b in crop.tobytes() if b > 0)
                        if active_pixels > (tile_w * tile_h * 0.12):
                            orig_x1 = tx * scale
                            orig_y1 = ty * scale
                            orig_x2 = min(w, (tx + tile_w) * scale)
                            orig_y2 = min(h, (ty + tile_h) * scale)
                            boxes.append((orig_x1, orig_y1, orig_x2, orig_y2))
            except Exception as e:
                pass

        # 3. Deduplicate overlapping boxes
        deduped = self._deduplicate_boxes(boxes, iou_thresh=0.55)

        # 4. Sort top-to-bottom, left-to-right
        deduped.sort(key=lambda b: (b[1] // 30, b[0]))
        return deduped[:max_marks]

    def _deduplicate_boxes(
        self,
        boxes: List[Tuple[int, int, int, int]],
        iou_thresh: float = 0.55,
    ) -> List[Tuple[int, int, int, int]]:
        """Removes highly overlapping bounding boxes."""
        if not boxes:
            return []

        def iou(b1, b2) -> float:
            ix1 = max(b1[0], b2[0])
            iy1 = max(b1[1], b2[1])
            ix2 = min(b1[2], b2[2])
            iy2 = min(b1[3], b2[3])
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            inter = iw * ih
            if inter == 0:
                return 0.0
            a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
            a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
            return inter / float(a1 + a2 - inter)

        kept: List[Tuple[int, int, int, int]] = []
        for box in boxes:
            if not any(iou(box, k) > iou_thresh for k in kept):
                kept.append(box)
        return kept

    def annotate_screenshot(
        self,
        image: PIL.Image.Image,
        uia_controls: Optional[List[UIControl]] = None,
    ) -> Tuple[PIL.Image.Image, Dict[int, Mark]]:
        """
        Draws high-contrast numbered badges over candidate interactive elements.
        Returns (annotated_image, marks_dict).
        """
        if not _HAS_PIL or image is None:
            return image, {}

        annotated = image.copy()
        draw = PIL.ImageDraw.Draw(annotated, "RGBA")

        # Map UIA controls for quick label lookup
        uia_map: Dict[Tuple[int, int, int, int], UIControl] = {}
        if uia_controls:
            for c in uia_controls:
                uia_map[c.rect] = c

        candidate_boxes = self.extract_candidate_regions(image, uia_controls=uia_controls)
        marks: Dict[int, Mark] = {}

        for idx, rect in enumerate(candidate_boxes, start=1):
            x1, y1, x2, y2 = rect
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            matched_ctrl = uia_map.get(rect)
            ctrl_label = matched_ctrl.name if matched_ctrl else ""
            ctrl_type = matched_ctrl.control_type if matched_ctrl else "element"

            mark = Mark(
                id=idx,
                rect=rect,
                center=(cx, cy),
                label=ctrl_label,
                control_type=ctrl_type,
                source="uia" if matched_ctrl else "visual_contour",
            )
            marks[idx] = mark

            # Pick color from palette
            palette = BADGE_PALETTE[(idx - 1) % len(BADGE_PALETTE)]
            border_color = palette["bg"] + (220,)
            badge_bg = palette["bg"] + (255,)
            badge_fg = palette["fg"]

            # 1. Subtle outline around the element boundary
            draw.rectangle([x1, y1, x2, y2], outline=border_color, width=2)

            # 2. Numbered badge badge [ N ]
            badge_text = f"{idx}"
            tag_w = max(18, len(badge_text) * 9 + 8)
            tag_h = 16
            bx1 = x1
            by1 = max(0, y1 - tag_h - 2) if y1 >= tag_h + 2 else y1 + 2
            bx2 = bx1 + tag_w
            by2 = by1 + tag_h

            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=3, fill=badge_bg, outline=(0, 0, 0, 200), width=1)
            # Center text in badge
            draw.text((bx1 + 4, by1 + 1), badge_text, fill=badge_fg, font=self._font)

        return annotated, marks

    def query_mark(
        self,
        query: str,
        annotated_image: PIL.Image.Image,
        marks: Dict[int, Mark],
        timeout_ms: int = 12000,
    ) -> Optional[Mark]:
        """
        Sends the tagged image to Gemini to identify which mark ID corresponds to the query.
        Returns the exact matching Mark, completely eliminating floating-point coordinate drift.
        """
        if not marks or annotated_image is None:
            return None

        # Quick check: if any UIA mark already has exact text match
        q_lower = query.strip().lower()
        for mark in marks.values():
            if mark.label and mark.label.lower() == q_lower:
                return mark

        # Build candidate marks brief for contextual guidance
        labeled_marks = [
            f"[{m.id}]: '{m.label}' ({m.control_type})"
            for m in list(marks.values())[:30]
            if m.label
        ]
        context_str = "\n".join(labeled_marks) if labeled_marks else "No explicit text labels."

        prompt = f"""
You are the NEO Precision Visual Grounding Engine using Set-of-Marks (SoM).
The user wants to locate and interact with: "{query}"

The image has numbered mark badges [1], [2], [3], etc. placed over UI elements.
Known labeled controls:
{context_str}

Identify which numbered badge corresponds to the user's target: "{query}".
Respond ONLY with a JSON object:
{{
    "found": true,
    "mark_id": 3,
    "confidence": 0.95,
    "label": "brief description of marked element"
}}
If the target is not visible among the numbered marks, reply:
{{"found": false}}
"""
        buf = io.BytesIO()
        annotated_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        try:
            from core import gemini
            raw = gemini.multimodal(prompt, image_bytes, mime="image/png", timeout_ms=timeout_ms)
            cleaned = re.sub(r"^```json\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE)
            data = json.loads(cleaned)

            if data.get("found", False) and "mark_id" in data:
                m_id = int(data["mark_id"])
                if m_id in marks:
                    return marks[m_id]

            # Fallback regex search for mark number in response
            m_match = re.search(r"mark_id[\"']?\s*:\s*(\d+)", raw or "")
            if not m_match:
                m_match = re.search(r"\[(\d+)\]", raw or "")
            if m_match:
                m_id = int(m_match.group(1))
                if m_id in marks:
                    return marks[m_id]

        except Exception as e:
            # Fallback check
            pass

        return None


# Singleton Instance
set_of_marks = SetOfMarksEngine()
