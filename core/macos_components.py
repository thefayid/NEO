"""
core/macos_components.py — Apple AppKit & SwiftUI Native Component Library.

Senior Design Engineering Specification (Phase 3):
1. Push Button (MacOSButton):
   - Variants: Default (Primary Accent), Secondary (Control Card), Destructive (System Red).
   - States: Rest, Hover, Pressed, Focused (3px accent ring), Disabled.
   - Sizing: 28px standard height, 6px continuous radius (sm).
2. Segmented Control with Sliding Selection Pill (MacOSSegmentedControl):
   - Sliding selection pill animated smoothly (180ms OutCubic) beneath active segment.
   - Translucent groove track, elevated pill card with subtle multi-layer shadow.
   - States: Rest, Hover, Active, Focused, Disabled.
3. Toggle Switch (MacOSToggle):
   - iOS/macOS exact 38x22 dimensions.
   - Pill track (inactive #3A3A3C, active accent).
   - 18x18px white circle thumb with tactile expansion to 20px on mouse press.
   - Smooth 150ms OutCubic sliding animation.
   - States: Rest Off/On, Hover, Pressed, Focused (3px ring), Disabled.
4. Text Field with 3px Accent Focus Ring (MacOSTextField):
   - 28px height, 6px radius, 1px separator border at rest.
   - Authentic 3px diffused outer accent focus ring on focus.
   - States: Rest, Hover, Pressed, Focused, Disabled.
5. Search Field with Magnifier and Clear Button (MacOSSearchField):
   - 28px height, 6px radius, Lucide search icon (1.5 stroke) on left.
   - Auto-revealing circular clear button ('✕') when text is non-empty.
   - 3px accent focus ring surrounding container.
   - States: Rest, Hover, Focused, Disabled.
6. Popover with Directional Arrow (MacOSPopover):
   - Contiguous squircle bubble (10px radius) with triangular arrow notch.
   - Directions: Top, Bottom, Left, Right. Translucent background, elevation shadow.
   - Auto-dismisses on outside click.
7. Context Menu with 6px Radius & Keyboard Shortcut Column (MacOSContextMenu):
   - 6px corner radius, 1px border, layered elevation.
   - Lucide 1.5 stroke icons, label, and right-aligned keyboard shortcut badges.
   - Native macOS accent pill highlight on hover.
8. Sidebar List with Selection Highlight & SF/Lucide Icons (MacOSSidebarList):
   - 16x16px Lucide icons at 1.5 stroke, 13pt body text, badge pill support.
   - Smooth 6px selection highlight capsule. Section headers in 10pt semibold uppercase.
9. Toast / Notification Banner (MacOSToast):
   - Notification Center card with 10px radius, 1px highlight border, shadow.
   - Slide-in from top-right (250ms OutCubic), auto-dismiss timer, hover pause.
   - Variants: Info, Success, Warning, Error.
10. Sheet Modal (MacOSSheetModal):
    - Anchors to top of parent window with 14px rounded bottom corners.
    - Dimmed backdrop scrim (rgba(0,0,0,0.45)), 250ms OutCubic slide-down.
    - Header with title, content host, Cancel / Done action footer.
11. Tooltip with 600ms Delay (MacOSTooltip):
    - Apple HIG exact 600ms resting hover delay before reveal.
    - Dark translucent pill, 6px radius, SF Caption 10pt typography.
12. Thin Overlay Scrollbars (MacOSOverlayScrollBar & MacOSScrollArea):
    - Floats over content with 0px reserved width.
    - 5px resting width (8px hover), fades in during scroll, auto-fades out after 800ms.
"""
from __future__ import annotations

import sys
from enum import Enum
from typing import Optional, List, Callable, Union

from PyQt6.QtCore import (
    Qt, QPoint, QRect, QRectF, QSize, pyqtSignal, pyqtProperty,
    QPropertyAnimation, QEasingCurve, QTimer, QByteArray, QEvent, QObject
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush,
    QPixmap, QIcon, QMouseEvent, QKeyEvent, QFocusEvent, QEnterEvent
)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLineEdit, QLabel, QFrame, QHBoxLayout,
    QVBoxLayout, QMenu, QScrollArea, QScrollBar, QSizePolicy,
    QGraphicsDropShadowEffect, QApplication, QStyleOptionButton,
    QStyle, QGraphicsBlurEffect, QGraphicsOpacityEffect
)
from PyQt6.QtSvg import QSvgRenderer

from core.theme_provider import theme
from core.macos_motion import motion, SpringPresets, create_spring_animation, stagger_reveal


# ── 1. Lucide 1.5 Stroke Vector Icons Engine ─────────────────────────────────

_LUCIDE_PATHS = {
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    "alert-triangle": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "chevron-left": '<polyline points="15 18 9 12 15 6"/>',
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "check-square": '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "terminal": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "trash-2": '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "sun": '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>',
    "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
}


def render_lucide_icon(name: str, color: Optional[str] = None, size: int = 16, stroke_width: float = 1.5) -> QPixmap:
    """
    Renders an Apple SF-style vector icon matching Lucide 1.5 stroke specs.
    Returns a crisp transparent QPixmap.
    """
    if color is None:
        color = theme.colors.labelPrimary
    inner = _LUCIDE_PATHS.get(name, _LUCIDE_PATHS["info"])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


# ── 2. Push Button (Default, Secondary, Destructive) ──────────────────────────

