"""
core/neo_chat.py — Comprehensive Next-Gen AI Chat Command Center for NEO.

Features:
  1. Multi-Chat Sessions & History Drawer (Save, switch, create, and delete conversations).
  2. Floating Slash Commands (/) popup menu (/code, /research, /spotify, /brief, /notes, /clear).
  3. Model & Reasoning Mode Switcher (Fast vs Pro vs Local Ollama) + Auto-Voice toggle.
  4. Live Tool Execution & Thought Process Accordion with expandable inspector.
  5. "Save to Notes" quick memory pinning & Star bookmarking.
  6. Rich Web & Media Cards for auto-detected URLs with one-click browser launch.
  7. Formatted Code Blocks with syntax titles and instant copy buttons.
  8. Compact File Attachment chip bar with full drag-and-drop support.
  9. Export conversation to Markdown (.md) report.
  10. Smart In-Place Streaming Text Updates (avoids creating duplicate bubbles during speech/token stream).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QDesktopServices, QFont, QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

BG_OBSIDIAN = "#0b0f19"
CARD_BG = "rgba(18, 24, 38, 0.92)"
CARD_BORDER = "rgba(96, 165, 250, 0.22)"
TEXT_WHITE = "#f8fafc"
TEXT_MUTED = "#94a3b8"
TEXT_DIM = "#64748b"
ACCENT_CYAN = "#00e5ff"
ACCENT_BLUE = "#60a5fa"
ACCENT_GREEN = "#4ade80"
ACCENT_AMBER = "#fbbf24"

_BASE_DIR = Path(__file__).resolve().parent.parent
_SESSIONS_FILE = _BASE_DIR / "memory" / "chat_sessions.json"
_EXPORTS_DIR = _BASE_DIR / "memory" / "exports"


# ─────────────────────────────────────────────────────────────────────────────
#  1. CODE BLOCK WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class CodeBlockWidget(QFrame):
    """Sleek syntax-highlighted code block with macOS-style window dots and copy feedback."""
    canvas_requested = pyqtSignal(str, str)

    def __init__(self, code: str, language: str = "CODE", parent=None):
        super().__init__(parent)
        self.code_text = code.strip()
        lang_label = language.strip().upper() if language.strip() else "CODE"

        self.setStyleSheet("""
            QFrame {
                background: #060912;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 10px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)

        dot_box = QHBoxLayout()
        dot_box.setSpacing(5)
        for c in ("#ef4444", "#f59e0b", "#10b981"):
            d = QLabel()
            d.setFixedSize(8, 8)
            d.setStyleSheet(f"background: {c}; border-radius: 4px;")
            dot_box.addWidget(d)
        hdr.addLayout(dot_box)
        hdr.addSpacing(6)

        lang_lbl = QLabel(lang_label)
        lang_lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        lang_lbl.setStyleSheet("color: #38bdf8; border: none; background: transparent; letter-spacing: 0.5px;")
        hdr.addWidget(lang_lbl)

        hdr.addStretch()

        self.canvas_btn = QPushButton("✦ Canvas")
        self.canvas_btn.setToolTip("Open in Interactive Sandbox & Preview Canvas")
        self.canvas_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.canvas_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.canvas_btn.setFixedHeight(22)
        self.canvas_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.12);
                color: #00e5ff;
                border: 1px solid rgba(0, 229, 255, 0.3);
                border-radius: 5px;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.25);
                color: #ffffff;
            }
        """)
        self.canvas_btn.clicked.connect(lambda: self.canvas_requested.emit(self.code_text, lang_label))
        hdr.addWidget(self.canvas_btn)

        self.copy_btn = QPushButton("📋 Copy Code")
        self.copy_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.setFixedHeight(22)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 5px;
                padding: 1px 10px;
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

        code_lbl = QLabel(self.code_text)
        code_lbl.setFont(QFont("Consolas", 9))
        code_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code_lbl.setWordWrap(True)
        code_lbl.setStyleSheet("color: #e2e8f0; border: none; background: transparent; padding: 6px 0; line-height: 140%;")
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


# ─────────────────────────────────────────────────────────────────────────────
#  2. WEB & MEDIA CARD WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class WebLinkCard(QFrame):
    """Rich interactive card preview for URLs in assistant messages."""

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QFrame#WebLinkCard {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 8px;
            }
            QFrame#WebLinkCard:hover {
                border-color: #38bdf8;
                background: rgba(22, 33, 56, 0.95);
            }
        """)
        self.setObjectName("WebLinkCard")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(10)

        icn = QLabel("🌐")
        icn.setFont(QFont("Segoe UI", 11))
        lay.addWidget(icn)

        domain = "Web Resource"
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or domain
        except Exception:
            pass

        vbox = QVBoxLayout()
        vbox.setSpacing(1)
        dom_lbl = QLabel(domain)
        dom_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        dom_lbl.setStyleSheet(f"color: {ACCENT_CYAN}; border: none; background: transparent;")
        vbox.addWidget(dom_lbl)

        clean_url = url[:50] + ("..." if len(url) > 50 else "")
        url_lbl = QLabel(clean_url)
        url_lbl.setFont(QFont("Segoe UI", 7))
        url_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        vbox.addWidget(url_lbl)
        lay.addLayout(vbox)

        lay.addStretch()

        open_lbl = QLabel("Open ↗")
        open_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        open_lbl.setStyleSheet("color: #60a5fa; border: none; background: transparent;")
        lay.addWidget(open_lbl)

    def mousePressEvent(self, e):
        QDesktopServices.openUrl(QUrl(self.url))


