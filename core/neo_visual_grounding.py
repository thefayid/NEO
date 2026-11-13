"""
core/neo_visual_grounding.py — Multimodal Visual Grounding & Desktop Interaction for NEO.

Senior Intelligence Architecture (Pillar 5):
1. Screen Capture & Coordinate Space Normalization:
   - High-performance screen capture (mss / PIL.ImageGrab).
   - Multi-monitor coordinate normalization [0.0, 1.0] <-> physical screen pixels.
2. Multimodal UI Grounding:
   - Locates UI elements (buttons, inputs, menus, text) on screen via Gemini multimodal vision.
   - Parses normalized bounding boxes into structured UIElement instances.
3. Desktop Interaction:
   - Native OS cursor movement and mouse clicks (SetCursorPos / pyautogui / ctypes).
   - Smooth human-like cursor interpolation.
4. macOS-Grade Screen Highlight Overlay:
   - Frameless, translucent, click-through macOS Sequoia overlay widget.
   - Visualizes grounded targets with Apple accent borders, badges, and fade-out animation.
5. Visual Reverse-Engineering:
   - Converts UI mockups, architecture diagrams, and wireframes into Mermaid or PyQt code.
"""
from __future__ import annotations

import ctypes
import io
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from core.theme_provider import theme
from core.design_tokens import Radii, Spacing

# Safe optional imports for capture and automation
try:
    import mss
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False

try:
    import PIL.Image
    import PIL.ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    from core.neo_ui_automation import ui_automation
    _HAS_UIA = True
except ImportError:
    _HAS_UIA = False

try:
    from core.neo_set_of_marks import set_of_marks
    _HAS_SOM = True
except ImportError:
    _HAS_SOM = False

try:
    from core.neo_ui_verifier import ui_verifier
    _HAS_VERIFIER = True
except ImportError:
    _HAS_VERIFIER = False