class MacOSButton(QPushButton):
    """
    Apple AppKit / SwiftUI Push Button.
    Variants:
      - DEFAULT: System Accent Blue filled, white text, subtle active press darkening.
      - SECONDARY: Translucent control background, 1px separator border, labelPrimary.
      - DESTRUCTIVE: System Red tinted/filled for irreversible actions.
    States: Rest, Hover, Pressed, Focused (3px accent ring), Disabled.
    """
    class Variant(Enum):
        DEFAULT = "default"
        SECONDARY = "secondary"
        DESTRUCTIVE = "destructive"

    def __init__(
        self,
        text: str = "",
        variant: Union[Variant, str] = Variant.SECONDARY,
        icon_name: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        if isinstance(variant, str):
            self._variant = self.Variant(variant.lower())
        else:
            self._variant = variant

        self._icon_name = icon_name
        self._scale_factor: float = 1.0
        self._press_anim: Optional[QPropertyAnimation] = None

        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.font(theme.typography.headline))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, val: float) -> None:
        self._scale_factor = val
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if not motion.is_reduced_motion() and self.isEnabled():
            if self._press_anim and self._press_anim.state() == QPropertyAnimation.State.Running:
                self._press_anim.stop()
            self._scale_factor = 0.98
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if not motion.is_reduced_motion() and self.isEnabled():
            self._press_anim = create_spring_animation(
                self, b"scale_factor", self._scale_factor, 1.0, spring=SpringPresets.snappy
            )
            self._press_anim.start()
        else:
            self._scale_factor = 1.0
            self.update()

    def leaveEvent(self, event: QEvent):
        super().leaveEvent(event)
        if abs(self._scale_factor - 1.0) > 1e-4:
            if not motion.is_reduced_motion() and self.isEnabled():
                self._press_anim = create_spring_animation(
                    self, b"scale_factor", self._scale_factor, 1.0, spring=SpringPresets.snappy
                )
                self._press_anim.start()
            else:
                self._scale_factor = 1.0
                self.update()

    def set_variant(self, variant: Union[Variant, str]) -> None:
        if isinstance(variant, str):
            self._variant = self.Variant(variant.lower())
        else:
            self._variant = variant
        self._apply_style()

    def set_icon_name(self, name: Optional[str]) -> None:
        self._icon_name = name
        self._apply_style()

    def _apply_style(self) -> None:
        accent = theme.accent_color
        r = theme.radii.sm

        # Icon rendering if present
        if self._icon_name:
            icon_color = "#FFFFFF" if self._variant == self.Variant.DEFAULT else theme.colors.labelPrimary
            pix = render_lucide_icon(self._icon_name, color=icon_color, size=14)
            self.setIcon(QIcon(pix))
            self.setIconSize(QSize(14, 14))

        if self._variant == self.Variant.DEFAULT:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {accent};
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: {r}px;
                    padding: 0 12px;
                    font-family: -apple-system, Inter, sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {theme.accent_color_hover};
                }}
                QPushButton:pressed {{
                    background-color: {theme.accent_color_pressed};
                }}
                QPushButton:focus {{
                    outline: none;
                    border: 1.5px solid #FFFFFF;
                }}
                QPushButton:disabled {{
                    background-color: {theme.colors.controlBackground};
                    color: {theme.colors.labelQuaternary};
                    border: 1px solid {theme.colors.separator};
                }}
            """)
        elif self._variant == self.Variant.DESTRUCTIVE:
            red = theme.colors.systemRed
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 69, 58, 0.16);
                    color: {red};
                    border: 1px solid rgba(255, 69, 58, 0.36);
                    border-radius: {r}px;
                    padding: 0 12px;
                    font-family: -apple-system, Inter, sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {red};
                    color: #FFFFFF;
                    border: 1px solid {red};
                }}
                QPushButton:pressed {{
                    background-color: #D70015;
                    color: #FFFFFF;
                }}
                QPushButton:focus {{
                    outline: none;
                    border: 1.5px solid {red};
                }}
                QPushButton:disabled {{
                    background-color: transparent;
                    color: {theme.colors.labelQuaternary};
                    border: 1px solid {theme.colors.separator};
                }}
            """)
        else:  # SECONDARY
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.colors.controlBackground};
                    color: {theme.colors.labelPrimary};
                    border: 1px solid {theme.colors.separator};
                    border-radius: {r}px;
                    padding: 0 12px;
                    font-family: -apple-system, Inter, sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {theme.colors.cardBackgroundHover};
                    border-color: rgba(255, 255, 255, 0.16);
                }}
                QPushButton:pressed {{
                    background-color: {theme.colors.controlBackgroundSecondary};
                }}
                QPushButton:focus {{
                    outline: none;
                    border: 1.5px solid {accent};
                }}
                QPushButton:disabled {{
                    background-color: {theme.colors.controlBackground};
                    color: {theme.colors.labelQuaternary};
                    border: 1px solid {theme.colors.separator};
                }}
            """)

    def paintEvent(self, event):
        if abs(self._scale_factor - 1.0) > 1e-4:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(self._scale_factor, self._scale_factor)
            painter.translate(-cx, -cy)

            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)

            if self.hasFocus() and self.isEnabled():
                focus_col = QColor(theme.accent_color if self._variant != self.Variant.DESTRUCTIVE else theme.colors.systemRed)
                focus_col.setAlpha(80)
                pen = QPen(focus_col, 2.5)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = theme.radii.sm
                painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), r, r)
            painter.end()
            return

        super().paintEvent(event)
        # Render signature 3px diffused outer focus halo when focused
        if self.hasFocus() and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            focus_col = QColor(theme.accent_color if self._variant != self.Variant.DESTRUCTIVE else theme.colors.systemRed)
            focus_col.setAlpha(80)
            pen = QPen(focus_col, 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = theme.radii.sm
            painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), r, r)
            painter.end()


# ── 3. Segmented Control with Sliding Selection Pill ──────────────────────────

class _SlidingPill(QWidget):
    """The elevated white/card sliding capsule behind the active segment."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        r = max(2, theme.radii.sm - 1)
        bg = "#3A3A3C" if theme.is_dark else "#FFFFFF"
        border = "rgba(255, 255, 255, 0.08)" if theme.is_dark else "rgba(0, 0, 0, 0.06)"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {r}px;
            }}
        """)


class MacOSSegmentedControl(QWidget):
    """
    Apple NSSegmentedControl / SwiftUI Segmented Picker.
    Features:
      - Sliding animated selection pill (180ms OutCubic)
      - Translucent track with subtle 1px border
      - Keyboard navigation (Left / Right arrow keys)
      - All states: Rest, Hover, Selected, Focused, Disabled.
    """
    current_changed = pyqtSignal(int, str)

    def __init__(self, items: Optional[List[str]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items = items or ["Item 1", "Item 2"]
        self._current_index = 0

        self.setFixedHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._track = QFrame(self)
        self._pill = _SlidingPill(self._track)

        self._buttons: List[QPushButton] = []
        self._track_layout = QHBoxLayout(self._track)
        self._track_layout.setContentsMargins(2, 2, 2, 2)
        self._track_layout.setSpacing(1)

        self._pill_anim = QPropertyAnimation(self._pill, b"geometry")
        self._pill_anim.setDuration(180)
        self._pill_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._rebuild_items()
        self._apply_track_style()
        theme.theme_changed.connect(self._apply_track_style)

    def _apply_track_style(self):
        r = theme.radii.sm + 1
        track_bg = "rgba(0, 0, 0, 0.22)" if theme.is_dark else "rgba(0, 0, 0, 0.06)"
        self._track.setStyleSheet(f"""
            QFrame {{
                background-color: {track_bg};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)
        self._update_button_colors()

    def _rebuild_items(self):
        while self._track_layout.count():
            item = self._track_layout.takeAt(0)
            if item.widget() and item.widget() != self._pill:
                item.widget().deleteLater()
        self._buttons.clear()

        for idx, label in enumerate(self._items):
            btn = QPushButton(label, self._track)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(theme.font(theme.typography.callout, QFont.Weight.Medium))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, i=idx: self.set_current_index(i))
            self._track_layout.addWidget(btn)
            self._buttons.append(btn)

        self._update_button_colors()
        QTimer.singleShot(10, self._sync_pill_instant)

    def set_items(self, items: List[str]) -> None:
        self._items = items
        self._current_index = min(self._current_index, max(0, len(items) - 1))
        self._rebuild_items()

    def current_index(self) -> int:
        return self._current_index

    def current_text(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return ""

    def set_current_index(self, index: int) -> None:
        if not (0 <= index < len(self._buttons)):
            return
        if self._current_index != index:
            self._current_index = index
            self._animate_pill_to_index(index)
            self._update_button_colors()
            self.current_changed.emit(index, self._items[index])

    def _animate_pill_to_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            target_btn = self._buttons[index]
            target_rect = target_btn.geometry()
            self._pill_anim.stop()
            self._pill_anim.setStartValue(self._pill.geometry())
            self._pill_anim.setEndValue(target_rect)
            self._pill_anim.start()

    def _sync_pill_instant(self) -> None:
        if 0 <= self._current_index < len(self._buttons):
            target_btn = self._buttons[self._current_index]
            self._pill.setGeometry(target_btn.geometry())
            self._pill.show()

    def _update_button_colors(self) -> None:
        for idx, btn in enumerate(self._buttons):
            is_active = (idx == self._current_index)
            col = theme.colors.labelPrimary if is_active else theme.colors.labelSecondary
            weight = "bold" if is_active else "normal"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {col};
                    border: none;
                    border-radius: {theme.radii.sm - 1}px;
                    padding: 0 8px;
                    font-weight: {weight};
                }}
                QPushButton:hover {{
                    color: {theme.colors.labelPrimary};
                }}
            """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._track.setGeometry(self.rect())
        self._sync_pill_instant()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self.set_current_index(max(0, self._current_index - 1))
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self.set_current_index(min(len(self._buttons) - 1, self._current_index + 1))
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus() and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            focus_col = QColor(theme.accent_color)
            focus_col.setAlpha(70)
            painter.setPen(QPen(focus_col, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = theme.radii.sm + 1
            painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), r, r)
            painter.end()


# ── 4. Toggle Switch (iOS / macOS 38x22) ──────────────────────────────────────

class MacOSToggle(QWidget):
    """
    Apple HIG Toggle Switch (Exact 38x22 dimensions).
    Features:
      - 38px width, 22px height pill track
      - 18x18px circular white thumb
      - Tactile width expansion to 20px while pressed (authentic Apple physics)
      - Smooth 150ms OutCubic animation
      - Space key toggling with 3px focus ring
    """
    toggled = pyqtSignal(bool)

    WIDTH = 38
    HEIGHT = 22
    THUMB_SIZE = 18

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._checked = checked
        self._thumb_x = 18.0 if checked else 2.0
        self._is_pressed = False

        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._anim = QPropertyAnimation(self, b"thumb_x")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        theme.theme_changed.connect(self.update)

    @pyqtProperty(float)
    def thumb_x(self) -> float:
        return self._thumb_x

    @thumb_x.setter
    def thumb_x(self, val: float):
        self._thumb_x = val
        self.update()

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool, animated: bool = True) -> None:
        if self._checked == checked:
            return
        self._checked = checked
        target_x = 18.0 if checked else 2.0
        if animated:
            self._anim.stop()
            self._anim.setStartValue(self._thumb_x)
            self._anim.setEndValue(target_x)
            self._anim.start()
        else:
            self.thumb_x = target_x
        self.toggled.emit(checked)

    def toggle(self) -> None:
        self.set_checked(not self._checked)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._is_pressed = True
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._is_pressed = False
            self.toggle()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return) and self.isEnabled():
            self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Track Color
        if not self.isEnabled():
            track_col = QColor(theme.colors.controlBackgroundSecondary)
        elif self._checked:
            track_col = QColor(theme.accent_color)
        else:
            track_col = QColor("#3A3A3C" if theme.is_dark else "#E5E5EA")

        # Draw pill track
        track_radius = self.HEIGHT / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_col))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT), track_radius, track_radius)

        # 2. Thumb Geometry with Apple Press Elasticity
        thumb_w = 20.0 if self._is_pressed else 18.0
        thumb_h = 18.0
        thumb_y = 2.0

        # Draw subtle thumb drop shadow
        shadow_rect = QRectF(self._thumb_x, thumb_y + 1, thumb_w, thumb_h)
        painter.setBrush(QBrush(QColor(0, 0, 0, 45)))
        painter.drawRoundedRect(shadow_rect, 9, 9)

        # Draw pure white thumb
        thumb_col = QColor("#FFFFFF") if self.isEnabled() else QColor("#A1A1A6")
        painter.setBrush(QBrush(thumb_col))
        painter.drawRoundedRect(QRectF(self._thumb_x, thumb_y, thumb_w, thumb_h), 9, 9)

        # 3. Focus Ring
        if self.hasFocus() and self.isEnabled():
            focus_col = QColor(theme.accent_color)
            focus_col.setAlpha(80)
            painter.setPen(QPen(focus_col, 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(-1, -1, self.WIDTH + 2, self.HEIGHT + 2), track_radius + 1, track_radius + 1)

        painter.end()


# ── 5. Text Field with 3px Focus Ring ─────────────────────────────────────────

class MacOSTextField(QLineEdit):
    """
    Apple AppKit NSTextField / SwiftUI TextField.
    Features:
      - 28px height, 6px radius (sm)
      - Rest: subtle 1px border
      - Focus: 3px diffused accent focus halo
      - All states: Rest, Hover, Pressed, Focused, Disabled.
    """
    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(28)
        self.setFont(theme.font(theme.typography.body))
        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        r = theme.radii.sm
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {theme.colors.controlBackground};
                color: {theme.colors.labelPrimary};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
                padding: 0 8px;
                font-family: -apple-system, Inter, sans-serif;
            }}
            QLineEdit:hover {{
                border-color: rgba(255, 255, 255, 0.18);
            }}
            QLineEdit:focus {{
                border: 1.5px solid {theme.accent_color};
                background-color: {theme.colors.windowBackground};
            }}
            QLineEdit:disabled {{
                color: {theme.colors.labelQuaternary};
                background-color: {theme.colors.controlBackgroundSecondary};
                border-color: {theme.colors.separator};
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus() and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            focus_col = QColor(theme.accent_color)
            focus_col.setAlpha(70)
            painter.setPen(QPen(focus_col, 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = theme.radii.sm
            painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), r, r)
            painter.end()


# ── 6. Search Field with Magnifier & Clear Button ─────────────────────────────

class MacOSSearchField(QFrame):
    """
    Apple NSSearchField / SwiftUI Searchable Field.
    Features:
      - 28px height, 6px radius
      - Lucide 1.5 stroke magnifier icon on left
      - Embedded borderless QLineEdit
      - Auto-revealing clear button (✕) when text is non-empty
      - 3px accent focus ring surrounding the outer container
    """
    text_changed = pyqtSignal(str)
    return_pressed = pyqtSignal()
    cleared = pyqtSignal()

    def __init__(self, placeholder: str = "Search...", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._is_focused = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 6, 0)
        lay.setSpacing(6)

        # Magnifier Icon
        self._icon_lbl = QLabel(self)
        self._icon_lbl.setFixedSize(14, 14)
        lay.addWidget(self._icon_lbl)

        # Inner Input
        self.input = QLineEdit(self)
        self.input.setPlaceholderText(placeholder)
        self.input.setFont(theme.font(theme.typography.body))
        self.input.setStyleSheet("background: transparent; border: none; color: inherit;")
        self.input.textChanged.connect(self._on_text_changed)
        self.input.returnPressed.connect(self.return_pressed.emit)
        self.input.installEventFilter(self)
        lay.addWidget(self.input, stretch=1)

        # Clear Button
        self.btn_clear = QPushButton("✕", self)
        self.btn_clear.setFixedSize(14, 14)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setToolTip("Clear text")
        self.btn_clear.hide()
        self.btn_clear.clicked.connect(self.clear)
        lay.addWidget(self.btn_clear)

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        r = theme.radii.sm
        pix = render_lucide_icon("search", color=theme.colors.labelTertiary, size=14)
        self._icon_lbl.setPixmap(pix)

        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.labelTertiary};
                color: {theme.colors.windowBackground};
                border: none;
                border-radius: 7px;
                font-size: 8px;
                font-weight: bold;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.labelSecondary};
            }}
        """)

        border_col = theme.accent_color if self._is_focused else theme.colors.separator
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                color: {theme.colors.labelPrimary};
                border: 1px solid {border_col};
                border-radius: {r}px;
            }}
            QFrame:hover {{
                border-color: rgba(255, 255, 255, 0.18);
            }}
        """)

    def _on_text_changed(self, text: str):
        self.btn_clear.setVisible(bool(text))
        self.text_changed.emit(text)

    def text(self) -> str:
        return self.input.text()

    def set_text(self, text: str) -> None:
        self.input.setText(text)

    def clear(self) -> None:
        self.input.clear()
        self.input.setFocus()
        self.cleared.emit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched == self.input:
            if event.type() == QEvent.Type.FocusIn:
                self._is_focused = True
                self._apply_style()
                self.update()
            elif event.type() == QEvent.Type.FocusOut:
                self._is_focused = False
                self._apply_style()
                self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._is_focused and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            focus_col = QColor(theme.accent_color)
            focus_col.setAlpha(70)
            painter.setPen(QPen(focus_col, 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = theme.radii.sm
            painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), r, r)
            painter.end()


# ── 7. Popover with Directional Arrow ─────────────────────────────────────────

class MacOSPopover(QWidget):
    """
    Apple NSPopover / SwiftUI .popover().
    Features:
      - Directional triangular arrow notch pointing to anchor
      - 10px continuous squircle corner radius
      - Layered elevation shadow + translucent vibrancy fallback
      - Auto-dismisses on outside click or Escape
    """
    ARROW_SIZE = 9
    CORNER_RADIUS = 10

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._direction = "bottom"  # Arrow points: top | bottom | left | right
        self._content_widget: Optional[QWidget] = None
        self._scale_factor: float = 1.0
        self._popover_opacity: float = 1.0
        self._target_rect: QRect = QRect()
        self._anchor_pt: QPoint = QPoint()
        self._anim_scale: Optional[QPropertyAnimation] = None
        self._anim_opacity: Optional[QPropertyAnimation] = None

        self._container = QWidget(self)
        self.content_lay = QVBoxLayout(self._container)
        self.content_lay.setContentsMargins(12, 12, 12, 12)
        self.content_lay.setSpacing(theme.spacing.sm)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, s: float) -> None:
        self._scale_factor = s
        if self._target_rect.isValid() and abs(s - 1.0) > 1e-4:
            tw, th = self._target_rect.width(), self._target_rect.height()
            w = max(10, int(tw * s))
            h = max(10, int(th * s))
            if self._direction == "bottom":
                x = self._anchor_pt.x() - w // 2
                y = self._anchor_pt.y()
            elif self._direction == "top":
                x = self._anchor_pt.x() - w // 2
                y = self._anchor_pt.y() - h
            elif self._direction == "right":
                x = self._anchor_pt.x()
                y = self._anchor_pt.y() - h // 2
            else:
                x = self._anchor_pt.x() - w
                y = self._anchor_pt.y() - h // 2
            self.setGeometry(x, y, w, h)
        elif self._target_rect.isValid():
            self.setGeometry(self._target_rect)
        self.update()

    @pyqtProperty(float)
    def popover_opacity(self) -> float:
        return self._popover_opacity

    @popover_opacity.setter
    def popover_opacity(self, val: float) -> None:
        self._popover_opacity = max(0.0, min(1.0, val))
        self.update()

    def set_content(self, widget: QWidget) -> None:
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._content_widget = widget
        self.content_lay.addWidget(widget)
        self.adjustSize()

    def show_at_widget(self, anchor: QWidget, direction: str = "bottom") -> None:
        self._direction = direction
        self.adjustSize()

        anchor_global = anchor.mapToGlobal(QPoint(0, 0))
        aw, ah = anchor.width(), anchor.height()
        pw, ph = self.sizeHint().width(), self.sizeHint().height()

        if direction == "bottom":
            x = anchor_global.x() + (aw - pw) // 2
            y = anchor_global.y() + ah + 4
            self._anchor_pt = QPoint(anchor_global.x() + aw // 2, anchor_global.y() + ah + 4)
        elif direction == "top":
            x = anchor_global.x() + (aw - pw) // 2
            y = anchor_global.y() - ph - 4
            self._anchor_pt = QPoint(anchor_global.x() + aw // 2, anchor_global.y() - 4)
        elif direction == "left":
            x = anchor_global.x() - pw - 4
            y = anchor_global.y() + (ah - ph) // 2
            self._anchor_pt = QPoint(anchor_global.x() - 4, anchor_global.y() + ah // 2)
        else:  # right
            x = anchor_global.x() + aw + 4
            y = anchor_global.y() + (ah - ph) // 2
            self._anchor_pt = QPoint(anchor_global.x() + aw + 4, anchor_global.y() + ah // 2)

        self._target_rect = QRect(x, y, pw, ph)

        if motion.is_reduced_motion():
            self._scale_factor = 1.0
            self._popover_opacity = 0.0
            self.setGeometry(self._target_rect)
            self.show()
            self._anim_opacity = create_spring_animation(self, b"popover_opacity", 0.0, 1.0, duration_ms=100)
            self._anim_opacity.start()
        else:
            self._scale_factor = 0.96
            self._popover_opacity = 0.0
            # Initialize scaled start geometry
            self.scale_factor = 0.96
            self.show()
            self._anim_scale = create_spring_animation(self, b"scale_factor", 0.96, 1.0, spring=SpringPresets.snappy)
            self._anim_opacity = create_spring_animation(self, b"popover_opacity", 0.0, 1.0, spring=SpringPresets.snappy)
            self._anim_scale.start()
            self._anim_opacity.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position content container inside bubble bounds accounting for arrow notch
        a = self.ARROW_SIZE
        if self._direction == "bottom":
            self._container.setGeometry(2, a + 2, self.width() - 4, self.height() - a - 4)
        elif self._direction == "top":
            self._container.setGeometry(2, 2, self.width() - 4, self.height() - a - 4)
        elif self._direction == "right":
            self._container.setGeometry(a + 2, 2, self.width() - a - 4, self.height() - 4)
        else:
            self._container.setGeometry(2, 2, self.width() - a - 4, self.height() - 4)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._popover_opacity)

        path = QPainterPath()
        w, h = float(self.width()), float(self.height())
        a = float(self.ARROW_SIZE)
        r = float(self.CORNER_RADIUS)

        # Build contiguous bubble + arrow geometry
        if self._direction == "bottom":
            rect = QRectF(1.5, a + 1.5, w - 3.0, h - a - 3.0)
            path.addRoundedRect(rect, r, r)
            # Arrow pointing up toward anchor
            mid = w / 2.0
            arrow = QPainterPath()
            arrow.moveTo(mid - a, a + 1.5)
            arrow.lineTo(mid, 1.5)
            arrow.lineTo(mid + a, a + 1.5)
            arrow.closeSubpath()
            path = path.united(arrow)
        else:
            rect = QRectF(1.5, 1.5, w - 3.0, h - a - 3.0)
            path.addRoundedRect(rect, r, r)
            mid = w / 2.0
            arrow = QPainterPath()
            arrow.moveTo(mid - a, h - a - 1.5)
            arrow.lineTo(mid, h - 1.5)
            arrow.lineTo(mid + a, h - a - 1.5)
            arrow.closeSubpath()
            path = path.united(arrow)

        bg_col = QColor(theme.colors.windowBackground)
        bg_col.setAlpha(245)
        painter.setBrush(QBrush(bg_col))
        painter.setPen(QPen(QColor(theme.colors.separator), 1.0))
        painter.drawPath(path)
        painter.end()


# ── 8. Context Menu with 6px Radius & Shortcut Column ─────────────────────────

class MacOSContextMenu(QMenu):
    """
    Apple AppKit NSMenu / SwiftUI ContextMenu.
    Features:
      - 6px continuous corner radius (sm)
      - Translucent window background with 1px separator border
      - Dedicated right-aligned keyboard shortcut column
      - Lucide 1.5 stroke icons
      - Native macOS selection highlight on hover
    """
    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(title, parent)
        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        r = theme.radii.sm
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
                padding: 4px;
                color: {theme.colors.labelPrimary};
                font-family: -apple-system, Inter, sans-serif;
            }}
            QMenu::item {{
                padding: 5px 24px 5px 10px;
                border-radius: 4px;
                margin: 1px 2px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background-color: {theme.accent_color};
                color: #FFFFFF;
            }}
            QMenu::item:disabled {{
                color: {theme.colors.labelQuaternary};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {theme.colors.separator};
                margin: 4px 6px;
            }}
        """)

    def add_action_item(
        self,
        label: str,
        callback: Optional[Callable] = None,
        shortcut: Optional[str] = None,
        icon_name: Optional[str] = None,
        destructive: bool = False,
        enabled: bool = True,
    ):
        """Adds a context menu item with Lucide icon and keyboard shortcut text."""
        icon = QIcon(render_lucide_icon(icon_name, size=14)) if icon_name else QIcon()
        display_text = f"{label}\t{shortcut}" if shortcut else label
        action = self.addAction(icon, display_text)
        action.setEnabled(enabled)
        if callback:
            action.triggered.connect(callback)
        return action


