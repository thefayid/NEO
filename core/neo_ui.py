"""
core/neo_ui.py — Full-Featured Modern Glassmorphic Dashboard & Subsystems for NEO.

Provides pixel-perfect implementation matching the modern NEO dashboard:
1. NeoNavSidebar: Left navigation panel with active indicator and live view routing.
2. NeoHeroStage: Celestial arc, audio reactive waveform, dynamic greeting, search capsule, quick actions.
3. NeoWidgetsSidebar: Right status widgets:
   - System Status (live CPU, RAM, Disk with one-click telemetry drawer toggle)
   - Upcoming Events (agenda & calendar items)
   - Focus Session (25:00 Pomodoro countdown timer with working controls)
   - Media Transport (live Spotify player with track info and playback controls)
4. Functional Central Pages:
   - NeoTasksView: Interactive task checklist with new task creation and filters
   - NeoNotesView: Quick memory scratchpad with save/search functionality
   - NeoProjectsView: Project file explorer and workspace health
   - NeoKnowledgeView: Semantic memory and knowledge base search
   - NeoFilesView: Ingestion drop zone and active document analyzer
"""
from __future__ import annotations

import math
import os
import time
import json
import webbrowser
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QPainterPath,
    QPen, QBrush, QFont, QCursor, QPixmap, QImage
)
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QProgressBar, QFrame, QScrollArea,
    QCheckBox, QListWidget, QListWidgetItem, QSizePolicy,
    QStackedWidget, QGridLayout, QDialog, QComboBox, QButtonGroup
)
import psutil
import random

try:
    from core.avatar import HoloAvatar
except Exception:
    HoloAvatar = None

EMOTION_PALETTES = {
    "listening": (QColor(56, 189, 248), QColor(96, 165, 250),  "Listening"),
    "attuned":   (QColor(56, 189, 248), QColor(96, 165, 250),  "Listening"),
    "thinking":  (QColor(245, 158, 11), QColor(251, 191, 36),  "Thinking..."),
    "speaking":  (QColor(96, 165, 250), QColor(167, 139, 250), "Speaking"),
    "happy":     (QColor(52, 211, 153), QColor(56, 189, 248),  "Pleased"),
    "curious":   (QColor(129, 140, 248), QColor(56, 189, 248), "Curious"),
    "empathy":   (QColor(236, 72, 153), QColor(192, 132, 252), "Empathetic"),
    "muted":     (QColor(148, 163, 184), QColor(244, 63, 94),  "Muted"),
}

def _lerp_color(c1: QColor, c2: QColor, factor: float) -> QColor:
    r = int(c1.red() + (c2.red() - c1.red()) * factor)
    g = int(c1.green() + (c2.green() - c1.green()) * factor)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * factor)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * factor)
    return QColor(r, g, b, a)