# ─────────────────────────────────────────────────────────────────────────────
#  3. LIVE TOOL EXECUTION ACCORDION
# ─────────────────────────────────────────────────────────────────────────────
class ToolExecutionAccordion(QFrame):
    """Collapsible Thought & Tool call inspection drawer."""

    def __init__(self, tool_name: str, details: str = "", parent=None):
        super().__init__(parent)
        self.tool_name = tool_name
        self.details = details or f"Backend tool call '{tool_name}' completed."
        self.is_expanded = False

        self.setStyleSheet("""
            QFrame#ToolExecutionAccordion {
                background: rgba(15, 23, 42, 0.65);
                border: 1px solid rgba(56, 189, 248, 0.20);
                border-radius: 8px;
            }
        """)
        self.setObjectName("ToolExecutionAccordion")

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(10, 6, 10, 6)
        self.lay.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        gear = QLabel("⚙️")
        gear.setFont(QFont("Segoe UI", 9))
        hdr.addWidget(gear)

        title = QLabel(f"Tool Execution: <span style='color: #38bdf8; font-weight:600;'>{tool_name}</span>")
        title.setFont(QFont("Segoe UI", 8))
        title.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        hdr.addWidget(title)

        hdr.addStretch()

        self.toggle_btn = QPushButton("▼ Inspect")
        self.toggle_btn.setFont(QFont("Segoe UI", 7))
        self.toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_btn.setFixedHeight(20)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 3px;
                padding: 1px 6px;
            }
            QPushButton:hover {
                color: #38bdf8;
                border-color: #38bdf8;
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle_expand)
        hdr.addWidget(self.toggle_btn)
        self.lay.addLayout(hdr)

        self.body = QFrame()
        self.body.setVisible(False)
        self.body.setStyleSheet("""
            QFrame {
                background: #060911;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                padding: 6px;
            }
        """)
        b_lay = QVBoxLayout(self.body)
        b_lay.setContentsMargins(8, 6, 8, 6)

        ts_now = datetime.now().strftime("%H:%M:%S")
        txt = QLabel(f"Status: Complete [OK]\nTimestamp: {ts_now}\nTool: {self.tool_name}\nPayload: {self.details}")
        txt.setFont(QFont("Consolas", 8))
        txt.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        b_lay.addWidget(txt)

        self.lay.addWidget(self.body)

    def _toggle_expand(self):
        self.is_expanded = not self.is_expanded
        self.body.setVisible(self.is_expanded)
        self.toggle_btn.setText("▲ Collapse" if self.is_expanded else "▼ Inspect")


# ─────────────────────────────────────────────────────────────────────────────
#  4. CHAT MESSAGE BUBBLE (Supports in-place streaming updates)
# ─────────────────────────────────────────────────────────────────────────────
def _format_markdown_prose(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(
        r"`([^`]+)`",
        r'<span style="background: rgba(255,255,255,0.08); color: #38bdf8; font-family: Consolas; padding: 1px 4px; border-radius: 3px;">\1</span>',
        escaped,
    )
    escaped = re.sub(r"(?m)^[\*\-]\s+(.+)$", r"&nbsp;•&nbsp; \1", escaped)
    escaped = escaped.replace("\n", "<br/>")
    return escaped


class ChatWelcomeView(QWidget):
    """Futuristic zero-state command center shown when a conversation has no messages."""
    prompt_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 30, 20, 20)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        orb = QLabel("⭘")
        orb.setFont(QFont("Segoe UI", 36))
        orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb.setStyleSheet("color: #00e5ff; background: transparent; border: none;")
        lay.addWidget(orb)

        title = QLabel("NEO Intelligence Command Center")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #f8fafc; letter-spacing: -0.3px; background: transparent; border: none;")
        lay.addWidget(title)

        sub = QLabel("Autonomous multimodal assistant ready to inspect code, research, and execute workflows.")
        sub.setFont(QFont("Segoe UI", 9))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        lay.addWidget(sub)

        lay.addSpacing(14)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        cards = [
            ("⚡ Code Diagnostics", "Debug compiler tracebacks and refactor modules", "/code "),
            ("🔍 Deep Web Research", "Synthesize live web searches with citations", "/research "),
            ("📅 Schedule & Briefing", "Review today's agenda and plan daily priorities", "/brief"),
            ("📷 Vision & Optical", "Check camera feed or inspect screen errors", "Look at this on camera and describe what you see"),
        ]

        for idx, (t, d, p) in enumerate(cards):
            card = QFrame()
            card.setFixedWidth(290)
            card.setFixedHeight(66)
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            card.setStyleSheet("""
                QFrame {
                    background: rgba(18, 26, 42, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }
                QFrame:hover {
                    background: rgba(56, 189, 248, 0.14);
                    border-color: rgba(56, 189, 248, 0.40);
                }
            """)
            c_v = QVBoxLayout(card)
            c_v.setContentsMargins(14, 10, 14, 10)
            c_v.setSpacing(2)

            t_lbl = QLabel(t)
            t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            t_lbl.setStyleSheet("color: #38bdf8; background: transparent; border: none;")
            c_v.addWidget(t_lbl)

            d_lbl = QLabel(d)
            d_lbl.setFont(QFont("Segoe UI", 7))
            d_lbl.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            c_v.addWidget(d_lbl)

            card.mousePressEvent = lambda e, pr=p: self.prompt_selected.emit(pr)
            r = idx // 2
            c = idx % 2
            grid.addWidget(card, r, c)

        grid_box = QHBoxLayout()
        grid_box.addStretch()
        grid_box.addWidget(grid_w)
        grid_box.addStretch()
        lay.addLayout(grid_box)
        lay.addStretch()


