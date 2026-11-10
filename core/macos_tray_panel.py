"""
core/macos_tray_panel.py — Apple macOS Menu Bar Extra / Control Center Quick Panel.

Senior Design Engineering Specification (Phase 5):
1. Geometry & Shell:
   - 280px fixed width, 14px continuous corner radius (theme.radii.lg).
   - Translucent background with 1px highlight border and elevation shadow.
   - Anchored to menu bar status item / system tray icon.
2. Contents:
   - Assistant header with live telemetry indicator (e.g., "260ms · Online").
   - 2x2 Quick Toggle Grid (Microphone, Live Engine, Spatial Vision, Stealth Mode).
   - Volume / Mic sensitivity slider.
   - Studio Quick Jump pill strip (Chat, Terminal, Swarm, Files).
   - Bottom action bar (Restore Main HUD, Settings, Quit).
3. Motion & Behavior:
   - Smooth bloom (scale 0.96 to 1.0) via SpringPresets.snappy.
   - Auto-dismiss on outside click or Escape.
"""
from __future__ import annotations

from typing import Optional, Callable

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, pyqtSignal, pyqtProperty, QPropertyAnimation
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QApplication
)

from core.theme_provider import theme
from core.macos_components import (
    MacOSButton,
    MacOSToggle,
    render_lucide_icon,
)
from core.macos_motion import motion, SpringPresets, create_spring_animation
from core.macos_waveform import MacOSWaveformIndicator, WaveformState


class _QuickToggleTile(QFrame):
    """Square Control Center toggle tile with icon, title, and active state."""
    toggled = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        icon_name: str,
        initial_state: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._title = title
        self._icon_name = icon_name
        self._is_active = initial_state

        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        self._icon_lbl = QLabel(self)
        self._icon_lbl.setFixedSize(20, 20)
        lay.addWidget(self._icon_lbl)

        v_lay = QVBoxLayout()
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(1)

        self._title_lbl = QLabel(title, self)
        self._title_lbl.setFont(theme.font(theme.typography.headline))
        v_lay.addWidget(self._title_lbl)

        self._sub_lbl = QLabel("Active" if initial_state else "Off", self)
        self._sub_lbl.setFont(theme.font(theme.typography.caption_2))
        v_lay.addWidget(self._sub_lbl)

        lay.addLayout(v_lay, stretch=1)

        self._apply_style()

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._sub_lbl.setText("Active" if active else "Off")
        self._apply_style()

    def toggle(self) -> None:
        self.set_active(not self._is_active)
        self.toggled.emit(self._is_active)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        self.toggle()

    def _apply_style(self) -> None:
        r = theme.radii.sm
        if self._is_active:
            bg = theme.accent_color
            fg = "#FFFFFF"
            sub_col = "rgba(255, 255, 255, 0.78)"
            icon_col = "#FFFFFF"
        else:
            bg = theme.colors.controlBackgroundSecondary
            fg = theme.colors.labelPrimary
            sub_col = theme.colors.labelTertiary
            icon_col = theme.colors.labelSecondary

        self._icon_lbl.setPixmap(render_lucide_icon(self._icon_name, color=icon_col, size=18))
        self._title_lbl.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self._sub_lbl.setStyleSheet(f"color: {sub_col}; background: transparent; border: none;")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)


