"""
core/floating_island.py — Stark Floating Desktop Voice Capsule & Mini-HUD.
A sleek, draggable, always-on-top dynamic capsule that stays on your desktop
when NEO's main window is minimized:
- Real-time listening indicator & state pulsing.
- Compact quick-prompt bar & mic toggle.
- One-click restore to main HUD window.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class NeoFloatingIsland(QWidget):
    """Sleek draggable dynamic island capsule widget that floats on the desktop."""

    mic_toggled = pyqtSignal()
    command_submitted = pyqtSignal(str)
    restore_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(320, 48)

        self._drag_pos: QPoint | None = None
        self._is_expanded = False
        self._is_muted = False

        root_v = QVBoxLayout(self)
        root_v.setContentsMargins(0, 0, 0, 0)

        self.pill = QFrame(self)
        self.pill.setStyleSheet("""
            QFrame {
                background: rgba(9, 13, 22, 0.96);
                border: 1.5px solid rgba(0, 229, 255, 0.40);
                border-radius: 24px;
            }
        """)
        pill_lay = QHBoxLayout(self.pill)
        pill_lay.setContentsMargins(12, 0, 10, 0)
        pill_lay.setSpacing(8)

        # 1. Glowing Logo / Restore Trigger
        self.orb_btn = QPushButton("⭘")
        self.orb_btn.setFixedSize(26, 26)
        self.orb_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.orb_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.orb_btn.setToolTip("Restore Main NEO Window")
        self.orb_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #00e5ff; border: none;
            }
            QPushButton:hover { color: #38bdf8; }
        """)
        self.orb_btn.clicked.connect(self.restore_requested.emit)
        pill_lay.addWidget(self.orb_btn)

        # 2. Status Label or Mini Prompt Input
        self.status_lbl = QLabel("NEO Online")
        self.status_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.status_lbl.setStyleSheet("color: #f8fafc; border: none; background: transparent;")
        pill_lay.addWidget(self.status_lbl)

        pill_lay.addStretch()

        # 3. Mic Toggle
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(26, 26)
        self.mic_btn.setFont(QFont("Segoe UI", 10))
        self.mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #4ade80;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 13px;
            }
            QPushButton:hover { background: rgba(52, 211, 153, 0.2); }
        """)
        self.mic_btn.clicked.connect(self._on_mic_click)
        pill_lay.addWidget(self.mic_btn)

        # 4. Maximize / Restore Button
        expand_btn = QPushButton("↗")
        expand_btn.setFixedSize(26, 26)
        expand_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        expand_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        expand_btn.setToolTip("Open Full NEO Console")
        expand_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 13px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
            }
        """)
        expand_btn.clicked.connect(self.restore_requested.emit)
        pill_lay.addWidget(expand_btn)

        root_v.addWidget(self.pill)

        # Initial screen positioning (top center of active screen)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(geom.x() + (geom.width() - self.width()) // 2, geom.y() + 18)

    def set_status(self, text: str, color: str = "#f8fafc"):
        self.status_lbl.setText(text[:24])
        self.status_lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")

    def set_mic_muted(self, muted: bool):
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

    def _on_mic_click(self):
        self.mic_toggled.emit()

    # Dragging logic
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