# ── 9. Sidebar List with Selection Highlight & Lucide Icons ───────────────────

class MacOSSidebarItem(QPushButton):
    """Single row inside a macOS Source List."""
    def __init__(
        self,
        item_id: str,
        label: str,
        icon_name: str = "folder",
        badge_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.item_id = item_id
        self._label = label
        self._icon_name = icon_name
        self._badge_text = badge_text
        self._is_active = False

        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        self._icon_lbl = QLabel(self)
        self._icon_lbl.setFixedSize(16, 16)
        lay.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(label, self)
        self._title_lbl.setFont(theme.font(theme.typography.body))
        lay.addWidget(self._title_lbl, stretch=1)

        self._badge_lbl = QLabel(badge_text, self)
        self._badge_lbl.setFont(theme.font(theme.typography.caption_2))
        self._badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge_lbl.setFixedHeight(16)
        self._badge_lbl.setVisible(bool(badge_text))
        lay.addWidget(self._badge_lbl)

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._apply_style()

    def set_badge(self, text: str) -> None:
        self._badge_text = text
        self._badge_lbl.setText(text)
        self._badge_lbl.setVisible(bool(text))

    def _apply_style(self) -> None:
        r = theme.radii.sm
        if self._is_active:
            bg = theme.accent_color
            text_col = "#FFFFFF"
            icon_col = "#FFFFFF"
            badge_bg = "rgba(255, 255, 255, 0.25)"
            badge_text = "#FFFFFF"
        else:
            bg = "transparent"
            text_col = theme.colors.labelPrimary
            icon_col = theme.colors.labelSecondary
            badge_bg = theme.colors.controlBackgroundSecondary
            badge_text = theme.colors.labelSecondary

        self._icon_lbl.setPixmap(render_lucide_icon(self._icon_name, color=icon_col, size=16))
        self._title_lbl.setStyleSheet(f"color: {text_col}; background: transparent; border: none;")

        self._badge_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {badge_bg};
                color: {badge_text};
                border-radius: 8px;
                padding: 0 6px;
                border: none;
            }}
        """)

        hover_bg = theme.colors.cardBackgroundHover if not self._is_active else theme.accent_color_hover
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: {r}px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
        """)


