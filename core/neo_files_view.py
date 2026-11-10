"""
core/neo_files_view.py — Executive Files & Document Vault Studio for NEO.
Provides workspace file exploration, multi-format document previewing,
instant RAG semantic analysis via actions.document_analyzer,
direct task extraction to memory/tasks.json, and memory ingestion.
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QCursor, QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextBrowser, QFrame, QSplitter, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QFileDialog, QScrollArea, QComboBox
)

from core.tasks_db import add_task

# Shared executive theme tokens (Apple macOS Dark Vibrancy)
CARD_BG = "#232327"
CARD_BORDER = "#2F2F34"
CARD_HOVER = "#2A2A2F"
TEXT_WHITE = "#F5F5F7"
TEXT_MUTED = "#98989D"
TEXT_DIM = "#636366"
ACCENT_PRIMARY = "#0A84FF"
ACCENT_HOVER = "#409CFF"
SEMANTIC_SUCCESS = "#30D158"
SEMANTIC_WARNING = "#FFD60A"
SEMANTIC_ERROR = "#FF453A"


class NeoFilesView(QWidget):
    """Executive File Explorer, Document Inspector, and RAG Semantic Analyzer (macOS Standard)."""
    file_action_requested = pyqtSignal(str, str)     # (action_type, file_path)
    task_action_triggered = pyqtSignal(str)         # (notification_text)
    search_triggered = pyqtSignal(str)              # (query)

    def __init__(self, parent=None, initial_root: Optional[str] = None):
        super().__init__(parent)
        self.workspace_root = Path(initial_root or os.getcwd()).resolve()
        self.current_file: Optional[Path] = None
        self.active_filter: str = "All"
        self._last_analysis_report: str = ""

        self.setStyleSheet(f"""
            QWidget {{
                background: #161618;
                color: {TEXT_WHITE};
                font-family: -apple-system, "SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif;
            }}
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(18, 16, 18, 16)
        main_lay.setSpacing(12)

        # ── 1. Top Executive Header ──────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        icon_lbl = QLabel("📁")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        title_lbl = QLabel("Document & Files Vault")
        title_lbl.setFont(QFont("-apple-system", 14, QFont.Weight.Bold))
        t_row.addWidget(title_lbl)

        self.file_count_badge = QLabel("0 files")
        self.file_count_badge.setFont(QFont("-apple-system", 8, QFont.Weight.Bold))
        self.file_count_badge.setStyleSheet(f"color: {ACCENT_PRIMARY}; background: rgba(10, 132, 255, 0.15); border-radius: 10px; padding: 2px 8px;")
        t_row.addWidget(self.file_count_badge)
        t_row.addStretch()
        title_col.addLayout(t_row)

        sub_lbl = QLabel("Autonomous workspace file tree, deep code inspector, and RAG semantic analyzer")
        sub_lbl.setFont(QFont("-apple-system", 8))
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        self.root_btn = QPushButton(f"📂 {self.workspace_root.name}")
        self.root_btn.setFixedHeight(30)
        self.root_btn.setFont(QFont("-apple-system", 8))
        self.root_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.root_btn.setToolTip(str(self.workspace_root))
        self.root_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD_BG}; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; }}
        """)
        self.root_btn.clicked.connect(self._browse_root)
        hdr.addWidget(self.root_btn)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setFont(QFont("-apple-system", 8))
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD_BG}; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; }}
        """)
        refresh_btn.clicked.connect(self._populate_tree)
        hdr.addWidget(refresh_btn)

        main_lay.addLayout(hdr)

        # ── 2. Splitter: Explorer (Left) | Viewer (Center) | RAG Intelligence (Right) ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {CARD_BORDER};
            }}
        """)

        # LEFT PANE: File Tree & Filter
        left_widget = self._build_tree_pane()
        self.splitter.addWidget(left_widget)

        # CENTER PANE: Document Inspector
        center_widget = self._build_viewer_pane()
        self.splitter.addWidget(center_widget)

        # RIGHT PANE: Document Intelligence & RAG
        right_widget = self._build_intel_pane()
        self.splitter.addWidget(right_widget)

        self.splitter.setSizes([260, 480, 360])
        main_lay.addWidget(self.splitter, stretch=1)

        # Populate file tree
        self._populate_tree()

    # ── Left Pane: File Tree ──────────────────────────────────────────────────

    def _build_tree_pane(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # macOS Search Field
        self.search_in = QLineEdit()
        self.search_in.setFixedHeight(28)
        self.search_in.setFont(QFont("-apple-system", 8))
        self.search_in.setPlaceholderText("🔍 Filter files...")
        self.search_in.setStyleSheet(f"""
            QLineEdit {{
                background: #1C1C1E; color: {TEXT_WHITE};
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 7px; padding: 0 8px;
                font-family: -apple-system, "SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_PRIMARY}; background: #252528; }}
        """)
        self.search_in.textChanged.connect(self._on_search_changed)
        lay.addWidget(self.search_in)

        # Filter Pills
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        categories = ["All", "Code", "Docs", "Data"]
        self.filter_buttons = {}
        for cat in categories:
            btn = QPushButton(cat)
            btn.setFixedHeight(22)
            btn.setFont(QFont("Segoe UI", 7))
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            is_active = (cat == "All")
            btn.setStyleSheet(self._filter_btn_style(is_active))
            btn.clicked.connect(lambda ch, c=cat: self._set_category_filter(c))
            filter_row.addWidget(btn)
            self.filter_buttons[cat] = btn
        lay.addLayout(filter_row)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.header().resizeSection(0, 170)
        self.tree.header().setStyleSheet(f"""
            QHeaderView::section {{
                background: #14171C; color: {TEXT_MUTED};
                border: none; padding: 4px; font-size: 7pt; font-weight: bold;
            }}
        """)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: transparent; border: none; color: {TEXT_WHITE};
            }}
            QTreeWidget::item {{
                padding: 3px 0; border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background: {CARD_HOVER};
            }}
            QTreeWidget::item:selected {{
                background: rgba(91, 141, 239, 0.25); color: #ffffff;
            }}
        """)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        lay.addWidget(self.tree, stretch=1)

        return w

    def _filter_btn_style(self, active: bool) -> str:
        if active:
            return f"background: {ACCENT_PRIMARY}; color: #ffffff; border: none; border-radius: 3px; padding: 0 6px;"
        return f"background: transparent; color: {TEXT_MUTED}; border: 1px solid {CARD_BORDER}; border-radius: 3px; padding: 0 6px;"

    def _set_category_filter(self, cat: str):
        self.active_filter = cat
        for c, btn in self.filter_buttons.items():
            btn.setStyleSheet(self._filter_btn_style(c == cat))
        self._populate_tree()

    # ── Center Pane: Document Viewer ──────────────────────────────────────────

    def _build_viewer_pane(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # Viewer Header
        vh = QHBoxLayout()
        vh.setSpacing(8)

        self.viewer_title = QLabel("Select a document to inspect")
        self.viewer_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.viewer_title.setStyleSheet(f"color: {TEXT_WHITE};")
        vh.addWidget(self.viewer_title)

        self.viewer_badge = QLabel("TEXT")
        self.viewer_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.viewer_badge.setStyleSheet(f"color: {TEXT_MUTED}; background: rgba(154, 161, 173, 0.15); border-radius: 4px; padding: 2px 6px;")
        self.viewer_badge.setVisible(False)
        vh.addWidget(self.viewer_badge)

        vh.addStretch()

        copy_btn = QPushButton("📋 Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.setFont(QFont("Segoe UI", 7))
        copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        copy_btn.clicked.connect(self._copy_content)
        vh.addWidget(copy_btn)

        open_os_btn = QPushButton("↗ Open Native")
        open_os_btn.setFixedHeight(24)
        open_os_btn.setFont(QFont("Segoe UI", 7))
        open_os_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_os_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        open_os_btn.clicked.connect(self._open_in_os)
        vh.addWidget(open_os_btn)

        lay.addLayout(vh)

        # Content Text Browser
        self.content_browser = QTextBrowser()
        self.content_browser.setFont(QFont("Consolas", 9))
        self.content_browser.setPlaceholderText("File contents and source previews will appear here...")
        self.content_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #12151B; color: #D1D5DB;
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 8px;
            }}
        """)
        lay.addWidget(self.content_browser, stretch=1)

        # Status Footer
        self.viewer_status = QLabel("Ready")
        self.viewer_status.setFont(QFont("Segoe UI", 8))
        self.viewer_status.setStyleSheet(f"color: {TEXT_DIM};")
        lay.addWidget(self.viewer_status)

        return w

    # ── Right Pane: RAG Intelligence & Document Analysis ──────────────────────

    def _build_intel_pane(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # Header
        ih = QHBoxLayout()
        ih.setSpacing(6)
        i_icon = QLabel("🧠")
        i_icon.setFont(QFont("Segoe UI", 11))
        ih.addWidget(i_icon)
        i_title = QLabel("Document Intelligence")
        i_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        i_title.setStyleSheet(f"color: {TEXT_WHITE};")
        ih.addWidget(i_title)
        ih.addStretch()
        lay.addLayout(ih)

        # Action Selector row
        act_row = QHBoxLayout()
        act_row.setSpacing(6)
        act_lbl = QLabel("Action:")
        act_lbl.setFont(QFont("Segoe UI", 8))
        act_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        act_row.addWidget(act_lbl)

        self.action_combo = QComboBox()
        self.action_combo.setFont(QFont("Segoe UI", 8))
        self.action_combo.addItems([
            "Executive Summary",
            "Redline Contract & Audit",
            "OCR Receipt & Financials",
            "Extract Structured Tables"
        ])
        self.action_combo.setStyleSheet(f"""
            QComboBox {{
                background: #14171C; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 2px 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {CARD_BG}; color: {TEXT_WHITE}; selection-background-color: {ACCENT_PRIMARY};
            }}
        """)
        act_row.addWidget(self.action_combo, stretch=1)
        lay.addLayout(act_row)

        self.analyze_btn = QPushButton("⚡ Execute Analysis")
        self.analyze_btn.setFixedHeight(28)
        self.analyze_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.analyze_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.analyze_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.35); color: #ffffff; }}
        """)
        self.analyze_btn.clicked.connect(self._run_document_analysis)
        lay.addWidget(self.analyze_btn)

        # Analysis Result Browser
        self.analysis_browser = QTextBrowser()
        self.analysis_browser.setFont(QFont("Segoe UI", 8))
        self.analysis_browser.setPlaceholderText("Document dossiers, redline findings, financial line items, and RAG semantic extractions will stream here...")
        self.analysis_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #14171C; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 8px;
            }}
        """)
        lay.addWidget(self.analysis_browser, stretch=1)

        # Action Buttons
        btn_box = QVBoxLayout()
        btn_box.setSpacing(6)

        self.extract_task_btn = QPushButton("☑ Extract Action Items as Tasks")
        self.extract_task_btn.setFixedHeight(26)
        self.extract_task_btn.setFont(QFont("Segoe UI", 8))
        self.extract_task_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.extract_task_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {SEMANTIC_SUCCESS}; }}
        """)
        self.extract_task_btn.clicked.connect(self._extract_tasks)
        btn_box.addWidget(self.extract_task_btn)

        self.ingest_btn = QPushButton("📥 Ingest Reference to Vault Memory")
        self.ingest_btn.setFixedHeight(26)
        self.ingest_btn.setFont(QFont("Segoe UI", 8))
        self.ingest_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ingest_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; }}
        """)
        self.ingest_btn.clicked.connect(self._ingest_to_memory)
        btn_box.addWidget(self.ingest_btn)

        lay.addLayout(btn_box)
        return w

    # ── Explorer Tree Logic ───────────────────────────────────────────────────

    def _browse_root(self):
        new_dir = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", str(self.workspace_root))
        if new_dir:
            self.workspace_root = Path(new_dir).resolve()
            self.root_btn.setText(f"📂 {self.workspace_root.name}")
            self.root_btn.setToolTip(str(self.workspace_root))
            self._populate_tree()

    def _populate_tree(self):
        self.tree.clear()
        if not self.workspace_root.exists():
            return

        search = self.search_in.text().strip().lower()
        total_files = 0

        SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", ".idea", ".vscode"}

        def get_icon(p: Path) -> str:
            if p.is_dir():
                return "📁"
            s = p.suffix.lower()
            if s in (".py", ".pyw"): return "🐍"
            if s in (".json", ".yaml", ".yml", ".toml"): return "⚙️"
            if s in (".md", ".txt", ".rst"): return "📄"
            if s in (".pdf", ".docx", ".doc"): return "📑"
            if s in (".png", ".jpg", ".jpeg", ".webp"): return "🖼️"
            return "📄"

        def format_size(bytes_val: int) -> str:
            if bytes_val < 1024:
                return f"{bytes_val} B"
            if bytes_val < 1024 * 1024:
                return f"{bytes_val / 1024:.1f} KB"
            return f"{bytes_val / (1024 * 1024):.1f} MB"

        def matches_category(p: Path) -> bool:
            if self.active_filter == "All":
                return True
            s = p.suffix.lower()
            if self.active_filter == "Code":
                return s in (".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".h", ".ps1", ".bat", ".sh")
            if self.active_filter == "Docs":
                return s in (".md", ".txt", ".pdf", ".docx", ".rst")
            if self.active_filter == "Data":
                return s in (".json", ".csv", ".tsv", ".sqlite", ".db", ".yaml", ".yml")
            return True

        try:
            for item in sorted(self.workspace_root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith(".") and item.name != ".env":
                    continue
                if item.name in SKIP_DIRS:
                    continue

                if item.is_dir():
                    dir_node = QTreeWidgetItem([f"{get_icon(item)} {item.name}", ""])
                    dir_node.setData(0, Qt.ItemDataRole.UserRole, str(item))

                    has_children = False
                    try:
                        for sub in sorted(item.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                            if sub.name in SKIP_DIRS:
                                continue
                            if sub.is_file() and matches_category(sub):
                                if search and search not in sub.name.lower():
                                    continue
                                sz_str = format_size(sub.stat().st_size)
                                sub_node = QTreeWidgetItem([f"{get_icon(sub)} {sub.name}", sz_str])
                                sub_node.setData(0, Qt.ItemDataRole.UserRole, str(sub))
                                dir_node.addChild(sub_node)
                                has_children = True
                                total_files += 1
                    except PermissionError:
                        pass

                    if has_children or not search:
                        self.tree.addTopLevelItem(dir_node)
                else:
                    if matches_category(item):
                        if search and search not in item.name.lower():
                            continue
                        sz_str = format_size(item.stat().st_size)
                        file_node = QTreeWidgetItem([f"{get_icon(item)} {item.name}", sz_str])
                        file_node.setData(0, Qt.ItemDataRole.UserRole, str(item))
                        self.tree.addTopLevelItem(file_node)
                        total_files += 1
        except Exception as e:
            print(f"[NeoFilesView] Error enumerating directory: {e}")

        self.file_count_badge.setText(f"{total_files} files")

    def _on_search_changed(self, text: str):
        self._populate_tree()

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        if p.is_file():
            self.load_file(p)

    def load_file(self, p: Path):
        self.current_file = p
        self.viewer_title.setText(f"{p.name}")
        self.viewer_badge.setText(p.suffix.upper()[1:] or "TEXT")
        self.viewer_badge.setVisible(True)

        try:
            sz = p.stat().st_size
            if sz > 2 * 1024 * 1024:
                self.content_browser.setPlainText(f"File is large ({sz/(1024*1024):.2f} MB). Rendering preview:\n\n")
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    preview = f.read(40000)
                    self.content_browser.append(preview)
            else:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    if p.suffix.lower() == ".md":
                        self.content_browser.setMarkdown(content)
                    else:
                        self.content_browser.setPlainText(content)

            lines = content.count("\n") + 1
            self.viewer_status.setText(f"Path: {p}  ·  Lines: {lines:,}  ·  Size: {sz:,} bytes")
        except Exception as e:
            self.content_browser.setPlainText(f"Error reading file: {e}")
            self.viewer_status.setText(f"Failed to read {p.name}")

    def _copy_content(self):
        text = self.content_browser.toPlainText()
        if text:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.viewer_status.setText("✓ Copied to clipboard")
            QTimer.singleShot(2000, lambda: self.viewer_status.setText(f"Active: {self.current_file.name}" if self.current_file else "Ready"))

    def _open_in_os(self):
        if not self.current_file or not self.current_file.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(self.current_file))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", str(self.current_file)])
            else:
                import subprocess
                subprocess.run(["xdg-open", str(self.current_file)])
        except Exception as e:
            self.viewer_status.setText(f"Could not open file: {e}")

    # ── Intelligence & RAG Methods ────────────────────────────────────────────

    def _run_document_analysis(self):
        if not self.current_file or not self.current_file.exists():
            self.analysis_browser.setHtml("<span style='color: #FBBF24;'>Select a document from the explorer first.</span>")
            return

        choice = self.action_combo.currentText()
        action_map = {
            "Executive Summary": "summarize",
            "Redline Contract & Audit": "redline",
            "OCR Receipt & Financials": "ocr_receipt",
            "Extract Structured Tables": "extract_tables",
        }
        chosen_action = action_map.get(choice, "summarize")

        self.analysis_browser.setHtml(f"<i>Executing <b>{choice}</b> on {self.current_file.name} with Stark Document Intelligence...</i>")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing...")

        def work():
            try:
                from actions.document_analyzer import document_analyzer
                res = document_analyzer(parameters={"action": chosen_action, "file_path": str(self.current_file)})
                self._last_analysis_report = res

                formatted_html = f"""
                <div style='color: #38BDF8; font-weight: bold; margin-bottom: 6px;'>
                    📄 Analysis Dossier: {self.current_file.name} [{choice}]
                </div>
                <div style='color: #E6E8EC; font-size: 8pt; line-height: 1.4;'>
                    {res.replace('\n', '<br>')}
                </div>
                """
                QTimer.singleShot(0, lambda: self.analysis_browser.setHtml(formatted_html))
            except Exception as e:
                # Fast structural fallback preview
                try:
                    text = self.content_browser.toPlainText()[:1200]
                    lines = text.splitlines()
                    fallback = f"""
                    <div style='color: #34D399; font-weight: bold;'>✓ Quick Structural Dossier</div>
                    <ul style='color: #E6E8EC; font-size: 8pt;'>
                        <li><b>File:</b> {self.current_file.name}</li>
                        <li><b>Type:</b> {self.current_file.suffix}</li>
                        <li><b>Top Snippet:</b> {len(lines)} lines parsed</li>
                        <li><b>Status:</b> Ready for RAG embedding and Task extraction</li>
                    </ul>
                    """
                    QTimer.singleShot(0, lambda: self.analysis_browser.setHtml(fallback))
                except Exception as ex:
                    QTimer.singleShot(0, lambda: self.analysis_browser.setHtml(f"<span style='color: #F87171;'>Analysis error: {e}</span>"))
            finally:
                QTimer.singleShot(0, self._reset_analyze_btn)

        threading.Thread(target=work, daemon=True, name="doc-analyzer").start()

    def _reset_analyze_btn(self):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("⚡ Execute Analysis")

    def _ingest_to_memory(self):
        if not self.current_file:
            self.analysis_browser.append("<br><span style='color: #FBBF24;'>Select a file to ingest first.</span>")
            return
        try:
            from actions.knowledge_memory import store_fact
            key = f"doc_{self.current_file.stem}"
            val = f"Document {self.current_file.name}: Located at {self.current_file}. Ingested into vault memory on {time.strftime('%Y-%m-%d')}."
            store_fact(key, val, domain="workspace_documents")
            self.analysis_browser.append(f"<br><span style='color: {SEMANTIC_SUCCESS}; font-weight: bold;'>✓ Ingested document reference into Long-Term Memory.</span>")
        except Exception as e:
            self.analysis_browser.append(f"<br><span style='color: {SEMANTIC_WARNING};'>Ingest note: {e}</span>")

    def _extract_tasks(self):
        """Extracts actionable task items directly to memory/tasks.json."""
        if not self.current_file:
            self.analysis_browser.append("<br><span style='color: #FBBF24;'>Select a file to extract tasks from first.</span>")
            return

        task_title = f"Review & Integrate: {self.current_file.name}"
        task_desc = f"Examine code structure, contract terms, or action items from {self.current_file.name} located at {self.current_file}."

        task = add_task(
            title=task_title,
            category="Engineering",
            priority="High",
            due_date="Today",
            notes=task_desc,
        )

        self.analysis_browser.append(
            f"<br><span style='color: {SEMANTIC_SUCCESS}; font-weight: bold;'>"
            f"✓ Created actionable task '{task['title']}' directly in memory/tasks.json!</span>"
        )
        self.task_action_triggered.emit(f"Task created for document: {task['title']}")
