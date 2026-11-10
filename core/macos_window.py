"""
core/macos_window.py — Apple macOS Sequoia / Tahoe Native Window Shell & Chrome.

Senior Design Engineering Specification (Phase 2):
1. Frameless Window Frame:
   - Qt.WindowType.FramelessWindowHint with hardware-accelerated startSystemMove & startSystemResize.
   - Double-click unified toolbar to toggle Zoom/Maximize (macOS standard).
   - 1px inner highlight border (rgba(255, 255, 255, 0.06) dark mode / rgba(0, 0, 0, 0.08) light mode).
   - Native macOS window shadow depth via DwmExtendFrameIntoClientArea & layered elevation.
2. Custom Top-Left Traffic Lights:
   - 🔴 Close (#FF5F56), 🟡 Minimize (#FFBD2E), 🟢 Zoom (#27C93F).
   - 12x12px circular, 8px spacing, hover glyphs (×, −, +) visible only on hover.
3. Draggable Unified Toolbar with Centered Title:
   - 48px height, draggable background, centered typography in Inter Headline 13pt Semibold.
4. Translucent Sidebar with Mica/Acrylic & Vibrancy Fallback:
   - Windows 11 DWM backdrop (Acrylic/Mica) + rgba(26, 26, 29, 0.88) vibrancy fallback.
5. Resizable Sidebar (220px standard):
   - Min width: 180px, Max width: 320px.
   - Smooth collapse/expand animation via QPropertyAnimation (200ms OutCubic).
6. Layout: Sidebar (220px) + Full Content + Optional Inspector Panel (280px).
"""
from __future__ import annotations

import sys
import platform
import ctypes
from ctypes import c_int, byref, sizeof, Structure
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QCursor, QColor, QPainter, QPen, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSplitter
)

from core.theme_provider import theme


# ── Windows DWM Vibrancy & Frame Shadow ────────────────────────────────────────

class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]


def apply_macos_vibrancy(hwnd: int, is_dark: bool = True) -> bool:
    """
    Applies Windows 11 Acrylic/Mica system backdrop and extends the frame
    into client area for authentic native OS drop shadow depth.
    """
    if sys.platform != "win32":
        return False
    try:
        dwmapi = ctypes.windll.dwmapi

        # 1. Immersive dark mode (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)
        dark_flag = c_int(1 if is_dark else 0)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(dark_flag), sizeof(dark_flag))

        # 2. System Backdrop: Acrylic (3) or Mica (2) (DWMWA_SYSTEMBACKDROP_TYPE = 38)
        backdrop_type = c_int(3)  # Acrylic frosted vibrancy
        res = dwmapi.DwmSetWindowAttribute(hwnd, 38, byref(backdrop_type), sizeof(backdrop_type))
        if res != 0:
            # Fallback to Mica
            backdrop_type = c_int(2)
            dwmapi.DwmSetWindowAttribute(hwnd, 38, byref(backdrop_type), sizeof(backdrop_type))

        # 3. Native OS drop shadow via 1px frame extension
        margins = MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))
        return True
    except Exception:
        return False


# ── 1. Top-Left macOS Traffic Lights ──────────────────────────────────────────

