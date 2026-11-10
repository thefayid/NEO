"""
core/macos_conversation.py — Minimalist Apple macOS Native Conversation View.

Senior Design Engineering Specification (Phase 5):
1. Message Bubbles:
   - Zero avatars or emoji icons ("👤 You", "⭘ NEO AI" omitted for clean Apple HIG minimalism).
   - Subtle tonal difference using semantic tokens:
     - User bubble: theme.colors.controlBackgroundSecondary with subtle 1px border.
     - Assistant bubble: theme.colors.controlBackground with 1px separator border.
   - 10px continuous corner radius (theme.radii.md).
   - SF Body (13pt, -0.01em tracking) for message prose.
   - SF Caption (10pt) for right-aligned subtle timestamp.
2. Monospace Command Output & Code Blocks:
   - Dedicated macOS Terminal-style card container with 8px radius.
   - SF Mono / Menlo / Consolas font at 12px with 1.45 line height.
   - Top chrome bar: syntax label, copy button, status dot.
   - Zero hardcoded colors; strictly uses theme tokens.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Callable

from PyQt6.QtCore import Qt, QPoint, QRectF, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy
)

from core.theme_provider import theme
from core.macos_components import MacOSButton, MacOSScrollArea, render_lucide_icon


class MacOSCommandOutputBlock(QFrame):
    """
    Minimalist macOS Monospace Block for terminal command output and code snippets.
    SF Mono typography, 8px radius, subtle border, and instant copy button.
    """
    def __init__(self, code_text: str, language: str = "COMMAND", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.code_text = code_text.strip()
        self._language = language.upper()

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(6)

        # Header Chrome
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        # Status Dot
        self.dot = QLabel(self)
        self.dot.setFixedSize(7, 7)
        self.dot.setStyleSheet(f"background-color: {theme.accent_color}; border-radius: 3.5px;")
        hdr.addWidget(self.dot)

        # Language / Command Label
        self.lbl_lang = QLabel(self._language, self)
        self.lbl_lang.setFont(theme.font(theme.typography.caption_2, QFont.Weight.DemiBold))
        self.lbl_lang.setStyleSheet(f"color: {theme.colors.labelSecondary}; letter-spacing: 0.5px; border: none; background: transparent;")
        hdr.addWidget(self.lbl_lang)

        hdr.addStretch()

        # Copy Button
        self.btn_copy = QPushButton("Copy", self)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setFont(theme.font(theme.typography.caption_2))
        self.btn_copy.setFixedHeight(20)
        self.btn_copy.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.controlBackground};
                color: {theme.colors.labelSecondary};
                border: 1px solid {theme.colors.separator};
                border-radius: 4px;
                padding: 1px 8px;
            }}
            QPushButton:hover {{
                background-color: {theme.colors.cardBackgroundHover};
                color: {theme.colors.labelPrimary};
            }}
        """)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        hdr.addWidget(self.btn_copy)

        lay.addLayout(hdr)

        # Monospace Code Label
        self.lbl_code = QLabel(self.code_text, self)
        mono_font = QFont("SF Mono", 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.lbl_code.setFont(mono_font)
        self.lbl_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_code.setWordWrap(True)
        self.lbl_code.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none; padding: 2px 0;")
        lay.addWidget(self.lbl_code)

    def _apply_style(self):
        r = theme.radii.sm
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackgroundSecondary};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)

    def _copy_to_clipboard(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.code_text)
        self.btn_copy.setText("Copied")
        self.btn_copy.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.colors.controlBackground};
                color: {theme.colors.systemGreen};
                border: 1px solid {theme.colors.systemGreen};
                border-radius: 4px;
                padding: 1px 8px;
            }}
        """)


class MacOSMessageBubble(QFrame):
    """
    Clean, minimal Apple HIG conversation message bubble.
    No avatars, subtle tonal difference, 10px continuous radius.
    """
    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.role = role.lower()
        self.is_user = self.role in ("user", "you")
        self.content_text = content
        self.ts = timestamp or datetime.now().strftime("%I:%M %p")

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 3, 0, 3)
        outer_lay.setSpacing(0)

        # Message Container Card
        self.card = QFrame(self)
        self.card.setMaximumWidth(780)

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(6)

        # Header (Timestamp only, right-aligned for user, left-aligned for assistant)
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)

        self.lbl_role = QLabel("You" if self.is_user else "NEO", self.card)
        self.lbl_role.setFont(theme.font(theme.typography.caption_1, QFont.Weight.DemiBold))
        self.lbl_role.setStyleSheet(f"color: {theme.accent_color if not self.is_user else theme.colors.labelSecondary}; background: transparent; border: none;")

        self.lbl_ts = QLabel(self.ts, self.card)
        self.lbl_ts.setFont(theme.font(theme.typography.caption_2))
        self.lbl_ts.setStyleSheet(f"color: {theme.colors.labelTertiary}; background: transparent; border: none;")

        if self.is_user:
            hdr.addStretch()
            hdr.addWidget(self.lbl_ts)
            hdr.addWidget(self.lbl_role)
        else:
            hdr.addWidget(self.lbl_role)
            hdr.addWidget(self.lbl_ts)
            hdr.addStretch()

        card_lay.addLayout(hdr)

        # Parse content for code blocks or plain text
        self._build_content(card_lay)

        # Align card left or right
        if self.is_user:
            outer_lay.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignRight)
        else:
            outer_lay.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignLeft)

    def _apply_style(self):
        r = theme.radii.md
        if self.is_user:
            # Subtle tonal difference: elevated secondary control background
            bg = theme.colors.controlBackgroundSecondary
            border = theme.colors.separator
        else:
            # Subtle tonal difference: window control card
            bg = theme.colors.controlBackground
            border = theme.colors.separator

        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {r}px;
            }}
        """)

    def _build_content(self, card_lay: QVBoxLayout):
        parts = self.content_text.split("```")
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                # Monospace block
                lines = part.strip().split("\n")
                lang = "CODE"
                code_body = part
                if lines and lines[0].strip().isalpha():
                    lang = lines[0].strip().upper()
                    code_body = "\n".join(lines[1:])
                block = MacOSCommandOutputBlock(code_body, language=lang, parent=self.card)
                card_lay.addWidget(block)
            else:
                txt = part.strip()
                if txt:
                    lbl = QLabel(txt, self.card)
                    lbl.setFont(theme.font(theme.typography.body))
                    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none; line-height: 140%;")
                    card_lay.addWidget(lbl)


class MacOSConversationView(QWidget):
    """
    Apple HIG Scrollable Conversation Feed.
    Manages message bubbles, auto-scrolling, and minimal clean aesthetics.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("macOSConversationView")

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        self.scroll_area = MacOSScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        outer_lay.addWidget(self.scroll_area)

        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        self.messages_lay = QVBoxLayout(self.content_widget)
        self.messages_lay.setContentsMargins(18, 16, 18, 16)
        self.messages_lay.setSpacing(12)
        self.messages_lay.addStretch()

        self._bubbles: List[MacOSMessageBubble] = []

    def add_message(self, role: str, content: str, timestamp: Optional[str] = None) -> MacOSMessageBubble:
        bubble = MacOSMessageBubble(role, content, timestamp=timestamp, parent=self.content_widget)
        # Insert before stretch
        self.messages_lay.insertWidget(self.messages_lay.count() - 1, bubble)
        self._bubbles.append(bubble)
        self.scroll_to_bottom()
        return bubble

    def clear(self):
        while self.messages_lay.count() > 1:
            item = self.messages_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._bubbles.clear()

    def scroll_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())