def font_display(size: int = 26, weight: QFont.Weight = QFont.Weight.Medium) -> QFont:
    """Modern human-designed display typography (Segoe UI Variable Display / Inter)."""
    f = QFont("Segoe UI Variable Display", size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f

def font_text(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal, letter_spacing: float = 0.0) -> QFont:
    """Modern human-designed body typography with refined tracking."""
    f = QFont("Segoe UI Variable Text", size)
    f.setWeight(weight)
    if letter_spacing > 0.0:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f

# ── Color Palette ────────────────────────────────────────────────────────────
BG_OBSIDIAN    = "#07090e"
SIDEBAR_BG     = "#090c14"
CARD_BG        = "rgba(16, 21, 33, 0.78)"
CARD_BORDER    = "rgba(255, 255, 255, 0.07)"
NAV_ACTIVE_BG  = "#1a2335"
TEXT_WHITE     = "#ffffff"
TEXT_MUTED     = "#8e9eb5"
TEXT_DIM       = "#526078"
ACCENT_BLUE    = "#60a5fa"
ACCENT_CYAN    = "#38bdf8"
SEND_BTN_BG    = "#8ba4d0"


# ─────────────────────────────────────────────────────────────────────────────
#  1. CELESTIAL ECLIPSE ARC & 3D EMOTIONAL AVATAR
# ─────────────────────────────────────────────────────────────────────────────
class NeoEclipseCanvas(QWidget):
    """Draws the ethereal celestial sphere with an animated 3D emotional holographic avatar,
    interactive gaze tracking, live audio/viseme lip sync, orbital particles, and voice wave."""
    emotion_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(236)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.avatar = HoloAvatar() if HoloAvatar is not None else None
        self.audio_level = 0.15
        self._live_amp = 0.0
        self._amp_disp = 0.0
        self.phase = 0.0
        self._last_t = time.time()
        self._visemes = None
        self._vis_i = None

        self.current_state = "LISTENING"
        self.current_emotion = "listening"
        self.is_speaking = False
        self.is_muted = False
        self._emotion_hold = 0.0

        p_col, a_col, _ = EMOTION_PALETTES["listening"]
        self.cur_pri = QColor(p_col)
        self.cur_acc = QColor(a_col)
        self.tgt_pri = QColor(p_col)
        self.tgt_acc = QColor(a_col)

        # 3D Orbital particles
        self.particles = []
        for i in range(16):
            self.particles.append({
                "angle": (i / 16.0) * math.tau,
                "speed": random.uniform(0.6, 1.2),
                "r_offset": random.uniform(-6, 6),
                "size": random.uniform(1.8, 3.2),
            })

        # Touch ripple
        self.ripple_rad = 0.0
        self.ripple_alpha = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def set_emotion(self, emotion: str, duration: float = 0.0):
        emo = (emotion or "listening").lower()
        if emo not in EMOTION_PALETTES:
            emo = "listening"
        self.current_emotion = emo
        if duration > 0.0:
            self._emotion_hold = time.time() + float(duration)
        else:
            self._emotion_hold = 0.0
        if self.avatar is not None:
            self.avatar.set_emotion(emo, duration)
        p, a, _ = EMOTION_PALETTES[emo]
        self.tgt_pri = QColor(p)
        self.tgt_acc = QColor(a)
        self.emotion_changed.emit(emo)

    def cycle_emotion(self):
        # Unique display emotions
        emotions = ["listening", "thinking", "speaking", "happy", "curious", "empathy"]
        try:
            idx = emotions.index(self.current_emotion) if self.current_emotion in emotions else 0
            next_emo = emotions[(idx + 1) % len(emotions)]
        except Exception:
            next_emo = "listening"
        self.set_emotion(next_emo, duration=6.0)

    def set_state(self, state: str):
        self._emotion_hold = 0.0
        self.current_state = str(state or "").upper()
        self.is_speaking = (self.current_state == "SPEAKING")
        if self.is_speaking:
            self.set_emotion("speaking")
        elif self.current_state in ("THINKING", "PROCESSING"):
            self.set_emotion("thinking")
        elif self.current_state in ("MUTED", "SLEEPING"):
            self.set_emotion("muted")
        elif self.current_state in ("LISTENING", "IDLE", "ONLINE", "ACTIVE", "AWAKE", ""):
            self.set_emotion("listening")
        else:
            self.set_emotion("listening")

    def set_muted(self, muted: bool):
        self.is_muted = bool(muted)
        if self.is_muted:
            self.set_emotion("muted")
        else:
            self.set_emotion("listening")



    def set_audio_level(self, level: float):
        try:
            lv = float(level)
            self._live_amp = max(self._live_amp, max(0.0, min(1.0, lv)))
            self.audio_level = max(0.05, min(1.0, lv))
        except Exception:
            pass

    def push_visemes(self, frames, hop: float, at: float):
        try:
            if not frames:
                return
            hop = max(1e-3, float(hop))
            at = float(at)
            new = list(frames)
            cur = self._visemes
            if cur is not None:
                old, t0, ohop = cur
                if abs(ohop - hop) < 1e-6:
                    i = int(round((at - t0) / hop))
                    if 0 <= i <= len(old) + 1:
                        merged = old[:i] + new
                        played = int((time.time() - t0) / hop) - 2
                        if played > 60:
                            merged = merged[played:]
                            t0 += played * hop
                            if self._vis_i is not None:
                                self._vis_i = max(0, self._vis_i - played)
                        self._visemes = (merged, t0, hop)
                        return
            self._visemes = (new, at, hop)
            self._vis_i = None
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1):
        if self.avatar is not None:
            self.avatar.glance(dx, dy, hold)

    def _tick(self):
        now = time.time()
        if self._emotion_hold > 0.0 and now >= self._emotion_hold:
            self._emotion_hold = 0.0
            base_emo = "muted" if self.is_muted else ("speaking" if self.is_speaking else "listening")
            self.set_emotion(base_emo, duration=0.0)

        dt = max(0.001, min(0.08, now - self._last_t))
        self._last_t = now
        self.phase += dt * (1.8 if self.current_emotion in ("thinking", "speaking") else 1.0)

        # Smooth audio amplitude decay
        self._live_amp *= 0.86
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
        amp = self._amp_disp

        # Smooth emotional palette interpolation
        self.cur_pri = _lerp_color(self.cur_pri, self.tgt_pri, 0.12)
        self.cur_acc = _lerp_color(self.cur_acc, self.tgt_acc, 0.12)

        # Visemes schedule
        v_open = v_wide = v_level = None
        v_seq = None
        sched = self._visemes
        if sched is not None:
            frames, t0, hop = sched
            i = int((now - t0) / hop)
            if 0 <= i < len(frames):
                j = self._vis_i if self._vis_i is not None else i
                v_seq = frames[max(0, j):i + 1]
                self._vis_i = max(j, i + 1)
                v_level, v_open, v_wide = frames[i]
                if v_seq:
                    peak = max(f[0] for f in v_seq)
                    if peak > self._live_amp:
                        self._live_amp = peak
            elif i >= len(frames):
                self._visemes = None
                self._vis_i = None

        # Step 3D avatar
        if self.avatar is not None:
            self.avatar.step(
                dt, amp,
                speaking=self.is_speaking,
                muted=self.is_muted,
                state=self.current_state,
                v_open=v_open,
                v_wide=v_wide or 0.0,
                v_level=v_level,
                v_seq=v_seq,
                v_hop=(sched[2] if sched is not None else 0.02)
            )

        # Decay touch ripple
        if self.ripple_alpha > 0.0:
            self.ripple_rad += dt * 120.0
            self.ripple_alpha = max(0.0, self.ripple_alpha - dt * 260.0)

        self.update()

    def mouseMoveEvent(self, event):
        cx = self.width() / 2.0
        cy = 118.0
        pos = event.position()
        dx = (pos.x() - cx) / max(cx, 1.0)
        dy = (pos.y() - cy) / max(cy, 1.0)
        if self.avatar is not None:
            self.avatar.glance(dx * 1.6, dy * 1.6, hold=0.7)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        cx = self.width() / 2.0
        cy = 118.0
        pos = event.position()
        dist = math.hypot(pos.x() - cx, pos.y() - (cy - 22))

        # Check click directly on avatar head
        if dist < 65:
            self.ripple_rad = 15.0
            self.ripple_alpha = 240.0
            if self.avatar is not None:
                self.avatar._blink = 1.0
            self.set_emotion("happy", duration=4.5)
        # Check click on emotion status pill (bottom area)
        elif 192 <= pos.y() <= 222 and abs(pos.x() - cx) < 85:
            self.cycle_emotion()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        cx = w / 2.0
        cy = 118.0
        r = 110.0
        head_cy = 96.0
        head_r = 46.0

        # ── 1. AMBIENT ATMOSPHERIC GLOW ──────────────────────────────────────
        glow = QRadialGradient(cx, cy - 8, r * 1.85)
        glow.setColorAt(0.0, QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 55))
        glow.setColorAt(0.42, QColor(self.cur_acc.red(), self.cur_acc.green(), self.cur_acc.blue(), 20))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r * 1.85, (cy - 8) - r * 1.85, r * 3.7, r * 3.7))

        # ── 2. CELESTIAL CIRCLE & RADIANT RIM ARC ────────────────────────────
        circ_rect = QRectF(cx - r, cy - r, r * 2.0, r * 2.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
        p.drawEllipse(circ_rect)

        # Outer rim glow
        arc_pen_outer = QPen(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 75), 7.0)
        p.setPen(arc_pen_outer)
        p.drawArc(circ_rect, 25 * 16, 130 * 16)

        # Mid radiant rim
        arc_pen_mid = QPen(QColor(self.cur_acc.red(), self.cur_acc.green(), self.cur_acc.blue(), 145), 3.5)
        p.setPen(arc_pen_mid)
        p.drawArc(circ_rect, 32 * 16, 116 * 16)

        # Core pure white rim highlight
        arc_pen_core = QPen(QColor(245, 250, 255, 250), 1.8)
        p.setPen(arc_pen_core)
        p.drawArc(circ_rect, 42 * 16, 96 * 16)

        # ── 3. 3D ORBITAL NEURAL PARTICLES ──────────────────────────────────
        orbit_rx = r * 0.90
        orbit_ry = r * 0.28
        tilt_cos = math.cos(-0.16)
        tilt_sin = math.sin(-0.16)

        p_list = []
        for pt in self.particles:
            ang = pt["angle"] + self.phase * pt["speed"]
            lx = math.cos(ang) * (orbit_rx + pt["r_offset"])
            ly = math.sin(ang) * (orbit_ry + pt["r_offset"])
            px = cx + (lx * tilt_cos - ly * tilt_sin)
            py = head_cy + (lx * tilt_sin + ly * tilt_cos)
            z = ly
            p_list.append((z, px, py, pt["size"], ang))

        p_list.sort(key=lambda item: item[0])

        for z, px, py, sz, ang in p_list:
            if z <= 0:
                alpha = int(70 + 60 * math.sin(ang + self.phase))
                col = QColor(self.cur_acc.red(), self.cur_acc.green(), self.cur_acc.blue(), alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col))
                p.drawEllipse(QPointF(px, py), sz * 0.7, sz * 0.7)

        # ── 4. TOUCH RIPPLE ─────────────────────────────────────────────────
        if self.ripple_alpha > 1.0:
            rip_pen = QPen(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), int(self.ripple_alpha)), 1.5)
            p.setPen(rip_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, head_cy), self.ripple_rad, self.ripple_rad)

        # ── 5. 3D HOLOGRAPHIC AVATAR HEAD ────────────────────────────────────
        if self.avatar is not None:
            self.avatar.paint(p, cx, head_cy, head_r, self.cur_pri, self.cur_acc, QColor(7, 9, 14))

        for z, px, py, sz, ang in p_list:
            if z > 0:
                alpha = int(140 + 100 * math.sin(ang + self.phase))
                col = QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), min(255, alpha))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col))
                p.drawEllipse(QPointF(px, py), sz, sz)

        # ── 6. HARMONIC VOICE SOUNDWAVE ─────────────────────────────────────
        num_bars = 7
        bar_w = 3.2
        spacing = 4.8
        total_w = num_bars * bar_w + (num_bars - 1) * spacing
        start_x = cx - total_w / 2.0
        wave_cy = 168.0

        for i in range(num_bars):
            norm = abs(i - 3) / 3.0
            base_h = 18.0 * (1.0 - norm * 0.55)
            wave = math.sin(self.phase * 3.2 + i * 0.85) * 3.0
            live_h = max(5.0, base_h + wave + self.audio_level * 36.0 * (1.0 - norm * 0.35))

            bx = start_x + i * (bar_w + spacing)
            by = wave_cy - live_h / 2.0

            grad = QLinearGradient(bx, by, bx, by + live_h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 240))
            grad.setColorAt(0.5, self.cur_pri)
            grad.setColorAt(1.0, self.cur_acc)

            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(bx, by, bar_w, live_h), 1.6, 1.6)

        # ── 7. INTERACTIVE EMOTION STATUS PILL (MODERN TYPOGRAPHY) ─────────
        _, _, tag_text = EMOTION_PALETTES.get(self.current_emotion, (None, None, "Listening"))
        pill_w = 118.0
        pill_h = 25.0
        pill_x = cx - pill_w / 2.0
        pill_y = 197.0
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        # Ultra-sleek translucent glass capsule
        p.setBrush(QBrush(QColor(15, 23, 42, 160)))
        p.setPen(QPen(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 42), 1.0))
        p.drawRoundedRect(pill_rect, 12.5, 12.5)

        # Antialiased glowing pulse indicator dot
        dot_center = QPointF(pill_x + 18.0, pill_y + 12.5)
        pulse_alpha = int(45 + 30 * math.sin(self.phase * 2.5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), pulse_alpha)))
        p.drawEllipse(dot_center, 4.5, 4.5)
        p.setBrush(QBrush(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 240)))
        p.drawEllipse(dot_center, 2.5, 2.5)

        # Clean, human-designed modern typography with kerning
        f_pill = font_text(9, QFont.Weight.Medium, letter_spacing=0.4)
        p.setFont(f_pill)
        p.setPen(QPen(QColor(226, 232, 240, 240)))
        text_rect = QRectF(pill_x + 27.0, pill_y, pill_w - 32.0, pill_h)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, tag_text)

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  2. RIGHT STATUS WIDGETS
# ─────────────────────────────────────────────────────────────────────────────
class FocusSessionWidget(QFrame):
    """Pomodoro timer card with interactive Play/Pause, sound effects, and focus music trigger."""
    focus_mode_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.seconds_left = 25 * 60
        self.is_running = False
        self.setFixedHeight(135)

        self.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 12)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        icn = QLabel("🎯")
        icn.setFont(QFont("Segoe UI", 12))
        hdr.addWidget(icn)
        hdr_txt = QLabel("Focus Session")
        hdr_txt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(hdr_txt)
        hdr.addStretch()
        lay.addLayout(hdr)

        sub = QLabel("Stay in the zone with NEO")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        lay.addWidget(sub)
        lay.addSpacing(4)

        row = QHBoxLayout()
        self.timer_lbl = QLabel("25:00")
        self.timer_lbl.setFont(QFont("Segoe UI", 25, QFont.Weight.Bold))
        self.timer_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        row.addWidget(self.timer_lbl)
        row.addStretch()

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(38, 38)
        self.play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.play_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(96, 165, 250, 0.18);
                color: {ACCENT_BLUE};
                border: 1px solid rgba(96, 165, 250, 0.3);
                border-radius: 19px;
            }}
            QPushButton:hover {{
                background: rgba(96, 165, 250, 0.35);
                color: #ffffff;
            }}
        """)
        self.play_btn.clicked.connect(self._toggle_timer)
        row.addWidget(self.play_btn)
        lay.addLayout(row)

        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._on_tick)

    def _toggle_timer(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.play_btn.setText("⏸")
            self._ticker.start()
            self.focus_mode_toggled.emit(True)
        else:
            self.play_btn.setText("▶")
            self._ticker.stop()
            self.focus_mode_toggled.emit(False)

    def _on_tick(self):
        if self.seconds_left > 0:
            self.seconds_left -= 1
            mins = self.seconds_left // 60
            secs = self.seconds_left % 60
            self.timer_lbl.setText(f"{mins:02d}:{secs:02d}")
        else:
            self.seconds_left = 25 * 60
            self._toggle_timer()
            self.timer_lbl.setText("25:00")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        path = QPainterPath()
        path.moveTo(0, h - 16)
        path.cubicTo(w * 0.3, h - 30, w * 0.6, h - 6, w, h - 20)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(96, 165, 250, 30), 1.5))
        p.drawPath(path)


class SystemStatusWidget(QFrame):
    """System Status card with live System (Disk), CPU, Memory progress bars."""
    telemetry_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        icn = QLabel("📈")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        hdr_txt = QLabel("System Status")
        hdr_txt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(hdr_txt)
        hdr.addStretch()

        arr_btn = QPushButton("›")
        arr_btn.setFixedSize(20, 20)
        arr_btn.setFont(QFont("Segoe UI", 13))
        arr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        arr_btn.setStyleSheet("""
            QPushButton {
                color: #8e9eb5; border: none; background: transparent;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        arr_btn.clicked.connect(self.telemetry_requested.emit)
        hdr.addWidget(arr_btn)
        lay.addLayout(hdr)

        self.sys_bar, self.sys_pct = self._add_metric_row(lay, "💻", "System", 27)
        self.cpu_bar, self.cpu_pct = self._add_metric_row(lay, "🔲", "CPU", 34)
        self.mem_bar, self.mem_pct = self._add_metric_row(lay, "💾", "Memory", 62)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(2000)
        self._refresh()

    def _add_metric_row(self, layout, icon, name, initial_val):
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl_icn = QLabel(icon)
        lbl_icn.setFont(QFont("Segoe UI", 9))
        lbl_icn.setStyleSheet("border: none; background: transparent;")
        row.addWidget(lbl_icn)

        lbl_name = QLabel(name)
        lbl_name.setFont(QFont("Segoe UI", 9))
        lbl_name.setFixedWidth(54)
        lbl_name.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        row.addWidget(lbl_name)

        bar = QProgressBar()
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(initial_val)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: #19202f;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #60a5fa, stop:1 #93c5fd);
                border-radius: 3px;
            }}
        """)
        row.addWidget(bar, stretch=1)

        pct = QLabel(f"{initial_val}%")
        pct.setFont(QFont("Segoe UI", 9))
        pct.setFixedWidth(34)
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pct.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        row.addWidget(pct)

        layout.addLayout(row)
        return bar, pct

    def _refresh(self):
        try:
            cpu = int(psutil.cpu_percent())
            mem = int(psutil.virtual_memory().percent)
            disk = int(psutil.disk_usage("/").percent) if hasattr(psutil, "disk_usage") else 27

            self.cpu_bar.setValue(cpu)
            self.cpu_pct.setText(f"{cpu}%")

            self.mem_bar.setValue(mem)
            self.mem_pct.setText(f"{mem}%")

            self.sys_bar.setValue(disk)
            self.sys_pct.setText(f"{disk}%")
        except Exception:
            pass


def _time_to_minutes(time_str: str) -> int:
    clean = (time_str or "").strip().upper()
    try:
        if "AM" in clean or "PM" in clean:
            dt = datetime.strptime(clean, "%I:%M %p")
            return dt.hour * 60 + dt.minute
        parts = clean.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0

def _format_time_friendly(time_str: str) -> str:
    try:
        clean = (time_str or "").strip().upper()
        if "AM" in clean or "PM" in clean:
            return clean
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        suffix = "AM" if h < 12 else "PM"
        h12 = h if (h == 12 or h == 0) else (h % 12)
        if h == 0:
            h12 = 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return str(time_str or "")

class CalendarSyncDialog(QDialog):
    """Spacious glassmorphic dialog for configuring Google Calendar / Outlook iCal feed and adding events."""
    feed_synced = pyqtSignal(int)
    event_added = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(500, 410)
        self.setStyleSheet("""
            QDialog {
                background: #0b0f19;
                border: 1.5px solid rgba(56, 189, 248, 0.38);
                border-radius: 16px;
            }
        """)

        frame = QFrame(self)
        frame.setGeometry(0, 0, 500, 410)
        frame.setStyleSheet("""
            QFrame {
                background: #0b0f19;
                border: none;
                border-radius: 16px;
            }
        """)

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        # 1. Header
        hdr = QHBoxLayout()
        icn = QLabel("📅")
        icn.setFont(QFont("Segoe UI", 12))
        hdr.addWidget(icn)

        t_lbl = QLabel("CALENDAR & AGENDA SYNC")
        t_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; border: none; background: transparent; letter-spacing: 0.5px;")
        hdr.addWidget(t_lbl)

        hdr.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFont(QFont("Segoe UI", 10))
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                color: #64748b; background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 13px;
            }
            QPushButton:hover { color: #ffffff; background: rgba(239, 68, 68, 0.25); border-color: #ef4444; }
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        sub = QLabel("Sync Google Calendar / Outlook via private iCal (.ics) feed or quick-add events.")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        lay.addWidget(sub)

        # 2. Feed URL Section
        f_lbl = QLabel("GOOGLE CALENDAR / OUTLOOK ICAL FEED URL:")
        f_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        f_lbl.setStyleSheet("color: #38bdf8; border: none; background: transparent;")
        lay.addWidget(f_lbl)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://calendar.google.com/calendar/ical/.../basic.ics")
        self.url_input.setFont(QFont("Segoe UI", 9))
        self.url_input.setFixedHeight(32)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background: #0f1626; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 4px 8px;
            }
            QLineEdit:focus { border: 1.5px solid #00e5ff; }
        """)
        lay.addWidget(self.url_input)

        sync_row = QHBoxLayout()
        self.sync_btn = QPushButton("⚡  Sync Feed Now")
        self.sync_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_btn.setFixedHeight(30)
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00e5ff);
                color: #080c14; border: none; border-radius: 6px; padding: 4px 16px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        self.sync_btn.clicked.connect(self._sync_feed)
        sync_row.addWidget(self.sync_btn)

        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Segoe UI", 8))
        self.status_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        sync_row.addWidget(self.status_lbl)
        sync_row.addStretch(1)
        lay.addLayout(sync_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.08);")
        lay.addWidget(sep)

        # 3. Quick Add Event Section
        a_lbl = QLabel("QUICK ADD EVENT TO TODAY'S SCHEDULE:")
        a_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        a_lbl.setStyleSheet("color: #4ade80; border: none; background: transparent;")
        lay.addWidget(a_lbl)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Event title (e.g. AI Architecture Review, Client Call)...")
        self.title_input.setFont(QFont("Segoe UI", 9))
        self.title_input.setFixedHeight(30)
        self.title_input.setStyleSheet("""
            QLineEdit {
                background: #0f1626; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 4px 8px;
            }
            QLineEdit:focus { border: 1.5px solid #00e5ff; }
        """)
        lay.addWidget(self.title_input)

        time_row = QHBoxLayout()
        t1_lbl = QLabel("Start:")
        t1_lbl.setFont(QFont("Segoe UI", 8))
        t1_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        time_row.addWidget(t1_lbl)

        self.start_input = QLineEdit("17:00")
        self.start_input.setFont(QFont("Segoe UI", 8))
        self.start_input.setFixedHeight(28)
        self.start_input.setFixedWidth(64)
        self.start_input.setStyleSheet("background: #0f1626; color: #ffffff; border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; padding: 2px 6px;")
        time_row.addWidget(self.start_input)

        t2_lbl = QLabel("End:")
        t2_lbl.setFont(QFont("Segoe UI", 8))
        t2_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        time_row.addWidget(t2_lbl)

        self.end_input = QLineEdit("18:30")
        self.end_input.setFont(QFont("Segoe UI", 8))
        self.end_input.setFixedHeight(28)
        self.end_input.setFixedWidth(64)
        self.end_input.setStyleSheet("background: #0f1626; color: #ffffff; border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; padding: 2px 6px;")
        time_row.addWidget(self.end_input)

        time_row.addStretch(1)

        add_b = QPushButton("+ Add to Schedule")
        add_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        add_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_b.setFixedHeight(28)
        add_b.setStyleSheet("""
            QPushButton {
                background: rgba(34, 197, 94, 0.2);
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.4);
                border-radius: 5px; padding: 4px 14px;
            }
            QPushButton:hover { background: rgba(34, 197, 94, 0.35); color: #ffffff; }
        """)
        add_b.clicked.connect(self._add_event)
        time_row.addWidget(add_b)
        lay.addLayout(time_row)

        self._load_current_url()

    def _load_current_url(self):
        try:
            cfg_p = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                url = cfg.get("calendar_ical_url", "")
                if url:
                    self.url_input.setText(url)
                    self.status_lbl.setText("● Feed URL loaded")
        except Exception:
            pass

    def _sync_feed(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_lbl.setText("⚠️ Enter iCal URL first")
            return

        # Auto-clean common URL paste fragments
        if url.startswith("webcal://"):
            url = "https://" + url[9:]
        if url.startswith("ndar.google.com"):
            url = "https://cale" + url
        elif url.startswith("calendar.google.com"):
            url = "https://" + url
        elif not url.startswith(("http://", "https://")):
            url = "https://" + url

        self.url_input.setText(url)
        self.status_lbl.setText("Syncing feed...")
        try:
            import json as _json
            cfg_p = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = _json.load(f)
                cfg["calendar_ical_url"] = url
                with open(cfg_p, "w", encoding="utf-8") as f:
                    _json.dump(cfg, f, indent=4)

            from actions.executive_briefing import _sync_ical_feed
            count = _sync_ical_feed(url)
            self.status_lbl.setText(f"✓ Synced {count} events successfully!" if count else "✓ Connected (0 events in feed)")
            self.feed_synced.emit(count)
        except Exception as e:
            self.status_lbl.setText(f"⚠️ {e}")

    def _add_event(self):
        title = self.title_input.text().strip()
        start = self.start_input.text().strip()
        end = self.end_input.text().strip()
        if not title:
            return
        today_str = datetime.now().strftime("%Y-%m-%d")
        new_ev = {
            "id": f"evt_{int(datetime.now().timestamp())}",
            "title": title,
            "date": today_str,
            "start_time": start,
            "end_time": end,
            "source": "local",
        }
        try:
            from actions.executive_briefing import _load_agenda, _save_agenda
            data = _load_agenda()
            evs = data.get("events", [])
            evs.append(new_ev)
            data["events"] = evs
            _save_agenda(data)
            self.title_input.clear()
            self.event_added.emit(new_ev)
            self.status_lbl.setText(f"✓ Added '{title}' to today's schedule!")
        except Exception as e:
            self.status_lbl.setText(f"⚠️ Error adding event: {e}")

class UpcomingScheduleWidget(QFrame):
    """
    Clean, pixel-perfect Upcoming schedule card matching user's exact design.
    Seamlessly synchronizes with Google Calendar / Outlook and shows authentic upcoming events.
    """
    schedule_clicked = pyqtSignal()
    event_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame#UpcomingScheduleWidget {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 16px;
            }}
        """)
        self.setObjectName("UpcomingScheduleWidget")

        self.root_lay = QVBoxLayout(self)
        self.root_lay.setContentsMargins(18, 14, 18, 14)
        self.root_lay.setSpacing(8)

        # 1. Header
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        icn = QLabel("📅")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        hdr_txt = QLabel("Upcoming")
        hdr_txt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(hdr_txt)

        hdr.addStretch(1)

        # Small toggle gear button to connect API
        self.api_btn = QPushButton("⚙")
        self.api_btn.setToolTip("Connect Calendar API & Manage Events")
        self.api_btn.setFont(QFont("Segoe UI", 9))
        self.api_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.api_btn.setFixedSize(22, 22)
        self.api_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #8e9eb5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 11px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.api_btn.clicked.connect(self._open_sync_dialog)
        hdr.addWidget(self.api_btn)

        arr_btn = QPushButton("›")
        arr_btn.setFixedSize(22, 22)
        arr_btn.setFont(QFont("Segoe UI", 13))
        arr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        arr_btn.setStyleSheet("""
            QPushButton {
                color: #8e9eb5; border: none; background: transparent;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        arr_btn.clicked.connect(self.schedule_clicked.emit)
        hdr.addWidget(arr_btn)
        self.root_lay.addLayout(hdr)

        # 2. Subtitle Header Row
        sub_row = QHBoxLayout()
        self.sub_date_lbl = QLabel("Today, " + datetime.now().strftime("%b %d"))
        self.sub_date_lbl.setFont(QFont("Segoe UI", 8))
        self.sub_date_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        sub_row.addWidget(self.sub_date_lbl)

        sub_row.addStretch(1)

        self.sub_count_lbl = QLabel("")
        self.sub_count_lbl.setFont(QFont("Segoe UI", 8))
        self.sub_count_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        sub_row.addWidget(self.sub_count_lbl)

        self.root_lay.addLayout(sub_row)
        self.root_lay.addSpacing(2)

        # 3. Events Container
        self.events_layout = QVBoxLayout()
        self.events_layout.setSpacing(8)
        self.root_lay.addLayout(self.events_layout)

        # Timer to auto-update
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.reload_events)
        self.refresh_timer.start(30000)

        self._dialog = None
        self.reload_events()

        # Background auto-sync if calendar URL configured
        QTimer.singleShot(1500, self._auto_sync_calendar)

    def _auto_sync_calendar(self):
        try:
            import json as _json
            cfg_p = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = _json.load(f)
                url = cfg.get("calendar_ical_url")
                if url:
                    def _worker():
                        try:
                            from actions.executive_briefing import _sync_ical_feed
                            _sync_ical_feed(url)
                            QTimer.singleShot(0, self.reload_events)
                        except Exception:
                            pass
                    threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass

    def _open_sync_dialog(self):
        if not self._dialog:
            self._dialog = CalendarSyncDialog(self.window())
            self._dialog.feed_synced.connect(lambda _: self.reload_events())
            self._dialog.event_added.connect(lambda _: self.reload_events())
        win = self.window()
        if win:
            self._dialog.move(
                win.x() + (win.width() - self._dialog.width()) // 2,
                win.y() + (win.height() - self._dialog.height()) // 2
            )
        self._dialog.show()
        self._dialog.raise_()

    def reload_events(self):
        while self.events_layout.count():
            item = self.events_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        now = datetime.now()
        today = now.date()
        today_str = today.strftime("%Y-%m-%d")
        now_mins = now.hour * 60 + now.minute

        DUMMY_TITLES = {
            "Financial Management Exam", "SIH Team Sync", "Review & Notes",
            "Architecture Review & Sprint Sync", "Production Deployment & Telemetry Sign-off",
            "Executive Client Project Review"
        }

        all_evs = []
        try:
            from actions.executive_briefing import _load_agenda
            agenda = _load_agenda()
            raw_evs = agenda.get("events", [])
            for ev in raw_evs:
                if ev.get("title") not in DUMMY_TITLES:
                    all_evs.append(ev)
        except Exception:
            pass

        today_events = []
        future_events = []

        for ev in all_evs:
            ev_date_str = ev.get("date", "")
            if not ev_date_str:
                ev_date_str = today_str
            try:
                ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d").date()
            except Exception:
                continue

            if ev_date == today:
                today_events.append(ev)
            elif ev_date > today:
                future_events.append((ev_date, ev))

        today_events.sort(key=lambda ev: _time_to_minutes(ev.get("start_time", "00:00")))
        future_events.sort(key=lambda pair: (pair[0], _time_to_minutes(pair[1].get("start_time", "00:00"))))

        # Count active/remaining today
        remaining_today = 0
        for ev in today_events:
            s_mins = _time_to_minutes(ev.get("start_time", "00:00"))
            e_mins = _time_to_minutes(ev.get("end_time", "00:00"))
            if e_mins <= s_mins:
                e_mins = s_mins + 30
            if now_mins < e_mins:
                remaining_today += 1

        # Build list of items to show (up to 4 items)
        display_items = []
        for ev in today_events:
            display_items.append(("today", today, ev))

        if len(display_items) < 3:
            for ev_date, ev in future_events:
                display_items.append(("future", ev_date, ev))
                if len(display_items) >= 4:
                    break

        # Update Subtitle header
        if today_events:
            self.sub_date_lbl.setText(today.strftime("Today, %b %d"))
            if remaining_today > 0:
                self.sub_count_lbl.setText(f"{remaining_today} remaining")
            else:
                self.sub_count_lbl.setText("All caught up")
        elif future_events:
            next_date = future_events[0][0]
            days_away = (next_date - today).days
            if days_away == 1:
                self.sub_date_lbl.setText(today.strftime("Today, %b %d"))
                self.sub_count_lbl.setText("Next: Tomorrow")
            else:
                self.sub_date_lbl.setText(today.strftime("Today, %b %d"))
                self.sub_count_lbl.setText(f"Next: {next_date.strftime('%a, %b %d')}")
        else:
            self.sub_date_lbl.setText(today.strftime("Today, %b %d"))
            self.sub_count_lbl.setText("0 scheduled")

        if not display_items:
            self._add_empty_row()
            return

        for i, (kind, ev_date, ev) in enumerate(display_items[:4]):
            title = ev.get("title", "Event")
            s_str = ev.get("start_time", "")
            e_str = ev.get("end_time", "")
            s_mins = _time_to_minutes(s_str)
            e_mins = _time_to_minutes(e_str)
            if e_mins <= s_mins:
                e_mins = s_mins + 30

            friendly_s = _format_time_friendly(s_str)
            friendly_e = _format_time_friendly(e_str)

            if kind == "today":
                time_display = f"{friendly_s} – {friendly_e}"
                if now_mins >= e_mins:
                    badge_info = ("✓ Done", "rgba(148, 163, 184, 0.15)", "#94a3b8")
                    is_active = False
                    is_done = True
                elif s_mins <= now_mins < e_mins:
                    badge_info = ("● Now", "rgba(56, 189, 248, 0.2)", "#38bdf8")
                    is_active = True
                    is_done = False
                elif 0 < s_mins - now_mins <= 60:
                    badge_info = (f"In {s_mins - now_mins}m", "rgba(56, 189, 248, 0.2)", "#38bdf8")
                    is_active = (i == 0)
                    is_done = False
                else:
                    badge_info = None
                    is_active = (i == 0)
                    is_done = False
            else:
                days_away = (ev_date - today).days
                day_prefix = "Tomorrow" if days_away == 1 else ev_date.strftime("%a, %b %d")
                if s_str == "All Day":
                    time_display = f"{day_prefix} · All Day"
                else:
                    time_display = f"{day_prefix} · {friendly_s} – {friendly_e}"
                badge_info = ("Tomorrow", "rgba(96, 165, 250, 0.15)", "#60a5fa") if days_away == 1 else None
                is_active = (i == 0 and len(today_events) == 0)
                is_done = False

            self._add_event_row(title, time_display, active=is_active, badge_info=badge_info, is_done=is_done)

    def _add_empty_row(self):
        card = QFrame()
        card.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(4, 10, 4, 10)
        lay.setSpacing(4)

        t_lbl = QLabel("●  No upcoming events")
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        t_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        lay.addWidget(t_lbl)

        sub_lbl = QLabel("Schedule is clear. Tap ⚙ to sync or add events.")
        sub_lbl.setFont(QFont("Segoe UI", 8))
        sub_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        lay.addWidget(sub_lbl)

        self.events_layout.addWidget(card)

    def _add_event_row(self, title: str, time_str: str, active: bool = False, badge_info: tuple[str, str, str] | None = None, is_done: bool = False):
        card = QFrame()
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border-radius: 6px;
            }
            QFrame:hover {
                background: rgba(255, 255, 255, 0.04);
            }
        """)

        row = QHBoxLayout(card)
        row.setContentsMargins(2, 4, 2, 4)
        row.setSpacing(10)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 8))
        if is_done:
            dot_color = "#526078"
        elif active:
            dot_color = ACCENT_BLUE
        else:
            dot_color = TEXT_DIM
        dot.setStyleSheet(f"color: {dot_color}; border: none; background: transparent; padding-top: 1px;")
        row.addWidget(dot, alignment=Qt.AlignmentFlag.AlignTop)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        vbox.setContentsMargins(0, 0, 0, 0)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold if active else QFont.Weight.Normal))
        t_color = "#64748b" if is_done else (TEXT_WHITE if active else TEXT_MUTED)
        t_lbl.setStyleSheet(f"color: {t_color}; border: none; background: transparent;")
        vbox.addWidget(t_lbl)

        time_lay = QHBoxLayout()
        time_lay.setSpacing(6)
        time_lbl = QLabel(time_str)
        time_lbl.setFont(QFont("Segoe UI", 8))
        time_lbl.setStyleSheet(f"color: {'#475569' if is_done else TEXT_DIM}; border: none; background: transparent;")
        time_lay.addWidget(time_lbl)

        if badge_info:
            b_text, b_bg, b_fg = badge_info
            badge = QLabel(b_text)
            badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            badge.setStyleSheet(f"""
                QLabel {{
                    background: {b_bg};
                    color: {b_fg};
                    border-radius: 3px;
                    padding: 1px 5px;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                }}
            """)
            time_lay.addWidget(badge)

        time_lay.addStretch()
        vbox.addLayout(time_lay)

        row.addLayout(vbox)
        row.addStretch()

        card.mousePressEvent = lambda e, t=title: self._on_event_clicked(t)
        self.events_layout.addWidget(card)

    def _on_event_clicked(self, title: str):
        self.event_selected.emit(f"Review and brief me on '{title}'")
        self.schedule_clicked.emit()


class MediaTransportWidget(QFrame):
    """Media Transport & Spotify player card in the right sidebar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        icn = QLabel("♫")
        icn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        icn.setStyleSheet("color: #1ed760; border: none; background: transparent;")
        hdr.addWidget(icn)
        hdr_txt = QLabel("Media Transport")
        hdr_txt.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hdr_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(hdr_txt)
        hdr.addStretch()

        self.service_badge = QLabel("SPOTIFY")
        self.service_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.service_badge.setStyleSheet("""
            color: #1ed760; background: rgba(30, 215, 96, 0.12);
            border: 1px solid rgba(30, 215, 96, 0.3); border-radius: 4px; padding: 2px 5px;
        """)
        hdr.addWidget(self.service_badge)
        lay.addLayout(hdr)

        self.track_lbl = QLabel("No track playing")
        self.track_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.track_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        lay.addWidget(self.track_lbl)

        self.artist_lbl = QLabel("Spotify Idle")
        self.artist_lbl.setFont(QFont("Segoe UI", 8))
        self.artist_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        lay.addWidget(self.artist_lbl)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        def _btn(sym: str, tip: str, cb) -> QPushButton:
            b = QPushButton(sym)
            b.setFixedSize(26, 26)
            b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setToolTip(tip)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.06);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 13px;
                }
                QPushButton:hover {
                    background: rgba(96, 165, 250, 0.3);
                    border-color: #60a5fa;
                }
            """)
            b.clicked.connect(cb)
            return b

        controls.addWidget(_btn("⏮", "Previous Track", self._on_prev))
        self.play_toggle_btn = _btn("⏯", "Play / Pause", self._on_playpause)
        controls.addWidget(self.play_toggle_btn)
        controls.addWidget(_btn("⏭", "Next Track", self._on_next))
        controls.addStretch()

        vol_down = _btn("🔉", "Volume Down", lambda: self._on_vol("-15"))
        vol_up = _btn("🔊", "Volume Up", lambda: self._on_vol("+15"))
        controls.addWidget(vol_down)
        controls.addWidget(vol_up)

        lay.addLayout(controls)

        self._poll_tmr = QTimer(self)
        self._poll_tmr.setInterval(3000)
        self._poll_tmr.timeout.connect(self._poll_spotify)
        self._poll_tmr.start()
        self._poll_spotify()

    def _poll_spotify(self):
        try:
            from actions.spotify_control import _get_current_song_desktop
            desc = _get_current_song_desktop()
            if "Currently playing" in desc:
                # E.g. "Currently playing 'Starboy' by The Weeknd on Spotify, Boss."
                parts = desc.split("'")
                if len(parts) >= 2:
                    self.track_lbl.setText(parts[1][:28])
                    rem = parts[2]
                    if "by " in rem:
                        artist = rem.split("by ")[1].split(" on")[0].strip()
                        self.artist_lbl.setText(artist[:28])
            elif "paused" in desc.lower():
                self.artist_lbl.setText("Playback paused")
            else:
                self.track_lbl.setText("Spotify Standby")
                self.artist_lbl.setText("Press play to resume")
        except Exception:
            pass

    def _on_prev(self):
        try:
            from actions.spotify_control import spotify_control
            spotify_control({"action": "previous"})
            QTimer.singleShot(400, self._poll_spotify)
        except Exception:
            pass

    def _on_playpause(self):
        try:
            from actions.spotify_control import spotify_control
            spotify_control({"action": "play"})
            QTimer.singleShot(400, self._poll_spotify)
        except Exception:
            pass

    def _on_next(self):
        try:
            from actions.spotify_control import spotify_control
            spotify_control({"action": "next"})
            QTimer.singleShot(400, self._poll_spotify)
        except Exception:
            pass

    def _on_vol(self, change: str):
        try:
            from actions.spotify_control import spotify_control
            spotify_control({"action": "volume", "change": change})
        except Exception:
            pass


class NeoWidgetsSidebar(QWidget):
    """Right sidebar with System Status, Upcoming schedule, Focus Session, and Media Transport."""
    telemetry_requested = pyqtSignal()
    schedule_requested = pyqtSignal()
    event_briefing_requested = pyqtSignal(str)
    focus_mode_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(310)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 14, 16, 14)
        vbox.setSpacing(12)

        self.status_card = SystemStatusWidget()
        self.status_card.telemetry_requested.connect(self.telemetry_requested.emit)
        vbox.addWidget(self.status_card)

        self.upcoming_card = UpcomingScheduleWidget()
        self.upcoming_card.schedule_clicked.connect(self.schedule_requested.emit)
        self.upcoming_card.event_selected.connect(self.event_briefing_requested.emit)
        vbox.addWidget(self.upcoming_card)

        self.focus_card = FocusSessionWidget()
        self.focus_card.focus_mode_toggled.connect(self.focus_mode_toggled.emit)
        vbox.addWidget(self.focus_card)

        self.media_card = MediaTransportWidget()
        vbox.addWidget(self.media_card)

        vbox.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
#  3. LEFT NAVIGATION SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
class NeoNavSidebar(QWidget):
    """Left navigation panel with Home, Chat, Tasks, Notes, Tools, Settings."""
    tab_changed = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(205)
        self.setStyleSheet(f"""
            QWidget {{
                background: {SIDEBAR_BG};
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(4)

        # Header Logo
        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(6, 0, 6, 14)
        logo_icn = QLabel("⭘")
        logo_icn.setFont(QFont("Segoe UI", 16))
        logo_icn.setStyleSheet(f"color: {ACCENT_CYAN}; border: none; background: transparent;")
        logo_row.addWidget(logo_icn)

        logo_title = QLabel("NEO")
        logo_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        logo_title.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; letter-spacing: 1px;")
        logo_row.addWidget(logo_title)
        logo_row.addStretch()

        collapse_btn = QPushButton("◫")
        collapse_btn.setFixedSize(24, 24)
        collapse_btn.setFont(QFont("Segoe UI", 10))
        collapse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #526078; border: none;
            }
            QPushButton:hover { color: #8e9eb5; }
        """)
        logo_row.addWidget(collapse_btn)
        lay.addLayout(logo_row)

        self.btn_home = self._create_nav_item("⌂", "Home", active=True)
        self.btn_chat = self._create_nav_item("💬", "Chat", active=False)
        self.btn_tasks = self._create_nav_item("☑", "Tasks", active=False)
        self.btn_notes = self._create_nav_item("📄", "Notes", active=False)
        self.btn_projects = self._create_nav_item("🗂", "Projects", active=False)
        self.btn_knowledge = self._create_nav_item("📚", "Knowledge", active=False)

        for b in [self.btn_home, self.btn_chat, self.btn_tasks, self.btn_notes, self.btn_projects, self.btn_knowledge]:
            lay.addWidget(b)

        lay.addSpacing(14)
        tools_lbl = QLabel("TOOLS")
        tools_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        tools_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent; padding-left: 10px; letter-spacing: 1.5px;")
        lay.addWidget(tools_lbl)
        lay.addSpacing(2)

        self.btn_summarize = self._create_nav_item("📑", "Summarize", active=False)
        self.btn_research = self._create_nav_item("🔍", "Research", active=False)
        self.btn_code = self._create_nav_item("</>", "Code Assist", active=False)
        self.btn_files = self._create_nav_item("📁", "Files", active=False)

        for b in [self.btn_summarize, self.btn_research, self.btn_code, self.btn_files]:
            lay.addWidget(b)

        lay.addStretch()

        self.btn_settings = self._create_nav_item("⚙", "Settings", active=False)
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        lay.addWidget(self.btn_settings)

    def _create_nav_item(self, icon, label, active=False):
        btn = QPushButton(f"  {icon}   {label}")
        btn.setFixedHeight(38)
        btn.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold if active else QFont.Weight.Normal))
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(self._nav_style(active))
        btn.clicked.connect(lambda _, l=label: self._on_item_clicked(l))
        return btn

    def _nav_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {NAV_ACTIVE_BG};
                    color: {TEXT_WHITE};
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                    text-align: left;
                    padding-left: 12px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: none;
                border-radius: 10px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.04);
                color: {TEXT_WHITE};
            }}
        """

    def _on_item_clicked(self, name: str):
        for b, lbl in [
            (self.btn_home, "Home"), (self.btn_chat, "Chat"), (self.btn_tasks, "Tasks"),
            (self.btn_notes, "Notes"), (self.btn_projects, "Projects"), (self.btn_knowledge, "Knowledge"),
            (self.btn_summarize, "Summarize"), (self.btn_research, "Research"),
            (self.btn_code, "Code Assist"), (self.btn_files, "Files")
        ]:
            b.setStyleSheet(self._nav_style(lbl == name))
            b.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold if lbl == name else QFont.Weight.Normal))
        self.tab_changed.emit(name)

    def select_tab(self, name: str):
        self._on_item_clicked(name)