class MacOSTrafficLights(QWidget):
    """
    Apple HIG Traffic Lights Cluster placed at the far top-left.
    🔴 Close, 🟡 Minimize, 🟢 Zoom/Maximize.
    Glyphs (×, −, +) appear subtly on hover, resting as clean luminous dots.
    """
    close_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet("background: transparent; border: none;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.spacing.sm)  # 8pt spacing

        # 🔴 Close Button
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(12, 12)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Close")
        self.btn_close.clicked.connect(self.close_clicked.emit)
        lay.addWidget(self.btn_close)

        # 🟡 Minimize Button
        self.btn_min = QPushButton("−")
        self.btn_min.setFixedSize(12, 12)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setToolTip("Minimize")
        self.btn_min.clicked.connect(self.minimize_clicked.emit)
        lay.addWidget(self.btn_min)

        # 🟢 Zoom / Maximize Button
        self.btn_zoom = QPushButton("+")
        self.btn_zoom.setFixedSize(12, 12)
        self.btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom.setToolTip("Zoom")
        self.btn_zoom.clicked.connect(self.zoom_clicked.emit)
        lay.addWidget(self.btn_zoom)

        self._apply_button_styles(hover_all=False)

    def _apply_button_styles(self, hover_all: bool = False):
        close_color = "#4A0002" if hover_all else "transparent"
        min_color = "#5B3C00" if hover_all else "transparent"
        zoom_color = "#0A4410" if hover_all else "transparent"

        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.trafficClose};
                border: 1px solid #E0443E;
                border-radius: {theme.radii.sm}px;
                color: {close_color};
                font-family: -apple-system, Inter, sans-serif;
                font-size: 8px;
                font-weight: bold;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.trafficClose};
                color: #4A0002;
            }}
        """)

        self.btn_min.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.trafficMin};
                border: 1px solid #DEA123;
                border-radius: {theme.radii.sm}px;
                color: {min_color};
                font-family: -apple-system, Inter, sans-serif;
                font-size: 9px;
                font-weight: bold;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.trafficMin};
                color: #5B3C00;
            }}
        """)

        self.btn_zoom.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.trafficZoom};
                border: 1px solid #1AAB29;
                border-radius: {theme.radii.sm}px;
                color: {zoom_color};
                font-family: -apple-system, Inter, sans-serif;
                font-size: 8px;
                font-weight: bold;
                padding-bottom: 1px;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.trafficZoom};
                color: #0A4410;
            }}
        """)

    def enterEvent(self, event):
        self._apply_button_styles(hover_all=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_button_styles(hover_all=False)
        super().leaveEvent(event)


# ── 2. macOS Unified Toolbar with Centered Title & Draggable Area ────────────

class MacOSUnifiedToolbar(QFrame):
    """
    macOS Sequoia 48px Unified Titlebar & Toolbar.
    Features:
      - Top-left traffic lights
      - Draggable titlebar surface
      - Centered title in Inter Headline (13pt Semibold, -0.01em tracking)
      - Left & Right toolbar action items
      - Bottom 1px divider
    """
    sidebar_toggle_requested = pyqtSignal()
    inspector_toggle_requested = pyqtSignal()

    def __init__(self, title: str = "NEO", parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._title = title

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-bottom: 1px solid {theme.colors.separator};
            }}
        """)

        # Main Layout
        self._main_lay = QHBoxLayout(self)
        self._main_lay.setContentsMargins(theme.spacing.base, 0, theme.spacing.base, 0)
        self._main_lay.setSpacing(theme.spacing.md)

        # ── Left Area: Traffic Lights & Sidebar Toggle ──
        self.traffic_lights = MacOSTrafficLights(self)
        self._main_lay.addWidget(self.traffic_lights)

        self._main_lay.addSpacing(theme.spacing.xs)

        self.btn_toggle_sidebar = QPushButton("◫")
        self.btn_toggle_sidebar.setFixedSize(26, 26)
        self.btn_toggle_sidebar.setFont(theme.font(theme.typography.caption_1, QFont.Weight.Medium))
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.setToolTip("Toggle Sidebar [⌘1 / Ctrl+1]")
        self.btn_toggle_sidebar.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.colors.labelSecondary};
                border: none; border-radius: {theme.radii.sm}px;
            }}
            QPushButton:hover {{
                background: {theme.colors.cardBackgroundHover};
                color: {theme.colors.labelPrimary};
            }}
        """)
        self.btn_toggle_sidebar.clicked.connect(self.sidebar_toggle_requested.emit)
        self._main_lay.addWidget(self.btn_toggle_sidebar)

        # Left slot for status pills or brand
        self.left_slot = QHBoxLayout()
        self.left_slot.setSpacing(theme.spacing.sm)
        self._main_lay.addLayout(self.left_slot)

        # Stretch to center title
        self._main_lay.addStretch(1)

        # ── Center Area: Centered Window Title ──
        self.title_lbl = QLabel(self._title)
        self.title_lbl.setFont(theme.font(theme.typography.headline))
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.labelPrimary};
                background: transparent;
                border: none;
            }}
        """)
        self._main_lay.addWidget(self.title_lbl)

        # Stretch past center
        self._main_lay.addStretch(1)

        # ── Right Area: Action Pills & Inspector Toggle ──
        self.right_slot = QHBoxLayout()
        self.right_slot.setSpacing(theme.spacing.sm)
        self._main_lay.addLayout(self.right_slot)

        self.btn_toggle_inspector = QPushButton("◨")
        self.btn_toggle_inspector.setFixedSize(26, 26)
        self.btn_toggle_inspector.setFont(theme.font(theme.typography.caption_1, QFont.Weight.Medium))
        self.btn_toggle_inspector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_inspector.setToolTip("Toggle Inspector Panel")
        self.btn_toggle_inspector.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {theme.colors.labelSecondary};
                border: none; border-radius: {theme.radii.sm}px;
            }}
            QPushButton:hover {{
                background: {theme.colors.cardBackgroundHover};
                color: {theme.colors.labelPrimary};
            }}
        """)
        self.btn_toggle_inspector.clicked.connect(self.inspector_toggle_requested.emit)
        self._main_lay.addWidget(self.btn_toggle_inspector)

    def set_title(self, title: str) -> None:
        self._title = title
        self.title_lbl.setText(title)

    # ── Native Draggable Area Handling ────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Let the OS take over the window drag natively with Aero Snap
            win = self.window()
            if win and win.windowHandle():
                win.windowHandle().startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Double-clicking titlebar toggles Zoom/Maximize in macOS
            win = self.window()
            if win:
                if win.isMaximized():
                    win.showNormal()
                else:
                    win.showMaximized()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


# ── 3. Resizable & Collapsible macOS Sidebar Container (220px) ───────────────

class _SidebarResizeGrip(QWidget):
    """
    Subtle 4px hit target for mouse drag-resizing of sidebar / inspector containers.
    Provides native cursor feedback and drag-to-resize within min/max bounds.
    """
    def __init__(self, target_container: QWidget, side: str = "right"):
        super().__init__(target_container)
        self.target = target_container
        self.side = side
        self.setFixedWidth(4)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self._dragging = False
        self._start_x = 0
        self._start_w = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not getattr(self.target, "is_collapsed", False):
            self._dragging = True
            self._start_x = event.globalPosition().x()
            self._start_w = self.target.width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.globalPosition().x() - self._start_x
            if self.side == "left":
                new_w = self._start_w - delta
            else:
                new_w = self._start_w + delta
            new_w = max(self.target.MIN_WIDTH, min(self.target.MAX_WIDTH, int(new_w)))
            self.target.setFixedWidth(new_w)
            self.target._target_expanded_width = new_w
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.target.setFixedWidth(self.target.DEFAULT_WIDTH)
            self.target._target_expanded_width = self.target.DEFAULT_WIDTH
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MacOSSizingSidebarContainer(QFrame):
    """
    macOS Sequoia 220px Resizable Source List Sidebar Container.
    Features:
      - Default width: 220px (min: 180px, max: 320px)
      - Translucent Mica/Acrylic background with vibrancy fallback (rgba(26, 26, 29, 0.88))
      - 1px vertical right border
      - Smooth collapse/expand animation (200ms OutCubic)
      - Interactive right edge resize grip with double-click reset
    """
    DEFAULT_WIDTH = 220
    MIN_WIDTH = 180
    MAX_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.DEFAULT_WIDTH)
        self.is_collapsed = False
        self._target_expanded_width = self.DEFAULT_WIDTH

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-right: 1px solid {theme.colors.separator};
            }}
        """)

        self.anim = QPropertyAnimation(self, b"maximumWidth")
        self._configure_spring()

        self._outer_lay = QHBoxLayout(self)
        self._outer_lay.setContentsMargins(0, 0, 0, 0)
        self._outer_lay.setSpacing(0)

        self._content_host = QWidget(self)
        self._content_host.setStyleSheet("background: transparent; border: none;")
        self.content_lay = QVBoxLayout(self._content_host)
        self.content_lay.setContentsMargins(0, 0, 0, 0)
        self.content_lay.setSpacing(0)
        self._outer_lay.addWidget(self._content_host, stretch=1)

        self._grip = _SidebarResizeGrip(self, side="right")
        self._outer_lay.addWidget(self._grip)

    def _configure_spring(self):
        from core.macos_motion import SpringPresets, motion
        if motion.is_reduced_motion():
            self.anim.setDuration(100)
            self.anim.setEasingCurve(QEasingCurve.Type.Linear)
        else:
            self.anim.setDuration(SpringPresets.smooth.duration_ms)
            self.anim.setEasingCurve(SpringPresets.smooth.easing_curve())

    def set_content_widget(self, widget: QWidget) -> None:
        """Sets the inner Source List sidebar widget."""
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.content_lay.addWidget(widget)

    def toggle_collapse(self) -> None:
        """Smoothly animates collapsing/expanding the sidebar."""
        self.anim.stop()
        self._configure_spring()
        if not self.is_collapsed:
            # Collapse to 0
            self._target_expanded_width = max(self.MIN_WIDTH, self.width())
            self._grip.hide()
            self.setMinimumWidth(0)
            self.anim.setStartValue(self.width())
            self.anim.setEndValue(0)
            self.anim.finished.connect(self._on_collapse_finished)
            self.anim.start()
            self.is_collapsed = True
        else:
            # Expand to target
            self.show()
            self.anim.setStartValue(0)
            self.anim.setEndValue(self._target_expanded_width)
            self.anim.finished.connect(self._on_expand_finished)
            self.anim.start()
            self.is_collapsed = False

    def _on_collapse_finished(self):
        try:
            self.anim.finished.disconnect(self._on_collapse_finished)
        except Exception:
            pass
        if self.is_collapsed:
            self.hide()

    def _on_expand_finished(self):
        try:
            self.anim.finished.disconnect(self._on_expand_finished)
        except Exception:
            pass
        if not self.is_collapsed:
            self.setMinimumWidth(self.MIN_WIDTH)
            self.setMaximumWidth(self.MAX_WIDTH)
            self.setFixedWidth(self._target_expanded_width)
            self._grip.show()


