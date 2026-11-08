"""
core/neo_chat.py — Modern, next-generation AI Chat Stream for NEO.
Features:
  - Sleek message bubbles (You in green/cyan, NEO in obsidian/blue).
  - Markdown parser for bold, italics, inline code, and bullet lists.
  - Formatted Code Blocks with syntax header & one-click '📋 Copy Code' button.
  - Interactive Action Footers (Copy response, Speak aloud).
  - Compact File Attachment chip bar (replacing bulky drop zone) with drag-and-drop.
  - Quick Prompt Pills (Explain Code, Web Search, Summarize, Telemetry).
  - High-tech rounded capsule input bar matching NEO hero aesthetic.
  - Fully backward-compatible append_log() and speech signal listeners.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Color Palette matching NEO Obsidian Theme
BG_OBSIDIAN = "#0b0f19"
CARD_BG = "rgba(18, 24, 38, 0.90)"
CARD_BORDER = "rgba(96, 165, 250, 0.22)"
TEXT_WHITE = "#f8fafc"
TEXT_MUTED = "#94a3b8"
TEXT_DIM = "#64748b"
ACCENT_CYAN = "#00e5ff"
ACCENT_BLUE = "#60a5fa"
ACCENT_GREEN = "#4ade80"


class CodeBlockWidget(QFrame):
    """Sleek syntax-highlighted code block with language title and one-click Copy button."""

    def __init__(self, code: str, language: str = "CODE", parent=None):
        super().__init__(parent)
        self.code_text = code.strip()
        lang_label = language.strip().upper() if language.strip() else "CODE"

        self.setStyleSheet("""
            QFrame {
                background: #060911;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(6)

        # Header Bar
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        lang_lbl = QLabel(f"💻  {lang_label}")
        lang_lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        lang_lbl.setStyleSheet("color: #8e9eb5; border: none; background: transparent;")
        hdr.addWidget(lang_lbl)

        hdr.addStretch()

        self.copy_btn = QPushButton("📋 Copy Code")
        self.copy_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.setFixedHeight(22)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.copy_btn.clicked.connect(self._copy_code)
        hdr.addWidget(self.copy_btn)

        lay.addLayout(hdr)

        # Code Body
        code_lbl = QLabel(self.code_text)
        code_lbl.setFont(QFont("Consolas", 9))
        code_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code_lbl.setWordWrap(True)
        code_lbl.setStyleSheet("color: #e2e8f0; border: none; background: transparent; padding: 4px 0;")
        lay.addWidget(code_lbl)

    def _copy_code(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.code_text)
        self.copy_btn.setText("✓ Copied!")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 197, 94, 0.25);
                color: #4ade80;
                border: 1px solid #22c55e;
                border-radius: 4px;
                padding: 1px 8px;
            }
        """)
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self.copy_btn.setText("📋 Copy Code")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)


def _format_markdown_prose(text: str) -> str:
    """Transforms markdown bold, italic, inline code, and line breaks into clean HTML."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Bold: **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    # Italic: *text*
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    # Inline code: `text`
    escaped = re.sub(
        r"`([^`]+)`",
        r'<span style="background: rgba(255,255,255,0.08); color: #38bdf8; font-family: Consolas; padding: 1px 4px; border-radius: 3px;">\1</span>',
        escaped,
    )
    # Bullet lists
    escaped = re.sub(r"(?m)^[\*\-]\s+(.+)$", r"&nbsp;•&nbsp; \1", escaped)
    # Newlines
    escaped = escaped.replace("\n", "<br/>")
    return escaped