class MacOSSidebarList(QWidget):
    """
    Apple HIG Source List Sidebar Component.
    Manages sections, items, and active pill highlights.
    """
    item_selected = pyqtSignal(str, str)  # id, label

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: List[MacOSSidebarItem] = []
        self._selected_id: Optional[str] = None

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(2)

    def add_section_header(self, title: str) -> QLabel:
        hdr = QLabel(title.upper(), self)
        hdr.setFont(theme.font(theme.typography.caption_1, QFont.Weight.DemiBold))
        hdr.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.labelTertiary};
                padding: 10px 8px 4px 8px;
                background: transparent;
                border: none;
            }}
        """)
        self._lay.addWidget(hdr)
        return hdr

    def add_item(self, item_id: str, label: str, icon_name: str = "folder", badge: str = "") -> MacOSSidebarItem:
        item = MacOSSidebarItem(item_id, label, icon_name=icon_name, badge_text=badge, parent=self)
        item.clicked.connect(lambda: self.select_item(item_id))
        self._lay.addWidget(item)
        self._items.append(item)
        if len(self._items) == 1:
            self.select_item(item_id)
        return item

    def select_item(self, item_id: str) -> None:
        self._selected_id = item_id
        selected_label = ""
        for item in self._items:
            active = (item.item_id == item_id)
            item.set_active(active)
            if active:
                selected_label = item._label
        self.item_selected.emit(item_id, selected_label)

    def selected_id(self) -> Optional[str]:
        return self._selected_id


# ── 10. Toast / Notification Banner ───────────────────────────────────────────

class MacOSToast(QFrame):
    """
    macOS Notification Center Banner.
    Features:
      - 10px continuous corner radius, 1px highlight border, shadow
      - Slide-in from top-right (250ms OutCubic)
      - Auto-dismisses with pause on hover
      - Variants: Info, Success, Warning, Error
    """
    class Variant(Enum):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        ERROR = "error"

    def __init__(
        self,
        title: str,
        message: str,
        variant: Union[Variant, str] = Variant.INFO,
        duration_ms: int = 4000,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(320)
        self._duration_ms = duration_ms

        if isinstance(variant, str):
            self._variant = self.Variant(variant.lower())
        else:
            self._variant = variant

        # Outer Frame Style
        r = theme.radii.md
        bg = theme.colors.windowBackground
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)

        # Multi-layer elevation shadow
        self.setGraphicsEffect(theme.shadow_effect(theme.elevation.medium))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # Status Icon
        icon_name = "info"
        icon_col = theme.accent_color
        if self._variant == self.Variant.SUCCESS:
            icon_name = "check"
            icon_col = theme.colors.systemGreen
        elif self._variant == self.Variant.WARNING:
            icon_name = "alert-triangle"
            icon_col = theme.colors.systemYellow
        elif self._variant == self.Variant.ERROR:
            icon_name = "alert-circle"
            icon_col = theme.colors.systemRed

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setPixmap(render_lucide_icon(icon_name, color=icon_col, size=20))
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.icon_lbl)

        # Text column
        v_lay = QVBoxLayout()
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(2)

        self.title_lbl = QLabel(title, self)
        self.title_lbl.setFont(theme.font(theme.typography.headline))
        self.title_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        v_lay.addWidget(self.title_lbl)

        self.msg_lbl = QLabel(message, self)
        self.msg_lbl.setFont(theme.font(theme.typography.callout))
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
        v_lay.addWidget(self.msg_lbl)

        lay.addLayout(v_lay, stretch=1)

        # Close Button
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(16, 16)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                color: {theme.colors.labelTertiary};
                background: transparent;
                border: none;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {theme.colors.labelPrimary};
            }}
        """)
        btn_close.clicked.connect(self.dismiss)
        lay.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignTop)

        # Timer
        self._timer = QTimer(self)
        self._timer.setInterval(self._duration_ms)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start()

    def enterEvent(self, event: QEnterEvent):
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent):
        self._timer.start()
        super().leaveEvent(event)

    def dismiss(self):
        self._timer.stop()
        self.hide()
        self.deleteLater()

    @classmethod
    def show_toast(
        cls,
        parent: QWidget,
        title: str,
        message: str,
        variant: Union[Variant, str] = Variant.INFO,
        duration_ms: int = 4000,
    ) -> MacOSToast:
        toast = cls(title, message, variant=variant, duration_ms=duration_ms, parent=parent)
        pw = parent.width()
        x = max(10, pw - toast.width() - 20)
        y = 56  # Below 48px unified toolbar
        toast.move(x, y)
        toast.show()
        return toast