# ── 4. Optional macOS Inspector Panel Container (280px) ──────────────────────

class MacOSInspectorPanelContainer(QFrame):
    """
    macOS Sequoia 280px Inspector Panel Container (Right side).
    Features:
      - Default width: 280px (min: 240px, max: 360px)
      - Translucent background with 1px left separator border
      - Smooth collapse/expand animation
      - Interactive left edge resize grip with double-click reset
    """
    DEFAULT_WIDTH = 295
    MIN_WIDTH = 260
    MAX_WIDTH = 380

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.DEFAULT_WIDTH)
        self.is_collapsed = False
        self._target_expanded_width = self.DEFAULT_WIDTH

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-left: 1px solid {theme.colors.separator};
            }}
        """)

        self.anim = QPropertyAnimation(self, b"maximumWidth")
        self._configure_spring()

        self._outer_lay = QHBoxLayout(self)
        self._outer_lay.setContentsMargins(0, 0, 0, 0)
        self._outer_lay.setSpacing(0)

        self._grip = _SidebarResizeGrip(self, side="left")
        self._outer_lay.addWidget(self._grip)

        self._content_host = QWidget(self)
        self._content_host.setStyleSheet("background: transparent; border: none;")
        self.content_lay = QVBoxLayout(self._content_host)
        self.content_lay.setContentsMargins(0, 0, 0, 0)
        self.content_lay.setSpacing(0)
        self._outer_lay.addWidget(self._content_host, stretch=1)

    def _configure_spring(self):
        from core.macos_motion import SpringPresets, motion
        if motion.is_reduced_motion():
            self.anim.setDuration(100)
            self.anim.setEasingCurve(QEasingCurve.Type.Linear)
        else:
            self.anim.setDuration(SpringPresets.smooth.duration_ms)
            self.anim.setEasingCurve(SpringPresets.smooth.easing_curve())

    def set_content_widget(self, widget: QWidget) -> None:
        """Sets the inner Inspector sidebar widget."""
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.content_lay.addWidget(widget)

    def toggle_collapse(self) -> None:
        """Smoothly animates collapsing/expanding the inspector panel."""
        self.anim.stop()
        self._configure_spring()
        if not self.is_collapsed:
            self._target_expanded_width = max(self.MIN_WIDTH, self.width())
            self._grip.hide()
            self.setMinimumWidth(0)
            self.anim.setStartValue(self.width())
            self.anim.setEndValue(0)
            self.anim.finished.connect(self._on_collapse_finished)
            self.anim.start()
            self.is_collapsed = True
        else:
            self.show()
            self.anim.setStartValue(0)
            self.anim.setEndValue(self._target_expanded_width)
            self.anim.finished.connect(self._on_expand_finished)
            self.anim.start()
            self.is_collapsed = False

    def _on_collapse_finished(self):
        try:
            self.anim.finished.disconnect(self._on_collapse_finished)
        except Exception:
            pass
        if self.is_collapsed:
            self.hide()

    def _on_expand_finished(self):
        try:
            self.anim.finished.disconnect(self._on_expand_finished)
        except Exception:
            pass
        if not self.is_collapsed:
            self.setMinimumWidth(self.MIN_WIDTH)
            self.setMaximumWidth(self.MAX_WIDTH)
            self.setFixedWidth(self._target_expanded_width)
            self._grip.show()


# ── 5. Frameless Window Edge Resize Helper ────────────────────────────────────

class MacOSFramelessHelper:
    """
    Manages border hit-testing and edge/corner resizing for frameless windows
    using Qt 6's hardware-accelerated startSystemResize().
    """
    BORDER_SIZE = 8

    @classmethod
    def update_cursor_for_pos(cls, window: QWidget, pos: QPoint) -> None:
        if window.isMaximized():
            window.setCursor(Qt.CursorShape.ArrowCursor)
            return

        w, h = window.width(), window.height()
        x, y = pos.x(), pos.y()
        bs = cls.BORDER_SIZE

        # Corners
        if x <= bs and y <= bs:
            window.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif x >= w - bs and y >= h - bs:
            window.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif x >= w - bs and y <= bs:
            window.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif x <= bs and y >= h - bs:
            window.setCursor(Qt.CursorShape.SizeBDiagCursor)
        # Edges
        elif x <= bs or x >= w - bs:
            window.setCursor(Qt.CursorShape.SizeHorCursor)
        elif y <= bs or y >= h - bs:
            window.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            window.setCursor(Qt.CursorShape.ArrowCursor)

    @classmethod
    def handle_mouse_press(cls, window: QWidget, pos: QPoint) -> bool:
        """Returns True if the press triggered an OS system edge resize."""
        if window.isMaximized():
            return False

        w, h = window.width(), window.height()
        x, y = pos.x(), pos.y()
        bs = cls.BORDER_SIZE

        edge = None
        if x <= bs and y <= bs:
            edge = Qt.Edge.TopEdge | Qt.Edge.LeftEdge
        elif x >= w - bs and y >= h - bs:
            edge = Qt.Edge.BottomEdge | Qt.Edge.RightEdge
        elif x >= w - bs and y <= bs:
            edge = Qt.Edge.TopEdge | Qt.Edge.RightEdge
        elif x <= bs and y >= h - bs:
            edge = Qt.Edge.BottomEdge | Qt.Edge.LeftEdge
        elif x <= bs:
            edge = Qt.Edge.LeftEdge
        elif x >= w - bs:
            edge = Qt.Edge.RightEdge
        elif y <= bs:
            edge = Qt.Edge.TopEdge
        elif y >= h - bs:
            edge = Qt.Edge.BottomEdge

        if edge is not None and window.windowHandle():
            window.windowHandle().startSystemResize(edge)
            return True
        return False
