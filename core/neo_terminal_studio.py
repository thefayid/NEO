"""
core/neo_terminal_studio.py — Embedded Dev Terminal & Autonomous Agent Shell for NEO.
Provides an interactive PowerShell / system terminal, live command execution,
script runner presets, and AI error diagnosis.
"""
from __future__ import annotations

import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor, QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextBrowser, QFrame, QScrollArea
)

# Shared styling tokens
CARD_BG = "#1B1F26"
CARD_BORDER = "#262B34"
CARD_HOVER = "#222731"
TEXT_WHITE = "#E6E8EC"
TEXT_MUTED = "#9AA1AD"
TEXT_DIM = "#5F6672"
ACCENT_PRIMARY = "#5B8DEF"
SEMANTIC_SUCCESS = "#4CAF7D"
SEMANTIC_WARNING = "#D9A441"
SEMANTIC_ERROR = "#D9534F"


class _HistoryLineEdit(QLineEdit):
    """QLineEdit with Up/Down arrow history navigation."""
    up_pressed = pyqtSignal()
    down_pressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self.up_pressed.emit()
            return
        elif event.key() == Qt.Key.Key_Down:
            self.down_pressed.emit()
            return
        super().keyPressEvent(event)


class NeoTerminalStudio(QWidget):
    """Embedded Executive Dev Terminal & AI Agent Workbench."""
    diagnose_requested = pyqtSignal(str, str)  # (command, error_text)

    def __init__(self, parent=None, cwd: Optional[str] = None):
        super().__init__(parent)
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.history: List[str] = []
        self.history_index: int = -1
        self._current_process: Optional[subprocess.Popen] = None

        self.setStyleSheet(f"""
            QWidget {{
                background: #0E1013;
                color: {TEXT_WHITE};
            }}
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(18, 16, 18, 16)
        main_lay.setSpacing(10)

        # ── 1. Top Bar ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_lbl = QLabel("💻")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        title_lbl = QLabel("Dev Terminal & Agent Workbench")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        t_row.addWidget(title_lbl)

        self.status_pill = QLabel("● READY")
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_pill.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")
        t_row.addWidget(self.status_pill)
        t_row.addStretch()
        title_col.addLayout(t_row)

        self.cwd_lbl = QLabel(f"Working Directory: {self.cwd}")
        self.cwd_lbl.setFont(QFont("Segoe UI", 8))
        self.cwd_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        title_col.addWidget(self.cwd_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        clear_btn = QPushButton("Clear Console")
        clear_btn.setFixedHeight(28)
        clear_btn.setFont(QFont("Segoe UI", 8))
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD_BG}; color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER}; border-radius: 5px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; color: {TEXT_WHITE}; }}
        """)
        clear_btn.clicked.connect(self._clear_console)
        hdr.addWidget(clear_btn)

        self.abort_btn = QPushButton("⏹ Stop")
        self.abort_btn.setFixedHeight(28)
        self.abort_btn.setEnabled(False)
        self.abort_btn.setFont(QFont("Segoe UI", 8))
        self.abort_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.abort_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(217, 83, 79, 0.15); color: {SEMANTIC_ERROR};
                border: 1px solid rgba(217, 83, 79, 0.3); border-radius: 5px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: rgba(217, 83, 79, 0.3); }}
            QPushButton:disabled {{ background: transparent; color: {TEXT_DIM}; border-color: {CARD_BORDER}; }}
        """)
        self.abort_btn.clicked.connect(self._abort_command)
        hdr.addWidget(self.abort_btn)

        main_lay.addLayout(hdr)

        # ── 2. Preset Quick Scripts ──────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        p_lbl = QLabel("Quick Scripts:")
        p_lbl.setFont(QFont("Segoe UI", 8))
        p_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        preset_row.addWidget(p_lbl)

        presets = [
            ("git status", "git status"),
            ("git log -5", "git log -n 5 --oneline"),
            ("ps top cpu", "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"),
            ("python test", "python -m unittest discover -s . -p \"*test*.py\""),
            ("python version", "python --version; pip -V"),
            ("ollama tags", "ollama list"),
        ]
        for label, cmd in presets:
            pb = QPushButton(label)
            pb.setFixedHeight(22)
            pb.setFont(QFont("Segoe UI", 7))
            pb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            pb.setStyleSheet(f"""
                QPushButton {{
                    background: {CARD_BG}; color: {TEXT_MUTED};
                    border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
                }}
                QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; color: {TEXT_WHITE}; }}
            """)
            pb.clicked.connect(lambda _, c=cmd: self.execute_command(c))
            preset_row.addWidget(pb)
        preset_row.addStretch()
        main_lay.addLayout(preset_row)

        # ── 3. Console Output Screen ─────────────────────────────────────────
        self.console = QTextBrowser()
        self.console.setFont(QFont("Consolas", 9))
        self.console.setStyleSheet(f"""
            QTextBrowser {{
                background: #0B0E14;
                color: #C8D1DC;
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
                padding: 12px;
                line-height: 1.35;
            }}
        """)
        main_lay.addWidget(self.console, stretch=1)

        # ── 4. AI Diagnosis Banner (Visible on Error) ────────────────────────
        self.diag_frame = QFrame()
        self.diag_frame.setVisible(False)
        self.diag_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(217, 83, 79, 0.12);
                border: 1px solid rgba(217, 83, 79, 0.35);
                border-radius: 6px;
            }}
        """)
        d_lay = QHBoxLayout(self.diag_frame)
        d_lay.setContentsMargins(12, 6, 12, 6)
        d_lay.setSpacing(8)

        d_icon = QLabel("⚠️")
        d_icon.setFont(QFont("Segoe UI", 10))
        d_lay.addWidget(d_icon)

        self.diag_msg = QLabel("Command failed with non-zero exit status.")
        self.diag_msg.setFont(QFont("Segoe UI", 8))
        self.diag_msg.setStyleSheet(f"color: {SEMANTIC_ERROR};")
        d_lay.addWidget(self.diag_msg, stretch=1)

        self.diag_btn = QPushButton("🛠️ Diagnose & Auto-Fix with NEO")
        self.diag_btn.setFixedHeight(26)
        self.diag_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.diag_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.diag_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SEMANTIC_ERROR}; color: #ffffff;
                border: none; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #e04440; }}
        """)
        self.diag_btn.clicked.connect(self._trigger_ai_diagnosis)
        d_lay.addWidget(self.diag_btn)

        main_lay.addWidget(self.diag_frame)

        # ── 5. Command Input Line ────────────────────────────────────────────
        inp_box = QFrame()
        inp_box.setFixedHeight(38)
        inp_box.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        i_lay = QHBoxLayout(inp_box)
        i_lay.setContentsMargins(10, 0, 8, 0)
        i_lay.setSpacing(6)

        p_icn = QLabel("PS >")
        p_icn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p_icn.setStyleSheet(f"color: {ACCENT_PRIMARY}; border: none; background: transparent;")
        i_lay.addWidget(p_icn)

        self.cmd_input = _HistoryLineEdit()
        self.cmd_input.setFont(QFont("Consolas", 9))
        self.cmd_input.setPlaceholderText("Enter PowerShell command or script...")
        self.cmd_input.setStyleSheet("border: none; background: transparent; color: #E6E8EC;")
        self.cmd_input.returnPressed.connect(self._on_return_pressed)
        self.cmd_input.up_pressed.connect(self._history_up)
        self.cmd_input.down_pressed.connect(self._history_down)
        i_lay.addWidget(self.cmd_input, stretch=1)

        run_btn = QPushButton("Run ↵")
        run_btn.setFixedHeight(24)
        run_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        run_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_PRIMARY}; color: #ffffff;
                border: none; border-radius: 4px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: #4a7fdc; }}
        """)
        run_btn.clicked.connect(self._on_return_pressed)
        i_lay.addWidget(run_btn)

        main_lay.addWidget(inp_box)

        # Welcome message
        self.console.append(
            f"<span style='color: #5B8DEF; font-weight: bold;'>NEO Executive Developer Terminal & Subagent Shell [Version 3.1]</span><br>"
            f"<span style='color: #64748B;'>Working Environment: {self.cwd}</span><br>"
            f"<span style='color: #64748B;'>Type any system command, script, or use quick presets above.</span><br><br>"
        )

    # ── Execution Logic ───────────────────────────────────────────────────────

    def _on_return_pressed(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        self.cmd_input.clear()
        self.history.append(cmd)
        self.history_index = len(self.history)
        self.execute_command(cmd)

    def execute_command(self, cmd: str):
        if self._current_process is not None:
            self.console.append("<span style='color: #fbbf24;'>⚠️ A command is already executing. Stop it first.</span><br>")
            return

        self.diag_frame.setVisible(False)
        self.status_pill.setText("⚡ RUNNING")
        self.status_pill.setStyleSheet(f"color: {SEMANTIC_WARNING}; background: rgba(217, 164, 65, 0.15); border-radius: 10px; padding: 2px 8px;")
        self.abort_btn.setEnabled(True)

        self.console.append(f"<span style='color: #34D399; font-weight: bold;'>PS {self.cwd}&gt;</span> <span style='color: #ffffff;'>{cmd}</span><br>")

        def work():
            shell_cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd] if sys.platform == "win32" else ["bash", "-c", cmd]
            try:
                proc = subprocess.Popen(
                    shell_cmd,
                    cwd=str(self.cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                self._current_process = proc

                stdout_text = []
                stderr_text = []

                def read_stdout():
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            stdout_text.append(line)
                            QTimer.singleShot(0, lambda l=line: self._append_stdout(l))

                def read_stderr():
                    for line in iter(proc.stderr.readline, ''):
                        if line:
                            stderr_text.append(line)
                            QTimer.singleShot(0, lambda l=line: self._append_stderr(l))

                t1 = threading.Thread(target=read_stdout, daemon=True)
                t2 = threading.Thread(target=read_stderr, daemon=True)
                t1.start()
                t2.start()

                t1.join()
                t2.join()
                proc.wait()
                rc = proc.returncode

                QTimer.singleShot(0, lambda: self._on_process_complete(cmd, rc, "".join(stderr_text)))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._append_stderr(f"Execution Error: {e}\n"))
                QTimer.singleShot(0, lambda: self._on_process_complete(cmd, -1, str(e)))

        threading.Thread(target=work, daemon=True, name="terminal-runner").start()

    def _append_stdout(self, text: str):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.console.append(f"<span style='color: #C8D1DC;'>{safe}</span>")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def _append_stderr(self, text: str):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.console.append(f"<span style='color: #F87171;'>{safe}</span>")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def _on_process_complete(self, cmd: str, return_code: int, stderr_content: str):
        self._current_process = None
        self.abort_btn.setEnabled(False)

        if return_code == 0:
            self.status_pill.setText("● READY")
            self.status_pill.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")
            self.console.append("<span style='color: #64748B;'>Process completed with exit code 0.</span><br><br>")
        else:
            self.status_pill.setText(f"✕ EXIT {return_code}")
            self.status_pill.setStyleSheet(f"color: {SEMANTIC_ERROR}; background: rgba(217, 83, 79, 0.15); border-radius: 10px; padding: 2px 8px;")
            self.console.append(f"<span style='color: #F87171;'>Process terminated with exit code {return_code}.</span><br><br>")

            # Show AI Diagnosis Banner
            self.last_failed_cmd = cmd
            self.last_failed_err = stderr_content or f"Non-zero exit code {return_code}"
            self.diag_msg.setText(f"Command '{cmd[:30]}...' failed with exit code {return_code}.")
            self.diag_frame.setVisible(True)

    def _abort_command(self):
        if self._current_process is not None:
            try:
                self._current_process.terminate()
                self.console.append("<br><span style='color: #F87171; font-weight: bold;'>[Process Aborted by User]</span><br>")
            except Exception:
                pass

    def _clear_console(self):
        self.console.clear()

    def _trigger_ai_diagnosis(self):
        cmd = getattr(self, "last_failed_cmd", "")
        err = getattr(self, "last_failed_err", "")
        self.diagnose_requested.emit(cmd, err)
        self.console.append(f"<br><span style='color: {ACCENT_PRIMARY};'>🧠 Dispatched error diagnosis for '{cmd}' to NEO Assistant...</span><br>")

    # ── History Traversal ─────────────────────────────────────────────────────

    def _history_up(self):
        if not self.history:
            return
        if self.history_index > 0:
            self.history_index -= 1
            self.cmd_input.setText(self.history[self.history_index])

    def _history_down(self):
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.cmd_input.setText(self.history[self.history_index])
        else:
            self.history_index = len(self.history)
            self.cmd_input.clear()