# ─────────────────────────────────────────────────────────────────────────────
#  4. LIVE SPEECH TRANSCRIPT WIDGET (YOU IN GREEN, NEO IN WHITE)
# ─────────────────────────────────────────────────────────────────────────────
class NeoLiveTranscriptWidget(QFrame):
    """Clean, high-end live speech subtitle pill with green user text and white assistant text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setFixedWidth(640)
        self.setStyleSheet("""
            QFrame {
                background: rgba(14, 20, 32, 0.78);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 19px;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)

        self.dot = QLabel("●")
        self.dot.setFont(font_text(9, QFont.Weight.Bold))
        self.dot.setStyleSheet("color: #4ade80; border: none; background: transparent;")
        lay.addWidget(self.dot)

        self.text_lbl = QLabel('<span style="color: #64748b;">● Live Transcript Active · Speak to NEO</span>')
        self.text_lbl.setFont(font_text(10, QFont.Weight.Normal))
        self.text_lbl.setStyleSheet("border: none; background: transparent;")
        lay.addWidget(self.text_lbl, stretch=1)

        self._decay_tmr = QTimer(self)
        self._decay_tmr.setInterval(12000)
        self._decay_tmr.timeout.connect(self._on_decay)

    def set_speech(self, speaker: str, text: str):
        t = (text or "").strip()
        if not t:
            return
        self._decay_tmr.stop()
        if speaker.lower() in ("user", "you", "fayid"):
            self.dot.setStyleSheet("color: #4ade80; border: none; background: transparent;")
            self.text_lbl.setText(
                f'<span style="color: #4ade80; font-weight: 600;">You:</span> '
                f'<span style="color: #4ade80;">"{t}"</span>'
            )
        else:
            self.dot.setStyleSheet("color: #60a5fa; border: none; background: transparent;")
            self.text_lbl.setText(
                f'<span style="color: #94a3b8; font-weight: 600;">NEO:</span> '
                f'<span style="color: #ffffff;">"{t}"</span>'
            )
        self._decay_tmr.start()

    def _on_decay(self):
        self._decay_tmr.stop()
        self.dot.setStyleSheet("color: #526078; border: none; background: transparent;")
        self.text_lbl.setText('<span style="color: #526078;">● Live Transcript Active · Speak to NEO</span>')


