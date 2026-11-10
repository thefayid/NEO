"""
core/macos_spotlight.py — Apple macOS Spotlight-Style Floating Command Bar.

Senior Design Engineering Specification (Phase 5):
1. Geometry & Shell:
   - Centered horizontally on active screen.
   - Fixed 680px width, 14px continuous corner radius (theme.radii.lg).
   - Frameless, translucent background with heavy blur / vibrancy fallback.
   - 1px inner highlight border (rgba(255,255,255,0.12) dark / rgba(0,0,0,0.08) light).
   - Multi-layer elevation shadow (theme.elevation.highest).
2. Input Mechanics:
   - 18pt SF / Inter typography with -0.01em tracking.
   - Lucide 1.5 stroke search magnifier on left.
   - Auto-revealing clear button (✕) when text is non-empty.
3. Suggestion & Results List:
   - Filtered command suggestions and studio actions.
   - Keyboard navigation (Up/Down arrow keys move accent pill highlight).
   - Enter executes highlighted item or submits search prompt.
   - Escape dismisses with spring scale-down.
4. Motion:
   - Summon: scales from 0.96 to 1.0, fades from 0.0 to 1.0 using SpringPresets.snappy.
   - Dismiss: scales from 1.0 to 0.96, fades from 1.0 to 0.0 using SpringPresets.snappy.
   - Respects prefers-reduced-motion by swapping to 100ms simple fade.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Callable
from dataclasses import dataclass

from PyQt6.QtCore import (
    Qt, QPoint, QRect, QRectF, QSize, pyqtSignal, pyqtProperty,
    QPropertyAnimation, QTimer, QEvent
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush,
    QKeyEvent, QMouseEvent, QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QScrollArea, QApplication, QGraphicsDropShadowEffect
)

from core.theme_provider import theme
from core.macos_components import render_lucide_icon
from core.macos_motion import motion, SpringPresets, create_spring_animation


@dataclass
class SpotlightCommand:
    """Actionable command or suggestion entry in Spotlight."""
    command_id: str
    title: str
    category: str
    subtitle: str = ""
    icon_name: str = "search"
    shortcut: str = ""
    callback: Optional[Callable] = None


class _SpotlightResultRow(QFrame):
    """Single interactive row inside the Spotlight suggestions list."""
    clicked = pyqtSignal(str)

    def __init__(self, cmd: SpotlightCommand, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cmd = cmd
        self._is_highlighted = False

        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 14, 0)
        lay.setSpacing(10)

        # Icon container
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(18, 18)
        lay.addWidget(self.icon_lbl)

        # Text column
        v_box = QVBoxLayout()
        v_box.setContentsMargins(0, 5, 0, 5)
        v_box.setSpacing(1)

        self.lbl_title = QLabel(cmd.title, self)
        self.lbl_title.setFont(theme.font(theme.typography.headline))
        v_box.addWidget(self.lbl_title)

        if cmd.subtitle:
            self.lbl_sub = QLabel(cmd.subtitle, self)
            self.lbl_sub.setFont(theme.font(theme.typography.caption_1))
            v_box.addWidget(self.lbl_sub)

        lay.addLayout(v_box, stretch=1)

        # Category Pill
        self.lbl_cat = QLabel(cmd.category.upper(), self)
        self.lbl_cat.setFont(theme.font(theme.typography.caption_2))
        self.lbl_cat.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.labelTertiary};
                background: transparent;
                border: none;
                font-size: 9px;
                letter-spacing: 0.5px;
            }}
        """)
        lay.addWidget(self.lbl_cat)

        # Optional shortcut hint
        if cmd.shortcut:
            self.lbl_sc = QLabel(cmd.shortcut, self)
            self.lbl_sc.setFont(theme.font(theme.typography.caption_2))
            self.lbl_sc.setStyleSheet(f"""
                QLabel {{
                    color: {theme.colors.labelTertiary};
                    background-color: {theme.colors.controlBackgroundSecondary};
                    border: 1px solid {theme.colors.separator};
                    border-radius: 4px;
                    padding: 2px 5px;
                }}
            """)
            lay.addWidget(self.lbl_sc)

        self.set_highlighted(False)

    def set_highlighted(self, active: bool) -> None:
        self._is_highlighted = active
        r = theme.radii.sm

        if active:
            bg = theme.accent_color
            title_col = "#FFFFFF"
            sub_col = "rgba(255, 255, 255, 0.82)"
            cat_col = "rgba(255, 255, 255, 0.70)"
            icon_col = "#FFFFFF"
        else:
            bg = "transparent"
            title_col = theme.colors.labelPrimary
            sub_col = theme.colors.labelSecondary
            cat_col = theme.colors.labelTertiary
            icon_col = theme.colors.labelSecondary

        self.icon_lbl.setPixmap(render_lucide_icon(self.cmd.icon_name, color=icon_col, size=16))
        self.lbl_title.setStyleSheet(f"color: {title_col}; background: transparent; border: none;")
        if hasattr(self, "lbl_sub"):
            self.lbl_sub.setStyleSheet(f"color: {sub_col}; background: transparent; border: none;")
        self.lbl_cat.setStyleSheet(f"color: {cat_col}; background: transparent; border: none;")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: none;
                border-radius: {r}px;
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.clicked.emit(self.cmd.command_id)