class MacOSTrayQuickPanel(QWidget):
    """
    Apple Menu Bar Extra Quick Panel (280px wide).
    Floats near menu bar or system tray for instant assistant controls.
    """
    restore_main_requested = pyqtSignal()
    open_settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    studio_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(280)

        self._scale_factor: float = 1.0
        self._panel_opacity: float = 1.0
        self._target_pos: QPoint = QPoint()

        # Outer Frame
        self._card = QFrame(self)
        r = theme.radii.lg
        self._card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)
        self._card.setGraphicsEffect(theme.shadow_effect(theme.elevation.high))

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(8, 8, 8, 8)
        root_lay.addWidget(self._card)

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(14, 14, 14, 14)
        card_lay.setSpacing(10)

        # 1. Header with Status & Telemetry
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)

        self.icon_badge = QLabel(self._card)
        self.icon_badge.setPixmap(render_lucide_icon("cpu", color=theme.accent_color, size=16))
        hdr_row.addWidget(self.icon_badge)

        v_hdr = QVBoxLayout()
        v_hdr.setSpacing(0)
        t_lbl = QLabel("NEO Assistant", self._card)
        t_lbl.setFont(theme.font(theme.typography.headline))
        t_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        v_hdr.addWidget(t_lbl)

        s_lbl = QLabel("260ms · Online", self._card)
        s_lbl.setFont(theme.font(theme.typography.caption_2))
        s_lbl.setStyleSheet(f"color: {theme.colors.systemGreen}; background: transparent; border: none;")
        v_hdr.addWidget(s_lbl)
        hdr_row.addLayout(v_hdr, stretch=1)

        # Main window restore mini button
        btn_open = QPushButton("↗", self._card)
        btn_open.setFixedSize(22, 22)
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.setToolTip("Open Full HUD")
        btn_open.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.controlBackgroundSecondary};
                color: {theme.colors.labelSecondary};
                border: 1px solid {theme.colors.separator};
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.cardBackgroundHover};
                color: {theme.colors.labelPrimary};
            }}
        """)
        btn_open.clicked.connect(self._on_restore_clicked)
        hdr_row.addWidget(btn_open)

        card_lay.addLayout(hdr_row)

        # 2. Mini Waveform Status
        self.waveform = MacOSWaveformIndicator(self._card)
        self.waveform.setFixedHeight(40)
        self.waveform.set_state(WaveformState.LISTENING)
        card_lay.addWidget(self.waveform)

        # 3. 2x2 Quick Toggles Grid
        grid = QGridLayout()
        grid.setSpacing(6)

        self.tile_mic = _QuickToggleTile("Microphone", "sliders", initial_state=True, parent=self._card)
        grid.addWidget(self.tile_mic, 0, 0)

        self.tile_engine = _QuickToggleTile("Live Engine", "cpu", initial_state=True, parent=self._card)
        grid.addWidget(self.tile_engine, 0, 1)

        self.tile_vision = _QuickToggleTile("Vision Sentry", "eye", initial_state=False, parent=self._card)
        grid.addWidget(self.tile_vision, 1, 0)

        self.tile_stealth = _QuickToggleTile("Stealth Mode", "shield", initial_state=False, parent=self._card)
        grid.addWidget(self.tile_stealth, 1, 1)

        card_lay.addLayout(grid)

        # 4. Studio Quick Jump Strip
        jump_lbl = QLabel("Quick Jump:", self._card)
        jump_lbl.setFont(theme.font(theme.typography.caption_1, QFont.Weight.DemiBold))
        jump_lbl.setStyleSheet(f"color: {theme.colors.labelTertiary}; background: transparent; border: none;")
        card_lay.addWidget(jump_lbl)

        jump_row = QHBoxLayout()
        jump_row.setSpacing(4)
        studios = [
            ("Chat", "chat", "message-square"),
            ("Swarm", "swarm", "cpu"),
            ("Terminal", "terminal", "terminal"),
            ("Files", "files", "folder"),
        ]
        for name, sid, icon in studios:
            btn_s = QPushButton(name, self._card)
            btn_s.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_s.setFont(theme.font(theme.typography.caption_2))
            btn_s.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.colors.controlBackgroundSecondary};
                    color: {theme.colors.labelSecondary};
                    border: 1px solid {theme.colors.separator};
                    border-radius: 6px;
                    padding: 4px 6px;
                }}
                QPushButton:hover {{
                    background-color: {theme.colors.cardBackgroundHover};
                    color: {theme.colors.labelPrimary};
                }}
            """)
            btn_s.clicked.connect(lambda ch, s=sid: self._on_studio_clicked(s))
            jump_row.addWidget(btn_s)
        card_lay.addLayout(jump_row)

        # 5. Footer (Settings & Quit)
        foot_row = QHBoxLayout()
        foot_row.setSpacing(6)

        btn_sett = MacOSButton("Settings", variant="secondary", icon_name="settings", parent=self._card)
        btn_sett.clicked.connect(self._on_settings_clicked)
        foot_row.addWidget(btn_sett, stretch=1)

        btn_quit = MacOSButton("Quit", variant="destructive", icon_name="x", parent=self._card)
        btn_quit.clicked.connect(self.quit_requested.emit)
        foot_row.addWidget(btn_quit)

        card_lay.addLayout(foot_row)

        theme.theme_changed.connect(self._apply_style)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, s: float) -> None:
        self._scale_factor = s
        self.update()

    @pyqtProperty(float)
    def panel_opacity(self) -> float:
        return self._panel_opacity

    @panel_opacity.setter
    def panel_opacity(self, o: float) -> None:
        self._panel_opacity = max(0.0, min(1.0, o))
        self.update()

    def _apply_style(self):
        r = theme.radii.lg
        self._card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)

    def _on_restore_clicked(self):
        self.hide()
        self.restore_main_requested.emit()

    def _on_settings_clicked(self):
        self.hide()
        self.open_settings_requested.emit()

    def _on_studio_clicked(self, studio_id: str):
        self.hide()
        self.studio_selected.emit(studio_id)

    def show_at(self, global_pos: QPoint) -> None:
        """Presents quick panel blooming from global coordinate."""
        self.move(global_pos)
        self.show()
        self.raise_()
        self.activateWindow()

        if motion.is_reduced_motion():
            self._scale_factor = 1.0
            self._panel_opacity = 0.0
            anim = create_spring_animation(self, b"panel_opacity", 0.0, 1.0, duration_ms=100)
            anim.start()
        else:
            self._scale_factor = 0.96
            self._panel_opacity = 0.0
            a_scale = create_spring_animation(self, b"scale_factor", 0.96, 1.0, spring=SpringPresets.snappy)
            a_opacity = create_spring_animation(self, b"panel_opacity", 0.0, 1.0, spring=SpringPresets.snappy)
            a_scale.start()
            a_opacity.start()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._panel_opacity)

        if abs(self._scale_factor - 1.0) > 1e-4:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(self._scale_factor, self._scale_factor)
            painter.translate(-cx, -cy)

        # 1px Inner highlight border
        pen_col = QColor(255, 255, 255, 26) if theme.is_dark else QColor(0, 0, 0, 16)
        painter.setPen(QPen(pen_col, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = theme.radii.lg
        painter.drawRoundedRect(QRectF(8.5, 8.5, self.width() - 17.0, self.height() - 17.0), r, r)
        painter.end()