class NeoChatMessageBubble(QFrame):
    """Interactive individual chat message bubble (User or NEO)."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str = "",
        on_speak_requested=None,
        parent=None,
    ):
        super().__init__(parent)
        self.role = role.lower()
        self.raw_content = content
        self.on_speak = on_speak_requested
        ts = timestamp or datetime.now().strftime("%I:%M %p")

        is_user = self.role in ("user", "you")

        # Outer bubble layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(4)

        # Bubble card frame
        card = QFrame()
        if is_user:
            card.setStyleSheet("""
                QFrame {
                    background: rgba(16, 185, 129, 0.12);
                    border: 1px solid rgba(52, 211, 153, 0.35);
                    border-radius: 14px;
                    border-bottom-right-radius: 3px;
                }
            """)
        else:
            card.setStyleSheet(f"""
                QFrame {{
                    background: {CARD_BG};
                    border: 1px solid {CARD_BORDER};
                    border-radius: 14px;
                    border-bottom-left-radius: 3px;
                }}
            """)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(6)

        # Header: Speaker Name + Timestamp
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        if is_user:
            hdr.addStretch()
            ts_lbl = QLabel(ts)
            ts_lbl.setFont(QFont("Segoe UI", 7))
            ts_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
            hdr.addWidget(ts_lbl)

            name_lbl = QLabel("You")
            name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; border: none; background: transparent;")
            hdr.addWidget(name_lbl)
        else:
            dot = QLabel("●")
            dot.setFont(QFont("Segoe UI", 8))
            dot.setStyleSheet(f"color: {ACCENT_CYAN}; border: none; background: transparent;")
            hdr.addWidget(dot)

            name_lbl = QLabel("NEO")
            name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            name_lbl.setStyleSheet(f"color: {ACCENT_BLUE}; border: none; background: transparent;")
            hdr.addWidget(name_lbl)

            ts_lbl = QLabel(ts)
            ts_lbl.setFont(QFont("Segoe UI", 7))
            ts_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
            hdr.addWidget(ts_lbl)
            hdr.addStretch()

        card_lay.addLayout(hdr)

        # Content Rendering (Prose & Code Blocks)
        if is_user:
            txt_lbl = QLabel(_format_markdown_prose(content))
            txt_lbl.setFont(QFont("Segoe UI", 9))
            txt_lbl.setWordWrap(True)
            txt_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            txt_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; line-height: 140%;")
            card_lay.addWidget(txt_lbl)
        else:
            # Parse code blocks (```lang ... ```)
            parts = re.split(r"```([a-zA-Z0-9_\-\+]*)\r?\n(.*?)```", content, flags=re.DOTALL)
            if len(parts) > 1:
                i = 0
                while i < len(parts):
                    prose = parts[i].strip()
                    if prose:
                        p_lbl = QLabel(_format_markdown_prose(prose))
                        p_lbl.setFont(QFont("Segoe UI", 9))
                        p_lbl.setWordWrap(True)
                        p_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                        p_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
                        card_lay.addWidget(p_lbl)

                    if i + 2 < len(parts):
                        lang = parts[i + 1].strip() or "CODE"
                        code = parts[i + 2].strip()
                        card_lay.addWidget(CodeBlockWidget(code, lang))
                        i += 3
                    else:
                        break
            else:
                txt_lbl = QLabel(_format_markdown_prose(content))
                txt_lbl.setFont(QFont("Segoe UI", 9))
                txt_lbl.setWordWrap(True)
                txt_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                txt_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
                card_lay.addWidget(txt_lbl)

            # Action Footer for NEO response
            footer = QHBoxLayout()
            footer.setContentsMargins(0, 4, 0, 0)
            footer.setSpacing(8)

            def _btn(lbl_text: str, cb):
                b = QPushButton(lbl_text)
                b.setFont(QFont("Segoe UI", 7))
                b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                b.setFixedHeight(20)
                b.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #8e9eb5;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 3px;
                        padding: 1px 7px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.06);
                        color: #ffffff;
                    }
                """)
                b.clicked.connect(cb)
                return b

            self.copy_btn = _btn("📋 Copy", self._copy_msg)
            footer.addWidget(self.copy_btn)

            if self.on_speak:
                speak_b = _btn("🔊 Speak", lambda: self.on_speak(self.raw_content))
                footer.addWidget(speak_b)

            footer.addStretch()
            card_lay.addLayout(footer)

        # Alignment
        h_row = QHBoxLayout()
        h_row.setContentsMargins(0, 0, 0, 0)
        if is_user:
            h_row.addStretch()
            h_row.addWidget(card, stretch=0)
        else:
            h_row.addWidget(card, stretch=0)
            h_row.addStretch()

        outer.addLayout(h_row)

    def _copy_msg(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.raw_content)
        self.copy_btn.setText("✓ Copied!")
        QTimer.singleShot(1800, lambda: self.copy_btn.setText("📋 Copy"))


class SystemPillWidget(QWidget):
    """Subtle centered pill for telemetry and status messages."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)

        pill = QLabel(text)
        pill.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
        pill.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.04);
                color: #8e9eb5;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 9px;
                padding: 2px 10px;
            }
        """)
        lay.addStretch()
        lay.addWidget(pill)
        lay.addStretch()


