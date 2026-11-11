"""
core/floating_island.py — Stark Floating Desktop Dynamic Island & Mini-HUD.
A sleek, draggable, always-on-top macOS Sequoia-style dynamic capsule that floats
on your desktop across all workspaces:
- Real-time listening indicator, neural state pulsing, and mini waveform visualizer.
- Proactive Affordance Chips rendering with direct one-click execution.
- Spotlight inline command input with auto-expansion.
- Dedicated Screen Lens quick-trigger (🔍) and Mic Mute toggle (🎙).
- Seamless snap-to-top docking and one-click restore to main HUD.
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QPoint, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)


class MiniWaveformWidget(QWidget):
    """Compact 3-bar audio-reactive visualizer for the dynamic island."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(16, 20)
        self._level: float = 0.0
        self._bars = [0.2, 0.5, 0.3]
        self._color = QColor(56, 189, 248)  # Cyan
        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._step_decay)
        self._decay_timer.start(50)

    def set_level(self, level: float, state: str = "LISTENING") -> None:
        self._level = max(0.0, min(1.0, float(level)))
        if state == "SPEAKING":
            self._color = QColor(52, 211, 153)  # Emerald
        elif state == "THINKING":
            self._color = QColor(168, 85, 247)  # Violet
        elif state == "MUTED":
            self._color = QColor(244, 63, 94)   # Rose
        else:
            self._color = QColor(56, 189, 248)  # Cyan
        self.update()

    def _step_decay(self) -> None:
        decay = 0.85
        self._level *= decay
        target = max(0.15, self._level)
        self._bars[0] = target * 0.75 + 0.1
        self._bars[1] = target * 1.00 + 0.1
        self._bars[2] = target * 0.80 + 0.1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        bar_w = 3.0
        gap = 2.0
        start_x = (w - (3 * bar_w + 2 * gap)) / 2.0

        for i, val in enumerate(self._bars):
            bar_h = max(3.0, min(float(h - 2), val * (h - 2)))
            bx = start_x + i * (bar_w + gap)
            by = (h - bar_h) / 2.0
            painter.setBrush(self._color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(int(bx), int(by), int(bar_w), int(bar_h)), 1.5, 1.5)