# ── 11. Sheet Modal ───────────────────────────────────────────────────────────

class MacOSSheetModal(QWidget):
    """
    Apple AppKit beginSheet: / SwiftUI .sheet().
    Features:
      - Translucent backdrop scrim (rgba(0,0,0,0.45))
      - Top-anchored sheet panel with 14px rounded bottom corners
      - Smooth 250ms OutCubic slide-down animation
      - Cancel / Done action footer
    """
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, title: str = "Sheet", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title = title
        self._dim_opacity: float = 0.0
        self._blur_effect: Optional[QGraphicsBlurEffect] = None
        self._blurred_target: Optional[QWidget] = None

        # Full-window Scrim Backdrop
        self.setStyleSheet("background: transparent;")
        self.hide()

        # Sheet Card
        self.card = QFrame(self)
        self.card.setFixedWidth(460)
        r = theme.radii.lg
        bg = theme.colors.windowBackground
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-left: 1px solid {theme.colors.separator};
                border-right: 1px solid {theme.colors.separator};
                border-bottom: 1px solid {theme.colors.separator};
                border-bottom-left-radius: {r}px;
                border-bottom-right-radius: {r}px;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
        """)
        self.card.setGraphicsEffect(theme.shadow_effect(theme.elevation.high))

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(20, 16, 20, 16)
        card_lay.setSpacing(12)

        # Header with Title
        hdr = QHBoxLayout()
        self.title_lbl = QLabel(title, self.card)
        self.title_lbl.setFont(theme.font(theme.typography.title_3))
        self.title_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        hdr.addWidget(self.title_lbl)
        hdr.addStretch()

        btn_x = QPushButton("✕", self.card)
        btn_x.setFixedSize(18, 18)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setStyleSheet(f"""
            QPushButton {{
                color: {theme.colors.labelTertiary};
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{ color: {theme.colors.labelPrimary}; }}
        """)
        btn_x.clicked.connect(self.dismiss)
        hdr.addWidget(btn_x)
        card_lay.addLayout(hdr)

        # Content Container
        self.content_host = QWidget(self.card)
        self.content_host.setStyleSheet("background: transparent; border: none;")
        self.content_lay = QVBoxLayout(self.content_host)
        self.content_lay.setContentsMargins(0, 8, 0, 8)
        self.content_lay.setSpacing(8)
        card_lay.addWidget(self.content_host, stretch=1)

        # Action Footer
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_cancel = MacOSButton("Cancel", variant="secondary", parent=self.card)
        self.btn_cancel.clicked.connect(self.dismiss)
        footer.addWidget(self.btn_cancel)

        self.btn_done = MacOSButton("Done", variant="default", parent=self.card)
        self.btn_done.clicked.connect(self.accept)
        footer.addWidget(self.btn_done)

        card_lay.addLayout(footer)

        self._anim_pos: Optional[QPropertyAnimation] = None
        self._anim_dim: Optional[QPropertyAnimation] = None

    @pyqtProperty(float)
    def dim_opacity(self) -> float:
        return self._dim_opacity

    @dim_opacity.setter
    def dim_opacity(self, val: float) -> None:
        self._dim_opacity = max(0.0, min(1.0, val))
        self.update()

    def set_content_widget(self, widget: QWidget) -> None:
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.content_lay.addWidget(widget)

    def open_sheet(self) -> None:
        p = self.parentWidget()
        if not p:
            return
        self.setGeometry(0, 48, p.width(), p.height() - 48)  # Under unified toolbar
        self.show()

        cw = self.card.width()
        x = (self.width() - cw) // 2
        card_h = self.card.sizeHint().height()
        self.card.resize(cw, card_h)

        # Apply subtle Apple blur to parent window content if supported
        if not motion.is_reduced_motion():
            target = getattr(p, "content_area", None) or getattr(p, "central_widget", None)
            if target and target != self:
                self._blurred_target = target
                self._blur_effect = QGraphicsBlurEffect(self)
                self._blur_effect.setBlurRadius(8.0)
                target.setGraphicsEffect(self._blur_effect)

        # Slide down & dim
        if motion.is_reduced_motion():
            self.card.move(x, 0)
            self._dim_opacity = 0.0
            self._anim_dim = create_spring_animation(self, b"dim_opacity", 0.0, 1.0, duration_ms=100)
            self._anim_dim.start()
        else:
            self._anim_pos = create_spring_animation(self.card, b"pos", QPoint(x, -card_h), QPoint(x, 0), spring=SpringPresets.smooth)
            self._anim_dim = create_spring_animation(self, b"dim_opacity", 0.0, 1.0, spring=SpringPresets.smooth)
            self._anim_pos.start()
            self._anim_dim.start()

    def accept(self):
        self.accepted.emit()
        self.dismiss()

    def dismiss(self):
        cw = self.card.width()
        x = (self.width() - cw) // 2
        card_h = self.card.height()

        if motion.is_reduced_motion():
            self._anim_dim = create_spring_animation(self, b"dim_opacity", self._dim_opacity, 0.0, duration_ms=100)
            self._anim_dim.finished.connect(self._on_dismiss_finished)
            self._anim_dim.start()
        else:
            self._anim_pos = create_spring_animation(self.card, b"pos", QPoint(x, 0), QPoint(x, -card_h), spring=SpringPresets.smooth)
            self._anim_dim = create_spring_animation(self, b"dim_opacity", self._dim_opacity, 0.0, spring=SpringPresets.smooth)
            self._anim_pos.finished.connect(self._on_dismiss_finished)
            self._anim_pos.start()
            self._anim_dim.start()

    def _on_dismiss_finished(self):
        if self._anim_pos:
            try:
                self._anim_pos.finished.disconnect(self._on_dismiss_finished)
            except Exception:
                pass
        if self._anim_dim:
            try:
                self._anim_dim.finished.disconnect(self._on_dismiss_finished)
            except Exception:
                pass

        if self._blurred_target and self._blur_effect:
            self._blurred_target.setGraphicsEffect(None)
            self._blur_effect = None
            self._blurred_target = None

        self.hide()
        self.rejected.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        alpha = int(115 * self._dim_opacity)
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))
        painter.end()


# ── 12. Tooltip with 600ms Delay ──────────────────────────────────────────────

class MacOSTooltip(QFrame):
    """
    Apple HIG Tooltip with exact 600ms resting hover delay.
    """
    DELAY_MS = 600

    def __init__(self, text: str = ""):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        r = theme.radii.sm
        bg = "#252528" if theme.is_dark else "#FFFFFF"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                color: {theme.colors.labelPrimary};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
                padding: 4px 8px;
            }}
        """)
        self.setGraphicsEffect(theme.shadow_effect(theme.elevation.low))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        self.lbl = QLabel(text, self)
        self.lbl.setFont(theme.font(theme.typography.caption_1))
        self.lbl.setStyleSheet("border: none; background: transparent; color: inherit;")
        lay.addWidget(self.lbl)

    @classmethod
    def attach(cls, target_widget: QWidget, text: str) -> _TooltipFilter:
        f = _TooltipFilter(target_widget, text)
        target_widget.installEventFilter(f)
        return f