@dataclass
class UIElement:
    """Represents a grounded UI element on the desktop."""
    label: str
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in physical pixels
    confidence: float = 1.0
    element_type: str = "text"      # "button", "input", "icon", "text", "link"
    norm_bbox: Optional[Tuple[float, float, float, float]] = None

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def width(self) -> int:
        return max(1, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> int:
        return max(1, self.bbox[3] - self.bbox[1])

    @property
    def center(self) -> Tuple[int, int]:
        return (self.bbox[0] + self.width // 2, self.bbox[1] + self.height // 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "element_type": self.element_type,
            "confidence": self.confidence,
        }


class MacOSScreenHighlightOverlay(QWidget):
    """
    Frameless, transparent, click-through overlay that displays a macOS Sequoia
    accent-colored highlight box around grounded UI elements with smooth fade-out.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # Frameless, stays on top, tool window (hidden from taskbar)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._target_rect: Optional[QRect] = None
        self._target_label: str = ""
        self._opacity: float = 1.0

        # Fade out animation
        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setDuration(1200)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.valueChanged.connect(self._on_opacity_change)
        self._fade_anim.finished.connect(self.hide)

        # Auto-hide timer
        self._linger_timer = QTimer(self)
        self._linger_timer.setSingleShot(True)
        self._linger_timer.timeout.connect(self._start_fade)

    def highlight_target(
        self,
        rect: Tuple[int, int, int, int],
        label: str = "",
        linger_ms: int = 1500,
    ) -> None:
        """
        Shows a highlight around rect=(x1, y1, x2, y2) in physical coordinates.
        """
        x1, y1, x2, y2 = rect
        w = max(20, x2 - x1)
        h = max(20, y2 - y1)

        # Expand widget to encompass the target plus badge margin
        padding = 32
        wx = max(0, x1 - padding)
        wy = max(0, y1 - padding)
        ww = w + (padding * 2)
        wh = h + (padding * 2)

        self.setGeometry(wx, wy, ww, wh)
        self._target_rect = QRect(padding, padding, w, h)
        self._target_label = label
        self._opacity = 1.0

        self._fade_anim.stop()
        self._linger_timer.stop()
        self.show()
        self.update()

        self._linger_timer.start(linger_ms)

    def _start_fade(self) -> None:
        self._fade_anim.start()

    def _on_opacity_change(self, val: Any) -> None:
        self._opacity = float(val)
        self.update()

    def paintEvent(self, event) -> None:
        if not self._target_rect:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        accent_color = theme.accent_color
        alpha = int(255 * self._opacity)

        # 1. Fill highlight box
        fill_color = QColor(accent_color)
        fill_color.setAlpha(int(36 * self._opacity))
        painter.setBrush(QBrush(fill_color))

        # 2. Border
        border_color = QColor(accent_color)
        border_color.setAlpha(alpha)
        pen = QPen(border_color, 2.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        r = self._target_rect
        corner_radius = 8.0
        painter.drawRoundedRect(QRectF(r), corner_radius, corner_radius)

        # 3. Label badge if provided
        if self._target_label:
            font = QFont("Inter", 9)
            font.setBold(True)
            painter.setFont(font)

            badge_text = self._target_label[:30]
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(badge_text) + 12
            text_h = metrics.height() + 4

            badge_x = r.left()
            badge_y = max(4, r.top() - text_h - 4)
            badge_rect = QRectF(badge_x, badge_y, text_w, text_h)

            badge_bg = QColor(accent_color)
            badge_bg.setAlpha(int(220 * self._opacity))
            painter.setBrush(QBrush(badge_bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 4.0, 4.0)

            # Badge text
            painter.setPen(QColor(255, 255, 255, alpha))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)


class VisualGroundingEngine(QObject):
    """
    Coordinates multimodal vision, UI element grounding, OS cursor clicks, and reverse-engineering.
    """
    target_grounded = pyqtSignal(str, int, int)          # label, center_x, center_y
    action_executed = pyqtSignal(str, bool, str)         # action, success, detail
    highlight_requested = pyqtSignal(object, str, int)   # bbox, label, linger_ms (thread-safe signal)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._overlay: Optional[MacOSScreenHighlightOverlay] = None

    def _ensure_overlay(self) -> Optional[MacOSScreenHighlightOverlay]:
        """Ensures the overlay widget is created strictly on the main Qt GUI thread."""
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            if self._overlay is None:
                self._overlay = MacOSScreenHighlightOverlay()
            return self._overlay
        return None

    # -------------------------------------------------------------------------
    # Screen Capture
    # -------------------------------------------------------------------------
    def capture_screen(
        self,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[Optional[Any], Tuple[int, int]]:
        """
        Captures the primary monitor or bbox=(x1, y1, x2, y2).
        Returns (PIL.Image, (screen_width, screen_height)).
        """
        if _HAS_MSS:
            try:
                mss_cls = getattr(mss, "MSS", getattr(mss, "mss", None))
                with mss_cls() as sct:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    if bbox:
                        monitor = {
                            "left": bbox[0],
                            "top": bbox[1],
                            "width": bbox[2] - bbox[0],
                            "height": bbox[3] - bbox[1],
                        }
                    sct_img = sct.grab(monitor)
                    if _HAS_PIL:
                        img = PIL.Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        return img, (monitor["width"], monitor["height"])
            except Exception as e:
                print(f"[VisualGrounding] mss capture fallback: {e}")

        if _HAS_PIL:
            try:
                img = PIL.ImageGrab.grab(bbox=bbox)
                return img, img.size
            except Exception as e:
                print(f"[VisualGrounding] PIL.ImageGrab error: {e}")

        return None, (1920, 1080)

    def image_to_bytes(self, image: Any, format: str = "PNG") -> bytes:
        """Converts PIL Image to bytes."""
        if image is None:
            return b""
        buf = io.BytesIO()
        image.save(buf, format=format)
        return buf.getvalue()

    # -------------------------------------------------------------------------
    # Coordinate Space Normalization
    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_box(
        box: Tuple[int, int, int, int],
        screen_w: int,
        screen_h: int,
    ) -> Tuple[float, float, float, float]:
        """Maps [x1, y1, x2, y2] to [0.0, 1.0]."""
        w = max(1, screen_w)
        h = max(1, screen_h)
        return (
            round(box[0] / w, 4),
            round(box[1] / h, 4),
            round(box[2] / w, 4),
            round(box[3] / h, 4),
        )

    @staticmethod
    def denormalize_box(
        norm_box: Tuple[float, float, float, float],
        screen_w: int,
        screen_h: int,
    ) -> Tuple[int, int, int, int]:
        """Maps normalized box [0.0, 1.0] to physical screen pixels."""
        return (
            int(norm_box[0] * screen_w),
            int(norm_box[1] * screen_h),
            int(norm_box[2] * screen_w),
            int(norm_box[3] * screen_h),
        )

    # -------------------------------------------------------------------------
    # Multimodal UI Grounding (3-Tier Precision Architecture)
    # -------------------------------------------------------------------------
    def ground_target_on_screen(
        self,
        query: str,
        highlight: bool = True,
        use_uia: bool = True,
        use_som: bool = True,
    ) -> Optional[UIElement]:
        """
        Locates target UI element across 3 precision tiers:
        Tier 1: Windows Native UI Automation (UIA) - 100% exact OS bounding box, 0 drift, no vision cost.
        Tier 2: Set-of-Marks (SoM) Tagging - discrete numbered badges [1], [2], [3]... preventing coordinate hallucination.
        Tier 3: Multimodal Bounding Box Fallback - standard normalized box detection.
        """
        # --- Tier 1: Windows UI Automation Direct Query ---
        if use_uia and _HAS_UIA and ui_automation.is_available:
            ctrl = ui_automation.find_control(query)
            if ctrl:
                elem = UIElement(
                    label=ctrl.name or query,
                    bbox=ctrl.rect,
                    confidence=1.0,
                    element_type=ctrl.control_type.lower(),
                )
                if highlight:
                    self.highlight_element(elem)
                self.target_grounded.emit(elem.label, elem.center[0], elem.center[1])
                return elem

        # Capture primary screen for visual inspection
        img, (sw, sh) = self.capture_screen()
        if not img:
            return None

        # --- Tier 2: Set-of-Marks (SoM) Discrete Numbered Badges ---
        if use_som and _HAS_SOM:
            try:
                uia_ctrls = ui_automation.get_interactive_controls() if (_HAS_UIA and ui_automation.is_available) else []
                annotated_img, marks = set_of_marks.annotate_screenshot(img, uia_controls=uia_ctrls)
                if marks:
                    matched_mark = set_of_marks.query_mark(query, annotated_img, marks)
                    if matched_mark:
                        elem = UIElement(
                            label=matched_mark.label or query,
                            bbox=matched_mark.rect,
                            confidence=0.98,
                            element_type=matched_mark.control_type.lower(),
                        )
                        if highlight:
                            self.highlight_element(elem)
                        self.target_grounded.emit(elem.label, elem.center[0], elem.center[1])
                        return elem
            except Exception as e:
                print(f"[VisualGrounding] SoM resolution warning: {e}")

        # --- Tier 3: Multimodal Bounding Box Fallback ---
        img_bytes = self.image_to_bytes(img, format="PNG")
        element = self._query_gemini_grounding(query, img_bytes, sw, sh)

        if element and highlight:
            self.highlight_element(element)

        if element:
            self.target_grounded.emit(element.label, element.center[0], element.center[1])

        return element

    def _query_gemini_grounding(
        self,
        query: str,
        img_bytes: bytes,
        screen_w: int,
        screen_h: int,
    ) -> Optional[UIElement]:
        """Prompts Gemini to locate query in the image with bounding box."""
        try:
            from core import gemini
            prompt = f"""
You are NEO Visual Grounding Engine. Locate the UI element, icon, button, or text corresponding to:
"{query}"

Return ONLY a JSON object with this exact structure:
{{
    "found": true,
    "label": "{query}",
    "element_type": "button",
    "bbox_norm": [ymin, xmin, ymax, xmax],
    "confidence": 0.95
}}
where coordinates in bbox_norm are floats normalized between 0.0 and 1.0.
If the element cannot be found, return {{"found": false}}.
"""
            raw = gemini.multimodal(prompt, img_bytes, mime="image/png", timeout_ms=12000)
            cleaned = re.sub(r"^```json\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE)
            data = json.loads(cleaned)

            if not data.get("found", False) or "bbox_norm" not in data:
                return None

            ymin, xmin, ymax, xmax = data["bbox_norm"]
            # Convert [ymin, xmin, ymax, xmax] normalized to [x1, y1, x2, y2] physical
            x1 = int(xmin * screen_w)
            y1 = int(ymin * screen_h)
            x2 = int(xmax * screen_w)
            y2 = int(ymax * screen_h)

            return UIElement(
                label=data.get("label", query),
                bbox=(x1, y1, x2, y2),
                confidence=float(data.get("confidence", 0.9)),
                element_type=data.get("element_type", "element"),
                norm_bbox=(xmin, ymin, xmax, ymax),
            )
        except Exception as e:
            print(f"[VisualGrounding] Multimodal detection error: {e}")
            return None

    # -------------------------------------------------------------------------
    # Visual Highlighting & Interaction
    # -------------------------------------------------------------------------
    def highlight_element(self, element: UIElement, linger_ms: int = 1500) -> None:
        """Paints an animated macOS accent highlight over the element (strictly thread-safe)."""
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            overlay = self._ensure_overlay()
            if overlay:
                overlay.highlight_target(element.bbox, label=element.label, linger_ms=linger_ms)
        else:
            # Emit thread-safe queued signal to Main GUI thread
            self.highlight_requested.emit(element.bbox, element.label, linger_ms)

    def click_element(
        self,
        target: Union[UIElement, Tuple[int, int]],
        double_click: bool = False,
        right_click: bool = False,
        verify: bool = True,
    ) -> bool:
        """
        Moves cursor to target and clicks with closed-loop action verification.
        """
        if isinstance(target, UIElement):
            cx, cy = target.center
        else:
            cx, cy = target

        # Closed-loop pre-action snapshot
        pre_snap = None
        if verify and _HAS_VERIFIER:
            try:
                pre_snap = ui_verifier.capture_snapshot(target_pos=(cx, cy))
            except Exception:
                pass

        try:
            # 1. Smooth cursor movement
            self.move_cursor_smooth(cx, cy)
            time.sleep(0.04)

            # 2. Native click on Windows
            if sys.platform == "win32":
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                MOUSEEVENTF_RIGHTDOWN = 0x0008
                MOUSEEVENTF_RIGHTUP = 0x0010

                down_flag = MOUSEEVENTF_RIGHTDOWN if right_click else MOUSEEVENTF_LEFTDOWN
                up_flag = MOUSEEVENTF_RIGHTUP if right_click else MOUSEEVENTF_LEFTUP

                ctypes.windll.user32.SetCursorPos(cx, cy)
                ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, 0)

                if double_click and not right_click:
                    time.sleep(0.08)
                    ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
                    time.sleep(0.02)
                    ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, 0)

            elif _HAS_PYAUTOGUI:
                if double_click:
                    pyautogui.doubleClick(cx, cy)
                elif right_click:
                    pyautogui.rightClick(cx, cy)
                else:
                    pyautogui.click(cx, cy)

            # Closed-loop post-action verification
            if verify and _HAS_VERIFIER and pre_snap is not None:
                time.sleep(0.06)
                post_snap = ui_verifier.capture_snapshot(target_pos=(cx, cy))
                ver_res = ui_verifier.verify_action(pre_snap, post_snap, expected_action="click", target_pos=(cx, cy))
                self.action_executed.emit("click", True, f"Clicked ({cx}, {cy}) [{ver_res.reason}]")
            else:
                self.action_executed.emit("click", True, f"Clicked ({cx}, {cy})")

            return True
        except Exception as e:
            self.action_executed.emit("click", False, f"Click failed: {e}")
            return False

    def move_cursor_smooth(self, target_x: int, target_y: int, steps: int = 12) -> None:
        """Interpolates mouse movement smoothly for human-like computer use."""
        if sys.platform != "win32":
            if _HAS_PYAUTOGUI:
                pyautogui.moveTo(target_x, target_y, duration=0.15)
            return

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        start_x, start_y = pt.x, pt.y

        for i in range(1, steps + 1):
            t = i / steps
            # Smooth ease-out cubic curve
            ease_t = 1 - (1 - t) ** 3
            curr_x = int(start_x + (target_x - start_x) * ease_t)
            curr_y = int(start_y + (target_y - start_y) * ease_t)
            ctypes.windll.user32.SetCursorPos(curr_x, curr_y)
            time.sleep(0.005)

    # -------------------------------------------------------------------------
    # Visual Reverse-Engineering (Mockup/Diagram to Code or Mermaid)
    # -------------------------------------------------------------------------
    def reverse_engineer_visual(
        self,
        image_input: Union[str, Path, bytes, Any],
        target_format: str = "mermaid",
    ) -> str:
        """
        Translates a diagram, mockup, or screenshot into clean Mermaid syntax or code.
        """
        img_bytes = b""
        if isinstance(image_input, (str, Path)):
            p = Path(image_input)
            if p.exists():
                img_bytes = p.read_bytes()
        elif isinstance(image_input, bytes):
            img_bytes = image_input
        elif _HAS_PIL and isinstance(image_input, PIL.Image.Image):
            img_bytes = self.image_to_bytes(image_input)

        if not img_bytes:
            return "Error: No valid image provided for reverse engineering."

        from core import gemini

        prompts = {
            "mermaid": """
Reverse-engineer the architecture, flowchart, or state diagram shown in this image into valid Mermaid diagram syntax.
Output ONLY the raw Mermaid code block (e.g. ```mermaid ... ```).
Ensure all node labels and connections match the visual diagram exactly.
""",
            "pyqt": """
Reverse-engineer the UI mockup/window shown in this image into a clean, modern PyQt6 widget class.
Use standard layouts, QPushButton, QLabel, QLineEdit, and clean styling.
Output ONLY complete Python code inside ```python ... ``` fences.
""",
            "schema": """
Analyze the UI layout in this image and return a JSON hierarchy of elements, their spatial alignment, colors, and text content.
Output ONLY valid JSON inside ```json ... ``` fences.
"""
        }

        selected_prompt = prompts.get(target_format.lower(), prompts["mermaid"])
        result = gemini.multimodal(selected_prompt, img_bytes, mime="image/png")
        return result.strip()


# Singleton Instance & Aliases
VisualGrounding = VisualGroundingEngine
NEOVisualGrounding = VisualGroundingEngine
visual_grounding = VisualGroundingEngine()
