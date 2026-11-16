"""
neo/ui/confirmation_dialog.py — High-Security macOS Sheet Modal Confirmation Popup.

Architectural Guarantees:
1. Always modal and topmost (never obscured by other apps).
2. Pure Apple macOS Sequoia/Tahoe design system:
   - Windows 11 Acrylic/Mica frosted vibrancy fallback (`apply_macos_vibrancy`).
   - Top-left Apple traffic lights (`MacOSTrafficLights`).
   - Apple Grouped Inset Cards with 10px-14px continuous radii and subtle 1px border.
   - Vector Lucide icons (1.5 stroke) and Inter typography.
3. Live countdown progress bar and seconds counter with strict auto-deny when time expires.
4. Defaults to DENY on window close, escape key, timeout, or error.
5. Clean presentation displaying exact risk evidence, target action, and matched security rules.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from typing import Any, Optional, Tuple

from neo.safety.policy import RiskAssessment

logger = logging.getLogger("neo.ui.confirmation")


class MacOSConfirmationDialog:
    """
    Controller and Dialog for the Apple macOS Sequoia Style Confirmation Sheet.
    """

    def __init__(
        self,
        action_name: str,
        assessment: RiskAssessment,
        timeout_sec: float = 30.0,
    ) -> None:
        self.action_name = action_name
        self.assessment = assessment
        self.timeout_sec = max(1.0, float(timeout_sec))
        self.time_left = self.timeout_sec

        self.approved = False
        self.reason = "Defaulted to DENY."
        self._completed = False

    def show(self) -> Tuple[bool, str]:
        """
        Creates and executes the modal dialog, blocking until human decision or timeout.
        """
        try:
            from PyQt6.QtCore import Qt, QTimer, QPoint
            from PyQt6.QtGui import QFont, QColor
            from PyQt6.QtWidgets import (
                QApplication,
                QDialog,
                QFrame,
                QHBoxLayout,
                QLabel,
                QProgressBar,
                QSizePolicy,
                QVBoxLayout,
                QWidget,
            )

            from core.theme_provider import theme
            from core.macos_components import MacOSButton, render_lucide_icon
            from core.macos_window import apply_macos_vibrancy, MacOSTrafficLights
        except ImportError as e:
            logger.warning("PyQt6/Theme unavailable for macOS confirmation dialog: %s. Falling back to native Windows dialog.", e)
            return _fallback_native_dialog(self.action_name, self.assessment, self.timeout_sec)

        # Ensure QApplication exists
        app = QApplication.instance()
        created_app = False
        if app is None:
            if threading.current_thread() is not threading.main_thread():
                # Cannot create QApplication on a worker thread in Qt
                logger.warning("Confirmation requested on worker thread with no active QApplication. Using native fallback.")
                return _fallback_native_dialog(self.action_name, self.assessment, self.timeout_sec)
            app = QApplication(sys.argv)
            created_app = True

        dialog = QDialog()
        dialog.setWindowTitle("NEO Security Confirmation Gate")
        dialog.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        dialog.setMinimumSize(540, 390)
        dialog.resize(560, 420)

        # Outer root layout for shadow / border
        root_lay = QVBoxLayout(dialog)
        root_lay.setContentsMargins(12, 12, 12, 12)

        # Inset Container Frame
        is_hard_stop = bool(self.assessment.requires_hard_stop)
        accent_alert = "#ef4444" if is_hard_stop else "#f59e0b"
        border_col = "rgba(239, 68, 68, 0.4)" if is_hard_stop else "rgba(245, 158, 11, 0.35)"

        container = QFrame(dialog)
        container.setObjectName("macOSConfirmContainer")
        container.setStyleSheet(f"""
            QFrame#macOSConfirmContainer {{
                background-color: {theme.colors.cardBackground};
                border: 1px solid {border_col};
                border-radius: {theme.radii.lg}px;
            }}
        """)

        cont_lay = QVBoxLayout(container)
        cont_lay.setContentsMargins(20, 16, 20, 18)
        cont_lay.setSpacing(14)

        # ── 1. Top Traffic Lights & Title Header ─────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(10)

        traffic_lights = MacOSTrafficLights(container)
        traffic_lights.close_clicked.connect(dialog.reject)
        traffic_lights.minimize_clicked.connect(dialog.showMinimized)
        traffic_lights.zoom_clicked.connect(lambda: None)
        top_bar.addWidget(traffic_lights, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        top_bar.addStretch()

        gate_pill = QLabel(container)
        gate_pill.setText("SECURITY GATEWAY" if not is_hard_stop else "HARD STOP TAKEOVER")
        gate_pill.setFont(theme.font(theme.typography.caption_2))
        gate_pill.setStyleSheet(f"""
            QLabel {{
                background-color: rgba({"239, 68, 68" if is_hard_stop else "245, 158, 11"}, 0.15);
                color: {accent_alert};
                border: 1px solid {accent_alert};
                border-radius: 9px;
                padding: 2px 8px;
                font-weight: bold;
            }}
        """)
        top_bar.addWidget(gate_pill, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cont_lay.addLayout(top_bar)

        # ── 2. Alert Icon & Title ────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 2, 0, 2)
        header_row.setSpacing(12)

        icon_box = QFrame(container)
        icon_box.setFixedSize(38, 38)
        icon_box.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({"239, 68, 68" if is_hard_stop else "245, 158, 11"}, 0.18);
                border-radius: {theme.radii.md}px;
                border: 1px solid {accent_alert};
            }}
        """)
        ib_lay = QVBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ic = QLabel(icon_box)
        lbl_ic.setPixmap(render_lucide_icon("alert-triangle", color=accent_alert, size=20))
        ib_lay.addWidget(lbl_ic)
        header_row.addWidget(icon_box)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        lbl_title = QLabel(
            "HARD STOP: USER TAKEOVER REQUIRED" if is_hard_stop else "SECURITY CONFIRMATION REQUIRED",
            container,
        )
        lbl_title.setFont(theme.font(theme.typography.headline))
        lbl_title.setStyleSheet(f"color: {accent_alert}; font-weight: bold; border: none; background: transparent;")
        title_col.addWidget(lbl_title)

        lbl_subtitle = QLabel(
            "An autonomous action with irreversible impact requires explicit human authorization.",
            container,
        )
        lbl_subtitle.setFont(theme.font(theme.typography.caption_1))
        lbl_subtitle.setStyleSheet(f"color: {theme.colors.labelSecondary}; border: none; background: transparent;")
        lbl_subtitle.setWordWrap(True)
        title_col.addWidget(lbl_subtitle)

        header_row.addLayout(title_col, stretch=1)
        cont_lay.addLayout(header_row)

        # ── 3. Apple Grouped Inset Card for Action Details ───────────────────
        detail_card = QFrame(container)
        detail_card.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {theme.radii.md}px;
            }}
        """)
        card_lay = QVBoxLayout(detail_card)
        card_lay.setContentsMargins(14, 12, 14, 12)
        card_lay.setSpacing(8)

        # Action row
        act_row = QHBoxLayout()
        act_lbl = QLabel("Action:", detail_card)
        act_lbl.setFont(theme.font(theme.typography.caption_1))
        act_lbl.setStyleSheet(f"color: {theme.colors.labelTertiary}; border: none; background: transparent;")
        act_row.addWidget(act_lbl)

        act_val = QLabel(self.action_name.upper(), detail_card)
        act_val.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        act_val.setStyleSheet(f"""
            color: {theme.colors.labelPrimary};
            background-color: {theme.colors.controlBackgroundSecondary};
            border-radius: 4px;
            padding: 2px 6px;
            border: 1px solid {theme.colors.separator};
        """)
        act_row.addWidget(act_val)
        act_row.addStretch()
        card_lay.addLayout(act_row)

        # Reason / Summary row
        desc_lbl = QLabel(f"Reason: {self.assessment.summary}", detail_card)
        desc_lbl.setFont(theme.font(theme.typography.subheadline))
        desc_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; border: none; background: transparent;")
        desc_lbl.setWordWrap(True)
        card_lay.addWidget(desc_lbl)

        # Matched rules badges
        if self.assessment.matched_patterns:
            rules_box = QHBoxLayout()
            rules_box.setSpacing(6)
            for pat in self.assessment.matched_patterns[:4]:
                rule_badge = QLabel(pat, detail_card)
                rule_badge.setFont(theme.font(theme.typography.caption_2))
                rule_badge.setStyleSheet(f"""
                    color: {theme.colors.labelSecondary};
                    background-color: {theme.colors.controlBackgroundSecondary};
                    border: 1px solid {theme.colors.separator};
                    border-radius: 4px;
                    padding: 1px 6px;
                """)
                rules_box.addWidget(rule_badge)
            rules_box.addStretch()
            card_lay.addLayout(rules_box)

        cont_lay.addWidget(detail_card)

        # ── 4. Live Countdown Progress Bar ───────────────────────────────────
        timer_col = QVBoxLayout()
        timer_col.setContentsMargins(0, 0, 0, 0)
        timer_col.setSpacing(4)

        timer_hdr = QHBoxLayout()
        lbl_timer = QLabel(f"Time remaining: {int(self.time_left)}s (Default: DENY)", container)
        lbl_timer.setFont(theme.font(theme.typography.caption_1))
        lbl_timer.setStyleSheet(f"color: #fbbf24; font-weight: bold; border: none; background: transparent;")
        timer_hdr.addWidget(lbl_timer)
        timer_hdr.addStretch()
        timer_col.addLayout(timer_hdr)

        pbar = QProgressBar(container)
        pbar.setFixedHeight(5)
        pbar.setRange(0, int(self.timeout_sec * 10))
        pbar.setValue(int(self.time_left * 10))
        pbar.setTextVisible(False)
        pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {theme.colors.controlBackgroundSecondary};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: #fbbf24;
                border-radius: 2px;
            }}
        """)
        timer_col.addWidget(pbar)
        cont_lay.addLayout(timer_col)

        # ── 5. Action Buttons (Apple HIG standard) ───────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 4, 0, 0)
        btn_bar.setSpacing(10)
        btn_bar.addStretch()

        btn_deny = MacOSButton("✕ Deny Action (Esc)", variant=MacOSButton.Variant.DESTRUCTIVE, parent=container)
        btn_deny.setFixedWidth(160)

        btn_approve = MacOSButton("✓ Approve Action", variant=MacOSButton.Variant.DEFAULT, parent=container)
        btn_approve.setFixedWidth(150)

        btn_bar.addWidget(btn_deny)
        btn_bar.addWidget(btn_approve)
        cont_lay.addLayout(btn_bar)

        root_lay.addWidget(container)

        # Dragging support
        drag_pos = [QPoint()]

        def mouse_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                drag_pos[0] = ev.globalPosition().toPoint() - dialog.frameGeometry().topLeft()

        def mouse_move(ev):
            if ev.buttons() == Qt.MouseButton.LeftButton and not drag_pos[0].isNull():
                dialog.move(ev.globalPosition().toPoint() - drag_pos[0])

        container.mousePressEvent = mouse_press
        container.mouseMoveEvent = mouse_move

        # Timer countdown logic
        tick_timer = QTimer(dialog)

        def _on_tick():
            self.time_left -= 0.1
            if self.time_left <= 0:
                tick_timer.stop()
                self.approved = False
                self.reason = f"Confirmation dialog timed out after {self.timeout_sec:.0f}s. Defaulted to DENY."
                self._completed = True
                dialog.reject()
            else:
                secs_int = max(0, int(self.time_left))
                lbl_timer.setText(f"Time remaining: {secs_int}s (Default: DENY)")
                pbar.setValue(int(self.time_left * 10))

        tick_timer.timeout.connect(_on_tick)
        tick_timer.start(100)

        # Handlers
        def _handle_approve():
            tick_timer.stop()
            self.approved = True
            self.reason = "User explicitly approved via macOS confirmation dialog."
            self._completed = True
            dialog.accept()

        def _handle_deny():
            tick_timer.stop()
            self.approved = False
            self.reason = "User explicitly denied via macOS confirmation dialog."
            self._completed = True
            dialog.reject()

        btn_approve.clicked.connect(_handle_approve)
        btn_deny.clicked.connect(_handle_deny)
        dialog.rejected.connect(lambda: None)

        # Default focus on Deny for safety
        btn_deny.setFocus()

        # Apply macOS frosted vibrancy
        apply_macos_vibrancy(int(dialog.winId()), is_dark=theme.is_dark)

        # Show modal
        dialog.exec()

        if not self._completed:
            self.approved = False
            self.reason = "Confirmation dialog closed or cancelled by user. Defaulted to DENY."

        return self.approved, self.reason