class _TooltipFilter(QObject):
    def __init__(self, target: QWidget, text: str):
        super().__init__(target)
        self.target = target
        self.text = text
        self.tooltip: Optional[MacOSTooltip] = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(MacOSTooltip.DELAY_MS)
        self.timer.timeout.connect(self._show_tooltip)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched == self.target:
            if event.type() == QEvent.Type.Enter:
                self.timer.start()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
                self.timer.stop()
                if self.tooltip:
                    self.tooltip.hide()
        return super().eventFilter(watched, event)

    def _show_tooltip(self):
        if not self.tooltip:
            self.tooltip = MacOSTooltip(self.text)
        global_pos = self.target.mapToGlobal(QPoint(0, self.target.height() + 4))
        self.tooltip.move(global_pos)
        self.tooltip.show()


# ── 13. Thin Overlay Scrollbars (Appear on Scroll Only) ────────────────────────

class MacOSOverlayScrollBar(QScrollBar):
    """
    macOS NSScrollerStyleOverlay Dynamic Scrollbar.
    Floats over content with 0px reserved layout width.
    5px width at rest, expands to 8px on hover, auto-fades out after 800ms.
    """
    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Vertical, parent: Optional[QWidget] = None):
        super().__init__(orientation, parent)
        self._opacity = 0.0
        self._is_hovered = False

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(800)
        self._hide_timer.timeout.connect(self._fade_out)

        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(150)

        self.valueChanged.connect(self._on_scrolled)

    @pyqtProperty(float)
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, val: float):
        self._opacity = max(0.0, min(1.0, val))
        self.update()

    def _on_scrolled(self):
        self._show_active()

    def _show_active(self, animated: bool = True):
        self._hide_timer.stop()
        if not animated:
            self.opacity = 1.0
        elif self._opacity < 1.0:
            self._anim.stop()
            self._anim.setStartValue(self._opacity)
            self._anim.setEndValue(1.0)
            self._anim.start()
        self._hide_timer.start()

    def _fade_out(self):
        if not self._is_hovered:
            self._anim.stop()
            self._anim.setStartValue(self._opacity)
            self._anim.setEndValue(0.0)
            self._anim.start()

    def enterEvent(self, event: QEnterEvent):
        self._is_hovered = True
        self._show_active()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent):
        self._is_hovered = False
        self._hide_timer.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self._opacity <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pill thumb calculation
        val_range = self.maximum() - self.minimum()
        if val_range <= 0:
            return

        track_h = float(self.height())
        thumb_h = max(24.0, track_h * (float(self.pageStep()) / (val_range + self.pageStep())))
        thumb_y = (float(self.value() - self.minimum()) / val_range) * (track_h - thumb_h)

        thumb_w = 8.0 if self._is_hovered else 5.0
        thumb_x = float(self.width()) - thumb_w - 2.0

        thumb_col = QColor(255, 255, 255 if theme.is_dark else 0)
        thumb_col.setAlpha(int(100 * self._opacity if not self._is_hovered else 160 * self._opacity))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(thumb_col))
        r = thumb_w / 2.0
        painter.drawRoundedRect(QRectF(thumb_x, thumb_y, thumb_w, thumb_h), r, r)
        painter.end()


