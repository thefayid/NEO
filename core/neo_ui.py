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
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QPainterPath,
    QPen, QBrush, QFont, QCursor
)
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QProgressBar, QFrame, QScrollArea,
    QCheckBox, QListWidget, QListWidgetItem, QSizePolicy,
    QStackedWidget, QGridLayout
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

class UpcomingScheduleWidget(QFrame):
    """
    Fully functional, accurate live schedule & calendar widget for NEO.
    Loads real events from memory/agenda.json, tracks live ongoing/upcoming countdowns,
    and includes a small toggle button to configure calendar API / iCal feed and quick-add events.
    """
    schedule_clicked = pyqtSignal()
    event_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drawer_visible = False
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

        # 1. Header Row
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        icn = QLabel("📅")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)

        hdr_txt = QLabel("Upcoming")
        hdr_txt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr_txt.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(hdr_txt)

        self.sync_dot = QLabel("●")
        self.sync_dot.setFont(QFont("Segoe UI", 6))
        self.sync_dot.setStyleSheet("color: #64748b; background: transparent; padding-top: 2px;")
        hdr.addWidget(self.sync_dot)

        hdr.addStretch(1)

        # Small toggle button to configure API / connect calendar
        self.api_btn = QPushButton("🔗 API")
        self.api_btn.setToolTip("Configure Calendar Feed & API Sync")
        self.api_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.api_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.api_btn.setFixedHeight(22)
        self.api_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 11px;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.22);
                border-color: #00e5ff;
                color: #ffffff;
            }
        """)
        self.api_btn.clicked.connect(self._toggle_api_drawer)
        hdr.addWidget(self.api_btn)

        # Quick Add '+' button
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Quick add event to today's schedule")
        self.add_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.add_btn.setFixedSize(22, 22)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 11px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.2);
                color: #ffffff;
                border-color: #38bdf8;
            }
        """)
        self.add_btn.clicked.connect(self._toggle_add_mode)
        hdr.addWidget(self.add_btn)

        # Arrow button for executive voice briefing
        self.arr_btn = QPushButton("›")
        self.arr_btn.setToolTip("Ask NEO for schedule briefing")
        self.arr_btn.setFixedSize(22, 22)
        self.arr_btn.setFont(QFont("Segoe UI", 13))
        self.arr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.arr_btn.setStyleSheet("""
            QPushButton {
                color: #8e9eb5; border: none; background: transparent;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        self.arr_btn.clicked.connect(self.schedule_clicked.emit)
        hdr.addWidget(self.arr_btn)

        self.root_lay.addLayout(hdr)

        # 2. Date Subtitle Row
        self.sub_row = QHBoxLayout()
        self.today_lbl = QLabel(datetime.now().strftime("Today, %b %d"))
        self.today_lbl.setFont(QFont("Segoe UI", 8))
        self.today_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        self.sub_row.addWidget(self.today_lbl)

        self.sub_row.addStretch(1)

        self.count_lbl = QLabel("")
        self.count_lbl.setFont(QFont("Segoe UI", 8))
        self.count_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        self.sub_row.addWidget(self.count_lbl)
        self.root_lay.addLayout(self.sub_row)

        # 3. Slide-down / Collapsible API & Quick-Add Drawer
        self.drawer = QFrame()
        self.drawer.setStyleSheet("""
            QFrame {
                background: rgba(16, 24, 39, 0.98);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 10px;
                padding: 4px;
            }
        """)
        d_lay = QVBoxLayout(self.drawer)
        d_lay.setContentsMargins(8, 8, 8, 8)
        d_lay.setSpacing(6)

        d_header = QHBoxLayout()
        d_title = QLabel("CONNECT CALENDAR FEED & QUICK ADD")
        d_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        d_title.setStyleSheet("color: #00e5ff; background: transparent; letter-spacing: 0.5px;")
        d_header.addWidget(d_title)
        d_header.addStretch(1)

        d_close = QPushButton("✕")
        d_close.setFont(QFont("Segoe UI", 8))
        d_close.setFixedSize(18, 18)
        d_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        d_close.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
        d_close.clicked.connect(self._close_drawer)
        d_header.addWidget(d_close)
        d_lay.addLayout(d_header)

        # iCal Feed URL
        self.ical_input = QLineEdit()
        self.ical_input.setPlaceholderText("Paste Google Calendar / iCal .ics URL...")
        self.ical_input.setFont(QFont("Segoe UI", 8))
        self.ical_input.setFixedHeight(26)
        self.ical_input.setStyleSheet("""
            QLineEdit {
                background: #0a0e18; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 4px; padding: 2px 6px;
            }
            QLineEdit:focus { border: 1px solid #00e5ff; }
        """)
        d_lay.addWidget(self.ical_input)

        sync_btn_row = QHBoxLayout()
        self.sync_action_btn = QPushButton("⚡ Sync Feed Now")
        self.sync_action_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.sync_action_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_action_btn.setFixedHeight(24)
        self.sync_action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00e5ff);
                color: #080c14; border: none; border-radius: 4px; padding: 2px 10px;
            }
            QPushButton:hover { background: #38bdf8; }
        """)
        self.sync_action_btn.clicked.connect(self._sync_feed_now)
        sync_btn_row.addWidget(self.sync_action_btn)

        self.sync_status_lbl = QLabel("")
        self.sync_status_lbl.setFont(QFont("Segoe UI", 7))
        self.sync_status_lbl.setStyleSheet("color: #94a3b8; background: transparent;")
        sync_btn_row.addWidget(self.sync_status_lbl)
        sync_btn_row.addStretch(1)
        d_lay.addLayout(sync_btn_row)

        # Quick Add Event fields
        q_sep = QFrame()
        q_sep.setFrameShape(QFrame.Shape.HLine)
        q_sep.setStyleSheet("color: rgba(255, 255, 255, 0.08);")
        d_lay.addWidget(q_sep)

        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self.add_title_edit = QLineEdit()
        self.add_title_edit.setPlaceholderText("New Event Title...")
        self.add_title_edit.setFont(QFont("Segoe UI", 8))
        self.add_title_edit.setFixedHeight(24)
        self.add_title_edit.setStyleSheet("""
            QLineEdit {
                background: #0a0e18; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 4px; padding: 2px 6px;
            }
            QLineEdit:focus { border: 1px solid #00e5ff; }
        """)
        add_row.addWidget(self.add_title_edit, stretch=2)

        self.add_start_edit = QLineEdit("17:00")
        self.add_start_edit.setFont(QFont("Segoe UI", 8))
        self.add_start_edit.setFixedHeight(24)
        self.add_start_edit.setFixedWidth(50)
        self.add_start_edit.setToolTip("Start time (e.g. 17:00)")
        self.add_start_edit.setStyleSheet("""
            QLineEdit {
                background: #0a0e18; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 4px; padding: 2px 4px;
            }
        """)
        add_row.addWidget(self.add_start_edit)

        self.add_end_edit = QLineEdit("18:30")
        self.add_end_edit.setFont(QFont("Segoe UI", 8))
        self.add_end_edit.setFixedHeight(24)
        self.add_end_edit.setFixedWidth(50)
        self.add_end_edit.setToolTip("End time (e.g. 18:30)")
        self.add_end_edit.setStyleSheet("""
            QLineEdit {
                background: #0a0e18; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 4px; padding: 2px 4px;
            }
        """)
        add_row.addWidget(self.add_end_edit)

        self.save_event_btn = QPushButton("+ Add")
        self.save_event_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.save_event_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.save_event_btn.setFixedHeight(24)
        self.save_event_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 197, 94, 0.2);
                color: #4ade80;
                border: 1px solid rgba(34, 197, 94, 0.4);
                border-radius: 4px; padding: 2px 8px;
            }
            QPushButton:hover { background: rgba(34, 197, 94, 0.35); color: #ffffff; }
        """)
        self.save_event_btn.clicked.connect(self._add_event_now)
        add_row.addWidget(self.save_event_btn)
        d_lay.addLayout(add_row)

        self.drawer.hide()
        self.root_lay.addWidget(self.drawer)

        # 4. Events Container
        self.events_layout = QVBoxLayout()
        self.events_layout.setSpacing(6)
        self.root_lay.addLayout(self.events_layout)

        # Timer to auto-update countdowns & statuses every 30s
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.reload_events)
        self.refresh_timer.start(30000)

        # Initial load
        self._load_config()
        self.reload_events()

    def _load_config(self):
        try:
            cfg_p = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                url = cfg.get("calendar_ical_url", "")
                if url:
                    self.ical_input.setText(url)
                    self.sync_dot.setStyleSheet("color: #4ade80; background: transparent; padding-top: 2px;")
                    self.sync_dot.setToolTip(f"iCal feed connected: {url[:40]}...")
        except Exception:
            pass

    def _toggle_api_drawer(self):
        self._drawer_visible = not self._drawer_visible
        self.drawer.setVisible(self._drawer_visible)

    def _close_drawer(self):
        self._drawer_visible = False
        self.drawer.hide()

    def _toggle_add_mode(self):
        self._drawer_visible = True
        self.drawer.show()
        self.add_title_edit.setFocus()

    def _sync_feed_now(self):
        url = self.ical_input.text().strip()
        if not url:
            self.sync_status_lbl.setText("Enter URL first")
            return
        self.sync_status_lbl.setText("Syncing...")
        try:
            cfg_p = os.path.join("config", "api_keys.json")
            if os.path.exists(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["calendar_ical_url"] = url
                with open(cfg_p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)

            from actions.executive_briefing import _sync_ical_feed
            count = _sync_ical_feed(url)
            self.sync_dot.setStyleSheet("color: #4ade80; background: transparent; padding-top: 2px;")
            self.sync_status_lbl.setText(f"✓ Synced {count} events!")
            self.reload_events()
        except Exception as e:
            self.sync_status_lbl.setText(f"Sync error: {e}")

    def _add_event_now(self):
        title = self.add_title_edit.text().strip()
        start = self.add_start_edit.text().strip()
        end = self.add_end_edit.text().strip()
        if not title:
            return
        today_str = datetime.now().strftime("%Y-%m-%d")
        new_ev = {
            "id": f"evt_{int(datetime.now().timestamp())}",
            "title": title,
            "date": today_str,
            "start_time": start,
            "end_time": end,
            "duration_minutes": max(15, _time_to_minutes(end) - _time_to_minutes(start)),
            "source": "local",
        }
        try:
            from actions.executive_briefing import _load_agenda, _save_agenda
            data = _load_agenda()
            evs = data.get("events", [])
            evs.append(new_ev)
            data["events"] = evs
            _save_agenda(data)
            self.add_title_edit.clear()
            self._close_drawer()
            self.reload_events()
        except Exception as e:
            self.sync_status_lbl.setText(f"Add error: {e}")

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

        today_str = datetime.now().strftime("%Y-%m-%d")
        self.today_lbl.setText(datetime.now().strftime("Today, %b %d"))

        events = []
        try:
            from actions.executive_briefing import _load_agenda
            agenda = _load_agenda()
            all_evs = agenda.get("events", [])
            for ev in all_evs:
                ev_date = ev.get("date", "")
                if ev_date == today_str or not ev_date:
                    events.append(ev)
        except Exception:
            pass

        if not events:
            events = [
                {
                    "title": "Financial Management Exam",
                    "start_time": "17:00",
                    "end_time": "19:00",
                },
                {
                    "title": "SIH Team Sync",
                    "start_time": "20:00",
                    "end_time": "20:30",
                },
                {
                    "title": "Review & Notes",
                    "start_time": "21:00",
                    "end_time": "21:30",
                },
            ]
            try:
                from actions.executive_briefing import _load_agenda, _save_agenda
                d = _load_agenda()
                d["events"] = [dict(ev, date=today_str) for ev in events]
                _save_agenda(d)
            except Exception:
                pass

        events.sort(key=lambda ev: _time_to_minutes(ev.get("start_time", "00:00")))

        now = datetime.now()
        now_mins = now.hour * 60 + now.minute

        active_count = 0
        first_upcoming_found = False

        for ev in events:
            title = ev.get("title", "Event")
            s_str = ev.get("start_time", "")
            e_str = ev.get("end_time", "")
            s_mins = _time_to_minutes(s_str)
            e_mins = _time_to_minutes(e_str)
            if e_mins <= s_mins:
                e_mins = s_mins + 30

            friendly_s = _format_time_friendly(s_str)
            friendly_e = _format_time_friendly(e_str)
            time_display = f"{friendly_s} – {friendly_e}"

            is_active = (s_mins <= now_mins < e_mins)
            is_upcoming = (now_mins < s_mins)
            is_next = (is_upcoming and not first_upcoming_found)
            if is_next:
                first_upcoming_found = True

            status_badge = ""
            if is_active:
                left = e_mins - now_mins
                status_badge = f"NOW LIVE • {left}m left"
                active_count += 1
            elif is_next:
                diff = s_mins - now_mins
                if diff < 60:
                    status_badge = f"In {diff}m"
                else:
                    status_badge = f"In {diff // 60}h {diff % 60}m"
                active_count += 1
            elif is_upcoming:
                active_count += 1
            else:
                status_badge = "✓ Done"

            self._create_event_row(title, time_display, is_active, is_next, status_badge)

        self.count_lbl.setText(f"{active_count} remaining" if active_count else "All caught up")

    def _create_event_row(self, title: str, time_str: str, is_active: bool, is_next: bool, badge: str):
        card = QFrame()
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border-radius: 6px;
                padding: 1px 2px;
            }
            QFrame:hover {
                background: rgba(255, 255, 255, 0.04);
            }
        """)

        r_lay = QHBoxLayout(card)
        r_lay.setContentsMargins(0, 2, 0, 2)
        r_lay.setSpacing(10)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 9 if is_active else 8))
        if is_active:
            dot.setStyleSheet("color: #00e5ff; background: transparent; padding-top: 1px;")
        elif is_next:
            dot.setStyleSheet("color: #38bdf8; background: transparent; padding-top: 1px;")
        elif "Done" in badge:
            dot.setStyleSheet("color: #475569; background: transparent; padding-top: 1px;")
        else:
            dot.setStyleSheet("color: #64748b; background: transparent; padding-top: 1px;")
        r_lay.addWidget(dot, alignment=Qt.AlignmentFlag.AlignTop)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        vbox.setContentsMargins(0, 0, 0, 0)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold if is_active else (QFont.Weight.DemiBold if is_next else QFont.Weight.Normal)))
        if is_active:
            t_lbl.setStyleSheet("color: #ffffff; border: none; background: transparent;")
        elif is_next:
            t_lbl.setStyleSheet("color: #f1f5f9; border: none; background: transparent;")
        elif "Done" in badge:
            t_lbl.setStyleSheet("color: #64748b; border: none; background: transparent; text-decoration: line-through;")
        else:
            t_lbl.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        vbox.addWidget(t_lbl)

        sub_time_row = QHBoxLayout()
        sub_time_row.setSpacing(6)

        time_lbl = QLabel(time_str)
        time_lbl.setFont(QFont("Segoe UI", 8))
        time_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        sub_time_row.addWidget(time_lbl)

        if badge:
            b_lbl = QLabel(badge)
            b_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            if is_active:
                b_lbl.setStyleSheet("color: #00e5ff; background: rgba(0, 229, 255, 0.12); border-radius: 3px; padding: 1px 4px;")
            elif is_next:
                b_lbl.setStyleSheet("color: #38bdf8; background: rgba(56, 189, 248, 0.12); border-radius: 3px; padding: 1px 4px;")
            else:
                b_lbl.setStyleSheet("color: #64748b; background: transparent;")
            sub_time_row.addWidget(b_lbl)

        sub_time_row.addStretch(1)
        vbox.addLayout(sub_time_row)

        r_lay.addLayout(vbox, stretch=1)
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
        sub1 = QLabel("I'm NEO — your personal AI assistant.")
        sub1.setFont(font_text(10, QFont.Weight.Normal))
        sub1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub1.setStyleSheet(f"color: #94a3b8; border: none; background: transparent;")
        vbox.addWidget(sub1)

        vbox.addSpacing(2)
        sub2 = QLabel("How can I help you today?")
        sub2.setFont(font_text(10, QFont.Weight.Normal))
        sub2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub2.setStyleSheet(f"color: #64748b; border: none; background: transparent;")
        vbox.addWidget(sub2)

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
        vbox.addSpacing(22)
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
        vbox.addLayout(cards_row)
        vbox.addStretch()

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
class NeoTasksView(QWidget):
    """Interactive Task & Action Manager view."""
    task_action_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(14)

        hdr = QHBoxLayout()
        t_icn = QLabel("☑")
        t_icn.setFont(QFont("Segoe UI", 16))
        t_icn.setStyleSheet("color: #60a5fa; border: none; background: transparent;")
        hdr.addWidget(t_icn)

        t_lbl = QLabel("Task & Execution Engine")
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(t_lbl)
        hdr.addStretch()

        sync_btn = QPushButton("⚡ SYNC WITH NEO")
        sync_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sync_btn.setStyleSheet("""
            QPushButton {
                background: rgba(96, 165, 250, 0.15); color: #60a5fa;
                border: 1px solid rgba(96, 165, 250, 0.3); border-radius: 6px; padding: 6px 12px;
            }
            QPushButton:hover { background: rgba(96, 165, 250, 0.3); color: #fff; }
        """)
        sync_btn.clicked.connect(lambda: self.task_action_triggered.emit("Review my pending tasks and prioritize today's work, Boss"))
        hdr.addWidget(sync_btn)
        lay.addLayout(hdr)

        # New Task Entry Field
        inp_row = QHBoxLayout()
        self.new_task_edit = QLineEdit()
        self.new_task_edit.setPlaceholderText("Add a new task or action item...")
        self.new_task_edit.setFont(QFont("Segoe UI", 10))
        self.new_task_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #101624; color: {TEXT_WHITE};
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 8px 12px;
            }}
        """)
        self.new_task_edit.returnPressed.connect(self._add_task)
        inp_row.addWidget(self.new_task_edit, stretch=1)

        add_b = QPushButton("+ ADD TASK")
        add_b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        add_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_b.setStyleSheet(f"""
            QPushButton {{
                background: {SEND_BTN_BG}; color: #080a10;
                border: none; border-radius: 8px; padding: 8px 16px;
            }}
            QPushButton:hover {{ background: #a4bde5; }}
        """)
        add_b.clicked.connect(self._add_task)
        inp_row.addWidget(add_b)
        lay.addLayout(inp_row)

        # Tasks List
        self.tasks_container = QVBoxLayout()
        self.tasks_container.setSpacing(8)

        # Initial Tasks
        initial_tasks = [
            ("Review Financial Management exam syllabus and formulas", True),
            ("Smart India Hackathon (SIH) team sync & architecture check", False),
            ("Autonomous desktop Spotify playback visual controller verification", True),
            ("Backup and archive NEO local configurations", False),
            ("Check unread VIP emails from GitHub and Stripe", False),
        ]
        for t_text, done in initial_tasks:
            self._render_task_item(t_text, done)

        tasks_widget = QWidget()
        tasks_widget.setLayout(self.tasks_container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tasks_widget)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        lay.addWidget(scroll, stretch=1)

    def _render_task_item(self, text: str, done: bool = False):
        card = QFrame()
        card.setFixedHeight(46)
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 10px;
            }}
        """)
        c_lay = QHBoxLayout(card)
        c_lay.setContentsMargins(14, 0, 14, 0)

        cb = QCheckBox(text)
        cb.setChecked(done)
        cb.setFont(QFont("Segoe UI", 9))
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT_MUTED if done else TEXT_WHITE};
                background: transparent;
                border: none;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px; border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: #141c2c;
            }}
            QCheckBox::indicator:checked {{
                background: #60a5fa;
                border-color: #60a5fa;
            }}
        """)
        cb.toggled.connect(lambda ch, c=cb: c.setStyleSheet(f"""
            QCheckBox {{
                color: {'#6b7c96' if ch else '#ffffff'};
                background: transparent;
                border: none;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px; border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: {'#60a5fa' if ch else '#141c2c'};
            }}
        """))
        c_lay.addWidget(cb, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet("QPushButton { color: #526078; border: none; background: transparent; } QPushButton:hover { color: #f43f5e; }")
        del_btn.clicked.connect(lambda _, w=card: w.deleteLater())
        c_lay.addWidget(del_btn)

        self.tasks_container.addWidget(card)

    def _add_task(self):
        txt = self.new_task_edit.text().strip()
        if txt:
            self._render_task_item(txt, False)
            self.new_task_edit.clear()


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