class MacOSSpotlightCommandBar(QWidget):
    """
    Apple Spotlight-Style Floating Command Bar.
    Centered on screen, 680px wide, 14px continuous radius, heavy backdrop blur.
    """
    command_triggered = pyqtSignal(str, str)  # command_id, query_text
    dismissed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(680)

        self._scale_factor: float = 1.0
        self._bar_opacity: float = 1.0
        self._target_pos: QPoint = QPoint()
        self._anim_scale: Optional[QPropertyAnimation] = None
        self._anim_opacity: Optional[QPropertyAnimation] = None

        self._all_commands: List[SpotlightCommand] = []
        self._filtered_rows: List[_SpotlightResultRow] = []
        self._highlighted_index: int = 0

        # Build Main Card Container
        self._card = QFrame(self)
        self._card.setObjectName("spotlightCard")
        r = theme.radii.lg
        self._card.setStyleSheet(f"""
            QFrame#spotlightCard {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)
        self._card.setGraphicsEffect(theme.shadow_effect(theme.elevation.high))

        self.root_lay = QVBoxLayout(self)
        self.root_lay.setContentsMargins(12, 12, 12, 12)
        self.root_lay.setSpacing(0)
        self.root_lay.addWidget(self._card)

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(8)

        # 1. Search Bar Row
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(12)

        self._search_icon_lbl = QLabel(self._card)
        self._search_icon_lbl.setFixedSize(22, 22)
        self._search_icon_lbl.setPixmap(render_lucide_icon("search", color=theme.colors.labelSecondary, size=20))
        search_row.addWidget(self._search_icon_lbl)

        self.input_field = QLineEdit(self._card)
        self.input_field.setPlaceholderText("Spotlight Search or ask NEO...")
        self.input_field.setFont(theme.font(theme.typography.title_2))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {theme.colors.labelPrimary};
                padding: 4px 0;
            }}
        """)
        self.input_field.textChanged.connect(self._on_search_text_changed)
        self.input_field.returnPressed.connect(self._on_return_pressed)
        search_row.addWidget(self.input_field, stretch=1)

        # Clear button (✕)
        self.btn_clear = QPushButton("✕", self._card)
        self.btn_clear.setFixedSize(18, 18)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.labelTertiary};
                color: {theme.colors.windowBackground};
                border: none;
                border-radius: 9px;
                font-size: 9px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.labelSecondary};
            }}
        """)
        self.btn_clear.hide()
        self.btn_clear.clicked.connect(self.clear_search)
        search_row.addWidget(self.btn_clear)

        card_lay.addLayout(search_row)

        # 2. Divider Line
        self.divider = QFrame(self._card)
        self.divider.setFixedHeight(1)
        self.divider.setStyleSheet(f"background-color: {theme.colors.separator};")
        card_lay.addWidget(self.divider)

        # 3. Results Container (Scrollable)
        self.results_scroll = QScrollArea(self._card)
        self.results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results_scroll.setStyleSheet("background: transparent; border: none;")
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_scroll.setMaximumHeight(320)

        self.results_host = QWidget()
        self.results_host.setStyleSheet("background: transparent; border: none;")
        self.results_lay = QVBoxLayout(self.results_host)
        self.results_lay.setContentsMargins(0, 4, 0, 4)
        self.results_lay.setSpacing(2)
        self.results_scroll.setWidget(self.results_host)

        card_lay.addWidget(self.results_scroll)

        # 4. Footer info bar
        self.footer_row = QHBoxLayout()
        self.footer_row.setContentsMargins(4, 4, 4, 0)
        self.lbl_hint = QLabel("Press Return to execute · Esc to dismiss · ↑↓ to navigate", self._card)
        self.lbl_hint.setFont(theme.font(theme.typography.caption_2))
        self.lbl_hint.setStyleSheet(f"color: {theme.colors.labelTertiary}; background: transparent; border: none;")
        self.footer_row.addWidget(self.lbl_hint)
        self.footer_row.addStretch()

        self.lbl_brand = QLabel("NEO Spotlight", self._card)
        self.lbl_brand.setFont(theme.font(theme.typography.caption_2, QFont.Weight.DemiBold))
        self.lbl_brand.setStyleSheet(f"color: {theme.accent_color}; background: transparent; border: none;")
        self.footer_row.addWidget(self.lbl_brand)

        card_lay.addLayout(self.footer_row)

        # Install keyboard filter
        self.installEventFilter(self)
        self.input_field.installEventFilter(self)

        # Load default commands
        self._load_default_commands()
        self._refresh_results()

        # Connect theme changes
        theme.theme_changed.connect(self._apply_style)

    @pyqtProperty(float)
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, s: float) -> None:
        self._scale_factor = s
        self.update()

    @pyqtProperty(float)
    def bar_opacity(self) -> float:
        return self._bar_opacity

    @bar_opacity.setter
    def bar_opacity(self, o: float) -> None:
        self._bar_opacity = max(0.0, min(1.0, o))
        self.update()

    def _apply_style(self):
        r = theme.radii.lg
        self._card.setStyleSheet(f"""
            QFrame#spotlightCard {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)
        self.divider.setStyleSheet(f"background-color: {theme.colors.separator};")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {theme.colors.labelPrimary};
                padding: 4px 0;
            }}
        """)
        self._search_icon_lbl.setPixmap(render_lucide_icon("search", color=theme.colors.labelSecondary, size=20))
        self.lbl_brand.setStyleSheet(f"color: {theme.accent_color}; background: transparent; border: none;")
        self._refresh_results()

    def _load_default_commands(self):
        self._all_commands = [
            SpotlightCommand("ask", "Ask NEO Anything...", "Assistant", "Submit query to Gemini 3.1 Live Engine", icon_name="message-square", shortcut="↵"),
            SpotlightCommand("research", "Deep Autonomous Research", "Studio", "Launch multi-agent background research pipeline", icon_name="book-open"),
            SpotlightCommand("code", "Code Generation & Architecture", "Studio", "Generate, debug, or refactor codebase", icon_name="terminal"),
            SpotlightCommand("swarm", "Autonomous Subagent Swarm", "Intelligence", "Open 4-node concurrent swarm coordinator", icon_name="cpu"),
            SpotlightCommand("vision", "Spatial Vision & Gestures", "Intelligence", "Realtime gesture recognition and optical tracking", icon_name="eye"),
            SpotlightCommand("notes", "Knowledge & Notes Studio", "Studio", "Open structured memory knowledge base", icon_name="file-text"),
            SpotlightCommand("terminal", "Embedded Command Terminal", "Studio", "PowerShell & sandboxed environment runner", icon_name="terminal"),
            SpotlightCommand("settings", "System Settings", "Preferences", "Configure models, voice, audio, and appearance", icon_name="settings", shortcut="⌘,"),
            SpotlightCommand("mic_toggle", "Toggle Microphone (Mute / Unmute)", "Action", "Mute or restore active voice input stream", icon_name="sliders"),
            SpotlightCommand("mode_toggle", "Toggle Dark / Light Appearance", "Appearance", "Switch interface theme mode", icon_name="sun"),
            SpotlightCommand("stealth", "Toggle Ghost Stealth Mode", "System", "Minimize to background tray sentinel", icon_name="shield"),
        ]

    def register_command(self, cmd: SpotlightCommand):
        self._all_commands.append(cmd)
        self._refresh_results()

    def clear_search(self):
        self.input_field.clear()
        self.btn_clear.hide()
        self._refresh_results()

    def _on_search_text_changed(self, text: str):
        self.btn_clear.setVisible(bool(text))
        self._refresh_results(text)

    def _refresh_results(self, query: str = ""):
        # Clear existing rows
        while self.results_lay.count():
            item = self.results_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._filtered_rows.clear()

        q = query.strip().lower()
        matched = []
        for cmd in self._all_commands:
            if not q or (q in cmd.title.lower() or q in cmd.category.lower() or q in cmd.subtitle.lower()):
                matched.append(cmd)

        if not matched and q:
            # Custom dynamic search row
            custom_cmd = SpotlightCommand(
                command_id="custom_prompt",
                title=f'Ask NEO "{query}"',
                category="Prompt",
                subtitle="Execute live reasoning request with audio stream",
                icon_name="message-square",
                shortcut="↵"
            )
            matched.append(custom_cmd)

        for idx, cmd in enumerate(matched[:8]):
            row = _SpotlightResultRow(cmd, parent=self.results_host)
            row.clicked.connect(self._on_row_clicked)
            self.results_lay.addWidget(row)
            self._filtered_rows.append(row)

        self._highlighted_index = 0
        if self._filtered_rows:
            self._filtered_rows[0].set_highlighted(True)

        self.adjustSize()

    def _on_row_clicked(self, command_id: str):
        query = self.input_field.text().strip()
        self.command_triggered.emit(command_id, query)
        self.dismiss()

    def _on_return_pressed(self):
        if self._filtered_rows and 0 <= self._highlighted_index < len(self._filtered_rows):
            cmd = self._filtered_rows[self._highlighted_index].cmd
            query = self.input_field.text().strip()
            self.command_triggered.emit(cmd.command_id, query)
            if cmd.callback:
                cmd.callback()
            self.dismiss()
        else:
            query = self.input_field.text().strip()
            if query:
                self.command_triggered.emit("ask", query)
                self.dismiss()

    def summon(self):
        """Presents Spotlight with scale-up (0.96 to 1.0) and opacity fade."""
        # Center horizontally on primary screen, 15% from top
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + int(geo.height() * 0.16)
            self.move(x, y)
            self._target_pos = QPoint(x, y)

        self.input_field.clear()
        self.input_field.setFocus()
        self._refresh_results()
        self.show()
        self.raise_()
        self.activateWindow()

        if motion.is_reduced_motion():
            self._scale_factor = 1.0
            self._bar_opacity = 0.0
            self._anim_opacity = create_spring_animation(self, b"bar_opacity", 0.0, 1.0, duration_ms=100)
            self._anim_opacity.start()
        else:
            self._scale_factor = 0.96
            self._bar_opacity = 0.0
            self._anim_scale = create_spring_animation(self, b"scale_factor", 0.96, 1.0, spring=SpringPresets.snappy)
            self._anim_opacity = create_spring_animation(self, b"bar_opacity", 0.0, 1.0, spring=SpringPresets.snappy)
            self._anim_scale.start()
            self._anim_opacity.start()

    def dismiss(self):
        """Hides Spotlight with smooth snappy scale-down."""
        if motion.is_reduced_motion():
            self.hide()
            self.dismissed.emit()
            return

        self._anim_scale = create_spring_animation(self, b"scale_factor", self._scale_factor, 0.96, spring=SpringPresets.snappy)
        self._anim_opacity = create_spring_animation(self, b"bar_opacity", self._bar_opacity, 0.0, spring=SpringPresets.snappy)

        def _on_finished():
            self.hide()
            self.dismissed.emit()

        self._anim_opacity.finished.connect(_on_finished)
        self._anim_scale.start()
        self._anim_opacity.start()

    def toggle(self):
        if self.isVisible():
            self.dismiss()
        else:
            self.summon()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.dismiss()
                return True
            elif key == Qt.Key.Key_Down:
                if self._filtered_rows:
                    self._filtered_rows[self._highlighted_index].set_highlighted(False)
                    self._highlighted_index = (self._highlighted_index + 1) % len(self._filtered_rows)
                    self._filtered_rows[self._highlighted_index].set_highlighted(True)
                return True
            elif key == Qt.Key.Key_Up:
                if self._filtered_rows:
                    self._filtered_rows[self._highlighted_index].set_highlighted(False)
                    self._highlighted_index = (self._highlighted_index - 1 + len(self._filtered_rows)) % len(self._filtered_rows)
                    self._filtered_rows[self._highlighted_index].set_highlighted(True)
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._bar_opacity)

        if abs(self._scale_factor - 1.0) > 1e-4:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(self._scale_factor, self._scale_factor)
            painter.translate(-cx, -cy)

        # 1px Inner highlight border (Apple HIG macOS Sequoia style)
        pen_col = QColor(255, 255, 255, 28) if theme.is_dark else QColor(0, 0, 0, 18)
        painter.setPen(QPen(pen_col, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = theme.radii.lg
        painter.drawRoundedRect(QRectF(12.5, 12.5, self.width() - 25.0, self.height() - 25.0), r, r)
        painter.end()
