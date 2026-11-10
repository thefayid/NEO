"""
core/neo_terminal_studio.py — Embedded Dev Terminal & Autonomous Agent Shell for NEO.
Provides an interactive PowerShell / system terminal, live streaming command execution,
persistent working directory tracking (cd/pwd/cls emulation),
quick script runners, and AI error diagnosis bridge.
"""
from __future__ import annotations

import os
import re
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

# Shared executive styling tokens
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
            ("📊 Git Status", "git status -s"),
            ("🧪 Test Suite", "python -m unittest discover -s tests -p \"test_*.py\"" if (self.cwd / "tests").exists() else "python -c \"import main; print('Project Import OK')\""),
            ("📁 File List", "Get-ChildItem" if sys.platform == "win32" else "ls -la"),
            ("⚡ High CPU Tasks", "Get-Process | Sort-Object CPU -Descending | Select-Object -First 8 | Format-Table Id, ProcessName, CPU -AutoSize" if sys.platform == "win32" else "top -b -n 1 | head -n 12"),
        ]

        for label, cmd in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setFont(QFont("Segoe UI", 7))
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #14171C; color: {TEXT_WHITE};
                    border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
                }}
                QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; }}
            """)
            btn.clicked.connect(lambda ch, c=cmd: self.execute_command(c))
            preset_row.addWidget(btn)

        preset_row.addStretch()
        main_lay.addLayout(preset_row)

        # ── 3. Terminal Console Output Screen ────────────────────────────────
        self.console = QTextBrowser()
        self.console.setFont(QFont("Consolas", 9))
        self.console.setStyleSheet(f"""
            QTextBrowser {{
                background: #0B0E14;
                color: #C8D1DC;
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
                padding: 10px;
                line-height: 1.35;
            }}
        """)
        main_lay.addWidget(self.console, stretch=1)

        # ── 4. AI Error Diagnosis Banner (Hidden by default) ─────────────────
        self.diag_frame = QFrame()
        self.diag_frame.setVisible(False)
        self.diag_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(217, 83, 79, 0.1);
                border: 1px solid rgba(217, 83, 79, 0.4);
                border-radius: 6px;
            }}
        """)
        diag_lay = QHBoxLayout(self.diag_frame)
        diag_lay.setContentsMargins(10, 6, 10, 6)

        d_icn = QLabel("⚠️")
        d_icn.setFont(QFont("Segoe UI", 10))
        diag_lay.addWidget(d_icn)

        self.diag_msg = QLabel("Command failed with non-zero exit code.")
        self.diag_msg.setFont(QFont("Segoe UI", 8))
        self.diag_msg.setStyleSheet("color: #FCA5A5; border: none; background: transparent;")
        diag_lay.addWidget(self.diag_msg, stretch=1)

        self.diag_fix_btn = QPushButton("🧠 Ask NEO to Auto-Fix")
        self.diag_fix_btn.setFixedHeight(24)
        self.diag_fix_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.diag_fix_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.diag_fix_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_PRIMARY}; color: #ffffff;
                border: none; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #4a7fdc; }}
        """)
        self.diag_fix_btn.clicked.connect(self._trigger_ai_diagnosis)
        diag_lay.addWidget(self.diag_fix_btn)

        main_lay.addWidget(self.diag_frame)

        # ── 5. Command Input Box ─────────────────────────────────────────────
        inp_box = QFrame()
        inp_box.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        i_lay = QHBoxLayout(inp_box)
        i_lay.setContentsMargins(10, 4, 10, 4)
        i_lay.setSpacing(6)

        self.prompt_lbl = QLabel(f"PS {self.cwd.name}&gt;")
        self.prompt_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.prompt_lbl.setStyleSheet(f"color: {ACCENT_PRIMARY}; border: none; background: transparent;")
        i_lay.addWidget(self.prompt_lbl)

        self.cmd_input = _HistoryLineEdit()
        self.cmd_input.setFont(QFont("Consolas", 9))
        self.cmd_input.setPlaceholderText("Type command or script (e.g., git status, cd .., python script.py)...")
        self.cmd_input.setStyleSheet("""
            QLineEdit {
                background: transparent; color: #ffffff;
                border: none; padding: 2px 0;
            }
        """)
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

    # ── Execution Logic & Shell Built-in Emulation ────────────────────────────

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
        self.console.append(f"<span style='color: #34D399; font-weight: bold;'>PS {self.cwd}&gt;</span> <span style='color: #ffffff;'>{cmd}</span><br>")

        # ── Shell Built-in 1: cls / clear ──
        if cmd.strip().lower() in ("cls", "clear"):
            self.console.clear()
            return

        # ── Shell Built-in 2: pwd ──
        if cmd.strip().lower() == "pwd":
            self.console.append(f"<span style='color: #94A3B8;'>{self.cwd}</span><br><br>")
            return

        # ── Shell Built-in 3: cd / chdir / Set-Location ──
        cd_match = re.match(r'^(?:cd|chdir|set-location)(?:\s+(.*))?$', cmd.strip(), re.IGNORECASE)
        if cd_match:
            target_str = (cd_match.group(1) or "").strip()
            # Strip quotes if present
            if (target_str.startswith('"') and target_str.endswith('"')) or (target_str.startswith("'") and target_str.endswith("'")):
                target_str = target_str[1:-1]

            if not target_str or target_str == "~":
                new_path = Path.home()
            else:
                new_path = (self.cwd / target_str).resolve() if not Path(target_str).is_absolute() else Path(target_str).resolve()

            if new_path.is_dir():
                self.cwd = new_path
                self.cwd_lbl.setText(f"Working Directory: {self.cwd}")
                self.prompt_lbl.setText(f"PS {self.cwd.name}&gt;")
                self.console.append(f"<span style='color: #94A3B8;'>Changed directory to: {self.cwd}</span><br><br>")
            else:
                self.console.append(f"<span style='color: #F87171;'>Cannot find path '{target_str}' because it does not exist.</span><br><br>")
            return

        # ── Subprocess Execution ──
        self.status_pill.setText("⚡ RUNNING")
        self.status_pill.setStyleSheet(f"color: {SEMANTIC_WARNING}; background: rgba(217, 164, 65, 0.15); border-radius: 10px; padding: 2px 8px;")
        self.abort_btn.setEnabled(True)

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
            self.diag_msg.setText(f"Command '{cmd[:35]}...' failed with exit code {return_code}.")
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