# ─────────────────────────────────────────────────────────────────────────────
#  5. CENTER HERO STAGE
# ─────────────────────────────────────────────────────────────────────────────
class NeoHeroStage(QWidget):
    """Center main hero dashboard with celestial arc, dynamic greeting, search capsule, and quick actions."""
    command_submitted = pyqtSignal(str)
    attach_requested = pyqtSignal()
    mic_toggled = pyqtSignal()
    camera_close_requested = pyqtSignal()

    def __init__(self, user_name: str = "Fayid", parent=None):
        super().__init__(parent)
        self.user_name = user_name
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(40, 10, 40, 25)
        vbox.setSpacing(0)

        # 1. Celestial Arc Canvas
        self.eclipse = NeoEclipseCanvas()
        vbox.addWidget(self.eclipse)

        # 2. Greeting and Subtitles
        vbox.addSpacing(6)
        hr = datetime.now().hour
        period = "Morning" if hr < 12 else ("Afternoon" if hr < 17 else "Evening")
        self.title_lbl = QLabel(f"Good {period}, {self.user_name}.")
        self.title_lbl.setFont(font_display(26, QFont.Weight.Medium))
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; letter-spacing: -0.3px;")
        vbox.addWidget(self.title_lbl)

        vbox.addSpacing(7)
        self.sub1 = QLabel("I'm NEO — your personal AI assistant.")
        self.sub1.setFont(font_text(10, QFont.Weight.Normal))
        self.sub1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub1.setStyleSheet(f"color: #94a3b8; border: none; background: transparent;")
        vbox.addWidget(self.sub1)

        vbox.addSpacing(2)
        self.sub2 = QLabel("How can I help you today?")
        self.sub2.setFont(font_text(10, QFont.Weight.Normal))
        self.sub2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub2.setStyleSheet(f"color: #64748b; border: none; background: transparent;")
        vbox.addWidget(self.sub2)

        # Camera Viewport Container (Displayed directly in Home menu when active)
        self.camera_card = QFrame()
        self.camera_card.setFixedWidth(640)
        self.camera_card.setFixedHeight(350)
        self.camera_card.setStyleSheet("""
            QFrame {
                background: rgba(10, 14, 22, 0.95);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 20px;
            }
        """)
        cam_card_v = QVBoxLayout(self.camera_card)
        cam_card_v.setContentsMargins(16, 12, 16, 14)
        cam_card_v.setSpacing(8)

        cam_hdr = QHBoxLayout()
        cam_hdr.setContentsMargins(0, 0, 0, 0)
        dot = QLabel("🔴")
        dot.setFont(QFont("Segoe UI", 9))
        dot.setStyleSheet("background: transparent; border: none;")
        cam_hdr.addWidget(dot)

        cam_title = QLabel("NEO OPTICAL SENSOR // LIVE CAMERA FEED")
        cam_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        cam_title.setStyleSheet("color: #00e5ff; letter-spacing: 1px; border: none; background: transparent;")
        cam_hdr.addWidget(cam_title)

        cam_hdr.addStretch()

        badge = QLabel("720P HD • LIVE")
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        badge.setStyleSheet("""
            color: #94a3b8; background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px;
            padding: 2px 8px;
        """)
        cam_hdr.addWidget(badge)

        cam_close_btn = QPushButton("✕ Close Camera")
        cam_close_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        cam_close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cam_close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(244, 63, 94, 0.15);
                color: #fb7185;
                border: 1px solid rgba(244, 63, 94, 0.3);
                border-radius: 8px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background: rgba(244, 63, 94, 0.3);
                color: #ffffff;
            }
        """)
        cam_close_btn.clicked.connect(self.camera_close_requested.emit)
        cam_hdr.addWidget(cam_close_btn)
        cam_card_v.addLayout(cam_hdr)

        self.cam_live_lbl = QLabel("ACQUIRING OPTICAL FEED...")
        self.cam_live_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cam_live_lbl.setStyleSheet("""
            QLabel {
                background: #05070a;
                color: #64748b;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
            }
        """)
        self.cam_live_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cam_card_v.addWidget(self.cam_live_lbl, stretch=1)

        self.camera_box = QHBoxLayout()
        self.camera_box.addStretch()
        self.camera_box.addWidget(self.camera_card)
        self.camera_box.addStretch()
        vbox.addLayout(self.camera_box)
        self.camera_card.hide()

        # Live Transcript Subtitle Pill (You in Green, NEO in White)
        vbox.addSpacing(14)
        self._trans_box = QHBoxLayout()
        self._trans_box.addStretch()
        self.transcript_pill = NeoLiveTranscriptWidget()
        self._trans_box.addWidget(self.transcript_pill)
        self._trans_box.addStretch()
        vbox.addLayout(self._trans_box)

        # 3. Omni Prompt Capsule Bar
        vbox.addSpacing(16)
        bar_container = QHBoxLayout()
        bar_container.addStretch()

        self.input_frame = QFrame()
        self.input_frame.setFixedHeight(54)
        self.input_frame.setFixedWidth(640)
        self.input_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(18, 24, 38, 0.90);
                border: 1px solid rgba(120, 160, 255, 0.25);
                border-radius: 27px;
            }}
        """)
        bar_lay = QHBoxLayout(self.input_frame)
        bar_lay.setContentsMargins(12, 0, 10, 0)
        bar_lay.setSpacing(10)

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(30, 30)
        plus_btn.setFont(QFont("Segoe UI", 15))
        plus_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        plus_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #8e9eb5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 15px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }
        """)
        plus_btn.clicked.connect(self.attach_requested.emit)
        bar_lay.addWidget(plus_btn)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Ask NEO anything...")
        self.input_edit.setFont(font_text(10, QFont.Weight.Normal))
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

        self.cc_btn = QPushButton("CC")
        self.cc_btn.setFixedSize(32, 28)
        self.cc_btn.setFont(font_text(8, QFont.Weight.Bold))
        self.cc_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cc_btn.setToolTip("Toggle Live Subtitles (You in Green, NEO in White)")
        self._cc_enabled = True
        self._update_cc_style()
        self.cc_btn.clicked.connect(self.toggle_subtitles)
        bar_lay.addWidget(self.cc_btn)

        self.mic_btn = QPushButton("🎙")
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
                color: #60a5fa;
            }
        """)
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        bar_lay.addWidget(self.mic_btn)

        send_btn = QPushButton("➤")
        send_btn.setFixedSize(36, 32)
        send_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SEND_BTN_BG};
                color: #080a10;
                border: none;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background: #a4bde5;
            }}
        """)
        send_btn.clicked.connect(self._submit)
        bar_lay.addWidget(send_btn)

        bar_container.addWidget(self.input_frame)
        bar_container.addStretch()
        vbox.addLayout(bar_container)

        # 4. Quick Action Pill Cards
        self.cards_widget = QWidget()
        cards_widget_lay = QVBoxLayout(self.cards_widget)
        cards_widget_lay.setContentsMargins(0, 0, 0, 0)
        cards_widget_lay.setSpacing(0)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        cards_row.addStretch()

        actions = [
            ("📅", "Plan My Day"),
            ("🎯", "Focus Mode"),
            ("📚", "Research"),
            ("</>", "Write Code"),
            ("✦", "Brainstorm"),
        ]

        for icon, title in actions:
            card = self._create_action_card(icon, title)
            cards_row.addWidget(card)

        cards_row.addStretch()
        cards_widget_lay.addLayout(cards_row)
        vbox.addSpacing(22)
        vbox.addWidget(self.cards_widget)
        vbox.addStretch()

    def show_camera_stream(self, active: bool):
        """Toggle camera view inside the Home menu."""
        if active:
            if hasattr(self, "eclipse"):
                self.eclipse.hide()
            if hasattr(self, "title_lbl"):
                self.title_lbl.hide()
            if hasattr(self, "sub1"):
                self.sub1.hide()
            if hasattr(self, "sub2"):
                self.sub2.hide()
            if hasattr(self, "cards_widget"):
                self.cards_widget.hide()
            if hasattr(self, "camera_card"):
                self.camera_card.show()
                self.cam_live_lbl.setText("ACQUIRING OPTICAL FEED...")
        else:
            if hasattr(self, "camera_card"):
                self.camera_card.hide()
                self.cam_live_lbl.clear()
            if hasattr(self, "eclipse"):
                self.eclipse.show()
            if hasattr(self, "title_lbl"):
                self.title_lbl.show()
            if hasattr(self, "sub1"):
                self.sub1.show()
            if hasattr(self, "sub2"):
                self.sub2.show()
            if hasattr(self, "cards_widget"):
                self.cards_widget.show()

    def update_camera_frame(self, data: bytes):
        """Display live JPEG frame on Home menu camera card."""
        if not hasattr(self, "cam_live_lbl") or not hasattr(self, "camera_card"):
            return
        if not self.camera_card.isVisible():
            return
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w = max(10, self.cam_live_lbl.width())
            h = max(10, self.cam_live_lbl.height())
            self.cam_live_lbl.setPixmap(
                px.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _create_action_card(self, icon: str, title: str) -> QFrame:
        card = QFrame()
        card.setFixedSize(108, 64)
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
            }}
            QFrame:hover {{
                background: rgba(28, 38, 58, 0.85);
                border-color: rgba(96, 165, 250, 0.35);
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 10, 6, 10)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icn = QLabel(icon)
        icn.setFont(QFont("Segoe UI", 11))
        icn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icn.setStyleSheet("border: none; background: transparent; color: #8e9eb5;")
        lay.addWidget(icn)

        lbl = QLabel(title)
        lbl.setFont(font_text(8, QFont.Weight.Medium))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        lay.addWidget(lbl)

        card.mousePressEvent = lambda e, t=title: self._on_card_clicked(t)
        return card

    def set_user_name(self, name: str):
        self.user_name = name or "Boss"
        hr = datetime.now().hour
        period = "Morning" if hr < 12 else ("Afternoon" if hr < 17 else "Evening")
        if hasattr(self, "title_lbl"):
            self.title_lbl.setText(f"Good {period}, {self.user_name}.")

    def _on_card_clicked(self, title: str):
        if title == "Plan My Day":
            self.command_submitted.emit("Plan my day and review my schedule, Boss")
        elif title == "Focus Mode":
            self.command_submitted.emit("Activate focus mode and play calm focus vibe")
        elif title == "Research":
            self.input_edit.setText("Research ")
            self.input_edit.setFocus()
        elif title == "Write Code":
            self.input_edit.setText("Write Python code for ")
            self.input_edit.setFocus()
        elif title == "Brainstorm":
            self.input_edit.setText("Brainstorm ideas for ")
            self.input_edit.setFocus()

    def toggle_subtitles(self):
        self._cc_enabled = not self._cc_enabled
        self.transcript_pill.setVisible(self._cc_enabled)
        self._update_cc_style()

    def _update_cc_style(self):
        if getattr(self, "_cc_enabled", True):
            self.cc_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(96, 165, 250, 0.18);
                    color: #60a5fa;
                    border: 1px solid rgba(96, 165, 250, 0.38);
                    border-radius: 12px;
                }
                QPushButton:hover {
                    background: rgba(96, 165, 250, 0.28);
                }
            """)
        else:
            self.cc_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #526078;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }
                QPushButton:hover {
                    color: #8e9eb5;
                }
            """)

    def set_speech(self, speaker: str, text: str):
        if hasattr(self, "transcript_pill") and self.transcript_pill is not None:
            self.transcript_pill.set_speech(speaker, text)

    def _submit(self):
        text = self.input_edit.text().strip()
        if text:
            self.command_submitted.emit(text)
            self.input_edit.clear()

    def set_audio_level(self, level: float):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.set_audio_level(level)

    def push_visemes(self, frames, hop: float, at: float):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.push_visemes(frames, hop, at)

    def set_state(self, state: str):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.set_state(state)

    def set_emotion(self, emotion: str, duration: float = 0.0):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.set_emotion(emotion, duration)

    def glance(self, dx: float, dy: float, hold: float = 1.1):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.glance(dx, dy, hold)

    def set_mic_muted(self, muted: bool):
        if hasattr(self, "eclipse") and self.eclipse is not None:
            self.eclipse.set_muted(muted)
        if muted:
            self.mic_btn.setText("🔇")
            self.mic_btn.setToolTip("Microphone is MUTED (Click to unmute or press [F4])")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(244, 63, 94, 0.22);
                    color: #fb7185;
                    border: 1px solid rgba(244, 63, 94, 0.45);
                    border-radius: 15px;
                }
                QPushButton:hover {
                    background: rgba(244, 63, 94, 0.35);
                    color: #ffffff;
                }
            """)
        else:
            self.mic_btn.setText("🎙")
            self.mic_btn.setToolTip("Microphone is ACTIVE (Click to mute or press [F4])")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #60a5fa;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(96, 165, 250, 0.15);
                    border-radius: 15px;
                }
            """)

    def set_audio_level(self, level: float):
        self.eclipse.set_audio_level(level)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Layer 1: Back mountain ridge
        m_back = QPainterPath()
        m_back.moveTo(0, h)
        m_back.lineTo(0, h - 110)
        m_back.cubicTo(w * 0.2, h - 145, w * 0.4, h - 85, w * 0.55, h - 105)
        m_back.cubicTo(w * 0.7, h - 125, w * 0.85, h - 75, w, h - 95)
        m_back.lineTo(w, h)
        m_back.closeSubpath()

        g_back = QLinearGradient(0, h - 150, 0, h)
        g_back.setColorAt(0.0, QColor(22, 32, 50, 160))
        g_back.setColorAt(0.6, QColor(14, 20, 32, 220))
        g_back.setColorAt(1.0, QColor(8, 11, 18, 255))
        p.setBrush(QBrush(g_back))
        p.setPen(QPen(QColor(70, 100, 160, 50), 1.0))
        p.drawPath(m_back)

        # Layer 2: Front dune ridge
        m_path = QPainterPath()
        m_path.moveTo(0, h)
        m_path.lineTo(0, h - 75)
        m_path.cubicTo(w * 0.22, h - 105, w * 0.35, h - 50, w * 0.5, h - 70)
        m_path.cubicTo(w * 0.65, h - 90, w * 0.82, h - 40, w, h - 65)
        m_path.lineTo(w, h)
        m_path.closeSubpath()

        m_grad = QLinearGradient(0, h - 110, 0, h)
        m_grad.setColorAt(0.0, QColor(16, 24, 38, 230))
        m_grad.setColorAt(0.5, QColor(10, 15, 24, 250))
        m_grad.setColorAt(1.0, QColor(6, 8, 14, 255))
        p.setBrush(QBrush(m_grad))
        p.setPen(QPen(QColor(60, 90, 140, 60), 1.0))
        p.drawPath(m_path)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  5. INTERACTIVE FUNCTIONAL VIEWS (Tasks, Notes, Projects, Knowledge, Files)
# ─────────────────────────────────────────────────────────────────────────────
_TASKS_FILE = Path(__file__).resolve().parent.parent / "memory" / "tasks.json"

TASK_CATEGORY_COLORS = {
    "Academic": ("🎓 ACADEMIC", "#a78bfa", "rgba(167, 139, 250, 0.14)"),
    "Dev":      ("💻 DEV",      "#38bdf8", "rgba(56, 189, 248, 0.14)"),
    "SIH":      ("🏆 SIH",      "#f59e0b", "rgba(245, 158, 11, 0.14)"),
    "Security": ("🛡️ SEC",      "#34d399", "rgba(52, 211, 153, 0.14)"),
    "Ops":      ("⚡ OPS",      "#f43f5e", "rgba(244, 63, 94, 0.14)"),
    "General":  ("📋 TASK",     "#94a3b8", "rgba(148, 163, 184, 0.14)"),
}

TASK_PRIORITY_META = {
    "High":   ("🔴 CRITICAL", "#f43f5e", "rgba(244, 63, 94, 0.16)", "#f43f5e"),
    "Medium": ("🟡 MEDIUM",   "#f59e0b", "rgba(245, 158, 11, 0.16)", "#f59e0b"),
    "Low":    ("🔵 ROUTINE",  "#38bdf8", "rgba(56, 189, 248, 0.16)", "#38bdf8"),
}


class TaskEditDialog(QDialog):
    """Obsidian modal dialog to edit an objective's details and notes."""

    def __init__(self, task: dict, parent=None):
        super().__init__(parent)
        self.task = dict(task)
        self.setWindowTitle("Edit Objective // NEO")
        self.setFixedSize(480, 360)
        self.setStyleSheet("""
            QDialog {
                background: #090e1a;
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 12px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        hdr = QLabel("✎ Edit Tactical Objective")
        hdr.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #38bdf8; border: none; background: transparent;")
        lay.addWidget(hdr)

        self.title_edit = QLineEdit(self.task.get("title", ""))
        self.title_edit.setFont(QFont("Segoe UI", 10))
        self.title_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.05); color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #38bdf8; }
        """)
        lay.addWidget(self.title_edit)

        selectors = QHBoxLayout()
        selectors.setSpacing(8)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["🎓 Academic", "💻 Dev", "🏆 SIH", "🛡️ Security", "⚡ Ops", "📋 General"])
        curr_cat = self.task.get("category", "General")
        for i in range(self.cat_combo.count()):
            if curr_cat in self.cat_combo.itemText(i):
                self.cat_combo.setCurrentIndex(i)
                break
        selectors.addWidget(self.cat_combo)

        self.prio_combo = QComboBox()
        self.prio_combo.addItems(["🔴 High", "🟡 Med", "🔵 Low"])
        curr_prio = self.task.get("priority", "Medium")
        for i in range(self.prio_combo.count()):
            if curr_prio in self.prio_combo.itemText(i):
                self.prio_combo.setCurrentIndex(i)
                break
        selectors.addWidget(self.prio_combo)

        self.due_combo = QComboBox()
        self.due_combo.addItems(["📅 Today", "📅 Tomorrow", "📅 This Week", "📅 Later"])
        curr_due = self.task.get("due_date", "Today")
        for i in range(self.due_combo.count()):
            if curr_due in self.due_combo.itemText(i):
                self.due_combo.setCurrentIndex(i)
                break
        selectors.addWidget(self.due_combo)

        for cb in (self.cat_combo, self.prio_combo, self.due_combo):
            cb.setStyleSheet("""
                QComboBox {
                    background: rgba(255, 255, 255, 0.05); color: #cbd5e1;
                    border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 4px 8px;
                }
                QComboBox QAbstractItemView { background: #0b1120; color: #f8fafc; }
            """)
        lay.addLayout(selectors)

        notes_lbl = QLabel("Tactical Notes / Execution Context:")
        notes_lbl.setFont(QFont("Segoe UI", 8))
        notes_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        lay.addWidget(notes_lbl)

        self.notes_edit = QTextEdit(self.task.get("notes", ""))
        self.notes_edit.setFont(QFont("Consolas", 8))
        self.notes_edit.setStyleSheet("""
            QTextEdit {
                background: rgba(14, 20, 34, 0.95); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px;
            }
        """)
        lay.addWidget(self.notes_edit, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_b = QPushButton("Cancel")
        cancel_b.setFont(QFont("Segoe UI", 8))
        cancel_b.setStyleSheet("QPushButton { background: transparent; color: #94a3b8; border: none; padding: 6px 12px; } QPushButton:hover { color: #fff; }")
        cancel_b.clicked.connect(self.reject)
        btn_row.addWidget(cancel_b)

        save_b = QPushButton("Save Changes")
        save_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        save_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_b.setStyleSheet("""
            QPushButton {
                background: #00e5ff; color: #070b14;
                border: none; border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        save_b.clicked.connect(self._save)
        btn_row.addWidget(save_b)
        lay.addLayout(btn_row)

    def _save(self):
        self.task["title"] = self.title_edit.text().strip() or self.task.get("title", "")
        cat_t = self.cat_combo.currentText()
        if "Academic" in cat_t: self.task["category"] = "Academic"
        elif "Dev" in cat_t: self.task["category"] = "Dev"
        elif "SIH" in cat_t: self.task["category"] = "SIH"
        elif "Security" in cat_t: self.task["category"] = "Security"
        elif "Ops" in cat_t: self.task["category"] = "Ops"
        else: self.task["category"] = "General"

        prio_t = self.prio_combo.currentText()
        self.task["priority"] = "High" if "High" in prio_t else ("Low" if "Low" in prio_t else "Medium")
        self.task["due_date"] = self.due_combo.currentText().replace("📅 ", "").strip()
        self.task["notes"] = self.notes_edit.toPlainText().strip()
        self.accept()


class NeoTaskCard(QFrame):
    """High-tech obsidian task card with priority edge, tags, and AI execution action."""

    def __init__(self, task: dict, on_toggle: Callable, on_delete: Callable, on_execute: Callable, on_edit: Callable, parent=None):
        super().__init__(parent)
        self.task = task
        self.on_toggle = on_toggle
        self.on_delete = on_delete
        self.on_execute = on_execute
        self.on_edit = on_edit

        done = bool(task.get("done", False))
        priority = task.get("priority", "Medium")
        category = task.get("category", "General")
        due = task.get("due_date", "Today")
        notes = task.get("notes", "").strip()

        p_name, p_fg, p_bg, p_border = TASK_PRIORITY_META.get(priority, TASK_PRIORITY_META["Medium"])
        c_name, c_fg, c_bg = TASK_CATEGORY_COLORS.get(category, TASK_CATEGORY_COLORS["General"])

        has_notes = bool(notes)
        self.setFixedHeight(58 if has_notes else 50)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(14, 20, 34, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-left: 4px solid {p_border if not done else '#334155'};
                border-radius: 10px;
            }}
            QFrame:hover {{
                border-color: rgba(56, 189, 248, 0.35);
                background: rgba(18, 26, 44, 0.96);
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(12)

        # Checkbox
        self.cb = QCheckBox()
        self.cb.setChecked(done)
        self.cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 19px; height: 19px; border-radius: 5px;
                border: 1.5px solid rgba(255, 255, 255, 0.25);
                background: #0d1322;
            }
            QCheckBox::indicator:hover {
                border-color: #38bdf8;
                background: rgba(56, 189, 248, 0.12);
            }
            QCheckBox::indicator:checked {
                background: #00e5ff;
                border-color: #00e5ff;
            }
        """)
        self.cb.toggled.connect(self._handle_toggle)
        lay.addWidget(self.cb)

        # Title & Notes Column
        col = QVBoxLayout()
        col.setContentsMargins(0, 2, 0, 2)
        col.setSpacing(2)

        self.title_lbl = QLabel(task.get("title", ""))
        self.title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium if not done else QFont.Weight.Normal))
        self._apply_title_style(done)
        col.addWidget(self.title_lbl)

        if has_notes:
            note_lbl = QLabel(f"↳ {notes[:75]}" + ("..." if len(notes) > 75 else ""))
            note_lbl.setFont(QFont("Segoe UI", 7))
            note_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
            col.addWidget(note_lbl)

        lay.addLayout(col, stretch=1)

        # Category Tag Pill
        cat_badge = QLabel(c_name)
        cat_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        cat_badge.setStyleSheet(f"""
            color: {c_fg}; background: {c_bg};
            border: 1px solid {c_fg}44; border-radius: 5px;
            padding: 2px 7px;
        """)
        lay.addWidget(cat_badge)

        # Priority Tag Pill
        prio_badge = QLabel(p_name)
        prio_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        prio_badge.setStyleSheet(f"""
            color: {p_fg}; background: {p_bg};
            border: 1px solid {p_fg}44; border-radius: 5px;
            padding: 2px 7px;
        """)
        lay.addWidget(prio_badge)

        # Due Date Pill
        due_badge = QLabel(f"📅 {due}")
        due_badge.setFont(QFont("Segoe UI", 7))
        is_urgent = ("today" in due.lower() or "now" in due.lower()) and not done and priority == "High"
        due_color = "#f43f5e" if is_urgent else "#94a3b8"
        due_badge.setStyleSheet(f"""
            color: {due_color}; background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px;
            padding: 2px 7px;
        """)
        lay.addWidget(due_badge)

        # "⚡ EXECUTE WITH NEO" Tactical Dispatch Button
        if not done:
            exec_btn = QPushButton("⚡ EXECUTE")
            exec_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            exec_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            exec_btn.setFixedHeight(24)
            exec_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(56, 189, 248, 0.12);
                    color: #38bdf8;
                    border: 1px solid rgba(56, 189, 248, 0.35);
                    border-radius: 5px;
                    padding: 0 8px;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.3);
                    color: #ffffff;
                    border-color: #38bdf8;
                }
            """)
            exec_btn.clicked.connect(lambda: self.on_execute(self.task))
            lay.addWidget(exec_btn)

        # Edit button
        edit_btn = QPushButton("✎")
        edit_btn.setToolTip("Edit Objective Details")
        edit_btn.setFixedSize(24, 24)
        edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        edit_btn.setStyleSheet("QPushButton { color: #64748b; border: none; background: transparent; font-size: 11px; } QPushButton:hover { color: #38bdf8; }")
        edit_btn.clicked.connect(lambda: self.on_edit(self.task))
        lay.addWidget(edit_btn)

        # Delete Action
        del_btn = QPushButton("✕")
        del_btn.setToolTip("Delete Objective")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet("""
            QPushButton {
                color: #475569;
                border: none;
                background: transparent;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #f43f5e;
            }
        """)
        del_btn.clicked.connect(lambda: self.on_delete(self.task))
        lay.addWidget(del_btn)

    def _apply_title_style(self, done: bool):
        if done:
            self.title_lbl.setStyleSheet("color: #64748b; text-decoration: line-through; background: transparent; border: none;")
        else:
            self.title_lbl.setStyleSheet("color: #f8fafc; text-decoration: none; background: transparent; border: none;")

    def _handle_toggle(self, checked: bool):
        self.task["done"] = checked
        if checked:
            self.task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._apply_title_style(checked)
        self.on_toggle(self.task)


class NeoTasksView(QWidget):
    """
    Military-grade Tactical Task & Execution Engine for NEO.
    Features persistent database, live KPI HUD, multi-filter segmentation,
    quick-add objective capsule, and autonomous AI task execution.
    """
    task_action_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        self.active_status_filter = "ALL"
        self.active_category_filter = "All"
        self.search_keyword = ""

        # Load persisted task database (with guarantee of default population)
        self.tasks_data = self._load_tasks()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 16, 32, 16)
        lay.setSpacing(12)

        # 1. Header with Tactical Sync & Clean Actions
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        t_icn = QLabel("☑")
        t_icn.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_icn.setStyleSheet("color: #00e5ff; border: none; background: transparent;")
        hdr.addWidget(t_icn)

        t_lbl = QLabel("Task & Tactical Execution Engine")
        t_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; letter-spacing: -0.3px;")
        hdr.addWidget(t_lbl)
        hdr.addStretch()

        def _action_btn(text: str, bg: str, fg: str, border: str, hover_bg: str, cb):
            b = QPushButton(text)
            b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(28)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {fg};
                    border: 1px solid {border}; border-radius: 6px;
                    padding: 0 12px; letter-spacing: 0.4px;
                }}
                QPushButton:hover {{
                    background: {hover_bg}; color: #ffffff;
                }}
            """)
            b.clicked.connect(cb)
            return b

        hdr.addWidget(_action_btn(
            "⚡ SYNC WITH NEO", "rgba(56, 189, 248, 0.15)", "#38bdf8", "rgba(56, 189, 248, 0.35)", "rgba(56, 189, 248, 0.3)",
            lambda: self._on_sync_requested()
        ))

        hdr.addWidget(_action_btn(
            "🤖 AI ARCHITECT", "rgba(167, 139, 250, 0.15)", "#a78bfa", "rgba(167, 139, 250, 0.35)", "rgba(167, 139, 250, 0.3)",
            lambda: self._on_architect_requested()
        ))

        hdr.addWidget(_action_btn(
            "↺ RESTORE SAMPLE TASKS", "rgba(52, 211, 153, 0.12)", "#34d399", "rgba(52, 211, 153, 0.3)", "rgba(52, 211, 153, 0.25)",
            self._restore_default_tasks
        ))

        hdr.addWidget(_action_btn(
            "🧹 CLEAR DONE", "rgba(255, 255, 255, 0.05)", "#94a3b8", "rgba(255, 255, 255, 0.08)", "rgba(244, 63, 94, 0.2)",
            self._clear_completed_tasks
        ))

        lay.addLayout(hdr)

        # 2. Tactical KPI HUD & Velocity Strip
        self.kpi_frame = QFrame()
        self.kpi_frame.setFixedHeight(66)
        self.kpi_frame.setStyleSheet("""
            QFrame {
                background: rgba(14, 20, 34, 0.88);
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 12px;
            }
        """)
        kpi_lay = QVBoxLayout(self.kpi_frame)
        kpi_lay.setContentsMargins(16, 8, 16, 8)
        kpi_lay.setSpacing(6)

        kpi_top = QHBoxLayout()
        self.kpi_velocity_lbl = QLabel("VELOCITY: 0% · 0/0 OBJECTIVES COMPLETE")
        self.kpi_velocity_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.kpi_velocity_lbl.setStyleSheet("color: #38bdf8; border: none; background: transparent; letter-spacing: 0.5px;")
        kpi_top.addWidget(self.kpi_velocity_lbl)
        kpi_top.addStretch()

        self.badge_high = QLabel("🔴 0 Critical")
        self.badge_today = QLabel("📅 0 Today")
        self.badge_done = QLabel("✓ 0 Done")
        self.badge_pending = QLabel("⏳ 0 Pending")

        for b_lbl in (self.badge_high, self.badge_today, self.badge_done, self.badge_pending):
            b_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            b_lbl.setStyleSheet("""
                color: #cbd5e1; background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px;
                padding: 2px 7px;
            """)
            kpi_top.addWidget(b_lbl)

        kpi_lay.addLayout(kpi_top)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #38bdf8);
                border-radius: 3px;
            }
        """)
        kpi_lay.addWidget(self.progress_bar)

        lay.addWidget(self.kpi_frame)

        # 3. Executive Quick-Add Capsule Bar
        self.add_frame = QFrame()
        self.add_frame.setFixedHeight(48)
        self.add_frame.setStyleSheet("""
            QFrame {
                background: rgba(13, 19, 33, 0.96);
                border: 1.5px solid rgba(56, 189, 248, 0.28);
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: rgba(56, 189, 248, 0.45);
            }
        """)
        add_lay = QHBoxLayout(self.add_frame)
        add_lay.setContentsMargins(10, 0, 10, 0)
        add_lay.setSpacing(8)

        self.new_task_edit = QLineEdit()
        self.new_task_edit.setPlaceholderText("Deploy a new tactical objective or action item...")
        self.new_task_edit.setFont(QFont("Segoe UI", 9))
        self.new_task_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {TEXT_WHITE}; padding: 0 4px;
            }}
            QLineEdit::placeholder {{ color: #64748b; }}
        """)
        self.new_task_edit.returnPressed.connect(self._add_task)
        add_lay.addWidget(self.new_task_edit, stretch=1)

        # Category ComboBox
        self.cat_combo = QComboBox()
        self.cat_combo.addItems(["🎓 Academic", "💻 Dev", "🏆 SIH", "🛡️ Security", "⚡ Ops", "📋 General"])
        self._style_combo(self.cat_combo, 115)
        add_lay.addWidget(self.cat_combo)

        # Priority ComboBox
        self.prio_combo = QComboBox()
        self.prio_combo.addItems(["🔴 High", "🟡 Med", "🔵 Low"])
        self._style_combo(self.prio_combo, 90)
        add_lay.addWidget(self.prio_combo)

        # Due Date ComboBox
        self.due_combo = QComboBox()
        self.due_combo.addItems(["📅 Today", "📅 Tomorrow", "📅 This Week", "📅 Later"])
        self._style_combo(self.due_combo, 105)
        add_lay.addWidget(self.due_combo)

        add_b = QPushButton("+ ADD OBJECTIVE")
        add_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        add_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_b.setFixedHeight(30)
        add_b.setStyleSheet("""
            QPushButton {
                background: #00e5ff; color: #080a10;
                border: none; border-radius: 6px; padding: 0 12px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        add_b.clicked.connect(self._add_task)
        add_lay.addWidget(add_b)

        lay.addWidget(self.add_frame)

        # 4. Multi-Filter Tabs & Category Segmentation
        # Row A: Status Filters & Search
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.status_btn_group = QButtonGroup(self)
        self.status_btns = {}
        statuses = [
            ("ALL", "All"),
            ("IN_PROGRESS", "⏳ In Progress"),
            ("COMPLETED", "✓ Completed"),
            ("HIGH_PRIO", "🔴 High Priority"),
            ("TODAY", "📅 Today"),
        ]
        for key, label in statuses:
            b = QPushButton(label)
            b.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(26)
            b.setCheckable(True)
            if key == "ALL":
                b.setChecked(True)
            self._update_tab_style(b, b.isChecked())
            b.clicked.connect(lambda _, k=key: self._on_status_filter_changed(k))
            self.status_btn_group.addButton(b)
            self.status_btns[key] = b
            filter_row.addWidget(b)

        filter_row.addSpacing(10)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter objectives...")
        self.search_input.setFont(QFont("Segoe UI", 8))
        self.search_input.setFixedWidth(160)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.05); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;
                padding: 3px 8px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self.search_input)

        filter_row.addStretch()
        lay.addLayout(filter_row)

        # Row B: Domain Category Filter Pills
        cat_filter_row = QHBoxLayout()
        cat_filter_row.setSpacing(6)

        self.cat_btns = {}
        cats = [
            ("All", "All Domains"),
            ("Academic", "🎓 Academic"),
            ("Dev", "💻 Dev"),
            ("SIH", "🏆 SIH Hackathon"),
            ("Security", "🛡️ CyberSec"),
            ("Ops", "⚡ Daily Ops"),
            ("General", "📋 General"),
        ]
        for key, label in cats:
            b = QPushButton(label)
            b.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(24)
            b.setCheckable(True)
            if key == "All":
                b.setChecked(True)
            self._update_pill_style(b, b.isChecked())
            b.clicked.connect(lambda _, k=key: self._on_category_filter_changed(k))
            self.cat_btns[key] = b
            cat_filter_row.addWidget(b)

        cat_filter_row.addStretch()
        lay.addLayout(cat_filter_row)

        # 5. Tasks List Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 165, 250, 0.25); border-radius: 3px; min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(56, 189, 248, 0.6);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.tasks_container = QWidget()
        self.tasks_container.setStyleSheet("background: transparent;")
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 4, 6, 4)
        self.tasks_layout.setSpacing(8)
        self.tasks_layout.addStretch()

        self.scroll.setWidget(self.tasks_container)
        lay.addWidget(self.scroll, stretch=1)

        # Floating Toast Pill
        self.toast_lbl = QLabel(self)
        self.toast_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.toast_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_lbl.setStyleSheet("""
            QLabel {
                background: rgba(14, 165, 233, 0.95);
                color: #070b14;
                border: 1px solid #38bdf8;
                border-radius: 12px;
                padding: 4px 18px;
            }
        """)
        self.toast_lbl.setVisible(False)

        # Initial render
        self._refresh_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_toast()

    def _reposition_toast(self):
        w = self.toast_lbl.sizeHint().width() + 20
        h = 28
        self.toast_lbl.setGeometry((self.width() - w) // 2, 12, w, h)

    def _show_toast(self, text: str):
        self.toast_lbl.setText(text)
        self.toast_lbl.adjustSize()
        self._reposition_toast()
        self.toast_lbl.show()
        self.toast_lbl.raise_()
        QTimer.singleShot(2500, self.toast_lbl.hide)

    def _style_combo(self, combo: QComboBox, width: int):
        combo.setFixedWidth(width)
        combo.setFont(QFont("Segoe UI", 8))
        combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.05);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 4px 8px;
            }
            QComboBox:hover {
                border-color: rgba(56, 189, 248, 0.4);
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #0d1322;
                color: #f8fafc;
                border: 1px solid rgba(56, 189, 248, 0.3);
                selection-background-color: rgba(56, 189, 248, 0.2);
            }
        """)

    def _update_tab_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(56, 189, 248, 0.2);
                    color: #38bdf8;
                    border: 1px solid #38bdf8;
                    border-radius: 6px;
                    padding: 0 10px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.08);
                    color: #ffffff;
                }
            """)

    def _update_pill_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(52, 211, 153, 0.18);
                    color: #34d399;
                    border: 1px solid #34d399;
                    border-radius: 12px;
                    padding: 0 10px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.03);
                    color: #64748b;
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 12px;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.06);
                    color: #cbd5e1;
                }
            """)

    # ─────────────────────────────────────────────────────────────────────────
    # Storage & State
    # ─────────────────────────────────────────────────────────────────────────
    def _get_default_tasks(self) -> list[dict]:
        return [
            {
                "id": "task_1",
                "title": "Review Financial Management exam syllabus and formulas",
                "category": "Academic",
                "priority": "High",
                "due_date": "Today",
                "done": True,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "notes": "Chapter 4 ratio analysis and capital budgeting cash flows",
            },
            {
                "id": "task_2",
                "title": "Smart India Hackathon (SIH) team sync & architecture check",
                "category": "SIH",
                "priority": "High",
                "due_date": "Today",
                "done": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "notes": "Verify backend API endpoints, latency and database schemas",
            },
            {
                "id": "task_3",
                "title": "Autonomous desktop Spotify playback visual controller verification",
                "category": "Dev",
                "priority": "Medium",
                "due_date": "Today",
                "done": True,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "notes": "Confirm token refresh and media session hooks",
            },
            {
                "id": "task_4",
                "title": "Backup and archive NEO local configurations",
                "category": "Ops",
                "priority": "Low",
                "due_date": "This Week",
                "done": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "notes": "Archive .env, api_keys.json, and speech profiles",
            },
            {
                "id": "task_5",
                "title": "Check unread VIP emails from GitHub and Stripe",
                "category": "Ops",
                "priority": "Medium",
                "due_date": "Today",
                "done": False,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "notes": "Check webhook failure logs and security alerts",
            },
        ]

    def _load_tasks(self) -> list[dict]:
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _TASKS_FILE.exists():
            try:
                with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "tasks" in data:
                        tasks = data.get("tasks", [])
                        if tasks:
                            return tasks
            except Exception:
                pass

        default_tasks = self._get_default_tasks()
        self._write_tasks(default_tasks)
        return default_tasks

    def _write_tasks(self, tasks: list[dict]):
        try:
            with open(_TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump({"tasks": tasks}, f, indent=2)
        except Exception:
            pass

    def _save_tasks(self):
        self._write_tasks(self.tasks_data)

    def _restore_default_tasks(self):
        self.tasks_data = self._get_default_tasks()
        self._save_tasks()
        self._refresh_ui()
        self._show_toast("↺ Restored default sample objectives!")

    # ─────────────────────────────────────────────────────────────────────────
    # UI Refresh & Filtering
    # ─────────────────────────────────────────────────────────────────────────
    def _refresh_ui(self):
        # 1. Update KPI stats
        total = len(self.tasks_data)
        done_cnt = sum(1 for t in self.tasks_data if t.get("done"))
        pending_cnt = total - done_cnt
        high_cnt = sum(1 for t in self.tasks_data if t.get("priority") == "High" and not t.get("done"))
        today_cnt = sum(1 for t in self.tasks_data if "today" in str(t.get("due_date", "")).lower() and not t.get("done"))

        pct = int((done_cnt / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.kpi_velocity_lbl.setText(f"VELOCITY: {pct}% · {done_cnt}/{total} OBJECTIVES COMPLETE")

        self.badge_high.setText(f"🔴 {high_cnt} Critical")
        self.badge_today.setText(f"📅 {today_cnt} Today")
        self.badge_done.setText(f"✓ {done_cnt} Done")
        self.badge_pending.setText(f"⏳ {pending_cnt} Pending")

        # 2. Clear current task cards (keep bottom stretch intact)
        for i in reversed(range(self.tasks_layout.count())):
            item = self.tasks_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                self.tasks_layout.removeWidget(w)
                w.deleteLater()

        # 3. Filter tasks
        filtered = []
        kw = self.search_keyword.lower().strip()
        for t in self.tasks_data:
            t_done = bool(t.get("done", False))
            t_prio = str(t.get("priority", "Medium"))
            t_cat = str(t.get("category", "General"))
            t_due = str(t.get("due_date", "")).lower()
            t_title = str(t.get("title", "")).lower()
            t_notes = str(t.get("notes", "")).lower()

            # Status filter
            if self.active_status_filter == "IN_PROGRESS" and t_done:
                continue
            elif self.active_status_filter == "COMPLETED" and not t_done:
                continue
            elif self.active_status_filter == "HIGH_PRIO" and (t_prio != "High" or t_done):
                continue
            elif self.active_status_filter == "TODAY" and ("today" not in t_due or t_done):
                continue

            # Category filter
            if self.active_category_filter != "All" and t_cat != self.active_category_filter:
                continue

            # Keyword filter
            if kw and (kw not in t_title and kw not in t_notes):
                continue

            filtered.append(t)

        # 4. Render cards or empty state
        if not filtered:
            empty_card = QFrame()
            empty_card.setFixedHeight(100)
            empty_card.setStyleSheet("""
                QFrame {
                    background: rgba(14, 20, 34, 0.6);
                    border: 1px dashed rgba(255, 255, 255, 0.12);
                    border-radius: 12px;
                }
            """)
            e_lay = QVBoxLayout(empty_card)
            e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.setSpacing(6)

            e_lbl = QLabel("No objectives found matching current filter.")
            e_lbl.setFont(QFont("Segoe UI", 9))
            e_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
            e_lay.addWidget(e_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

            restore_btn = QPushButton("⚡ Restore Sample Objectives")
            restore_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            restore_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            restore_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(56, 189, 248, 0.15);
                    color: #38bdf8;
                    border: 1px solid rgba(56, 189, 248, 0.35);
                    border-radius: 6px;
                    padding: 3px 12px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.3);
                    color: #ffffff;
                }
            """)
            restore_btn.clicked.connect(self._restore_default_tasks)
            e_lay.addWidget(restore_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            self.tasks_layout.insertWidget(0, empty_card)
        else:
            for idx, task in enumerate(filtered):
                card = NeoTaskCard(
                    task=task,
                    on_toggle=self._on_task_toggled,
                    on_delete=self._on_task_deleted,
                    on_execute=self._on_task_executed,
                    on_edit=self._on_task_edited,
                    parent=self.tasks_container,
                )
                self.tasks_layout.insertWidget(idx, card)

    # ─────────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ─────────────────────────────────────────────────────────────────────────
    def _on_status_filter_changed(self, key: str):
        self.active_status_filter = key
        for k, b in self.status_btns.items():
            self._update_tab_style(b, k == key)
        self._refresh_ui()

    def _on_category_filter_changed(self, key: str):
        self.active_category_filter = key
        for k, b in self.cat_btns.items():
            self._update_pill_style(b, k == key)
        self._refresh_ui()

    def _on_search_changed(self, text: str):
        self.search_keyword = text
        self._refresh_ui()

    def _on_task_toggled(self, task: dict):
        self._save_tasks()
        self._refresh_ui()

    def _on_task_deleted(self, task: dict):
        self.tasks_data = [t for t in self.tasks_data if t.get("id") != task.get("id")]
        self._save_tasks()
        self._refresh_ui()
        self._show_toast("✓ Objective deleted.")

    def _on_task_edited(self, task: dict):
        dlg = TaskEditDialog(task, self)
        if dlg.exec():
            # Update task in memory
            for i, t in enumerate(self.tasks_data):
                if t.get("id") == task.get("id"):
                    self.tasks_data[i] = dlg.task
                    break
            self._save_tasks()
            self._refresh_ui()
            self._show_toast("✓ Objective updated.")

    def _on_task_executed(self, task: dict):
        title = task.get("title", "")
        category = task.get("category", "")
        cmd = f"Execute objective: '{title}' (Category: {category}). Formulate an actionable execution blueprint, generate required code or materials, and assist me in completing it, Boss."
        self._show_toast(f"⚡ Dispatched to NEO: '{title[:28]}...'")
        self.task_action_triggered.emit(cmd)

    def _on_sync_requested(self):
        self._show_toast("⚡ Syncing objectives with NEO...")
        self.task_action_triggered.emit("Sync and prioritize my current tasks from the Task Engine, Boss. Give me the top 3 tactical actions to focus on now.")

    def _on_architect_requested(self):
        self._show_toast("🤖 Engaging AI Task Architect...")
        self.task_action_triggered.emit("Review my highest priority pending task, decompose it into 4 actionable technical subtasks, and prepare an execution outline, Boss.")

    def _reset_input_style(self):
        self.new_task_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {TEXT_WHITE}; padding: 0 4px;
            }}
            QLineEdit::placeholder {{ color: #64748b; }}
        """)
        self.new_task_edit.setPlaceholderText("Deploy a new tactical objective or action item...")

    def _add_task(self):
        title = self.new_task_edit.text().strip()
        if not title:
            self.new_task_edit.setStyleSheet("""
                QLineEdit {
                    background: rgba(244, 63, 94, 0.14);
                    border: 1.5px solid #f43f5e;
                    border-radius: 6px;
                    color: #ffffff;
                    padding: 0 6px;
                }
            """)
            self.new_task_edit.setPlaceholderText("⚠️ Please enter an objective title first...")
            self.new_task_edit.setFocus()
            QTimer.singleShot(1500, self._reset_input_style)
            return

        cat_raw = self.cat_combo.currentText()
        category = "General"
        if "Academic" in cat_raw: category = "Academic"
        elif "Dev" in cat_raw: category = "Dev"
        elif "SIH" in cat_raw: category = "SIH"
        elif "Security" in cat_raw: category = "Security"
        elif "Ops" in cat_raw: category = "Ops"

        prio_raw = self.prio_combo.currentText()
        priority = "High" if "High" in prio_raw else ("Low" if "Low" in prio_raw else "Medium")

        due_raw = self.due_combo.currentText()
        due = due_raw.replace("📅 ", "").strip()

        new_t = {
            "id": f"task_{int(time.time() * 1000)}",
            "title": title,
            "category": category,
            "priority": priority,
            "due_date": due,
            "done": False,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "notes": "",
        }

        self.tasks_data.insert(0, new_t)
        self._save_tasks()
        self.new_task_edit.clear()
        self._reset_input_style()
        self._show_toast(f"✓ Objective deployed: '{title[:28]}...'")
        self._refresh_ui()

    def _clear_completed_tasks(self):
        self.tasks_data = [t for t in self.tasks_data if not t.get("done")]
        self._save_tasks()
        self._refresh_ui()
        self._show_toast("✓ Completed objectives cleared.")


class NeoNotesView(QWidget):
    """Memory & Scratchpad quick notes interface."""
    note_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        n_lbl = QLabel("📄  Memory Notes & Scratchpad")
        n_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        n_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(n_lbl)
        hdr.addStretch()

        save_b = QPushButton("💾 SAVE TO LONG-TERM MEMORY")
        save_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        save_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_b.setStyleSheet("""
            QPushButton {
                background: rgba(96, 165, 250, 0.15); color: #60a5fa;
                border: 1px solid rgba(96, 165, 250, 0.3); border-radius: 6px; padding: 6px 14px;
            }
            QPushButton:hover { background: rgba(96, 165, 250, 0.3); color: #fff; }
        """)
        save_b.clicked.connect(self._save_note)
        hdr.addWidget(save_b)
        lay.addLayout(hdr)

        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("Write notes, research snippets, or memory facts for NEO here...")
        self.note_edit.setFont(QFont("Segoe UI", 10))
        self.note_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #101624; color: {TEXT_WHITE};
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px;
            }}
        """)
        lay.addWidget(self.note_edit, stretch=1)

        self.status_lbl = QLabel("Notes are automatically indexed and recallable by NEO via memory search.")
        self.status_lbl.setFont(QFont("Segoe UI", 8))
        self.status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        lay.addWidget(self.status_lbl)

    def _save_note(self):
        text = self.note_edit.toPlainText().strip()
        if text:
            self.note_saved.emit(f"Remember this memory note: {text}")
            self.status_lbl.setText(f"✓ Saved note ({len(text)} characters) to NEO long-term memory at {datetime.now().strftime('%H:%M:%S')}")
            self.status_lbl.setStyleSheet("color: #34d399; border: none; background: transparent;")


class NeoProjectsView(QWidget):
    """Active Workspace Explorer."""
    file_open_requested = pyqtSignal(str)

    def __init__(self, workspace_path: str = ".", parent=None):
        super().__init__(parent)
        self.workspace_path = Path(workspace_path)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        p_lbl = QLabel("🗂  Workspace & Project Explorer")
        p_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        p_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(p_lbl)
        hdr.addStretch()

        branch_lbl = QLabel("🌿 git: main [clean]")
        branch_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        branch_lbl.setStyleSheet("color: #34d399; background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 6px; padding: 4px 8px;")
        hdr.addWidget(branch_lbl)
        lay.addLayout(hdr)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: #101624; color: {TEXT_WHITE};
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 8px;
            }}
            QListWidget::item {{
                padding: 8px 12px; border-radius: 6px;
            }}
            QListWidget::item:hover {{
                background: rgba(96, 165, 250, 0.12); color: #60a5fa;
            }}
        """)
        self.list_widget.itemDoubleClicked.connect(lambda item: self.file_open_requested.emit(item.text()))
        lay.addWidget(self.list_widget, stretch=1)
        self._load_files()

    def _load_files(self):
        self.list_widget.clear()
        try:
            if self.workspace_path.exists():
                for p in sorted(self.workspace_path.iterdir()):
                    if not p.name.startswith("."):
                        icn = "📁" if p.is_dir() else "📄"
                        self.list_widget.addItem(f"{icn}  {p.name}")
        except Exception:
            pass