class MacOSScrollArea(QScrollArea):
    """
    QScrollArea wrapper equipped with native macOS thin overlay scrollbars.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")

        # Attach custom overlay scrollbar
        self._overlay_vbar = MacOSOverlayScrollBar(Qt.Orientation.Vertical, self)
        self.setVerticalScrollBar(self._overlay_vbar)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


# ── 14. Reorderable List with Spring Motion (MacOSReorderableList) ───────────

class MacOSReorderableItem(QFrame):
    """
    Individual card row inside a macOS Reorderable List.
    Equipped with vertical translation offset physics driven by SpringPresets.snappy.
    """
    move_up_requested = pyqtSignal(str)
    move_down_requested = pyqtSignal(str)

    def __init__(
        self,
        item_id: str,
        title: str,
        subtitle: str = "",
        badge: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.item_id = item_id
        self._title = title
        self._subtitle = subtitle
        self._badge = badge
        self._y_offset: float = 0.0
        self._base_y: int = 0

        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        r = theme.radii.sm
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
            QFrame:hover {{
                border-color: rgba(255, 255, 255, 0.20);
                background-color: {theme.colors.cardBackgroundHover};
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        # Drag grip icon
        self.grip_lbl = QLabel(self)
        self.grip_lbl.setPixmap(render_lucide_icon("sliders", color=theme.colors.labelTertiary, size=14))
        lay.addWidget(self.grip_lbl)

        # Title & Subtitle column
        t_box = QVBoxLayout()
        t_box.setContentsMargins(0, 4, 0, 4)
        t_box.setSpacing(1)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setFont(theme.font(theme.typography.headline))
        self.lbl_title.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        t_box.addWidget(self.lbl_title)

        if subtitle:
            self.lbl_sub = QLabel(subtitle, self)
            self.lbl_sub.setFont(theme.font(theme.typography.caption_1))
            self.lbl_sub.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
            t_box.addWidget(self.lbl_sub)

        lay.addLayout(t_box, stretch=1)

        # Optional Badge Pill
        if badge:
            badge_lbl = QLabel(badge, self)
            badge_lbl.setFont(theme.font(theme.typography.caption_2))
            badge_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {theme.colors.controlBackgroundSecondary};
                    color: {theme.colors.labelSecondary};
                    border-radius: 6px;
                    padding: 2px 6px;
                    border: none;
                }}
            """)
            lay.addWidget(badge_lbl)

        # Move Up / Down Buttons
        self.btn_up = QPushButton("▲", self)
        self.btn_up.setFixedSize(20, 20)
        self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.colors.labelSecondary};
                border: none;
                font-size: 9px;
            }}
            QPushButton:hover {{
                color: {theme.colors.labelPrimary};
                background-color: {theme.colors.controlBackgroundSecondary};
                border-radius: 4px;
            }}
        """)
        self.btn_up.clicked.connect(lambda: self.move_up_requested.emit(self.item_id))
        lay.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼", self)
        self.btn_down.setFixedSize(20, 20)
        self.btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.colors.labelSecondary};
                border: none;
                font-size: 9px;
            }}
            QPushButton:hover {{
                color: {theme.colors.labelPrimary};
                background-color: {theme.colors.controlBackgroundSecondary};
                border-radius: 4px;
            }}
        """)
        self.btn_down.clicked.connect(lambda: self.move_down_requested.emit(self.item_id))
        lay.addWidget(self.btn_down)

    @pyqtProperty(float)
    def y_offset(self) -> float:
        return self._y_offset

    @y_offset.setter
    def y_offset(self, val: float) -> None:
        self._y_offset = val
        self.move(self.x(), int(self._base_y + val))


