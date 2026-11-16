"""
neo/ui/dashboard.py — Real-Time Local Controller Dashboard and Safety Command Center.
Built with Apple macOS Sequoia / Tahoe Native Design System (PyQt6).

Architectural Guarantees:
1. Native Apple macOS Look & Feel:
   - Frameless window with Acrylic/Mica frosted vibrancy fallback (apply_macos_vibrancy).
   - Authentic top-left Apple Traffic Lights (🔴 Close, 🟡 Minimize, 🟢 Zoom/Maximize).
   - Apple Grouped Inset Cards with 10px-14px continuous radii and subtle 1px borders.
   - Vector Lucide 1.5-stroke icons and Inter typography scale with optical tracking.
2. Live Multi-Panel Visualization:
   - Current stage & step progression indicator with macOS progress bar.
   - "What Neo Sees": Real-time scaled screenshot preview canvas & active interactive element table.
   - "Planned Action": Action name badge pill, monospace parameter block, and model rationale thought bubble.
   - Live streaming execution audit log with colored severity markers (INFO, SUCCESS, WARNING, ERROR, SAFETY).
3. Direct Human-in-the-Loop Controls:
   - Green "Approve" button and Red "Deny" button wired to Confirmation Gates.
   - Prominent, high-priority Red Destructive "EMERGENCY STOP (F12)" button halting all operations immediately.
   - One-click Voice Input trigger integrating local Whisper transcription.
4. Thread-Safe Architecture:
   - Thread-safe UI update queue; background agents, task managers, and workers can
     dispatch state updates without GUI thread locking or race conditions.
"""
from __future__ import annotations

import io
import json
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.ui.triggers import GlobalHotkeyManager, VoiceTrigger

logger = logging.getLogger("neo.ui.dashboard")