class NeoChatMessageBubble(QFrame):
    """Interactive individual chat message bubble with in-place streaming re-rendering."""
    canvas_requested = pyqtSignal(str, str)

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
        self.is_starred = False

        self.is_user = self.role in ("user", "you")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(4)

        card = QFrame()
        card.setMaximumWidth(820)
        if self.is_user:
            card.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(14, 165, 233, 0.18), stop:1 rgba(37, 99, 235, 0.14));
                    border: 1px solid rgba(56, 189, 248, 0.32);
                    border-radius: 16px;
                    border-bottom-right-radius: 4px;
                }
            """)
        else:
            card.setStyleSheet("""
                QFrame {
                    background: rgba(14, 20, 34, 0.90);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 16px;
                    border-bottom-left-radius: 4px;
                }
            """)

        self.card_lay = QVBoxLayout(card)
        self.card_lay.setContentsMargins(14, 10, 14, 10)
        self.card_lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        if self.is_user:
            hdr.addStretch()
            ts_lbl = QLabel(ts)
            ts_lbl.setFont(QFont("Segoe UI", 7))
            ts_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
            hdr.addWidget(ts_lbl)

            name_lbl = QLabel("👤 You")
            name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            name_lbl.setStyleSheet("color: #38bdf8; border: none; background: transparent;")
            hdr.addWidget(name_lbl)
        else:
            dot = QLabel("⭘")
            dot.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            dot.setStyleSheet("color: #00e5ff; border: none; background: transparent;")
            hdr.addWidget(dot)

            name_lbl = QLabel("NEO")
            name_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            name_lbl.setStyleSheet("color: #38bdf8; border: none; background: transparent; letter-spacing: 0.5px;")
            hdr.addWidget(name_lbl)

            badge = QLabel("AI")
            badge.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            badge.setStyleSheet("color: #00e5ff; background: rgba(0, 229, 255, 0.12); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 4px; padding: 1px 5px;")
            hdr.addWidget(badge)

            ts_lbl = QLabel(ts)
            ts_lbl.setFont(QFont("Segoe UI", 7))
            ts_lbl.setStyleSheet("color: #64748b; border: none; background: transparent; padding-left: 2px;")
            hdr.addWidget(ts_lbl)
            hdr.addStretch()

        self.card_lay.addLayout(hdr)

        # Body container (can be cleared and re-rendered in-place during speech stream)
        self.body_container = QWidget()
        self.body_container.setStyleSheet("background: transparent;")
        self.body_lay = QVBoxLayout(self.body_container)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(6)
        self.card_lay.addWidget(self.body_container)

        self._render_body(content)

        # Action Footer for NEO response
        if not self.is_user:
            footer = QHBoxLayout()
            footer.setContentsMargins(0, 4, 0, 0)
            footer.setSpacing(6)

            def _btn(lbl_text: str, cb):
                b = QPushButton(lbl_text)
                b.setFont(QFont("Segoe UI", 7))
                b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                b.setFixedHeight(22)
                b.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.04);
                        color: #94a3b8;
                        border: 1px solid rgba(255, 255, 255, 0.07);
                        border-radius: 5px;
                        padding: 1px 8px;
                    }
                    QPushButton:hover {
                        background: rgba(56, 189, 248, 0.15);
                        border-color: rgba(56, 189, 248, 0.35);
                        color: #ffffff;
                    }
                """)
                b.clicked.connect(cb)
                return b

            self.copy_btn = _btn("📋 Copy", self._copy_msg)
            footer.addWidget(self.copy_btn)

            self.notes_btn = _btn("📌 Save to Notes", self._save_to_notes)
            footer.addWidget(self.notes_btn)

            self.star_btn = _btn("⭐ Pin", self._toggle_star)
            footer.addWidget(self.star_btn)

            if self.on_speak:
                speak_b = _btn("🔊 Speak", lambda: self.on_speak(self.raw_content))
                footer.addWidget(speak_b)

            footer.addStretch()
            self.card_lay.addLayout(footer)

        h_row = QHBoxLayout()
        h_row.setContentsMargins(0, 0, 0, 0)
        if self.is_user:
            h_row.addStretch()
            h_row.addWidget(card, stretch=0)
        else:
            h_row.addWidget(card, stretch=0)
            h_row.addStretch()

        outer.addLayout(h_row)

    def update_content(self, new_text: str):
        """In-place update for streaming text chunks."""
        self.raw_content = new_text
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._render_body(new_text)

    def _render_body(self, content: str):
        if self.is_user:
            txt_lbl = QLabel(_format_markdown_prose(content))
            txt_lbl.setFont(QFont("Segoe UI", 9))
            txt_lbl.setWordWrap(True)
            txt_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            txt_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; line-height: 140%;")
            self.body_lay.addWidget(txt_lbl)
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
                        self.body_lay.addWidget(p_lbl)

                    if i + 2 < len(parts):
                        lang = parts[i + 1].strip() or "CODE"
                        code = parts[i + 2].strip()
                        cb_w = CodeBlockWidget(code, lang)
                        cb_w.canvas_requested.connect(self.canvas_requested.emit)
                        self.body_lay.addWidget(cb_w)
                        i += 3
                    else:
                        break
            else:
                txt_lbl = QLabel(_format_markdown_prose(content))
                txt_lbl.setFont(QFont("Segoe UI", 9))
                txt_lbl.setWordWrap(True)
                txt_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                txt_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
                self.body_lay.addWidget(txt_lbl)

            # Auto-detect URLs and render rich Web Link Cards
            urls = re.findall(r"https?://[^\s<>\"']+", content)
            if urls:
                for u in urls[:2]:
                    self.body_lay.addWidget(WebLinkCard(u))

    def _copy_msg(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.raw_content)
        self.copy_btn.setText("✓ Copied!")
        QTimer.singleShot(1800, lambda: self.copy_btn.setText("📋 Copy"))

    def _save_to_notes(self):
        try:
            notes_p = _BASE_DIR / "memory" / "notes.txt"
            notes_p.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n--- Note saved from NEO Chat ({ts}) ---\n{self.raw_content}\n"
            with open(notes_p, "a", encoding="utf-8") as f:
                f.write(entry)

            try:
                from memory.memory_manager import remember
                key = f"chat_note_{int(time.time())}"
                remember(key, self.raw_content[:200], category="notes")
            except Exception:
                pass

            self.notes_btn.setText("✓ Saved to Notes!")
            self.notes_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(34, 197, 94, 0.2);
                    color: #4ade80;
                    border: 1px solid #22c55e;
                    border-radius: 3px;
                    padding: 1px 7px;
                }
            """)
            QTimer.singleShot(2500, lambda: self.notes_btn.setText("📌 Save to Notes"))
        except Exception as e:
            self.notes_btn.setText("⚠️ Failed")

    def _toggle_star(self):
        self.is_starred = not self.is_starred
        if self.is_starred:
            self.star_btn.setText("★ Pinned")
            self.star_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(251, 191, 36, 0.2);
                    color: #fbbf24;
                    border: 1px solid #fbbf24;
                    border-radius: 3px;
                    padding: 1px 7px;
                }
            """)
        else:
            self.star_btn.setText("⭐ Pin")
            self.star_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #8e9eb5;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 3px;
                    padding: 1px 7px;
                }
            """)


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


# ─────────────────────────────────────────────────────────────────────────────
#  5. FLOATING SLASH COMMAND (/) POPUP MENU
# ─────────────────────────────────────────────────────────────────────────────
class SlashCommandPopup(QFrame):
    """Floating autocomplete popup for quick / commands."""

    command_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame#SlashCommandPopup {
                background: #0f1626;
                border: 1.5px solid rgba(56, 189, 248, 0.4);
                border-radius: 12px;
            }
        """)
        self.setObjectName("SlashCommandPopup")
        self.setFixedWidth(340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        hdr = QLabel("⚡ NEO SLASH COMMANDS")
        hdr.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #38bdf8; padding: 2px 6px; border: none; background: transparent;")
        lay.addWidget(hdr)

        commands = [
            ("💻 /code", "Focus on clean coding & debugging", "/code "),
            ("🔍 /research", "Deep web research with live citations", "/research "),
            ("🧠 /rag", "Local semantic file search with citations", "/rag "),
            ("👥 /swarm", "Delegate parallel task to subagent swarm", "/swarm "),
            ("🚀 /protocol", "Engage Stark macro protocol (dev, focus)", "/protocol "),
            ("✦ /canvas", "Open interactive code execution sandbox", "/canvas"),
            ("🎵 /spotify", "Control music (play, pause, next)", "/spotify "),
            ("📅 /brief", "Executive agenda & morning briefing", "/brief"),
            ("📝 /notes", "Save directly to long-term memory notes", "/notes "),
            ("🗑 /clear", "Clear the current dialogue stream", "/clear"),
        ]

        for trigger, desc, fill in commands:
            b = QPushButton()
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b_lay = QHBoxLayout(b)
            b_lay.setContentsMargins(8, 4, 8, 4)
            b_lay.setSpacing(6)

            t_lbl = QLabel(trigger)
            t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            t_lbl.setStyleSheet("color: #60a5fa; border: none; background: transparent;")
            b_lay.addWidget(t_lbl)

            d_lbl = QLabel(desc)
            d_lbl.setFont(QFont("Segoe UI", 7))
            d_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
            b_lay.addWidget(d_lbl)
            b_lay.addStretch()

            b.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.15);
                    border: 1px solid rgba(56, 189, 248, 0.3);
                }
            """)
            b.clicked.connect(lambda _, f=fill: self.command_selected.emit(f))
            lay.addWidget(b)


# ─────────────────────────────────────────────────────────────────────────────
#  6. MULTI-CHAT SESSIONS & HISTORY DRAWER
# ─────────────────────────────────────────────────────────────────────────────
class ChatHistoryDrawer(QFrame):
    """Slide-in sidebar for browsing, creating, and switching chat conversations."""

    session_switched = pyqtSignal(str)
    new_chat_requested = pyqtSignal()
    session_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet("""
            QFrame#ChatHistoryDrawer {
                background: rgba(11, 15, 25, 0.98);
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        self.setObjectName("ChatHistoryDrawer")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 14)
        lay.setSpacing(10)

        # Header + New Chat Button
        new_b = QPushButton("+ New Chat")
        new_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        new_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_b.setFixedHeight(30)
        new_b.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 8px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.3);
                color: #ffffff;
            }
        """)
        new_b.clicked.connect(self.new_chat_requested.emit)
        lay.addWidget(new_b)

        hdr_lbl = QLabel("SAVED CONVERSATIONS")
        hdr_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet("color: #64748b; padding: 4px 2px; border: none; background: transparent;")
        lay.addWidget(hdr_lbl)

        # Scrollable sessions list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.list_container = QWidget()
        self.list_lay = QVBoxLayout(self.list_container)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(4)
        self.list_lay.addStretch()

        self.scroll.setWidget(self.list_container)
        lay.addWidget(self.scroll, stretch=1)

    def render_sessions(self, sessions: list[dict], active_id: str):
        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for s in reversed(sessions):
            sid = s.get("id", "")
            title = s.get("title", "New Conversation")
            is_active = (sid == active_id)

            card = QFrame()
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            bg = "rgba(56, 189, 248, 0.14)" if is_active else "transparent"
            border = "rgba(56, 189, 248, 0.35)" if is_active else "transparent"
            card.setStyleSheet(f"""
                QFrame {{
                    background: {bg};
                    border: 1px solid {border};
                    border-radius: 6px;
                }}
                QFrame:hover {{
                    background: rgba(255, 255, 255, 0.05);
                }}
            """)

            c_lay = QHBoxLayout(card)
            c_lay.setContentsMargins(8, 6, 6, 6)
            c_lay.setSpacing(6)

            t_lbl = QLabel(title[:22] + ("..." if len(title) > 22 else ""))
            t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold if is_active else QFont.Weight.Normal))
            t_lbl.setStyleSheet(f"color: {'#ffffff' if is_active else '#94a3b8'}; border: none; background: transparent;")
            c_lay.addWidget(t_lbl, stretch=1)

            del_b = QPushButton("✕")
            del_b.setFont(QFont("Segoe UI", 7))
            del_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            del_b.setFixedSize(16, 16)
            del_b.setStyleSheet("QPushButton { color: #526078; border: none; background: transparent; } QPushButton:hover { color: #f43f5e; }")
            del_b.clicked.connect(lambda _, _id=sid: self.session_deleted.emit(_id))
            c_lay.addWidget(del_b)

            card.mousePressEvent = lambda e, _id=sid: self.session_switched.emit(_id)
            self.list_lay.insertWidget(self.list_lay.count() - 1, card)


# ─────────────────────────────────────────────────────────────────────────────
#  7. MAIN NEO MODERN CHAT WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class NeoModernChatWidget(QWidget):
    """Comprehensive AI Chat Command Center replacing the legacy log widget."""

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

        # Stream update state trackers
        self._active_stream_bubble: Optional[NeoChatMessageBubble] = None
        self._last_stream_role: str = ""
        self._last_stream_time: float = 0.0

        self.voice_muted = self._load_voice_muted()

        # Load / Initialize Sessions
        self.sessions_data = self._load_sessions_data()
        self.active_session_id = self.sessions_data.get("active_session_id", "default")

        root_h = QHBoxLayout(self)
        root_h.setContentsMargins(0, 0, 0, 0)
        root_h.setSpacing(0)

        # 1. Slide-in Chat History Drawer
        self.drawer = ChatHistoryDrawer(self)
        self.drawer.setVisible(False)
        self.drawer.new_chat_requested.connect(self._create_new_session)
        self.drawer.session_switched.connect(self._switch_session)
        self.drawer.session_deleted.connect(self._delete_session)
        root_h.addWidget(self.drawer)

        # 2. Main Chat Panel Area
        main_chat = QWidget()
        main_chat.setStyleSheet(f"background: {BG_OBSIDIAN};")
        chat_v = QVBoxLayout(main_chat)
        chat_v.setContentsMargins(18, 12, 18, 14)
        chat_v.setSpacing(8)

        # Modern Executive Header Bar
        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 2, 4, 6)
        hdr.setSpacing(10)

        self.drawer_btn = QPushButton("☰  Sessions")
        self.drawer_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.drawer_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.drawer_btn.setFixedHeight(28)
        self.drawer_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                padding: 2px 12px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.drawer_btn.clicked.connect(self._toggle_drawer)
        hdr.addWidget(self.drawer_btn)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 8))
        dot.setStyleSheet("color: #10b981; border: none; background: transparent;")
        hdr.addWidget(dot)

        self.hdr_title = QLabel("NEO Stream")
        self.hdr_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.hdr_title.setStyleSheet("color: #f8fafc; border: none; background: transparent;")
        hdr.addWidget(self.hdr_title)

        tag = QLabel("NEURAL ASSISTANT")
        tag.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
        tag.setStyleSheet("color: #64748b; background: rgba(255, 255, 255, 0.04); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(tag)

        hdr.addStretch()

        # Model Mode Switcher Pill
        self.model_combo = QComboBox()
        self.model_combo.addItems(["✦ Pro (Gemini 2.0)", "⚡ Fast (Gemini Flash)", "💻 Local (Ollama)"])
        self.model_combo.setFont(QFont("Segoe UI", 8))
        self.model_combo.setFixedHeight(28)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background: rgba(15, 23, 42, 0.85);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 7px;
                padding: 1px 10px;
            }
            QComboBox::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox QAbstractItemView {
                background: #0d1322;
                color: #f8fafc;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                border: 1px solid rgba(56, 189, 248, 0.3);
            }
        """)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        hdr.addWidget(self.model_combo)

        # Voice auto-speak toggle button
        self.voice_btn = QPushButton("🔇 Silent" if self.voice_muted else "🔊 Voice: ON")
        self.voice_btn.setFont(QFont("Segoe UI", 8))
        self.voice_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.voice_btn.setFixedHeight(28)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                padding: 1px 10px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
            }
        """)
        self.voice_btn.clicked.connect(self._toggle_voice)
        hdr.addWidget(self.voice_btn)

        # Interactive Canvas Toggle
        canvas_tgl = QPushButton("✦ Canvas")
        canvas_tgl.setToolTip("Toggle Interactive Artifact Canvas Sandbox")
        canvas_tgl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        canvas_tgl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        canvas_tgl.setFixedHeight(28)
        canvas_tgl.setStyleSheet("""
            QPushButton {
                background: rgba(0, 229, 255, 0.12);
                color: #00e5ff;
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 7px;
                padding: 1px 10px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.25);
                color: #ffffff;
            }
        """)
        canvas_tgl.clicked.connect(lambda: self.artifact_canvas.setVisible(not self.artifact_canvas.isVisible()))
        hdr.addWidget(canvas_tgl)

        # Export .md report button
        export_b = QPushButton("📋 Export")
        export_b.setToolTip("Export conversation as Markdown")
        export_b.setFont(QFont("Segoe UI", 8))
        export_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        export_b.setFixedHeight(28)
        export_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                padding: 1px 10px;
            }
            QPushButton:hover {
                background: rgba(96, 165, 250, 0.2);
                border-color: #60a5fa;
                color: #ffffff;
            }
        """)
        export_b.clicked.connect(self._export_conversation)
        hdr.addWidget(export_b)

        # Clear stream button
        clear_b = QPushButton("🗑 Clear")
        clear_b.setFont(QFont("Segoe UI", 8))
        clear_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_b.setFixedHeight(28)
        clear_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                padding: 1px 10px;
            }
            QPushButton:hover {
                background: rgba(244, 63, 94, 0.18);
                border-color: #f43f5e;
                color: #ffffff;
            }
        """)
        clear_b.clicked.connect(self.clear_stream)
        hdr.addWidget(clear_b)

        chat_v.addLayout(hdr)

        # Scrollable Messages Area
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
        self.msg_layout.setContentsMargins(6, 6, 12, 6)
        self.msg_layout.setSpacing(12)

        self.welcome_widget = ChatWelcomeView(self.messages_container)
        self.welcome_widget.prompt_selected.connect(self._apply_quick_pill)
        self.msg_layout.addWidget(self.welcome_widget)

        self.msg_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        chat_v.addWidget(self.scroll_area, stretch=1)

        # Compact Attachment Chip Bar
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
        remove_chip_b.setStyleSheet("QPushButton { background: transparent; color: #8e9eb5; border: none; } QPushButton:hover { color: #f43f5e; }")
        remove_chip_b.clicked.connect(self._clear_attached_file)
        chip_lay.addWidget(remove_chip_b)

        chat_v.addWidget(self.chip_frame)

        # Quick Action Prompt Pills
        pills_row = QHBoxLayout()
        pills_row.setContentsMargins(4, 0, 4, 0)
        pills_row.setSpacing(8)

        def _pill(text: str, prompt: str):
            b = QPushButton(text)
            b.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(24)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    padding: 2px 11px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.18);
                    border-color: #38bdf8;
                    color: #ffffff;
                }
            """)
            b.clicked.connect(lambda: self._apply_quick_pill(prompt))
            return b

        pills_row.addWidget(_pill("✦ Explain Code", "/code "))
        pills_row.addWidget(_pill("✦ Web Research", "/research "))
        pills_row.addWidget(_pill("✦ Spotify", "/spotify "))
        pills_row.addWidget(_pill("✦ Agenda Brief", "/brief"))
        pills_row.addWidget(_pill("✦ Quick Note", "/notes "))
        pills_row.addStretch()

        chat_v.addLayout(pills_row)

        # Bottom Input Capsule Frame
        self.bar_frame = QFrame()
        self.bar_frame.setFixedHeight(52)
        self.bar_frame.setStyleSheet("""
            QFrame#InputBarFrame {
                background: rgba(13, 19, 33, 0.96);
                border: 1.5px solid rgba(56, 189, 248, 0.28);
                border-radius: 26px;
            }
            QFrame#InputBarFrame:hover {
                border-color: rgba(56, 189, 248, 0.45);
            }
        """)
        self.bar_frame.setObjectName("InputBarFrame")
        bar_lay = QHBoxLayout(self.bar_frame)
        bar_lay.setContentsMargins(14, 0, 10, 0)
        bar_lay.setSpacing(10)

        attach_btn = QPushButton("📎")
        attach_btn.setToolTip("Attach file or image")
        attach_btn.setFixedSize(30, 30)
        attach_btn.setFont(QFont("Segoe UI", 12))
        attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        attach_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 15px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        attach_btn.clicked.connect(self._browse_file)
        bar_lay.addWidget(attach_btn)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Message NEO or type '/' for slash commands...")
        self.input_edit.setFont(QFont("Segoe UI", 10))
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_WHITE};
                padding: 0 4px;
            }}
            QLineEdit::placeholder {{
                color: #64748b;
            }}
        """)
        self.input_edit.textChanged.connect(self._on_input_text_changed)
        self.input_edit.returnPressed.connect(self._submit)
        bar_lay.addWidget(self.input_edit, stretch=1)

        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setToolTip("Toggle Voice Microphone (F4)")
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setFont(QFont("Segoe UI", 11))
        self.mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 15px;
            }
            QPushButton:hover {
                background: rgba(52, 211, 153, 0.2);
                border-color: #34d399;
                color: #34d399;
            }
        """)
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        bar_lay.addWidget(self.mic_btn)

        send_btn = QPushButton("➤")
        send_btn.setToolTip("Send message (Enter)")
        send_btn.setFixedSize(32, 32)
        send_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        send_btn.setStyleSheet("""
            QPushButton {
                background: #00e5ff;
                color: #070b14;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover {
                background: #38bdf8;
            }
        """)
        send_btn.clicked.connect(self._submit)
        bar_lay.addWidget(send_btn)

        chat_v.addWidget(self.bar_frame)
        root_h.addWidget(main_chat, stretch=1)

        from core.neo_artifacts import NeoArtifactCanvas
        self.artifact_canvas = NeoArtifactCanvas(self)
        self.artifact_canvas.setVisible(False)
        root_h.addWidget(self.artifact_canvas)

        # Floating Slash Command Popup
        self.slash_popup = SlashCommandPopup(self)
        self.slash_popup.setVisible(False)
        self.slash_popup.command_selected.connect(self._on_slash_command_chosen)

        # Render Active Session
        self._load_active_session()
        self._update_drawer_list()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API for Logging & External Tool Hooks
    # ─────────────────────────────────────────────────────────────────────────
    def current_file(self) -> Optional[str]:
        return self._current_file

    def clear_file(self):
        self._clear_attached_file()

    def append_log(self, text: str):
        """Thread-safe drop-in handler for legacy self._log.append_log() calls."""
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
        """
        Appends or updates a message bubble.
        Gracefully handles streaming tokens/speech in-place to avoid repeating bubbles.
        """
        clean = content.strip()
        if not clean:
            return

        role_lower = role.lower()
        now = time.time()

        # Check if this is an incremental streaming update from the active speaker
        is_streaming_chunk = (
            self._active_stream_bubble is not None
            and self._last_stream_role == role_lower
            and (
                clean.startswith(self._active_stream_bubble.raw_content)
                or self._active_stream_bubble.raw_content.startswith(clean)
                or (now - self._last_stream_time < 3.2)
            )
        )

        if is_streaming_chunk and self._active_stream_bubble is not None:
            self._active_stream_bubble.update_content(clean)
            self._last_stream_time = now

            # Update the last message in the active session
            curr = self._get_active_session()
            if curr and curr.get("messages"):
                curr["messages"][-1]["content"] = clean
                self._save_sessions_data()

            QTimer.singleShot(20, self._scroll_to_bottom)
            return

        # New turn starting
        ts = datetime.now().strftime("%I:%M %p")
        bubble = NeoChatMessageBubble(
            role=role,
            content=clean,
            timestamp=ts,
            on_speak_requested=self._on_speak_requested if not self.voice_muted else None,
            parent=self.messages_container,
        )
        bubble.canvas_requested.connect(self.open_artifact_canvas)
        self._active_stream_bubble = bubble
        self._last_stream_role = role_lower
        self._last_stream_time = now

        count = self.msg_layout.count()
        self.msg_layout.insertWidget(max(0, count - 1), bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

        if hasattr(self, "welcome_widget"):
            self.welcome_widget.hide()
        self._save_message_to_active_session(role, clean, ts)

    def add_tool_execution(self, tool_name: str, details: str = ""):
        self._active_stream_bubble = None
        count = self.msg_layout.count()
        acc = ToolExecutionAccordion(tool_name, details, parent=self.messages_container)
        self.msg_layout.insertWidget(max(0, count - 1), acc)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_system_pill(self, text: str):
        self._active_stream_bubble = None
        count = self.msg_layout.count()
        pill = SystemPillWidget(text, parent=self.messages_container)
        self.msg_layout.insertWidget(max(0, count - 1), pill)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _clear_messages_from_layout(self):
        """Remove all message bubbles and pills, keeping welcome_widget and stretch intact."""
        welcome = getattr(self, "welcome_widget", None)
        for i in reversed(range(self.msg_layout.count())):
            item = self.msg_layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if w and w is not welcome:
                self.msg_layout.removeWidget(w)
                w.deleteLater()

    def clear_stream(self):
        self._active_stream_bubble = None
        self._clear_messages_from_layout()
        self._last_content = None
        if hasattr(self, "welcome_widget") and self.welcome_widget is not None:
            try:
                self.welcome_widget.show()
            except Exception:
                pass
        self.add_system_pill("SYS: Conversation stream cleared.")

        curr = self._get_active_session()
        if curr:
            curr["messages"] = []
            self._save_sessions_data()

    def set_attached_file(self, file_path: str):
        self._current_file = file_path
        p = Path(file_path)
        sz = p.stat().st_size if p.exists() else 0
        sz_str = f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B"
        self.chip_lbl.setText(f"📄  {p.name}  ({sz_str})  ·  Attached")
        self.chip_frame.setVisible(True)

    # ─────────────────────────────────────────────────────────────────────────
    # Slash Command Autocomplete Handling
    # ─────────────────────────────────────────────────────────────────────────
    def _on_input_text_changed(self, text: str):
        if text.startswith("/"):
            self._reposition_slash_popup()
            self.slash_popup.show()
            self.slash_popup.raise_()
        else:
            self.slash_popup.hide()

    def _reposition_slash_popup(self):
        p = self.bar_frame.mapTo(self, self.bar_frame.rect().topLeft())
        self.slash_popup.move(p.x() + 30, max(10, p.y() - self.slash_popup.sizeHint().height() - 10))

    def _on_slash_command_chosen(self, fill_text: str):
        self.slash_popup.hide()
        self.input_edit.setText(fill_text)
        self.input_edit.setFocus()
        if fill_text in ("/clear", "/brief"):
            self._submit()

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Chat Sessions Management
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_drawer(self):
        is_vis = not self.drawer.isVisible()
        self.drawer.setVisible(is_vis)
        self.drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: {'rgba(56, 189, 248, 0.25)' if is_vis else 'rgba(255, 255, 255, 0.05)'};
                color: {'#38bdf8' if is_vis else '#8e9eb5'};
                border: 1px solid {'#38bdf8' if is_vis else 'rgba(255, 255, 255, 0.08)'};
                border-radius: 6px;
                padding: 2px 10px;
            }}
        """)

    def _load_sessions_data(self) -> dict:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _SESSIONS_FILE.exists():
            try:
                with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "sessions" in data:
                        return data
            except Exception:
                pass
        default_data = {
            "active_session_id": "default",
            "sessions": [
                {
                    "id": "default",
                    "title": "Main Conversation",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "messages": [],
                }
            ],
        }
        self._write_sessions_file(default_data)
        return default_data

    def _write_sessions_file(self, data: dict):
        try:
            with open(_SESSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _save_sessions_data(self):
        self._write_sessions_file(self.sessions_data)

    def _get_active_session(self) -> Optional[dict]:
        for s in self.sessions_data.get("sessions", []):
            if s.get("id") == self.active_session_id:
                return s
        return None

    def _save_message_to_active_session(self, role: str, content: str, timestamp: str):
        curr = self._get_active_session()
        if not curr:
            return
        msgs = curr.setdefault("messages", [])
        msgs.append({"role": role, "content": content, "timestamp": timestamp})

        if curr.get("title") in ("Main Conversation", "New Conversation") and role == "user":
            curr["title"] = content[:26] + ("..." if len(content) > 26 else "")
            self._update_drawer_list()
            if hasattr(self, "hdr_title"):
                self.hdr_title.setText(curr.get("title", "NEO Stream"))

        self._save_sessions_data()

    def _load_active_session(self):
        self._active_stream_bubble = None
        curr = self._get_active_session()
        if not curr:
            return
        self._clear_messages_from_layout()
        self._last_content = None

        msgs = curr.get("messages", [])
        if not msgs:
            if hasattr(self, "welcome_widget") and self.welcome_widget is not None:
                try:
                    self.welcome_widget.show()
                except Exception:
                    pass
        else:
            if hasattr(self, "welcome_widget") and self.welcome_widget is not None:
                try:
                    self.welcome_widget.hide()
                except Exception:
                    pass
        for m in msgs:
            role = m.get("role", "neo")
            txt = m.get("content", "")
            ts = m.get("timestamp", "")
            bubble = NeoChatMessageBubble(
                role=role,
                content=txt,
                timestamp=ts,
                on_speak_requested=self._on_speak_requested if not self.voice_muted else None,
                parent=self.messages_container,
            )
            bubble.canvas_requested.connect(self.open_artifact_canvas)
            count = self.msg_layout.count()
            self.msg_layout.insertWidget(max(0, count - 1), bubble)
        QTimer.singleShot(60, self._scroll_to_bottom)

    def _create_new_session(self):
        self._active_stream_bubble = None
        new_id = f"sess_{int(time.time())}"
        new_sess = {
            "id": new_id,
            "title": "New Conversation",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "messages": [],
        }
        self.sessions_data.setdefault("sessions", []).append(new_sess)
        self.active_session_id = new_id
        self.sessions_data["active_session_id"] = new_id
        self._save_sessions_data()
        self._load_active_session()
        self._update_drawer_list()

    def _switch_session(self, session_id: str):
        if session_id == self.active_session_id:
            return
        self._active_stream_bubble = None
        self.active_session_id = session_id
        self.sessions_data["active_session_id"] = session_id
        self._save_sessions_data()
        self._load_active_session()
        self._update_drawer_list()

    def _delete_session(self, session_id: str):
        self._active_stream_bubble = None
        sessions = self.sessions_data.get("sessions", [])
        if len(sessions) <= 1:
            self.clear_stream()
            return
        self.sessions_data["sessions"] = [s for s in sessions if s.get("id") != session_id]
        if self.active_session_id == session_id:
            self.active_session_id = self.sessions_data["sessions"][-1]["id"]
            self.sessions_data["active_session_id"] = self.active_session_id
            self._load_active_session()
        self._save_sessions_data()
        self._update_drawer_list()

    def _update_drawer_list(self):
        self.drawer.render_sessions(self.sessions_data.get("sessions", []), self.active_session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Model Mode & Voice Toggle
    # ─────────────────────────────────────────────────────────────────────────
    def _on_model_changed(self, idx: int):
        modes = ["gemini-1.5-pro", "gemini-1.5-flash", "local-ollama"]
        mode = modes[idx] if idx < len(modes) else "gemini-1.5-pro"
        try:
            cfg_p = _BASE_DIR / "config" / "api_keys.json"
            if cfg_p.exists():
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["chat_model_mode"] = mode
                with open(cfg_p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)
        except Exception:
            pass
        self.add_system_pill(f"SYS: Switched reasoning engine to {self.model_combo.currentText()}.")

    def _load_voice_muted(self) -> bool:
        try:
            cfg_p = _BASE_DIR / "config" / "api_keys.json"
            if cfg_p.exists():
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return bool(cfg.get("chat_voice_muted", False))
        except Exception:
            return False
        return False

    def _toggle_voice(self):
        self.voice_muted = not self.voice_muted
        self.voice_btn.setText("🔇 Silent" if self.voice_muted else "🔊 Voice: ON")
        try:
            cfg_p = _BASE_DIR / "config" / "api_keys.json"
            if cfg_p.exists():
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["chat_voice_muted"] = self.voice_muted
                with open(cfg_p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Export Conversation (.md)
    # ─────────────────────────────────────────────────────────────────────────
    def _export_conversation(self):
        curr = self._get_active_session()
        if not curr or not curr.get("messages"):
            self.add_system_pill("SYS: No messages in active conversation to export.")
            return

        _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = _EXPORTS_DIR / f"chat_export_{ts_slug}.md"

        lines = [
            f"# NEO Conversation Export — {curr.get('title')}",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
        ]
        for m in curr.get("messages", []):
            role_title = "User (Fayid)" if m.get("role") in ("user", "you") else "NEO Assistant"
            lines.append(f"### {role_title} ({m.get('timestamp')})")
            lines.append(f"{m.get('content')}\n")

        export_file.write_text("\n".join(lines), encoding="utf-8")
        self.add_system_pill(f"✓ Exported report to: {export_file.name}")

    # ─────────────────────────────────────────────────────────────────────────
    # Input Submission & File Actions
    # ─────────────────────────────────────────────────────────────────────────
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

    def open_artifact_canvas(self, code: str, language: str = "python"):
        if hasattr(self, "artifact_canvas"):
            self.artifact_canvas.display_artifact(code, language, title=f"NEO Artifact // {language.upper()}")

    def _submit(self):
        self._active_stream_bubble = None
        txt = self.input_edit.text().strip()
        self.slash_popup.hide()
        if not txt and not self._current_file:
            return

        full_cmd = txt
        if self._current_file:
            p = Path(self._current_file)
            if not txt:
                full_cmd = f"Please examine and analyze this file: {p.name}"
            self._clear_attached_file()

        self.input_edit.clear()

        if full_cmd == "/clear":
            self.clear_stream()
            return

        if full_cmd == "/brief":
            full_cmd = "Run executive morning briefing and upcoming schedule review."
        elif full_cmd.startswith("/code "):
            full_cmd = "Write clean, robust code for: " + full_cmd[6:].strip()
        elif full_cmd.startswith("/research "):
            full_cmd = "Conduct deep web research and summarize sources for: " + full_cmd[10:].strip()
        elif full_cmd.startswith("/spotify "):
            full_cmd = "Spotify control: " + full_cmd[9:].strip()
        elif full_cmd.startswith("/notes "):
            note_txt = full_cmd[7:].strip()
            self.add_message("user", full_cmd)
            p = _BASE_DIR / "memory" / "notes.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note_txt}\n")
            self.add_system_pill(f"✓ Saved note to memory: '{note_txt[:40]}...'")
            return

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