class NeoFloatingIsland(QWidget):
    """
    Sleek macOS Sequoia / Dynamic Island capsule widget that floats on the desktop.
    """

    mic_toggled = pyqtSignal()
    command_submitted = pyqtSignal(str)
    restore_requested = pyqtSignal()
    lens_requested = pyqtSignal()
    chip_action_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.SubWindow,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._normal_width = 390
        self._expanded_width = 540
        self._height = 46
        self.setFixedSize(self._normal_width, self._height)

        self._drag_pos: Optional[QPoint] = None
        self._is_expanded = False
        self._is_muted = False
        self._current_state = "IDLE"

        root_v = QVBoxLayout(self)
        root_v.setContentsMargins(0, 0, 0, 0)

        # ── Glass Pill Container ─────────────────────────────────────────────
        self.pill = QFrame(self)
        self.pill.setStyleSheet("""
            QFrame {
                background: rgba(10, 14, 23, 0.94);
                border: 1.5px solid rgba(56, 189, 248, 0.35);
                border-radius: 23px;
            }
        """)
        self.pill_lay = QHBoxLayout(self.pill)
        self.pill_lay.setContentsMargins(10, 0, 10, 0)
        self.pill_lay.setSpacing(8)

        # 1. State Orb / Pulse Indicator
        self.orb_btn = QPushButton("⭘")
        self.orb_btn.setFixedSize(28, 28)
        self.orb_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.orb_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.orb_btn.setToolTip("Click to Restore Full Console")
        self.orb_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #38bdf8;
                border: none;
            }
            QPushButton:hover { color: #00e5ff; }
        """)
        self.orb_btn.clicked.connect(self.restore_requested.emit)
        self.pill_lay.addWidget(self.orb_btn)

        # 2. Mini Audio Waveform
        self.waveform = MiniWaveformWidget(self.pill)
        self.pill_lay.addWidget(self.waveform)

        # 3. Stacked Center Area: Label vs Inline Input
        self.center_stack = QStackedLayout()

        # Page 0: Status label & Proactive Pill
        self.status_container = QWidget()
        stat_h = QHBoxLayout(self.status_container)
        stat_h.setContentsMargins(0, 0, 0, 0)
        stat_h.setSpacing(6)

        self.status_lbl = QLabel("NEO Online")
        self.status_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.status_lbl.setStyleSheet("color: #f8fafc; border: none; background: transparent;")
        stat_h.addWidget(self.status_lbl)

        # Optional Proactive Chip (Clickable)
        self.proactive_btn = QPushButton("")
        self.proactive_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.proactive_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.proactive_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 10px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.3);
                color: #ffffff;
            }
        """)
        self.proactive_btn.hide()
        self.proactive_btn.clicked.connect(self._on_proactive_clicked)
        stat_h.addWidget(self.proactive_btn)
        stat_h.addStretch()

        self.center_stack.addWidget(self.status_container)

        # Page 1: Inline Spotlight Command Input
        self.cmd_input = QLineEdit()
        self.cmd_input.setFont(QFont("Segoe UI", 9))
        self.cmd_input.setPlaceholderText("Ask NEO, inspect screen, or type command...")
        self.cmd_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                color: #f8fafc;
                border: 1px solid rgba(56, 189, 248, 0.5);
                border-radius: 12px;
                padding: 3px 10px;
            }
            QLineEdit:focus {
                border: 1.5px solid #38bdf8;
                background: rgba(255, 255, 255, 0.12);
            }
        """)
        self.cmd_input.returnPressed.connect(self._on_input_submitted)
        self.center_stack.addWidget(self.cmd_input)

        self.pill_lay.addLayout(self.center_stack, 1)

        # 4. Action Buttons (Right)
        # 4a. Quick Command Bar Toggle (Prompt icon)
        self.prompt_toggle_btn = QPushButton("⌨")
        self.prompt_toggle_btn.setFixedSize(26, 26)
        self.prompt_toggle_btn.setFont(QFont("Segoe UI", 10))
        self.prompt_toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.prompt_toggle_btn.setToolTip("Type Command (or click status)")
        self.prompt_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 13px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
            }
        """)
        self.prompt_toggle_btn.clicked.connect(self.toggle_expand)
        self.pill_lay.addWidget(self.prompt_toggle_btn)

        # 4b. Screen Lens Trigger (🔍)
        self.lens_btn = QPushButton("🔍")
        self.lens_btn.setFixedSize(26, 26)
        self.lens_btn.setFont(QFont("Segoe UI", 9))
        self.lens_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.lens_btn.setToolTip("Summon Screen Lens (F10 / Ctrl+Shift+L)")
        self.lens_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 13px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.3);
                color: #ffffff;
            }
        """)
        self.lens_btn.clicked.connect(self.lens_requested.emit)
        self.pill_lay.addWidget(self.lens_btn)

        # 4c. Mic Toggle Button
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(26, 26)
        self.mic_btn.setFont(QFont("Segoe UI", 10))
        self.mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(52, 211, 153, 0.15);
                color: #4ade80;
                border: 1px solid rgba(52, 211, 153, 0.35);
                border-radius: 13px;
            }
            QPushButton:hover { background: rgba(52, 211, 153, 0.3); }
        """)
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        self.pill_lay.addWidget(self.mic_btn)

        # 4d. Maximize / Restore Console Button
        expand_btn = QPushButton("↗")
        expand_btn.setFixedSize(26, 26)
        expand_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        expand_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        expand_btn.setToolTip("Open Full Console")
        expand_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 13px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
            }
        """)
        expand_btn.clicked.connect(self.restore_requested.emit)
        self.pill_lay.addWidget(expand_btn)

        root_v.addWidget(self.pill)

        # Initial screen positioning (top center of active screen)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(geom.x() + (geom.width() - self._normal_width) // 2, geom.y() + 16)

    # -------------------------------------------------------------------------
    # Public State API
    # -------------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        """Updates capsule visuals based on assistant state."""
        self._current_state = state.upper()
        if self._current_state == "SPEAKING":
            self.set_status("NEO Speaking...", "#34d399")
            self.orb_btn.setStyleSheet("QPushButton { background: transparent; color: #34d399; border: none; }")
            self.pill.setStyleSheet("""
                QFrame {
                    background: rgba(10, 14, 23, 0.96);
                    border: 1.5px solid rgba(52, 211, 153, 0.5);
                    border-radius: 23px;
                }
            """)
        elif self._current_state == "LISTENING":
            self.set_status("Listening to Boss...", "#38bdf8")
            self.orb_btn.setStyleSheet("QPushButton { background: transparent; color: #38bdf8; border: none; }")
            self.pill.setStyleSheet("""
                QFrame {
                    background: rgba(10, 14, 23, 0.94);
                    border: 1.5px solid rgba(56, 189, 248, 0.45);
                    border-radius: 23px;
                }
            """)
        elif self._current_state == "THINKING":
            self.set_status("Thinking...", "#c084fc")
            self.orb_btn.setStyleSheet("QPushButton { background: transparent; color: #c084fc; border: none; }")
            self.pill.setStyleSheet("""
                QFrame {
                    background: rgba(10, 14, 23, 0.94);
                    border: 1.5px solid rgba(192, 132, 252, 0.45);
                    border-radius: 23px;
                }
            """)
        else:
            self.set_status("NEO Online", "#94a3b8")
            self.orb_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: none; }")
            self.pill.setStyleSheet("""
                QFrame {
                    background: rgba(10, 14, 23, 0.94);
                    border: 1.5px solid rgba(56, 189, 248, 0.25);
                    border-radius: 23px;
                }
            """)

    def set_audio_level(self, level: float) -> None:
        """Passes real-time audio level into mini waveform."""
        if hasattr(self, "waveform") and self.waveform:
            self.waveform.set_level(level, self._current_state)

    def set_status(self, text: str, color: str = "#f8fafc") -> None:
        self.status_lbl.setText(text[:26])
        self.status_lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")

    def set_proactive_chip(self, label: str, payload: str = "") -> None:
        """Displays an actionable proactive chip right on the capsule."""
        if not label:
            self.proactive_btn.hide()
            return
        self.proactive_btn.setText(label[:24])
        self.proactive_btn.setProperty("payload", payload or label)
        self.proactive_btn.show()

    def set_mic_muted(self, muted: bool) -> None:
        self._is_muted = muted
        if muted:
            self.mic_btn.setText("🔇")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(244, 63, 94, 0.2);
                    color: #f43f5e;
                    border: 1px solid rgba(244, 63, 94, 0.4);
                    border-radius: 13px;
                }
            """)
        else:
            self.mic_btn.setText("🎙")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(52, 211, 153, 0.15);
                    color: #4ade80;
                    border: 1px solid rgba(52, 211, 153, 0.4);
                    border-radius: 13px;
                }
            """)

    # -------------------------------------------------------------------------
    # Expand / Spotlight Inline Mode
    # -------------------------------------------------------------------------
    def toggle_expand(self) -> None:
        if self._is_expanded:
            self.collapse_input()
        else:
            self.expand_input()

    def expand_input(self) -> None:
        self._is_expanded = True
        self.setFixedWidth(self._expanded_width)
        self.center_stack.setCurrentIndex(1)
        self.cmd_input.setFocus()
        self.prompt_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.25);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.5);
                border-radius: 13px;
            }
        """)

    def collapse_input(self) -> None:
        self._is_expanded = False
        self.cmd_input.clear()
        self.setFixedWidth(self._normal_width)
        self.center_stack.setCurrentIndex(0)
        self.prompt_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 13px;
            }
        """)

    def _on_input_submitted(self) -> None:
        text = self.cmd_input.text().strip()
        if text:
            self.command_submitted.emit(text)
        self.collapse_input()

    def _on_proactive_clicked(self) -> None:
        payload = str(self.proactive_btn.property("payload") or self.proactive_btn.text())
        self.chip_action_requested.emit(payload)
        self.proactive_btn.hide()

    # -------------------------------------------------------------------------
    # Smooth Snapping & Dragging
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        # Snap to top center if close to the top edge (< 60px)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            if self.y() < geom.y() + 60:
                self.move(geom.x() + (geom.width() - self.width()) // 2, geom.y() + 16)
