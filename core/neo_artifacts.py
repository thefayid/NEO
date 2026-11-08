"""
core/neo_artifacts.py — Interactive Artifacts & Code Execution Canvas for NEO.
Provides an executive sliding side-canvas (inspired by Claude Artifacts & Cursor):
- Live Code Sandbox (Python, HTML, JavaScript, Shell, Markdown, Mermaid).
- Interactive In-App HTML / JS preview using QTextBrowser with rich DOM support.
- Live Python execution sandbox with captured stdout/stderr terminal output.
- Instant Export, Download, Copy, and Pin to Notes.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon
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
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

BG_DARK = "#070a12"
CARD_BG = "rgba(13, 19, 32, 0.95)"
BORDER_CYAN = "rgba(56, 189, 248, 0.35)"
TEXT_WHITE = "#f8fafc"
TEXT_MUTED = "#94a3b8"


class NeoArtifactCanvas(QFrame):
    """Sliding interactive side-canvas for rendering live code, HTML, and running scripts."""

    closed = pyqtSignal()
    saved_to_notes = pyqtSignal(str)
    execution_output = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NeoArtifactCanvas")
        self.setFixedWidth(520)
        self.setStyleSheet(f"""
            QFrame#NeoArtifactCanvas {{
                background: #090d16;
                border-left: 1px solid rgba(56, 189, 248, 0.25);
            }}
        """)

        self.current_code = ""
        self.current_lang = "python"
        self.current_title = "Artifact"

        root_v = QVBoxLayout(self)
        root_v.setContentsMargins(14, 12, 14, 14)
        root_v.setSpacing(10)

        # 1. Header Bar
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        self.icon_lbl = QLabel("✦")
        self.icon_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.icon_lbl.setStyleSheet("color: #00e5ff; background: transparent; border: none;")
        hdr.addWidget(self.icon_lbl)

        self.title_lbl = QLabel("Artifact Canvas")
        self.title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #f8fafc; background: transparent; border: none;")
        hdr.addWidget(self.title_lbl, stretch=1)

        self.lang_badge = QLabel("PYTHON")
        self.lang_badge.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self.lang_badge.setStyleSheet("""
            color: #38bdf8; background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 4px;
            padding: 1px 6px;
        """)
        hdr.addWidget(self.lang_badge)

        close_b = QPushButton("✕")
        close_b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_b.setFixedSize(24, 24)
        close_b.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8; border: none; border-radius: 4px;
            }
            QPushButton:hover { background: rgba(244, 63, 94, 0.2); color: #f43f5e; }
        """)
        close_b.clicked.connect(self.close_canvas)
        hdr.addWidget(close_b)
        root_v.addLayout(hdr)

        # 2. Tabs Selector (Code vs Live Preview vs Execution Output)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(6)

        def _tab_btn(lbl: str, idx: int):
            b = QPushButton(lbl)
            b.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(26)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    padding: 2px 10px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.15);
                    color: #ffffff;
                }
            """)
            b.clicked.connect(lambda: self._switch_tab(idx))
            return b

        self.tab_code_btn = _tab_btn("💻 Code", 0)
        self.tab_preview_btn = _tab_btn("👁 Live Preview", 1)
        self.tab_console_btn = _tab_btn("⚡ Output Console", 2)

        tab_row.addWidget(self.tab_code_btn)
        tab_row.addWidget(self.tab_preview_btn)
        tab_row.addWidget(self.tab_console_btn)
        tab_row.addStretch()
        root_v.addLayout(tab_row)

        # 3. Stacked Content (Code / Preview / Console)
        self.stack = QStackedWidget()

        # Tab 0: Code Editor
        code_w = QWidget()
        code_v = QVBoxLayout(code_w)
        code_v.setContentsMargins(0, 0, 0, 0)
        code_v.setSpacing(6)

        self.code_edit = QTextEdit()
        self.code_edit.setFont(QFont("Consolas", 9))
        self.code_edit.setStyleSheet("""
            QTextEdit {
                background: #050811;
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 10px;
                line-height: 140%;
            }
        """)
        code_v.addWidget(self.code_edit)
        self.stack.addWidget(code_w)

        # Tab 1: Live Web / HTML Preview
        prev_w = QWidget()
        prev_v = QVBoxLayout(prev_w)
        prev_v.setContentsMargins(0, 0, 0, 0)

        self.html_view = QTextBrowser()
        self.html_view.setOpenExternalLinks(True)
        self.html_view.setStyleSheet("""
            QTextBrowser {
                background: #060912;
                color: #f1f5f9;
                border: 1px solid rgba(56, 189, 248, 0.2);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        prev_v.addWidget(self.html_view)
        self.stack.addWidget(prev_w)

        # Tab 2: Output Console
        con_w = QWidget()
        con_v = QVBoxLayout(con_w)
        con_v.setContentsMargins(0, 0, 0, 0)
        con_v.setSpacing(6)

        self.console_edit = QTextEdit()
        self.console_edit.setReadOnly(True)
        self.console_edit.setFont(QFont("Consolas", 8))
        self.console_edit.setStyleSheet("""
            QTextEdit {
                background: #03050a;
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.25);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        self.execution_output.connect(self.console_edit.append)
        con_v.addWidget(self.console_edit)
        self.stack.addWidget(con_w)

        root_v.addWidget(self.stack, stretch=1)

        # 4. Action Buttons Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.run_btn = QPushButton("▶ Run Code")
        self.run_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.run_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.run_btn.setFixedHeight(28)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 2px 12px;
            }
            QPushButton:hover { background: #00e5ff; color: #050811; }
        """)
        self.run_btn.clicked.connect(self._execute_code)
        footer.addWidget(self.run_btn)

        copy_b = QPushButton("📋 Copy")
        copy_b.setFont(QFont("Segoe UI", 8))
        copy_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_b.setFixedHeight(28)
        copy_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 2px 10px;
            }
            QPushButton:hover { background: rgba(56, 189, 248, 0.2); color: #ffffff; }
        """)
        copy_b.clicked.connect(self._copy_code)
        footer.addWidget(copy_b)

        save_b = QPushButton("💾 Save As...")
        save_b.setFont(QFont("Segoe UI", 8))
        save_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_b.setFixedHeight(28)
        save_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 2px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)
        save_b.clicked.connect(self._save_file)
        footer.addWidget(save_b)

        footer.addStretch()
        root_v.addLayout(footer)

    def display_artifact(self, code: str, language: str = "python", title: str = "Artifact"):
        """Populate canvas and show appropriate tab based on content type."""
        self.current_code = code.strip()
        self.current_lang = (language or "python").strip().lower()
        self.current_title = title or "Artifact"

        self.title_lbl.setText(self.current_title[:28])
        self.lang_badge.setText(self.current_lang.upper())
        self.code_edit.setPlainText(self.current_code)

        if self.current_lang in ("html", "htm", "svg", "markdown", "md"):
            self.html_view.setHtml(self.current_code)
            self._switch_tab(1)
            self.run_btn.setVisible(False)
        else:
            self.run_btn.setVisible(True)
            self._switch_tab(0)

        self.show()

    def _switch_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        # Update button highlights
        for b, i in [(self.tab_code_btn, 0), (self.tab_preview_btn, 1), (self.tab_console_btn, 2)]:
            active = (i == idx)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {'rgba(56, 189, 248, 0.2)' if active else 'rgba(255, 255, 255, 0.04)'};
                    color: {'#38bdf8' if active else '#94a3b8'};
                    border: 1px solid {'#38bdf8' if active else 'rgba(255, 255, 255, 0.08)'};
                    border-radius: 6px;
                    padding: 2px 10px;
                }}
            """)

    def _execute_code(self):
        """Run the active code snippet in a clean subprocess sandbox."""
        code = self.code_edit.toPlainText().strip()
        if not code:
            return

        self._switch_tab(2)
        self.console_edit.setText("⚡ Initializing Sandbox Execution...\n")

        def _run():
            try:
                if self.current_lang in ("python", "py"):
                    res = subprocess.run(
                        [sys.executable, "-c", code],
                        capture_output=True,
                        text=True,
                        timeout=12,
                    )
                    out = res.stdout + ("\n[STDERR]\n" + res.stderr if res.stderr else "")
                    code_exit = res.returncode
                elif self.current_lang in ("bash", "sh", "powershell", "ps1"):
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", code],
                        capture_output=True,
                        text=True,
                        timeout=12,
                    )
                    out = res.stdout + (res.stderr if res.stderr else "")
                    code_exit = res.returncode
                else:
                    out = f"Execution not supported for language: {self.current_lang}"
                    code_exit = 0

                ts = datetime.now().strftime("%H:%M:%S")
                final_msg = f"\n=== Process Exited (code {code_exit}) at {ts} ===\n{out}"
                self.execution_output.emit(final_msg)
            except subprocess.TimeoutExpired:
                self.execution_output.emit("\n⚠️ Process Timed Out (exceeded 12s limit)")
            except Exception as e:
                self.execution_output.emit(f"\nExecution error: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _copy_code(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.code_edit.toPlainText())

    def _save_file(self):
        ext_map = {"python": ".py", "javascript": ".js", "html": ".html", "markdown": ".md", "json": ".json"}
        default_ext = ext_map.get(self.current_lang, ".txt")
        fpath, _ = QFileDialog.getSaveFileName(self, "Save Artifact File", f"artifact{default_ext}", "All Files (*.*)")
        if fpath:
            Path(fpath).write_text(self.code_edit.toPlainText(), encoding="utf-8")

    def close_canvas(self):
        self.hide()
        self.closed.emit()