class NeoModernChatWidget(QWidget):
    """
    Modern AI Chat Stream replacing the legacy log widget and large drop zone.
    Provides message bubbles, code copy blocks, compact file attachments, quick prompt pills,
    and a high-tech prompt bar matching the NEO aesthetic.
    """

    command_submitted = pyqtSignal(str)
    file_selected = pyqtSignal(str)
    mic_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_name_lc = "neo"
        self._current_file: Optional[str] = None
        self._last_content: Optional[tuple[str, str]] = None
        self.setAcceptDrops(True)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(10)

        # 1. Header Bar
        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 0, 4, 0)
        hdr.setSpacing(8)

        chat_icn = QLabel("💬")
        chat_icn.setFont(QFont("Segoe UI", 12))
        hdr.addWidget(chat_icn)

        t_vbox = QVBoxLayout()
        t_vbox.setSpacing(1)
        ttl = QLabel("NEO Conversation Stream")
        ttl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        t_vbox.addWidget(ttl)

        sub_m = QLabel("Gemini 1.5 Pro · Interactive Dialogue")
        sub_m.setFont(QFont("Segoe UI", 7))
        sub_m.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        t_vbox.addWidget(sub_m)
        hdr.addLayout(t_vbox)

        hdr.addStretch()

        clear_b = QPushButton("🗑 Clear Stream")
        clear_b.setFont(QFont("Segoe UI", 8))
        clear_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_b.setFixedHeight(26)
        clear_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #8e9eb5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 5px;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background: rgba(244, 63, 94, 0.15);
                border-color: #f43f5e;
                color: #ffffff;
            }
        """)
        clear_b.clicked.connect(self.clear_stream)
        hdr.addWidget(clear_b)

        root.addLayout(hdr)

        # 2. Scrollable Messages Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 165, 250, 0.25);
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(56, 189, 248, 0.6);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background: transparent;")
        self.msg_layout = QVBoxLayout(self.messages_container)
        self.msg_layout.setContentsMargins(4, 4, 10, 4)
        self.msg_layout.setSpacing(10)
        self.msg_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        root.addWidget(self.scroll_area, stretch=1)

        # 3. Compact Attachment Chip Bar (hidden until file attached)
        self.chip_frame = QFrame()
        self.chip_frame.setVisible(False)
        self.chip_frame.setStyleSheet("""
            QFrame {
                background: rgba(56, 189, 248, 0.08);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 8px;
            }
        """)
        chip_lay = QHBoxLayout(self.chip_frame)
        chip_lay.setContentsMargins(10, 4, 10, 4)
        chip_lay.setSpacing(8)

        self.chip_lbl = QLabel("")
        self.chip_lbl.setFont(QFont("Segoe UI", 8))
        self.chip_lbl.setStyleSheet(f"color: {ACCENT_CYAN}; border: none; background: transparent;")
        chip_lay.addWidget(self.chip_lbl)

        chip_lay.addStretch()

        remove_chip_b = QPushButton("✕")
        remove_chip_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        remove_chip_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        remove_chip_b.setFixedSize(20, 20)
        remove_chip_b.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8e9eb5; border: none;
            }
            QPushButton:hover { color: #f43f5e; }
        """)
        remove_chip_b.clicked.connect(self._clear_attached_file)
        chip_lay.addWidget(remove_chip_b)

        root.addWidget(self.chip_frame)

        # 4. Quick Prompt Pills
        pills_row = QHBoxLayout()
        pills_row.setContentsMargins(4, 0, 4, 0)
        pills_row.setSpacing(8)

        def _pill(text: str, prompt: str):
            b = QPushButton(text)
            b.setFont(QFont("Segoe UI", 8))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(24)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #8e9eb5;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    padding: 2px 10px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.15);
                    border-color: #38bdf8;
                    color: #ffffff;
                }
            """)
            b.clicked.connect(lambda: self._apply_quick_pill(prompt))
            return b

        pills_row.addWidget(_pill("💡 Explain Code", "Explain the following code: "))
        pills_row.addWidget(_pill("🔍 Web Search", "Search the web for: "))
        pills_row.addWidget(_pill("📝 Summarize", "Summarize this: "))
        pills_row.addWidget(_pill("📊 System Health", "Check system status and telemetry."))
        pills_row.addWidget(_pill("🎯 Plan Day", "Review my upcoming schedule and plan my day."))
        pills_row.addStretch()

        root.addLayout(pills_row)

        # 5. Bottom Prompt Capsule Input Bar
        bar_frame = QFrame()
        bar_frame.setFixedHeight(50)
        bar_frame.setStyleSheet("""
            QFrame {
                background: rgba(18, 24, 38, 0.95);
                border: 1.5px solid rgba(120, 160, 255, 0.25);
                border-radius: 25px;
            }
        """)
        bar_lay = QHBoxLayout(bar_frame)
        bar_lay.setContentsMargins(12, 0, 10, 0)
        bar_lay.setSpacing(8)

        # Paperclip Attachment Button
        attach_btn = QPushButton("📎")
        attach_btn.setToolTip("Attach file or document (Images, Code, PDFs)")
        attach_btn.setFixedSize(30, 30)
        attach_btn.setFont(QFont("Segoe UI", 12))
        attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        attach_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8e9eb5;
                border: none;
            }
            QPushButton:hover {
                color: #38bdf8;
            }
        """)
        attach_btn.clicked.connect(self._browse_file)
        bar_lay.addWidget(attach_btn)

        # Input Edit Box
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Send a message to NEO...")
        self.input_edit.setFont(QFont("Segoe UI", 9))
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_WHITE};
                padding: 0 4px;
            }}
            QLineEdit::placeholder {{
                color: #61728d;
            }}
        """)
        self.input_edit.returnPressed.connect(self._submit)
        bar_lay.addWidget(self.input_edit, stretch=1)

        # Mic Button
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setToolTip("Toggle Voice Mic")
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setFont(QFont("Segoe UI", 11))
        self.mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8e9eb5;
                border: none;
            }
            QPushButton:hover {
                color: #4ade80;
            }
        """)
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        bar_lay.addWidget(self.mic_btn)

        # Send Button
        send_btn = QPushButton("➤")
        send_btn.setToolTip("Send message")
        send_btn.setFixedSize(32, 32)
        send_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        send_btn.setStyleSheet("""
            QPushButton {
                background: #00e5ff;
                color: #0b0f19;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover {
                background: #38bdf8;
            }
        """)
        send_btn.clicked.connect(self._submit)
        bar_lay.addWidget(send_btn)

        root.addWidget(bar_frame)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API for DropZone Compatibility & Logging Listeners
    # ─────────────────────────────────────────────────────────────────────────
    def current_file(self) -> Optional[str]:
        return self._current_file

    def clear_file(self):
        self._clear_attached_file()

    def append_log(self, text: str):
        """Thread-safe drop-in handler for all legacy self._log.append_log() calls."""
        if not text:
            return
        clean = text.strip()
        tl = clean.lower()

        if tl.startswith("user: ") or tl.startswith("you: "):
            content = clean.split(": ", 1)[1]
            self.add_message("user", content)
        elif tl.startswith(f"{self._ai_name_lc}: ") or tl.startswith("jarvis: ") or tl.startswith("neo: "):
            content = clean.split(": ", 1)[1]
            self.add_message("neo", content)
        elif tl.startswith("file: "):
            self.add_system_pill(f"📁 {clean}")
        elif tl.startswith("sys: ") or tl.startswith("err: ") or "mode" in tl:
            self.add_system_pill(clean)
        else:
            self.add_message("neo", clean)

    def add_message(self, role: str, content: str):
        """Appends a new message bubble to the stream and auto-scrolls down."""
        clean = content.strip()
        if not clean:
            return
        # Deduplicate identical consecutive messages
        if self._last_content == (role.lower(), clean):
            return
        self._last_content = (role.lower(), clean)

        count = self.msg_layout.count()
        bubble = NeoChatMessageBubble(
            role=role,
            content=clean,
            on_speak_requested=self._on_speak_requested,
            parent=self.messages_container,
        )
        self.msg_layout.insertWidget(max(0, count - 1), bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_system_pill(self, text: str):
        count = self.msg_layout.count()
        pill = SystemPillWidget(text, parent=self.messages_container)
        self.msg_layout.insertWidget(max(0, count - 1), pill)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def clear_stream(self):
        """Clears all conversation bubbles except the bottom stretch."""
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._last_content = None
        self.add_system_pill("SYS: Conversation stream cleared.")

    def set_attached_file(self, file_path: str):
        """Sets the compact attached file chip."""
        self._current_file = file_path
        p = Path(file_path)
        sz = p.stat().st_size if p.exists() else 0
        sz_str = f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B"
        self.chip_lbl.setText(f"📄  {p.name}  ({sz_str})  ·  Attached")
        self.chip_frame.setVisible(True)

    def _clear_attached_file(self):
        self._current_file = None
        self.chip_frame.setVisible(False)

    def _browse_file(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Attach file to NEO", "", "All Files (*.*)")
        if fpath:
            self.set_attached_file(fpath)
            self.file_selected.emit(fpath)

    def _apply_quick_pill(self, prompt: str):
        self.input_edit.setText(prompt)
        self.input_edit.setFocus()

    def _submit(self):
        txt = self.input_edit.text().strip()
        if not txt and not self._current_file:
            return

        full_cmd = txt
        if self._current_file:
            p = Path(self._current_file)
            if not txt:
                full_cmd = f"Please examine and analyze this file: {p.name}"
            self._clear_attached_file()

        self.input_edit.clear()
        self.add_message("user", full_cmd)
        self.command_submitted.emit(full_cmd)

    def _on_speak_requested(self, text: str):
        self.command_submitted.emit(f"Say aloud: {text[:200]}")

    def _scroll_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    # Drag and Drop handlers
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            fpath = urls[0].toLocalFile()
            if os.path.exists(fpath):
                self.set_attached_file(fpath)
                self.file_selected.emit(fpath)
                event.acceptProposedAction()