class MacOSReorderableList(QWidget):
    """
    Apple SwiftUI-style dynamic reorderable list with snappy spring physics.
    Moving rows animate smoothly using SpringPresets.snappy (k=400, d=30).
    """
    reordered = pyqtSignal(list)  # list of item_ids in new order

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: List[MacOSReorderableItem] = []
        self._animating: bool = False
        self._anims: List[QPropertyAnimation] = []

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)

    def add_item(self, item_id: str, title: str, subtitle: str = "", badge: str = "") -> MacOSReorderableItem:
        item = MacOSReorderableItem(item_id, title, subtitle=subtitle, badge=badge, parent=self)
        item.move_up_requested.connect(self._on_item_move_up)
        item.move_down_requested.connect(self._on_item_move_down)
        self._lay.addWidget(item)
        self._items.append(item)
        return item

    def get_item_ids(self) -> List[str]:
        return [it.item_id for it in self._items]

    def _on_item_move_up(self, item_id: str) -> None:
        idx = self._find_index(item_id)
        if idx > 0:
            self.swap_indices(idx, idx - 1)

    def _on_item_move_down(self, item_id: str) -> None:
        idx = self._find_index(item_id)
        if 0 <= idx < len(self._items) - 1:
            self.swap_indices(idx, idx + 1)

    def _find_index(self, item_id: str) -> int:
        for i, it in enumerate(self._items):
            if it.item_id == item_id:
                return i
        return -1

    def swap_indices(self, idx_a: int, idx_b: int) -> None:
        if self._animating or idx_a == idx_b:
            return

        item_a = self._items[idx_a]
        item_b = self._items[idx_b]

        if motion.is_reduced_motion():
            # Instant swap without spring animation
            self._items[idx_a], self._items[idx_b] = self._items[idx_b], self._items[idx_a]
            self._refresh_layout()
            self.reordered.emit(self.get_item_ids())
            return

        self._animating = True
        item_a._base_y = item_a.y()
        item_b._base_y = item_b.y()

        dy = item_b._base_y - item_a._base_y

        anim_a = create_spring_animation(item_a, b"y_offset", 0.0, float(dy), spring=SpringPresets.snappy)
        anim_b = create_spring_animation(item_b, b"y_offset", 0.0, float(-dy), spring=SpringPresets.snappy)

        def _on_finished():
            self._anims.clear()
            self._items[idx_a], self._items[idx_b] = self._items[idx_b], self._items[idx_a]
            item_a.y_offset = 0.0
            item_b.y_offset = 0.0
            self._refresh_layout()
            self._animating = False
            self.reordered.emit(self.get_item_ids())

        anim_a.finished.connect(_on_finished)
        self._anims = [anim_a, anim_b]
        anim_a.start()
        anim_b.start()

    def _refresh_layout(self):
        for it in self._items:
            self._lay.removeWidget(it)
        for it in self._items:
            self._lay.addWidget(it)