class NeoKnowledgeView(QWidget):
    """Semantic Knowledge & Memory Search interface."""
    search_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        k_lbl = QLabel("📚  NEO Knowledge & Neural Memory")
        k_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        k_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(k_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        s_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search knowledge memories, user preferences, past interactions...")
        self.search_edit.setFont(QFont("Segoe UI", 10))
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #101624; color: {TEXT_WHITE};
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 8px 12px;
            }}
        """)
        self.search_edit.returnPressed.connect(self._search)
        s_row.addWidget(self.search_edit, stretch=1)

        search_b = QPushButton("SEARCH")
        search_b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        search_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_b.setStyleSheet(f"""
            QPushButton {{
                background: {SEND_BTN_BG}; color: #080a10;
                border: none; border-radius: 8px; padding: 8px 16px;
            }}
            QPushButton:hover {{ background: #a4bde5; }}
        """)
        search_b.clicked.connect(self._search)
        s_row.addWidget(search_b)
        lay.addLayout(s_row)

        self.results_edit = QTextEdit()
        self.results_edit.setReadOnly(True)
        self.results_edit.setFont(QFont("Consolas", 9))
        self.results_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #101624; color: #a5b4fc;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px;
            }}
        """)
        lay.addWidget(self.results_edit, stretch=1)
        self._load_recent()

    def _load_recent(self):
        try:
            from memory.memory_manager import format_memory_for_prompt
            mem = format_memory_for_prompt()
            self.results_edit.setText(mem or "No long-term memories stored yet.")
        except Exception as e:
            self.results_edit.setText(f"Knowledge memory loaded: {e}")

    def _search(self):
        q = self.search_edit.text().strip()
        if q:
            self.search_triggered.emit(f"Search your memory for: {q}")
            try:
                from memory.memory_manager import search_memory
                hits = search_memory(q)
                if hits:
                    self.results_edit.setText(f"--- Search Results for '{q}' ---\n\n" + "\n\n".join(hits))
                else:
                    self.results_edit.setText(f"No direct matches found in local memory for '{q}'. Asking NEO...")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# NEO NEURAL ONBOARDING & CALIBRATION OVERLAY (Modern Glassmorphic Setup)
# ═══════════════════════════════════════════════════════════════════════════════

class _PillOption(QPushButton):
    """Interactive pill button with selected state styling."""
    def __init__(self, text: str, value: str = None, parent=None):
        super().__init__(text, parent)
        self.value = value if value is not None else text
        self.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(34)
        self.setCheckable(True)
        self._update_style()
        self.toggled.connect(self._update_style)

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(0, 229, 255, 0.16);
                    color: #ffffff;
                    border: 1.5px solid #00e5ff;
                    border-radius: 17px;
                    padding: 4px 14px;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04);
                    color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 17px;
                    padding: 4px 14px;
                }
                QPushButton:hover {
                    background: rgba(56, 189, 248, 0.08);
                    border-color: rgba(56, 189, 248, 0.35);
                    color: #e2e8f0;
                }
            """)

class _PillGroup:
    """Manages single-selection among a group of _PillOption buttons."""
    def __init__(self):
        self.pills: list[_PillOption] = []
        self._selected_val: str = ""

    def add(self, pill: _PillOption):
        self.pills.append(pill)
        pill.clicked.connect(lambda _, p=pill: self._on_clicked(p))

    def _on_clicked(self, clicked_pill: _PillOption):
        for p in self.pills:
            p.setChecked(p is clicked_pill)
        self._selected_val = clicked_pill.value

    def selected_value(self) -> str:
        for p in self.pills:
            if p.isChecked():
                return p.value
        return self._selected_val

    def set_selected_value(self, val: str):
        self._selected_val = val
        matched = False
        for p in self.pills:
            is_match = (p.value.lower() == val.lower() or val.lower() in p.value.lower())
            p.setChecked(is_match)
            if is_match:
                matched = True
        if not matched and self.pills:
            self.pills[0].setChecked(True)
            self._selected_val = self.pills[0].value

class _PersonaCard(QFrame):
    """Clickable personality matrix card with icon, title, badge, and description."""
    clicked = pyqtSignal(object)

    def __init__(self, key: str, icon: str, title: str, badge: str, desc: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.is_selected = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(120)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Header row: icon + title + badge
        h_row = QHBoxLayout()
        h_row.setSpacing(8)

        self.title_lbl = QLabel(f"{icon}  {title}")
        self.title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        h_row.addWidget(self.title_lbl)

        h_row.addStretch(1)

        self.badge_lbl = QLabel(badge)
        self.badge_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        h_row.addWidget(self.badge_lbl)
        lay.addLayout(h_row)

        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setFont(QFont("Segoe UI", 9))
        lay.addWidget(self.desc_lbl)

        self._update_style()

    def mousePressEvent(self, event):
        self.clicked.emit(self)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_style()

    def _update_style(self):
        if self.is_selected:
            self.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(0, 229, 255, 0.16),
                        stop:1 rgba(37, 99, 235, 0.12));
                    border: 1.5px solid #00e5ff;
                    border-radius: 12px;
                }
            """)
            self.title_lbl.setStyleSheet("color: #ffffff; border: none; background: transparent;")
            self.badge_lbl.setStyleSheet("""
                color: #00e5ff;
                background: rgba(0, 229, 255, 0.20);
                border: 1px solid rgba(0, 229, 255, 0.4);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            self.desc_lbl.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        else:
            self.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }
                QFrame:hover {
                    background: rgba(56, 189, 248, 0.06);
                    border-color: rgba(56, 189, 248, 0.3);
                }
            """)
            self.title_lbl.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
            self.badge_lbl.setStyleSheet("""
                color: #64748b;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            self.desc_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")

class _PersonaCardGroup:
    def __init__(self):
        self.cards: list[_PersonaCard] = []
        self._selected_key: str = ""

    def add(self, card: _PersonaCard):
        self.cards.append(card)
        card.clicked.connect(self._on_clicked)

    def _on_clicked(self, clicked_card: _PersonaCard):
        for c in self.cards:
            c.set_selected(c is clicked_card)
        self._selected_key = clicked_card.key

    def selected_value(self) -> str:
        for c in self.cards:
            if c.is_selected:
                return c.key
        return self._selected_key or "Tactical JARVIS"

    def set_selected_value(self, val: str):
        self._selected_key = val
        matched = False
        for c in self.cards:
            is_match = (c.key.lower() == val.lower())
            c.set_selected(is_match)
            if is_match:
                matched = True
        if not matched and self.cards:
            self.cards[0].set_selected(True)
            self._selected_key = self.cards[0].key

class NeoCalibrationOverlay(QFrame):
    """
    Modern glassmorphic first-configuration & onboarding popup window for new users.
    Learns about user identity, craft, peak flow rhythm, behavioral personality directives,
    feedback preferences, priority goal, and Gemini Neural API key.
    """
    _OW = 740
    _OH = 580
    done = pyqtSignal(object)  # Emits profile dict

    def __init__(self, parent=None):
        super().__init__(parent)
        import webbrowser
        self.setObjectName("NeoCalibrationOverlay")
        self.setFixedSize(self._OW, self._OH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#NeoCalibrationOverlay {
                background: rgba(13, 17, 28, 0.96);
                border: 1.5px solid rgba(56, 189, 248, 0.32);
                border-radius: 16px;
            }
        """)

        # Main Layout
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(28, 20, 28, 20)
        root_lay.setSpacing(12)

        # 1. Top Header Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        icon_lbl = QLabel("⬡")
        icon_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        icon_lbl.setStyleSheet("color: #00e5ff; background: transparent;")
        top_bar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("NEO // NEURAL ONBOARDING & CALIBRATION")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 0.5px;")
        title_col.addWidget(title_lbl)

        sub_lbl = QLabel("Calibrating your personal AI assistant's memory, persona & behavior directives.")
        sub_lbl.setFont(QFont("Segoe UI", 8))
        sub_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
        title_col.addWidget(sub_lbl)
        top_bar.addLayout(title_col)

        top_bar.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFont(QFont("Segoe UI", 11))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                color: #64748b; background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08); border-radius: 14px;
            }
            QPushButton:hover { color: #ffffff; background: rgba(239, 68, 68, 0.25); border-color: #ef4444; }
        """)
        close_btn.clicked.connect(self.hide)
        top_bar.addWidget(close_btn)
        root_lay.addLayout(top_bar)

        # 2. Step Progress Tabs Bar
        step_bar = QHBoxLayout()
        step_bar.setSpacing(8)
        self.step_btns: list[QPushButton] = []
        for i, (num, label) in enumerate([("1", "Operator Profile"), ("2", "Behavioral Matrix"), ("3", "Core & Mission")]):
            s_btn = QPushButton(f"  {num}  {label}  ")
            s_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            s_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            s_btn.setFixedHeight(28)
            s_btn.clicked.connect(lambda _, idx=i: self._go_step(idx))
            step_bar.addWidget(s_btn)
            self.step_btns.append(s_btn)
        root_lay.addLayout(step_bar)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.08);")
        root_lay.addWidget(sep)

        # 3. Stacked Step Pages
        self.stack = QStackedWidget()
        root_lay.addWidget(self.stack, stretch=1)

        # Build Pages
        self._build_page1_profile()
        self._build_page2_behavior()
        self._build_page3_mission_core()

        # Load existing config if available
        self._load_existing_state()
        self._go_step(0)

    def _go_step(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.step_btns):
            if i == idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(0, 229, 255, 0.18);
                        color: #00e5ff;
                        border: 1.5px solid #00e5ff;
                        border-radius: 14px;
                    }
                """)
            elif i < idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(34, 197, 94, 0.12);
                        color: #4ade80;
                        border: 1px solid rgba(34, 197, 94, 0.35);
                        border-radius: 14px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.03);
                        color: #64748b;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        border-radius: 14px;
                    }
                """)

    def _build_page1_profile(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(12)

        # Q1: Name
        q1_lbl = QLabel("What should NEO call you?")
        q1_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        q1_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
        lay.addWidget(q1_lbl)

        n_row = QHBoxLayout()
        n_row.setSpacing(8)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Fayid, Boss, Commander...")
        self.name_input.setFont(QFont("Segoe UI", 10))
        self.name_input.setFixedHeight(34)
        self.name_input.setStyleSheet("""
            QLineEdit {
                background: #111726; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 4px 10px;
            }
            QLineEdit:focus { border: 1.5px solid #00e5ff; }
        """)
        n_row.addWidget(self.name_input, stretch=1)

        # Quick chips
        for tag in ["Fayid", "Boss", "Chief", "Commander"]:
            tb = QPushButton(tag)
            tb.setFont(QFont("Segoe UI", 8))
            tb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            tb.setFixedHeight(30)
            tb.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 15px; padding: 2px 10px;
                }
                QPushButton:hover { background: rgba(0, 229, 255, 0.1); color: #00e5ff; border-color: #00e5ff; }
            """)
            tb.clicked.connect(lambda _, t=tag: self.name_input.setText(t))
            n_row.addWidget(tb)
        lay.addLayout(n_row)

        lay.addSpacing(4)

        # Q2: Role / Superpower
        q2_lbl = QLabel("What is your superpower or craft?")
        q2_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        q2_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
        lay.addWidget(q2_lbl)

        r_row = QHBoxLayout()
        r_row.setSpacing(8)
        self.role_pills = _PillGroup()
        for r_name in [
            "💻 AI / Software Engineer",
            "🚀 Startup Founder",
            "🎓 Student / Researcher",
            "🎨 Designer / Creator",
            "⚡ Polymath",
        ]:
            pill = _PillOption(r_name)
            r_row.addWidget(pill)
            self.role_pills.add(pill)
        lay.addLayout(r_row)

        lay.addSpacing(4)

        # Q3: Peak Flow Rhythm
        q3_lbl = QLabel("When does your brain hit peak flow?")
        q3_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        q3_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
        lay.addWidget(q3_lbl)

        flow_grid = QGridLayout()
        flow_grid.setSpacing(8)
        self.rhythm_pills = _PillGroup()
        rhythms = [
            ("🌙 Night Owl", "Midnight code, deep work & coffee"),
            ("🌅 Dawn Raider", "Early morning clarity before the world wakes"),
            ("⚡ Hyper-Burst", "Sporadic strikes of intense genius"),
            ("☕ Steady Flow", "Continuous all-day focus & automation"),
        ]
        for idx, (title, sub) in enumerate(rhythms):
            pill = _PillOption(f"{title}  —  {sub}", value=title)
            flow_grid.addWidget(pill, idx // 2, idx % 2)
            self.rhythm_pills.add(pill)
        lay.addLayout(flow_grid)

        lay.addStretch(1)

        # Bottom Next button
        b_row = QHBoxLayout()
        b_row.addStretch(1)
        next_b = QPushButton("Next: Behavioral Matrix  →")
        next_b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        next_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        next_b.setFixedHeight(36)
        next_b.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00e5ff);
                color: #080c14; font-weight: bold; border: none; border-radius: 8px; padding: 6px 20px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        next_b.clicked.connect(lambda: self._go_step(1))
        b_row.addWidget(next_b)
        lay.addLayout(b_row)

        self.stack.addWidget(page)

    def _build_page2_behavior(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        top_info = QLabel("Choose how NEO should behave and speak to you:")
        top_info.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        top_info.setStyleSheet("color: #e2e8f0; background: transparent;")
        lay.addWidget(top_info)

        # 4 Persona Cards in 2x2 grid
        card_grid = QGridLayout()
        card_grid.setSpacing(8)
        self.persona_group = _PersonaCardGroup()

        personas = [
            (
                "Tactical JARVIS", "⚡", "Tactical JARVIS", "DEFAULT // SPEED",
                "Razor-sharp, ultra-concise (1-2 sentences), zero fluff. Pure speed, immediate action execution."
            ),
            (
                "Brilliant Co-Pilot", "💡", "Brilliant Co-Pilot", "DEEP THINKER",
                "Senior engineering sparring partner. Proactive architectural advice and deep thinking."
            ),
            (
                "Chill Companion", "☕", "Chill Companion", "WITTY & WARM",
                "Conversational, clever, supportive tech-savvy best friend with personality and humor."
            ),
            (
                "Hyper-Focus Guardian", "🛡️", "Hyper-Focus Guardian", "DISCIPLINE",
                "Crushes procrastination, guards your deep work time, keeps you accountable to your daily goals."
            ),
        ]

        for i, (k, icon, title, badge, desc) in enumerate(personas):
            card = _PersonaCard(k, icon, title, badge, desc)
            card_grid.addWidget(card, i // 2, i % 2)
            self.persona_group.add(card)
        lay.addLayout(card_grid)

        # Feedback preference
        f_lbl = QLabel("How do you prefer your feedback?")
        f_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        f_lbl.setStyleSheet("color: #cbd5e1; background: transparent;")
        lay.addWidget(f_lbl)

        f_row = QHBoxLayout()
        f_row.setSpacing(8)
        self.feedback_pills = _PillGroup()
        for f_text in [
            "🎯 Brutally Honest (Tell me straight)",
            "🌱 Constructive & Encouraging",
            "🤔 Socratic (Challenge my assumptions)",
        ]:
            pill = _PillOption(f_text)
            f_row.addWidget(pill)
            self.feedback_pills.add(pill)
        lay.addLayout(f_row)

        # Voice Core preference
        v_lbl = QLabel("Preferred Neural Voice Core:")
        v_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        v_lbl.setStyleSheet("color: #cbd5e1; background: transparent;")
        lay.addWidget(v_lbl)

        v_row = QHBoxLayout()
        v_row.setSpacing(8)
        self.voice_pills = _PillGroup()
        for v_name in ["Aoede (Calm & Elegant)", "Puck (Energetic & Sharp)", "Charon (Deep Gravitas)", "Fenrir (Bold & Powerful)"]:
            pill = _PillOption(v_name, value=v_name.split()[0])
            v_row.addWidget(pill)
            self.voice_pills.add(pill)
        lay.addLayout(v_row)

        lay.addStretch(1)

        # Bottom nav
        b_row = QHBoxLayout()
        back_b = QPushButton("← Back")
        back_b.setFont(QFont("Segoe UI", 9))
        back_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_b.setFixedHeight(34)
        back_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 4px 16px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)
        back_b.clicked.connect(lambda: self._go_step(0))
        b_row.addWidget(back_b)

        b_row.addStretch(1)

        next_b = QPushButton("Next: Core & Mission  →")
        next_b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        next_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        next_b.setFixedHeight(36)
        next_b.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00e5ff);
                color: #080c14; font-weight: bold; border: none; border-radius: 8px; padding: 6px 20px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        next_b.clicked.connect(lambda: self._go_step(2))
        b_row.addWidget(next_b)
        lay.addLayout(b_row)

        self.stack.addWidget(page)

    def _build_page3_mission_core(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        # Q1: Goal / Mission
        g_lbl = QLabel("What is your #1 big goal or focus right now?")
        g_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        g_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
        lay.addWidget(g_lbl)

        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("e.g. Building an autonomous agent, finishing university exams, scaling my startup...")
        self.goal_input.setFont(QFont("Segoe UI", 10))
        self.goal_input.setFixedHeight(34)
        self.goal_input.setStyleSheet("""
            QLineEdit {
                background: #111726; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 4px 10px;
            }
            QLineEdit:focus { border: 1.5px solid #00e5ff; }
        """)
        lay.addWidget(self.goal_input)

        # Suggestion chips
        s_row = QHBoxLayout()
        s_row.setSpacing(6)
        for s_text in ["🤖 Build an AI project", "🎓 Ace university exams", "🚀 Launch my startup", "⚡ Automate my workflow"]:
            sb = QPushButton(s_text)
            sb.setFont(QFont("Segoe UI", 8))
            sb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            sb.setFixedHeight(26)
            sb.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 13px; padding: 2px 8px;
                }
                QPushButton:hover { background: rgba(0, 229, 255, 0.1); color: #00e5ff; border-color: #00e5ff; }
            """)
            sb.clicked.connect(lambda _, t=s_text: self.goal_input.setText(t))
            s_row.addWidget(sb)
        lay.addLayout(s_row)

        lay.addSpacing(6)

        # Q2: Gemini API Key
        k_header = QHBoxLayout()
        k_lbl = QLabel("Gemini Neural API Key:")
        k_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        k_lbl.setStyleSheet("color: #e2e8f0; background: transparent;")
        k_header.addWidget(k_lbl)

        k_header.addStretch(1)

        import webbrowser
        get_key_btn = QPushButton("Get Free API Key at Google AI Studio ↗")
        get_key_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        get_key_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        get_key_btn.setStyleSheet("color: #38bdf8; background: transparent; border: none; text-decoration: underline;")
        get_key_btn.clicked.connect(lambda: webbrowser.open("https://aistudio.google.com/app/apikey"))
        k_header.addWidget(get_key_btn)
        lay.addLayout(k_header)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("AIzaSy...")
        self.key_input.setFont(QFont("Segoe UI", 10))
        self.key_input.setFixedHeight(34)
        self.key_input.setStyleSheet("""
            QLineEdit {
                background: #111726; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 4px 10px;
            }
            QLineEdit:focus { border: 1.5px solid #00e5ff; }
        """)
        key_row.addWidget(self.key_input, stretch=1)

        self.toggle_eye_btn = QPushButton("👁")
        self.toggle_eye_btn.setFixedSize(34, 34)
        self.toggle_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_eye_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px;
            }
            QPushButton:hover { color: #ffffff; background: rgba(255, 255, 255, 0.1); }
        """)
        self.toggle_eye_btn.clicked.connect(self._toggle_key_vis)
        key_row.addWidget(self.toggle_eye_btn)
        lay.addLayout(key_row)

        lay.addSpacing(6)

        # Q3: Host Operating System
        os_lbl = QLabel("Operating System:")
        os_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        os_lbl.setStyleSheet("color: #cbd5e1; background: transparent;")
        lay.addWidget(os_lbl)

        os_row = QHBoxLayout()
        os_row.setSpacing(8)
        self.os_pills = _PillGroup()
        for os_k, os_label in [("windows", "⊞  Windows"), ("mac", "  macOS"), ("linux", "🐧  Linux")]:
            pill = _PillOption(os_label, value=os_k)
            os_row.addWidget(pill)
            self.os_pills.add(pill)
        lay.addLayout(os_row)

        self.error_lbl = QLabel("")
        self.error_lbl.setFont(QFont("Segoe UI", 9))
        self.error_lbl.setStyleSheet("color: #ef4444; background: transparent;")
        lay.addWidget(self.error_lbl)

        lay.addStretch(1)

        # Bottom Finish Actions
        b_row = QHBoxLayout()
        back_b = QPushButton("← Back")
        back_b.setFont(QFont("Segoe UI", 9))
        back_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_b.setFixedHeight(36)
        back_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 4px 16px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)
        back_b.clicked.connect(lambda: self._go_step(1))
        b_row.addWidget(back_b)

        b_row.addStretch(1)

        finish_b = QPushButton("⚡  ESTABLISH NEURAL LINK & INITIALIZE NEO")
        finish_b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        finish_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        finish_b.setFixedHeight(38)
        finish_b.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00e5ff, stop:0.5 #38bdf8, stop:1 #2563eb);
                color: #060911; font-weight: bold; border: none; border-radius: 8px; padding: 6px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #38bdf8, stop:1 #60a5fa);
                color: #000000;
            }
        """)
        finish_b.clicked.connect(self._submit)
        b_row.addWidget(finish_b)
        lay.addLayout(b_row)

        self.stack.addWidget(page)

    def _toggle_key_vis(self):
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_eye_btn.setText("🔒")
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_eye_btn.setText("👁")

    def _load_existing_state(self):
        import platform
        import json
        det = {"darwin": "mac", "windows": "windows"}.get(platform.system().lower(), "linux")
        self.os_pills.set_selected_value(det)

        self.role_pills.set_selected_value("💻 AI / Software Engineer")
        self.rhythm_pills.set_selected_value("🌙 Night Owl")
        self.persona_group.set_selected_value("Tactical JARVIS")
        self.feedback_pills.set_selected_value("🎯 Brutally Honest (Tell me straight)")
        self.voice_pills.set_selected_value("Aoede")

        try:
            cfg_path = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("user_name"):
                    self.name_input.setText(d["user_name"])
                else:
                    self.name_input.setText("Fayid")
                if d.get("gemini_api_key"):
                    self.key_input.setText(d["gemini_api_key"])
                if d.get("personality"):
                    self.persona_group.set_selected_value(d["personality"])
                if d.get("user_role"):
                    self.role_pills.set_selected_value(d["user_role"])
                if d.get("operating_rhythm"):
                    self.rhythm_pills.set_selected_value(d["operating_rhythm"])
                if d.get("feedback_style"):
                    self.feedback_pills.set_selected_value(d["feedback_style"])
                if d.get("voice_name"):
                    self.voice_pills.set_selected_value(d["voice_name"])
                if d.get("current_goal"):
                    self.goal_input.setText(d["current_goal"])
                if d.get("os_system"):
                    self.os_pills.set_selected_value(d["os_system"])
        except Exception:
            self.name_input.setText("Fayid")

    def _submit(self):
        key = self.key_input.text().strip()
        if not key:
            self.error_lbl.setText("⚠️ Please enter a valid Gemini API Key to establish neural link.")
            return

        payload = {
            "gemini_api_key": key,
            "os_system": self.os_pills.selected_value() or "windows",
            "user_name": self.name_input.text().strip() or "Boss",
            "role": self.role_pills.selected_value(),
            "rhythm": self.rhythm_pills.selected_value(),
            "personality": self.persona_group.selected_value(),
            "feedback_style": self.feedback_pills.selected_value(),
            "voice_name": self.voice_pills.selected_value() or "Aoede",
            "current_goal": self.goal_input.text().strip(),
            "onboarding_completed": True,
        }
        self.done.emit(payload)