def show_confirmation_popup(
    action_name: str,
    assessment: RiskAssessment,
    timeout_sec: float = 30.0,
) -> Tuple[bool, str]:
    """
    Displays a modal confirmation dialog requesting human approval.
    Blocks the calling thread until the user decides or until timeout_sec expires.
    TIMEOUTS STRICTLY DEFAULT TO DENY.

    Returns:
        (approved: bool, reason: str)
    """
    try:
        dialog = MacOSConfirmationDialog(
            action_name=action_name,
            assessment=assessment,
            timeout_sec=timeout_sec,
        )
        return dialog.show()
    except Exception as e:
        logger.error("Error creating macOS confirmation dialog: %s. Falling back to native Windows dialog.", e)
        return _fallback_native_dialog(action_name, assessment, timeout_sec)


def _fallback_native_dialog(
    action_name: str,
    assessment: RiskAssessment,
    timeout_sec: float,
) -> Tuple[bool, str]:
    """
    Fallback native Win32 MessageBox with timeout using user32.MessageBoxTimeoutW.
    """
    try:
        user32 = ctypes.windll.user32
        MB_YESNO = 0x00000004
        MB_ICONWARNING = 0x00000030
        MB_DEFBUTTON2 = 0x00000100  # Default to NO
        MB_TOPMOST = 0x00040000
        IDYES = 6
        IDNO = 7
        MB_TIMEDOUT = 32000

        msg = (
            f"NEO SECURITY CONFIRMATION REQUIRED\n\n"
            f"Action: {action_name.upper()}\n"
            f"Reason: {assessment.summary}\n\n"
            f"Do you approve this action?\n"
            f"(Times out in {int(timeout_sec)}s -> defaults to NO)"
        )
        title = "NEO Security Gate"

        timeout_ms = int(timeout_sec * 1000)
        ret = user32.MessageBoxTimeoutW(
            None,
            msg,
            title,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST,
            0,
            timeout_ms,
        )

        if ret == IDYES:
            return True, "User approved via native Windows MessageBox."
        elif ret == MB_TIMEDOUT:
            return False, f"Confirmation timed out after {timeout_sec:.0f}s. Defaulted to DENY."
        else:
            return False, "User denied via native Windows MessageBox."

    except Exception as e:
        logger.error("Native Windows MessageBox failed: %s. Defaulting to DENY.", e)
        return False, f"All confirmation dialogs failed: {e}. Defaulted to DENY."
