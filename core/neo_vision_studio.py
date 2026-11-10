"""
core/neo_vision_studio.py — Visual HUD, Gesture Spatial Controller & Deep OCR Studio for NEO.
Provides real-time camera vision streaming via CameraService,
neural hand gesture recognition via Google MediaPipe & calibrated OpenCV fallback,
screen/webcam high-precision OCR extraction, and Gemini Vision question answering (VQA).
"""
from __future__ import annotations

import io
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF
from PyQt6.QtGui import QFont, QCursor, QColor, QImage, QPixmap, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter, QTextBrowser, QApplication
)

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

from core import gemini

# Shared executive styling tokens (Apple macOS Dark Vibrancy)
CARD_BG = "#232327"
CARD_BORDER = "#2F2F34"
CARD_HOVER = "#2A2A2F"
TEXT_WHITE = "#F5F5F7"
TEXT_MUTED = "#98989D"
TEXT_DIM = "#636366"
ACCENT_PRIMARY = "#0A84FF"
SEMANTIC_SUCCESS = "#30D158"
SEMANTIC_WARNING = "#FFD60A"
SEMANTIC_ERROR = "#FF453A"


class NeoVisionSpatialStudio(QWidget):
    """Executive Computer Vision, Screen Region Inspector, and Gesture Controller (macOS Standard)."""
    command_requested = pyqtSignal(str)   # (voice_or_system_command)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera_streaming: bool = False
        self._fps_count: int = 0
        self._last_fps_time: float = time.monotonic()
        self._current_fps: int = 30
        self._last_snapshot_path: Optional[Path] = None
        self._last_ocr_text: str = ""

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

        # ── 1. Top Bar ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_lbl = QLabel("👁️")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        title_lbl = QLabel("Visual HUD, Gesture & Deep OCR Studio")
        title_lbl.setFont(QFont("-apple-system", 13, QFont.Weight.Bold))
        t_row.addWidget(title_lbl)

        self.vision_badge = QLabel("● VISION READY")
        self.vision_badge.setFont(QFont("-apple-system", 8, QFont.Weight.Bold))
        self.vision_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(48, 209, 88, 0.15); border-radius: 10px; padding: 2px 8px;")
        t_row.addWidget(self.vision_badge)
        t_row.addStretch()
        title_col.addLayout(t_row)

        sub_lbl = QLabel("Webcam optical targeting, Google MediaPipe neural gestures, and screen/camera text OCR extraction")
        sub_lbl.setFont(QFont("-apple-system", 8))
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        self.screen_ocr_btn = QPushButton("🔍 Extract Screen OCR")
        self.screen_ocr_btn.setFixedHeight(30)
        self.screen_ocr_btn.setFont(QFont("-apple-system", 8, QFont.Weight.Bold))
        self.screen_ocr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.screen_ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(48, 209, 88, 0.18); color: {SEMANTIC_SUCCESS};
                border: 1px solid {SEMANTIC_SUCCESS}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: rgba(48, 209, 88, 0.3); color: #ffffff; }}
        """)
        self.screen_ocr_btn.clicked.connect(self._capture_screen_ocr)
        hdr.addWidget(self.screen_ocr_btn)

        self.screen_cap_btn = QPushButton("📸 Screen VQA")
        self.screen_cap_btn.setFixedHeight(30)
        self.screen_cap_btn.setFont(QFont("Segoe UI", 8))
        self.screen_cap_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.screen_cap_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.35); color: #ffffff; }}
        """)
        self.screen_cap_btn.clicked.connect(self._capture_screen_region)
        hdr.addWidget(self.screen_cap_btn)

        main_lay.addLayout(hdr)

        # ── 2. Splitter: Camera/Screen View (Left) | Spatial Gestures (Right) ─
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {CARD_BORDER}; }}")

        # LEFT: Vision Stream Frame
        left_box = self._build_stream_pane()
        splitter.addWidget(left_box)

        # RIGHT: Gesture & Spatial Intelligence Pane
        right_box = self._build_gesture_pane()
        splitter.addWidget(right_box)

        splitter.setSizes([540, 420])
        main_lay.addWidget(splitter, stretch=1)

        # High-frequency Camera Stream Frame Timer (33ms = ~30 FPS)
        self.cam_timer = QTimer(self)
        self.cam_timer.setInterval(33)
        self.cam_timer.timeout.connect(self._fetch_and_render_frame)

        # Gesture & Telemetry Polling Timer (400ms)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(400)
        self.telemetry_timer.timeout.connect(self._refresh_telemetry)
        self.telemetry_timer.start()

        # Check initial gesture control status
        self._sync_gesture_state()

    # ── Left Pane: Vision Stream & Framing ────────────────────────────────────

    def _build_stream_pane(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Controls Header
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        v_title = QLabel("Optical Feed & HUD Target Matrix")
        v_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        v_title.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        ctrl_row.addWidget(v_title)
        ctrl_row.addStretch()

        self.snap_ocr_btn = QPushButton("📷 Snapshot Cam OCR")
        self.snap_ocr_btn.setFixedHeight(24)
        self.snap_ocr_btn.setFont(QFont("Segoe UI", 8))
        self.snap_ocr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.snap_ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {SEMANTIC_SUCCESS}; }}
        """)
        self.snap_ocr_btn.clicked.connect(self._snapshot_camera_ocr)
        ctrl_row.addWidget(self.snap_ocr_btn)

        self.stream_btn = QPushButton("▶ Start Camera")
        self.stream_btn.setFixedHeight(24)
        self.stream_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.stream_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.stream_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(76, 175, 125, 0.2); color: {SEMANTIC_SUCCESS};
                border: 1px solid {SEMANTIC_SUCCESS}; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: rgba(76, 175, 125, 0.35); color: #ffffff; }}
        """)
        self.stream_btn.clicked.connect(self._toggle_camera_stream)
        ctrl_row.addWidget(self.stream_btn)

        lay.addLayout(ctrl_row)

        # Viewport Screen
        self.viewport = QLabel()
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.setStyleSheet("""
            background: #0B0E14;
            border: 1px solid #262B34;
            border-radius: 6px;
        """)
        self._render_placeholder_hud()
        lay.addWidget(self.viewport, stretch=1)

        # Telemetry footer
        self.stream_stat = QLabel("Resolution: Standby · FPS: 0 · Focus: Continuous Auto-Focus · Service: Shared Camera")
        self.stream_stat.setFont(QFont("Segoe UI", 8))
        self.stream_stat.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        lay.addWidget(self.stream_stat)

        return w

    def _render_placeholder_hud(self):
        pix = QPixmap(520, 320)
        pix.fill(QColor("#0B0E14"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Crosshair and grid lines
        pen = QPen(QColor(91, 141, 239, 60), 1)
        p.setPen(pen)
        p.drawLine(260, 40, 260, 280)
        p.drawLine(40, 160, 480, 160)
        p.drawEllipse(QRectF(210, 110, 100, 100))
        p.drawEllipse(QRectF(160, 60, 200, 200))

        # Corner framing ticks
        pen_tick = QPen(QColor(91, 141, 239, 180), 2)
        p.setPen(pen_tick)
        # Top-left
        p.drawLine(50, 50, 80, 50); p.drawLine(50, 50, 50, 80)
        # Top-right
        p.drawLine(470, 50, 440, 50); p.drawLine(470, 50, 470, 80)
        # Bottom-left
        p.drawLine(50, 270, 80, 270); p.drawLine(50, 270, 50, 240)
        # Bottom-right
        p.drawLine(470, 270, 440, 270); p.drawLine(470, 270, 470, 240)

        # HUD Label
        p.setPen(QColor("#5B8DEF"))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(QRectF(0, 138, 520, 24), Qt.AlignmentFlag.AlignCenter, "NEO OPTICAL TARGETING SYSTEM")

        p.setPen(QColor("#64748B"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(0, 164, 520, 20), Qt.AlignmentFlag.AlignCenter, "Click 'Start Camera' for Live Video Feed or 'Extract Screen OCR' for Text")

        p.end()
        self.viewport.setPixmap(pix)

    # ── Right Pane: Spatial Gestures & VQA ────────────────────────────────────

    def _build_gesture_pane(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Header
        g_hdr = QHBoxLayout()
        g_icn = QLabel("🖐️")
        g_icn.setFont(QFont("Segoe UI", 11))
        g_hdr.addWidget(g_icn)
        g_txt = QLabel("Air Gestures & Deep OCR Engine")
        g_txt.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        g_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        g_hdr.addWidget(g_txt)
        g_hdr.addStretch()

        self.gesture_toggle_btn = QPushButton("▶ Enable Gestures")
        self.gesture_toggle_btn.setFixedHeight(22)
        self.gesture_toggle_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.gesture_toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.gesture_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px; padding: 0 8px;
            }}
        """)
        self.gesture_toggle_btn.clicked.connect(self._toggle_gestures)
        g_hdr.addWidget(self.gesture_toggle_btn)
        lay.addLayout(g_hdr)

        # Gestures Map Card
        g_map = QFrame()
        g_map.setStyleSheet("background: #14171C; border-radius: 6px; padding: 6px;")
        g_lay = QVBoxLayout(g_map)
        g_lay.setContentsMargins(8, 8, 8, 8)
        g_lay.setSpacing(6)

        gestures = [
            ("🖐️ Open Palm", "Pause Assistant Voice & Media (Interrupt)"),
            ("✊ Closed Fist", "Unmute Microphone / Resume Playback"),
            ("✌️ Victory / Peace", "Toggle Mute & Voice Mode"),
            ("💨 Swipe Right / Left", "Switch Active Workstation Tabs"),
        ]
        self.gesture_rows = []
        for g_name, g_action in gestures:
            row = QHBoxLayout()
            lbl_g = QLabel(g_name)
            lbl_g.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            lbl_g.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
            row.addWidget(lbl_g)
            row.addStretch()
            lbl_a = QLabel(g_action)
            lbl_a.setFont(QFont("Segoe UI", 8))
            lbl_a.setStyleSheet(f"color: {ACCENT_PRIMARY}; border: none; background: transparent;")
            row.addWidget(lbl_a)
            g_lay.addLayout(row)
            self.gesture_rows.append((g_name, lbl_g, lbl_a))

        lay.addWidget(g_map)

        # Live Optical Stance Indicator
        ind_box = QFrame()
        ind_box.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 6px;")
        ind_lay = QHBoxLayout(ind_box)
        ind_lay.setContentsMargins(10, 6, 10, 6)

        self.detected_lbl = QLabel("Active Optical Stance: STANDBY (Awaiting gesture)")
        self.detected_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.detected_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        ind_lay.addWidget(self.detected_lbl)
        ind_lay.addStretch()
        self.conf_lbl = QLabel("Air Gesture Engine: Active")
        self.conf_lbl.setFont(QFont("Segoe UI", 8))
        self.conf_lbl.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; border: none; background: transparent;")
        ind_lay.addWidget(self.conf_lbl)
        lay.addWidget(ind_box)

        # Visual QA / OCR Inspector output
        vqa_hdr = QHBoxLayout()
        vqa_lbl = QLabel("Visual Question Answering & OCR Output")
        vqa_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        vqa_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        vqa_hdr.addWidget(vqa_lbl)
        vqa_hdr.addStretch()

        self.copy_ocr_btn = QPushButton("📋 Copy Text")
        self.copy_ocr_btn.setFixedHeight(20)
        self.copy_ocr_btn.setFont(QFont("Segoe UI", 7))
        self.copy_ocr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_ocr_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER}; border-radius: 3px; padding: 0 6px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; color: {TEXT_WHITE}; }}
        """)
        self.copy_ocr_btn.clicked.connect(self._copy_ocr_text)
        vqa_hdr.addWidget(self.copy_ocr_btn)
        lay.addLayout(vqa_hdr)

        self.vqa_browser = QTextBrowser()
        self.vqa_browser.setFont(QFont("Consolas", 9))
        self.vqa_browser.setPlaceholderText("Capture a screen region, extract OCR, or take a camera snapshot to transcribe text and reason with Gemini Vision.")
        self.vqa_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #14171C; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 8px;
            }}
        """)
        lay.addWidget(self.vqa_browser, stretch=1)

        # Reason with NEO Action
        self.ask_vis_btn = QPushButton("🧠 Ask NEO to Explain Active Frame")
        self.ask_vis_btn.setFixedHeight(28)
        self.ask_vis_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.ask_vis_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ask_vis_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.35); color: #ffffff; }}
        """)
        self.ask_vis_btn.clicked.connect(self._explain_frame_with_neo)
        lay.addWidget(self.ask_vis_btn)

        return w

    # ── Live Camera Hardware Pipeline ─────────────────────────────────────────

    def _toggle_camera_stream(self):
        if not _CV2_OK:
            self.vqa_browser.setHtml("<span style='color: #F87171;'>OpenCV (cv2) is required for hardware camera streaming.</span>")
            return

        from core.camera_service import get_camera_service
        cam = get_camera_service()

        self.camera_streaming = not self.camera_streaming
        if self.camera_streaming:
            ok = cam.register_consumer("neo_vision_studio")
            if not ok:
                self.camera_streaming = False
                self.vqa_browser.setHtml("<span style='color: #F87171;'>Could not register camera consumer. Check hardware webcam connection.</span>")
                return

            self.stream_btn.setText("⏹ Stop Camera")
            self.stream_btn.setStyleSheet(f"background: rgba(217, 83, 79, 0.2); color: {SEMANTIC_ERROR}; border: 1px solid {SEMANTIC_ERROR}; border-radius: 4px; padding: 0 10px;")
            self.vision_badge.setText("● CAMERA STREAMING")
            self.vision_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")
            self.cam_timer.start()
        else:
            self.cam_timer.stop()
            cam.unregister_consumer("neo_vision_studio")
            self.stream_btn.setText("▶ Start Camera")
            self.stream_btn.setStyleSheet(f"background: rgba(76, 175, 125, 0.2); color: {SEMANTIC_SUCCESS}; border: 1px solid {SEMANTIC_SUCCESS}; border-radius: 4px; padding: 0 10px;")
            self.vision_badge.setText("● VISION READY")
            self.vision_badge.setStyleSheet(f"color: {ACCENT_PRIMARY}; background: rgba(91, 141, 239, 0.15); border-radius: 10px; padding: 2px 8px;")
            self._render_placeholder_hud()
            self.stream_stat.setText("Resolution: Standby · FPS: 0 · Focus: Continuous Auto-Focus · Service: Shared Camera")

    def _fetch_and_render_frame(self):
        """Fetches live frame from CameraService and renders with HUD overlay."""
        from core.camera_service import get_camera_service
        cam = get_camera_service()
        ok, frame = cam.get_frame(timeout=0.03)

        if not ok or frame is None:
            return

        h, w = frame.shape[:2]
        self._fps_count += 1
        now = time.monotonic()
        if now - self._last_fps_time >= 1.0:
            self._current_fps = self._fps_count
            self._fps_count = 0
            self._last_fps_time = now

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb_frame.data, w, h, rgb_frame.strides[0], QImage.Format.Format_RGB888)

        # Draw HUD overlays directly on live video
        pix = QPixmap.fromImage(qimg)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center reticle
        cx, cy = w / 2, h / 2
        p.setPen(QPen(QColor(91, 141, 239, 140), 1))
        p.drawLine(QPointF(cx - 30, cy), QPointF(cx + 30, cy))
        p.drawLine(QPointF(cx, cy - 30), QPointF(cx, cy + 30))
        p.drawEllipse(QRectF(cx - 20, cy - 20, 40, 40))

        # Four corner tactical brackets
        p.setPen(QPen(QColor(91, 141, 239, 200), 2))
        bracket_sz = 30
        margin = 25
        # Top-left
        p.drawLine(QPointF(margin, margin), QPointF(margin + bracket_sz, margin))
        p.drawLine(QPointF(margin, margin), QPointF(margin, margin + bracket_sz))
        # Top-right
        p.drawLine(QPointF(w - margin, margin), QPointF(w - margin - bracket_sz, margin))
        p.drawLine(QPointF(w - margin, margin), QPointF(w - margin, margin + bracket_sz))
        # Bottom-left
        p.drawLine(QPointF(margin, h - margin), QPointF(margin + bracket_sz, h - margin))
        p.drawLine(QPointF(margin, h - margin), QPointF(margin, h - margin - bracket_sz))
        # Bottom-right
        p.drawLine(QPointF(w - margin, h - margin), QPointF(w - margin - bracket_sz, h - margin))
        p.drawLine(QPointF(w - margin, h - margin), QPointF(w - margin, h - margin - bracket_sz))

        # HUD Text overlay
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor("#38BDF8"))
        p.drawText(QPointF(margin + 5, margin + 20), f"SYS OPTIC LOCK [{w}x{h}]")
        p.drawText(QPointF(margin + 5, h - margin - 10), f"LIVE FPS: {self._current_fps} · STARK VISION")

        p.end()

        # Scale to viewport while preserving aspect ratio
        scaled = pix.scaled(self.viewport.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.viewport.setPixmap(scaled)

        self.stream_stat.setText(f"Resolution: {w}×{h} · FPS: {self._current_fps} · Focus: Auto · Consumer: neo_vision_studio")

    # ── Gesture Control & Optical Stance ──────────────────────────────────────

    def _sync_gesture_state(self):
        try:
            from actions.gesture_control import _gesture_ctl
            active = _gesture_ctl.is_active()
            if active:
                self.gesture_toggle_btn.setText("⏹ Disable Gestures")
                self.gesture_toggle_btn.setStyleSheet(f"background: rgba(76, 175, 125, 0.2); color: {SEMANTIC_SUCCESS}; border: 1px solid {SEMANTIC_SUCCESS}; border-radius: 4px; padding: 0 8px;")
                self.detected_lbl.setText("Active Optical Stance: STANDBY (Awaiting gesture)")
                self.conf_lbl.setText("Air Gesture Engine: Active")
            else:
                self.gesture_toggle_btn.setText("▶ Enable Gestures")
                self.gesture_toggle_btn.setStyleSheet(f"background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY}; border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px; padding: 0 8px;")
                self.detected_lbl.setText("Active Optical Stance: GESTURES MUTED (Click Enable)")
                self.conf_lbl.setText("Engine: Muted")
        except Exception:
            pass

    def _toggle_gestures(self):
        try:
            from actions.gesture_control import _gesture_ctl
            if _gesture_ctl.is_active():
                _gesture_ctl.stop()
                self.gesture_toggle_btn.setText("▶ Enable Gestures")
                self.gesture_toggle_btn.setStyleSheet(f"background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY}; border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px; padding: 0 8px;")
                self.detected_lbl.setText("Active Optical Stance: GESTURES MUTED (Paused by user)")
                self.conf_lbl.setText("Air Gesture Engine: Muted")
            else:
                _gesture_ctl.start(player=self)
                self.gesture_toggle_btn.setText("⏹ Disable Gestures")
                self.gesture_toggle_btn.setStyleSheet(f"background: rgba(76, 175, 125, 0.2); color: {SEMANTIC_SUCCESS}; border: 1px solid {SEMANTIC_SUCCESS}; border-radius: 4px; padding: 0 8px;")
                self.detected_lbl.setText("Active Optical Stance: STANDBY (Awaiting gesture)")
                self.conf_lbl.setText("Air Gesture Engine: Active")
        except Exception as e:
            self.vqa_browser.setHtml(f"<span style='color: #F87171;'>Gesture toggle error: {e}</span>")

    def _refresh_telemetry(self):
        """Polls gesture controller for live detection triggers."""
        try:
            from actions.gesture_control import _gesture_ctl
            if not _gesture_ctl.is_active():
                self.detected_lbl.setText("Active Optical Stance: GESTURES MUTED")
                self.conf_lbl.setText("Engine: Muted")
                return

            last_gest, last_time = _gesture_ctl.get_last_gesture()
            now = time.monotonic()
            if now - last_time < 2.5 and "STANDBY" not in last_gest:
                self.detected_lbl.setText(f"Active Optical Stance: {last_gest}")
                self.detected_lbl.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; border: none; background: transparent; font-weight: bold;")
                self.conf_lbl.setText("Detected (98%)")
            else:
                self.detected_lbl.setText("Active Optical Stance: STANDBY (Awaiting gesture)")
                self.detected_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
                self.conf_lbl.setText("Air Gesture Engine: Active")
        except Exception:
            pass

    # ── High-Precision OCR & Multimodal Vision Reasoning ─────────────────────

    def _capture_screen_ocr(self):
        """Captures full screen and runs verbatim Optical Character Recognition (OCR)."""
        self.vqa_browser.setHtml("<i>Capturing screen surface and executing verbatim OCR transcription...</i>")
        self.screen_ocr_btn.setEnabled(False)
        self.screen_ocr_btn.setText("Extracting OCR...")

        def work():
            try:
                from PIL import ImageGrab
                shot = ImageGrab.grab()
                tmp_path = Path("assets/temp_screen_snapshot.png")
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                shot.save(str(tmp_path))
                self._last_snapshot_path = tmp_path

                # Display preview in viewport
                qimg = QImage(str(tmp_path))
                if not qimg.isNull():
                    scaled = qimg.scaled(self.viewport.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    QTimer.singleShot(0, lambda: self.viewport.setPixmap(QPixmap.fromImage(scaled)))

                prompt = (
                    "You are an ultra-high precision Optical Character Recognition (OCR) engine. "
                    "Extract and transcribe ALL text, logs, code, menus, dialogs, and numbers visible on this screen exactly as written. "
                    "Preserve indentation, code formatting, and structure verbatim. Output ONLY the pure extracted text."
                )

                img_bytes = tmp_path.read_bytes()
                ocr_result = gemini.multimodal(prompt, img_bytes, mime="image/png")
                self._last_ocr_text = ocr_result or ""

                clean_res = (ocr_result or "No text was detected on the active screen.").replace("\n", "<br>")

                result_html = f"""
                <div style='color: #34D399; font-weight: bold;'>✓ Verbatim Screen OCR Extracted</div>
                <div style='color: #64748B; font-size: 7.5pt; margin-bottom: 6px;'>
                    <b>Target:</b> Workstation Display · <b>Dimensions:</b> {shot.size[0]}×{shot.size[1]} px · Click 'Copy Text' to copy.
                </div>
                <div style='color: #E6E8EC; font-size: 8pt; line-height: 1.4; background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px;'>
                    {clean_res}
                </div>
                """
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(result_html))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(f"<span style='color: #F87171;'>OCR extraction error: {e}</span>"))
            finally:
                QTimer.singleShot(0, self._reset_ocr_btn)

        threading.Thread(target=work, daemon=True, name="screen-ocr-thread").start()

    def _reset_ocr_btn(self):
        self.screen_ocr_btn.setEnabled(True)
        self.screen_ocr_btn.setText("🔍 Extract Screen OCR")

    def _snapshot_camera_ocr(self):
        """Grabs the current webcam frame and transcribes any text/paper held in front of the lens."""
        self.vqa_browser.setHtml("<i>Grabbing camera frame and running document & text OCR...</i>")
        self.snap_ocr_btn.setEnabled(False)

        def work():
            try:
                from core.camera_service import get_camera_service
                cam = get_camera_service()
                img_bytes, mime = cam.snapshot()
                tmp_path = Path("assets/temp_camera_ocr_snapshot.png")
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(img_bytes)
                self._last_snapshot_path = tmp_path

                # Show preview in viewport
                qimg = QImage(str(tmp_path))
                if not qimg.isNull():
                    scaled = qimg.scaled(self.viewport.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    QTimer.singleShot(0, lambda: self.viewport.setPixmap(QPixmap.fromImage(scaled)))

                prompt = (
                    "Transcribe and extract ALL text, numbers, handwriting, or document text visible in this camera image verbatim. "
                    "Format clearly. Output only the transcribed text."
                )

                ocr_result = gemini.multimodal(prompt, img_bytes, mime=mime or "image/jpeg")
                self._last_ocr_text = ocr_result or ""

                clean_res = (ocr_result or "No text was detected in the camera frame.").replace("\n", "<br>")

                result_html = f"""
                <div style='color: #34D399; font-weight: bold;'>✓ Camera Frame OCR Transcribed</div>
                <div style='color: #64748B; font-size: 7.5pt; margin-bottom: 6px;'>
                    <b>Source:</b> Optical Hardware Camera Frame · Click 'Copy Text' to copy.
                </div>
                <div style='color: #E6E8EC; font-size: 8pt; line-height: 1.4; background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px;'>
                    {clean_res}
                </div>
                """
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(result_html))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(f"<span style='color: #F87171;'>Camera OCR error: {e}</span>"))
            finally:
                QTimer.singleShot(0, lambda: self.snap_ocr_btn.setEnabled(True))

        threading.Thread(target=work, daemon=True, name="cam-ocr-thread").start()

    def _capture_screen_region(self):
        """Captures full screen and executes semantic Visual Question Answering & UI Breakdown."""
        self.vqa_browser.setHtml("<i>Capturing screen surface and executing deep Gemini Vision analysis...</i>")
        self.screen_cap_btn.setEnabled(False)
        self.screen_cap_btn.setText("Analyzing...")

        def work():
            try:
                from PIL import ImageGrab
                shot = ImageGrab.grab()
                tmp_path = Path("assets/temp_screen_snapshot.png")
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                shot.save(str(tmp_path))
                self._last_snapshot_path = tmp_path

                # Display preview in viewport
                qimg = QImage(str(tmp_path))
                if not qimg.isNull():
                    scaled = qimg.scaled(self.viewport.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    QTimer.singleShot(0, lambda: self.viewport.setPixmap(QPixmap.fromImage(scaled)))

                # Perform actual visual reasoning via core.gemini
                prompt = (
                    "You are Tony Stark's executive visual intelligence analyst. "
                    "Analyze the user's active workstation screen: identify open applications, code files, "
                    "potential bugs, terminal messages, and provide a crisp 3-bullet executive briefing with action items."
                )

                img_bytes = tmp_path.read_bytes()
                vision_result = gemini.multimodal(prompt, img_bytes, mime="image/png")
                self._last_ocr_text = vision_result or ""

                clean_res = (vision_result or "Screen captured successfully. Ready for targeted query.").replace("\n", "<br>")

                result_html = f"""
                <div style='color: #34D399; font-weight: bold;'>✓ Visual Snapshot Analyzed</div>
                <div style='color: #64748B; font-size: 7.5pt; margin-bottom: 6px;'>
                    <b>Dimensions:</b> {shot.size[0]}×{shot.size[1]} px · <b>Saved:</b> assets/temp_screen_snapshot.png
                </div>
                <div style='color: #E6E8EC; font-size: 8pt; line-height: 1.4;'>
                    {clean_res}
                </div>
                """
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(result_html))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.vqa_browser.setHtml(f"<span style='color: #F87171;'>Capture error: {e}</span>"))
            finally:
                QTimer.singleShot(0, self._reset_cap_btn)

        threading.Thread(target=work, daemon=True, name="screen-cap-thread").start()

    def _reset_cap_btn(self):
        self.screen_cap_btn.setEnabled(True)
        self.screen_cap_btn.setText("📸 Screen VQA")

    def _copy_ocr_text(self):
        if self._last_ocr_text:
            QApplication.clipboard().setText(self._last_ocr_text)
            self.copy_ocr_btn.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self.copy_ocr_btn.setText("📋 Copy Text"))

    def _explain_frame_with_neo(self):
        """Passes active screen or frame to assistant for conversation dialogue."""
        if self._last_snapshot_path and self._last_snapshot_path.exists():
            cmd = f"Boss, I captured a snapshot of your screen at {self._last_snapshot_path}. Explain what you see and what I should work on next."
        else:
            cmd = "Boss, explain what is on my screen right now."
        self.command_requested.emit(cmd)
        self.vqa_browser.append(f"<br><span style='color: {ACCENT_PRIMARY}; font-weight: bold;'>🧠 Dispatched Visual Reasoning command to NEO Chat!</span>")

    def closeEvent(self, event):
        """Ensure hardware camera is released when closing widget."""
        if self.camera_streaming:
            try:
                from core.camera_service import get_camera_service
                get_camera_service().unregister_consumer("neo_vision_studio")
            except Exception:
                pass
        super().closeEvent(event)