class ScreenshotCanvas:
    """Widget container that draws a screenshot while strictly preserving aspect ratio."""

    def __init__(self, parent=None):
        from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
        from core.theme_provider import theme

        self.widget = QFrame(parent)
        self.widget.setObjectName("screenshotCanvas")
        self.widget.setMinimumHeight(220)
        self.widget.setStyleSheet(f"""
            QFrame#screenshotCanvas {{
                background-color: {theme.colors.controlBackgroundSecondary};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        lay = QVBoxLayout(self.widget)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_image = QLabel(self.widget)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setText("[Awaiting Screenshot Telemetry]")
        self.lbl_image.setFont(theme.font(theme.typography.caption_1))
        self.lbl_image.setStyleSheet(f"color: {theme.colors.labelTertiary}; background: transparent; border: none;")
        lay.addWidget(self.lbl_image)

        self._current_pixmap: Optional[QPixmap] = None

    def set_image(self, screenshot_path_or_bytes: Union[str, Path, bytes]) -> None:
        from PyQt6.QtGui import QPixmap, QImage
        from PyQt6.QtCore import Qt

        try:
            pix = QPixmap()
            if isinstance(screenshot_path_or_bytes, (str, Path)):
                pix.load(str(screenshot_path_or_bytes))
            else:
                pix.loadFromData(screenshot_path_or_bytes)

            if not pix.isNull():
                self._current_pixmap = pix
                self._render_scaled()
            else:
                self.lbl_image.setText("[Invalid Screenshot Data]")
        except Exception as e:
            logger.debug("Failed to set screenshot: %s", e)
            self.lbl_image.setText("[Screenshot Render Error]")

    def _render_scaled(self) -> None:
        from PyQt6.QtCore import Qt
        if not self._current_pixmap:
            return
        target_w = max(200, self.widget.width() - 16)
        target_h = max(180, self.widget.height() - 16)
        scaled = self._current_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_image.setPixmap(scaled)
        self.lbl_image.setText("")


class MacOSDashboardWindow:
    """
    Apple macOS Sequoia / Tahoe Styled Controller Dashboard Window.
    """

    def __init__(self, controller: "NeoDashboard") -> None:
        from PyQt6.QtCore import Qt, QPoint, QTimer
        from PyQt6.QtGui import QFont, QColor
        from PyQt6.QtWidgets import (
            QWidget,
            QFrame,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QProgressBar,
            QSplitter,
            QTreeWidget,
            QTreeWidgetItem,
            QHeaderView,
            QTextEdit,
            QSizePolicy,
        )
        from core.theme_provider import theme
        from core.macos_components import MacOSButton, render_lucide_icon, MacOSScrollArea
        from core.macos_window import apply_macos_vibrancy, MacOSTrafficLights

        self.controller = controller
        self.window = QWidget()
        self.window.setWindowTitle(controller.title)
        self.window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.window.resize(1140, 740)
        self.window.setMinimumSize(960, 640)

        # Outer Layout
        root_lay = QVBoxLayout(self.window)
        root_lay.setContentsMargins(10, 10, 10, 10)

        # Container Frame
        self.container = QFrame(self.window)
        self.container.setObjectName("dashboardRoot")
        self.container.setStyleSheet(f"""
            QFrame#dashboardRoot {{
                background-color: {theme.colors.windowBackground};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {theme.radii.lg}px;
            }}
        """)
        root_lay.addWidget(self.container)

        main_lay = QVBoxLayout(self.container)
        main_lay.setContentsMargins(16, 12, 16, 14)
        main_lay.setSpacing(10)

        # ── 1. Top Draggable Unified Toolbar with Traffic Lights ──────────────
        self.top_bar = QFrame(self.container)
        self.top_bar.setFixedHeight(38)
        self.top_bar.setStyleSheet("background: transparent; border: none;")
        top_lay = QHBoxLayout(self.top_bar)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(12)

        self.traffic_lights = MacOSTrafficLights(self.top_bar)
        self.traffic_lights.close_clicked.connect(self.window.close)
        self.traffic_lights.minimize_clicked.connect(self.window.showMinimized)
        self.traffic_lights.zoom_clicked.connect(self._toggle_zoom)
        top_lay.addWidget(self.traffic_lights, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Centered Brand Title
        title_box = QHBoxLayout()
        title_box.setSpacing(6)
        lbl_brand = QLabel("NEO CONTROLLER", self.top_bar)
        lbl_brand.setFont(theme.font(theme.typography.headline))
        lbl_brand.setStyleSheet(f"color: {theme.colors.labelPrimary}; font-weight: bold;")
        title_box.addWidget(lbl_brand)

        lbl_sub = QLabel("•  Deterministic Dual-Verified Engine", self.top_bar)
        lbl_sub.setFont(theme.font(theme.typography.caption_1))
        lbl_sub.setStyleSheet(f"color: {theme.colors.labelTertiary};")
        title_box.addWidget(lbl_sub)
        top_lay.addLayout(title_box)

        top_lay.addStretch()

        # Status Badge Pill
        self.lbl_status = QLabel("STATUS: IDLE", self.top_bar)
        self.lbl_status.setFont(theme.font(theme.typography.caption_1))
        self._update_status_pill("IDLE")
        top_lay.addWidget(self.lbl_status, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        main_lay.addWidget(self.top_bar)

        # Dragging logic for frameless window
        self._drag_pos = QPoint()

        def _bar_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = ev.globalPosition().toPoint() - self.window.frameGeometry().topLeft()

        def _bar_move(ev):
            if ev.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
                self.window.move(ev.globalPosition().toPoint() - self._drag_pos)

        def _bar_double(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._toggle_zoom()

        self.top_bar.mousePressEvent = _bar_press
        self.top_bar.mouseMoveEvent = _bar_move
        self.top_bar.mouseDoubleClickEvent = _bar_double

        # ── 2. Stage Progression Card ─────────────────────────────────────────
        stage_card = QFrame(self.container)
        stage_card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        stage_lay = QVBoxLayout(stage_card)
        stage_lay.setContentsMargins(14, 8, 14, 8)
        stage_lay.setSpacing(6)

        s_header = QHBoxLayout()
        self.lbl_stage = QLabel("Current Stage: [No Active Task]", stage_card)
        self.lbl_stage.setFont(theme.font(theme.typography.subheadline))
        self.lbl_stage.setStyleSheet(f"color: {theme.colors.labelPrimary}; font-weight: bold; border: none; background: transparent;")
        s_header.addWidget(self.lbl_stage)
        s_header.addStretch()

        self.lbl_step_counter = QLabel("Step 0 / 25", stage_card)
        self.lbl_step_counter.setFont(theme.font(theme.typography.caption_1))
        self.lbl_step_counter.setStyleSheet(f"color: {theme.colors.labelSecondary}; border: none; background: transparent;")
        s_header.addWidget(self.lbl_step_counter)
        stage_lay.addLayout(s_header)

        self.stage_pbar = QProgressBar(stage_card)
        self.stage_pbar.setFixedHeight(5)
        self.stage_pbar.setRange(0, 25)
        self.stage_pbar.setValue(0)
        self.stage_pbar.setTextVisible(False)
        self.stage_pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {theme.colors.controlBackgroundSecondary};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {theme.accent_color};
                border-radius: 2px;
            }}
        """)
        stage_lay.addWidget(self.stage_pbar)
        main_lay.addWidget(stage_card)

        # ── 3. Main Splitter (Left: Vision/Snapshot, Right: Actions/Audit) ────
        splitter = QSplitter(Qt.Orientation.Horizontal, self.container)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {theme.colors.separator};
                width: 1px;
            }}
        """)

        # ── LEFT PANE: Vision & DOM Telemetry ──
        left_pane = QWidget()
        left_lay = QVBoxLayout(left_pane)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(8)

        v_head = QHBoxLayout()
        lbl_v_title = QLabel("WHAT NEO SEES", left_pane)
        lbl_v_title.setFont(theme.font(theme.typography.caption_1))
        lbl_v_title.setStyleSheet(f"color: {theme.colors.labelSecondary}; font-weight: bold;")
        v_head.addWidget(lbl_v_title)
        v_head.addStretch()
        left_lay.addLayout(v_head)

        # Screenshot Preview Canvas
        self.screenshot_canvas = ScreenshotCanvas(left_pane)
        left_lay.addWidget(self.screenshot_canvas.widget)

        # Interactive Element Treeview
        tree_card = QFrame(left_pane)
        tree_card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        tree_lay = QVBoxLayout(tree_card)
        tree_lay.setContentsMargins(4, 4, 4, 4)

        self.element_tree = QTreeWidget(tree_card)
        self.element_tree.setColumnCount(5)
        self.element_tree.setHeaderLabels(["ID", "Role", "Name / Accessible Text", "Automation ID", "Enabled"])
        self.element_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {theme.colors.labelPrimary};
                font-family: -apple-system, "SF Pro Text", "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
            }}
            QTreeWidget::item {{
                height: 24px;
                padding-left: 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: rgba(10, 132, 255, 0.25);
                border-radius: 4px;
            }}
            QHeaderView::section {{
                background-color: {theme.colors.controlBackgroundSecondary};
                color: {theme.colors.labelTertiary};
                border: none;
                border-bottom: 1px solid {theme.colors.separator};
                padding: 4px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.element_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.element_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.element_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.element_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.element_tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tree_lay.addWidget(self.element_tree)
        left_lay.addWidget(tree_card, stretch=1)

        splitter.addWidget(left_pane)

        # ── RIGHT PANE: Planned Action & Live Audit Log ──
        right_pane = QWidget()
        right_lay = QVBoxLayout(right_pane)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(8)

        # Planned Action Inset Card
        lbl_act_title = QLabel("PLANNED ACTION & REASONING", right_pane)
        lbl_act_title.setFont(theme.font(theme.typography.caption_1))
        lbl_act_title.setStyleSheet(f"color: {theme.colors.labelSecondary}; font-weight: bold;")
        right_lay.addWidget(lbl_act_title)

        act_card = QFrame(right_pane)
        act_card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        act_lay = QVBoxLayout(act_card)
        act_lay.setContentsMargins(14, 10, 14, 10)
        act_lay.setSpacing(6)

        act_h = QHBoxLayout()
        self.lbl_action_name = QLabel("ACTION: IDLE", act_card)
        self.lbl_action_name.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.lbl_action_name.setStyleSheet(f"""
            color: {theme.accent_color};
            background-color: rgba(10, 132, 255, 0.12);
            border: 1px solid rgba(10, 132, 255, 0.3);
            border-radius: 6px;
            padding: 3px 8px;
        """)
        act_h.addWidget(self.lbl_action_name)
        act_h.addStretch()
        act_lay.addLayout(act_h)

        self.lbl_action_details = QLabel("Parameters: {}", act_card)
        self.lbl_action_details.setFont(QFont("Consolas", 9))
        self.lbl_action_details.setStyleSheet(f"""
            color: {theme.colors.labelPrimary};
            background-color: {theme.colors.controlBackgroundSecondary};
            border-radius: 6px;
            padding: 6px 8px;
            border: 1px solid {theme.colors.separator};
        """)
        self.lbl_action_details.setWordWrap(True)
        act_lay.addWidget(self.lbl_action_details)

        self.lbl_action_thought = QLabel("Thought: Agent is waiting for instructions.", act_card)
        self.lbl_action_thought.setFont(theme.font(theme.typography.caption_1))
        self.lbl_action_thought.setStyleSheet(f"color: {theme.colors.labelSecondary}; font-style: italic; border: none; background: transparent;")
        self.lbl_action_thought.setWordWrap(True)
        act_lay.addWidget(self.lbl_action_thought)
        right_lay.addWidget(act_card)

        # Live Audit Log Card
        lbl_log_title = QLabel("LIVE AUDIT LOG", right_pane)
        lbl_log_title.setFont(theme.font(theme.typography.caption_1))
        lbl_log_title.setStyleSheet(f"color: {theme.colors.labelSecondary}; font-weight: bold;")
        right_lay.addWidget(lbl_log_title)

        log_card = QFrame(right_pane)
        log_card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        log_lay = QVBoxLayout(log_card)
        log_lay.setContentsMargins(6, 6, 6, 6)

        self.txt_log = QTextEdit(log_card)
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        self.txt_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {theme.colors.labelPrimary};
                line-height: 1.4;
            }}
        """)
        log_lay.addWidget(self.txt_log)
        right_lay.addWidget(log_card, stretch=1)

        splitter.addWidget(right_pane)
        splitter.setSizes([540, 540])
        main_lay.addWidget(splitter, stretch=1)

        # ── 4. Bottom Controls Bar & Emergency Stop ───────────────────────────
        ctrl_dock = QFrame(self.container)
        ctrl_dock.setFixedHeight(54)
        ctrl_dock.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        dock_lay = QHBoxLayout(ctrl_dock)
        dock_lay.setContentsMargins(12, 6, 12, 6)
        dock_lay.setSpacing(10)

        # Approve Button
        self.btn_approve = MacOSButton("✔ APPROVE", variant=MacOSButton.Variant.DEFAULT, parent=ctrl_dock)
        self.btn_approve.setFixedWidth(120)
        self.btn_approve.setEnabled(False)
        self.btn_approve.clicked.connect(self.controller._on_approve)
        dock_lay.addWidget(self.btn_approve)

        # Deny Button
        self.btn_deny = MacOSButton("✖ DENY", variant=MacOSButton.Variant.DESTRUCTIVE, parent=ctrl_dock)
        self.btn_deny.setFixedWidth(110)
        self.btn_deny.setEnabled(False)
        self.btn_deny.clicked.connect(self.controller._on_deny)
        dock_lay.addWidget(self.btn_deny)

        # Voice Trigger Button
        self.btn_voice = MacOSButton("🎤 Voice Input", variant=MacOSButton.Variant.SECONDARY, parent=ctrl_dock)
        self.btn_voice.setFixedWidth(130)
        self.btn_voice.clicked.connect(self.controller._on_voice_trigger_click)
        dock_lay.addWidget(self.btn_voice)

        dock_lay.addStretch()

        # BIG RED EMERGENCY STOP BUTTON
        self.btn_stop = MacOSButton("🛑 EMERGENCY STOP (F12)", variant=MacOSButton.Variant.DESTRUCTIVE, parent=ctrl_dock)
        self.btn_stop.setFixedWidth(210)
        self.btn_stop.setStyleSheet(f"""
            QPushButton {{
                background-color: #dc2626;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                border: 1px solid #ef4444;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: #ef4444;
            }}
            QPushButton:pressed {{
                background-color: #b91c1c;
            }}
        """)
        self.btn_stop.clicked.connect(self.controller._on_emergency_stop)
        dock_lay.addWidget(self.btn_stop)

        main_lay.addWidget(ctrl_dock)

        # Periodic queue processor timer
        self.queue_timer = QTimer(self.window)
        self.queue_timer.timeout.connect(self.controller._process_queue)
        self.queue_timer.start(40)

        # Apply macOS backdrop vibrancy
        apply_macos_vibrancy(int(self.window.winId()), is_dark=theme.is_dark)

    def _toggle_zoom(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    def _update_status_pill(self, status: str) -> None:
        status_up = status.upper()
        if "RUN" in status_up:
            col = "#0a84ff"
            bg = "rgba(10, 132, 255, 0.15)"
            bd = "rgba(10, 132, 255, 0.35)"
        elif "APPROVAL" in status_up:
            col = "#f59e0b"
            bg = "rgba(245, 158, 11, 0.18)"
            bd = "rgba(245, 158, 11, 0.4)"
        elif "STOP" in status_up or "DENIED" in status_up or "ERR" in status_up:
            col = "#ef4444"
            bg = "rgba(239, 68, 68, 0.2)"
            bd = "rgba(239, 68, 68, 0.4)"
        else:
            col = "#10b981"
            bg = "rgba(16, 185, 129, 0.15)"
            bd = "rgba(16, 185, 129, 0.3)"

        self.lbl_status.setText(f"●  {status_up}")
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color: {col};
                background-color: {bg};
                border: 1px solid {bd};
                border-radius: 9px;
                padding: 3px 10px;
                font-weight: bold;
            }}
        """)


class NeoDashboard:
    """
    Controller & Bridge for the NEO Controller Dashboard.
    Thread-safe UI update queue and backward-compatible testing API.
    """

    def __init__(
        self,
        title: str = "NEO Autonomous Controller",
        enable_hotkeys: bool = True,
        on_voice_input: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.title = title
        self.enable_hotkeys = enable_hotkeys
        self.on_voice_input_cb = on_voice_input

        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._pending_approval_cb: Optional[Callable[[bool], None]] = None

        self.hotkey_mgr: Optional[GlobalHotkeyManager] = None
        self.voice_trigger = VoiceTrigger()
        self._gui_thread: Optional[threading.Thread] = None
        self._window: Optional[MacOSDashboardWindow] = None
        self._app = None

        # Internal state store for headless querying and test compatibility
        self.current_stage = "[No Active Task]"
        self.current_step = 0
        self.max_steps = 25
        self.status = "IDLE"
        self.logs: List[str] = []

    def start(self, in_thread: bool = False) -> None:
        """Starts the dashboard GUI. If in_thread is True, runs on a daemon background thread."""
        if in_thread:
            self._gui_thread = threading.Thread(target=self._run_gui, daemon=True)
            self._gui_thread.start()
            time.sleep(0.3)
        else:
            self._run_gui()

    def _run_gui(self) -> None:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
            self._app = app

        # Global Hotkeys
        if self.enable_hotkeys:
            self.hotkey_mgr = GlobalHotkeyManager()
            self.hotkey_mgr.register_default_hotkeys(
                on_stop=self._on_emergency_stop,
                on_focus=self._focus_window,
                on_voice=self._on_voice_trigger_click,
            )
            self.hotkey_mgr.start()

        self._running = True
        self._window = MacOSDashboardWindow(self)
        self._window.window.show()

        self.append_log("NEO Autonomous Controller macOS Dashboard initialized.", level="SUCCESS")

        try:
            if self._app:
                self._app.exec()
            elif app:
                # If an external app loop exists, keep running until closed
                while self._running and self._window.window.isVisible():
                    time.sleep(0.1)
        finally:
            self._running = False
            if self.hotkey_mgr:
                self.hotkey_mgr.stop()

    def _focus_window(self) -> None:
        """Brings the dashboard window to the foreground."""
        if self._window and self._window.window:
            try:
                self._window.window.raise_()
                self._window.window.activateWindow()
            except Exception:
                pass

    def _on_emergency_stop(self) -> None:
        """Triggers emergency stop instantly and updates dashboard state."""
        emergency_stop.trigger("EMERGENCY STOP BUTTON CLICKED ON DASHBOARD")
        self.status = "STOPPED"
        if self._window:
            self._window._update_status_pill("STOPPED")
        self.append_log("🛑 EMERGENCY STOP TRIGGERED. All actions halted immediately.", level="SAFETY")

    def _on_approve(self) -> None:
        if self._pending_approval_cb:
            cb = self._pending_approval_cb
            self._pending_approval_cb = None
            if self._window:
                self._window.btn_approve.setEnabled(False)
                self._window.btn_deny.setEnabled(False)
                self._window._update_status_pill("RUNNING")
            cb(True)

    def _on_deny(self) -> None:
        if self._pending_approval_cb:
            cb = self._pending_approval_cb
            self._pending_approval_cb = None
            if self._window:
                self._window.btn_approve.setEnabled(False)
                self._window.btn_deny.setEnabled(False)
                self._window._update_status_pill("DENIED")
            cb(False)

    def _on_voice_trigger_click(self) -> None:
        """Handles voice input button click, invoking Whisper transcription."""
        self.append_log("Voice capture active: Speak your instruction...", level="INFO")
        if self._window:
            self._window.btn_voice.setText("🎤 Listening...")

        def _voice_cb(transcribed_text: str):
            def _gui_update():
                if self._window:
                    self._window.btn_voice.setText("🎤 Voice Input")
                self.append_log(f"Voice Recognized: '{transcribed_text}'", level="SUCCESS")
                if self.on_voice_input_cb:
                    self.on_voice_input_cb(transcribed_text)
            self._queue.put(_gui_update)

        self.voice_trigger.listen_in_background(callback=_voice_cb, duration_s=4.0)

    # ─────────────────────────────────────────────────────────────────────────
    # Thread-Safe Public State Updating API
    # ─────────────────────────────────────────────────────────────────────────
    def update_stage(self, stage_name: str, current_step: int = 1, max_steps: int = 25) -> None:
        """Updates the top stage and progress indicators."""
        def _update():
            self.current_stage = stage_name
            self.current_step = current_step
            self.max_steps = max_steps
            self.status = "RUNNING"
            if self._window:
                self._window.lbl_stage.setText(f"Stage: {stage_name}")
                self._window.lbl_step_counter.setText(f"Step {current_step} / {max_steps}")
                self._window.stage_pbar.setMaximum(max_steps)
                self._window.stage_pbar.setValue(current_step)
                self._window._update_status_pill("RUNNING")
        self._queue.put(_update)

    def update_vision(
        self,
        elements: Sequence[Dict[str, Any]],
        screenshot_path_or_bytes: Optional[Union[str, Path, bytes]] = None,
    ) -> None:
        """Updates the interactive elements table and screenshot canvas."""
        def _update():
            if self._window:
                from PyQt6.QtWidgets import QTreeWidgetItem
                self._window.element_tree.clear()
                for el in elements:
                    item = QTreeWidgetItem([
                        str(el.get("id", "")),
                        str(el.get("control_type") or el.get("role", "")),
                        str(el.get("name") or el.get("text", "")),
                        str(el.get("automation_id", "")),
                        "Yes" if el.get("enabled", True) else "No",
                    ])
                    self._window.element_tree.addTopLevelItem(item)

                if screenshot_path_or_bytes:
                    self._window.screenshot_canvas.set_image(screenshot_path_or_bytes)
        self._queue.put(_update)

    def update_planned_action(self, action: str, parameters: Dict[str, Any], thought: str = "") -> None:
        """Updates the Planned Action inspection card."""
        def _update():
            param_str = json.dumps(parameters, indent=2) if parameters else "{}"
            if len(param_str) > 200:
                param_str = param_str[:190] + " ... }"
            if self._window:
                self._window.lbl_action_name.setText(f"ACTION: {action.upper()}")
                self._window.lbl_action_details.setText(f"Parameters:\n{param_str}")
                self._window.lbl_action_thought.setText(f"Thought: {thought}" if thought else "")
        self._queue.put(_update)

    def request_approval(self, action_name: str, reason: str, callback: Callable[[bool], None]) -> None:
        """Activates Approve/Deny buttons and awaits human user input."""
        def _update():
            self._pending_approval_cb = callback
            self.status = "AWAITING APPROVAL"
            if self._window:
                self._window._update_status_pill("AWAITING APPROVAL")
                self._window.btn_approve.setEnabled(True)
                self._window.btn_deny.setEnabled(True)
            self.append_log(f"⚠ SECURITY CONFIRMATION REQUIRED for '{action_name}': {reason}", level="WARNING")
        self._queue.put(_update)

    def append_log(self, message: str, level: str = "INFO") -> None:
        """Appends a timestamped log entry to the live audit log."""
        def _update():
            ts = time.strftime("%H:%M:%S")
            entry = f"[{ts}] [{level}] {message}"
            self.logs.append(entry)

            if self._window:
                # Color code levels with HTML
                col = "#38bdf8"
                if level == "SUCCESS":
                    col = "#34d399"
                elif level == "WARNING":
                    col = "#fbbf24"
                elif level == "ERROR":
                    col = "#f87171"
                elif level == "SAFETY":
                    col = "#ef4444"

                html_entry = f"<span style='color: #71717a;'>[{ts}]</span> <b style='color: {col};'>[{level}]</b> <span style='color: #f4f4f5;'>{message}</span>"
                self._window.txt_log.append(html_entry)
        self._queue.put(_update)

    def _process_queue(self) -> None:
        """Pumps queued callbacks."""
        while not self._queue.empty():
            try:
                fn = self._queue.get_nowait()
                fn()
            except Exception as e:
                logger.error("Error processing dashboard queue: %s", e)

    def close(self) -> None:
        """Gracefully closes the dashboard window."""
        self._running = False
        if self._window and self._window.window:
            try:
                self._window.window.close()
            except Exception:
                pass
        if self._app:
            try:
                self._app.quit()
            except Exception:
                pass


def main():
    """Runs the dashboard in standalone interactive demo mode."""
    dashboard = NeoDashboard(title="NEO Autonomous Controller (Demo)")
    dashboard.start(in_thread=True)

    time.sleep(0.5)
    dashboard.update_stage("Web Form Automation", current_step=1, max_steps=5)
    dashboard.update_planned_action("goto", {"url": "https://example.com/intake"}, thought="Navigating to portal")
    dashboard.append_log("Navigating to https://example.com/intake", level="INFO")

    time.sleep(1.0)
    sample_elements = [
        {"id": 1, "role": "heading", "name": "Intake Portal", "automation_id": "title", "enabled": True},
        {"id": 2, "role": "input", "name": "Username", "automation_id": "txtUser", "enabled": True},
        {"id": 3, "role": "button", "name": "Submit", "automation_id": "btnSubmit", "enabled": True},
    ]
    dashboard.update_vision(elements=sample_elements)
    dashboard.update_stage("Web Form Automation", current_step=2, max_steps=5)
    dashboard.update_planned_action("type", {"selector": "#txtUser", "text": "neo_agent"}, thought="Filling username")
    dashboard.append_log("Typed username 'neo_agent' into #txtUser", level="SUCCESS")

    try:
        while dashboard._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        dashboard.close()


if __name__ == "__main__":
    main()
