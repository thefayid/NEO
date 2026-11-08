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
    QCheckBox, QListWidget, QListWidgetItem, QSizePolicy
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


class UpcomingScheduleWidget(QFrame):
    """Upcoming events schedule card."""
    schedule_clicked = pyqtSignal()

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
        icn = QLabel("📅")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        hdr_txt = QLabel("Upcoming")
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
        arr_btn.clicked.connect(self.schedule_clicked.emit)
        hdr.addWidget(arr_btn)
        lay.addLayout(hdr)

        today_str = datetime.now().strftime("Today, %b %d")
        sub = QLabel(today_str)
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        lay.addWidget(sub)
        lay.addSpacing(2)

        self._add_event_item(lay, "Financial Management Exam", "5:00 PM – 7:00 PM", active=True)
        self._add_event_item(lay, "SIH Team Sync", "8:00 PM – 8:30 PM", active=False)
        self._add_event_item(lay, "Review & Notes", "9:00 PM – 9:30 PM", active=False)

    def _add_event_item(self, layout, title, time_str, active=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 2, 0, 2)

        dot = QLabel("●")
        dot.setFont(QFont("Segoe UI", 8))
        dot_color = ACCENT_BLUE if active else TEXT_DIM
        dot.setStyleSheet(f"color: {dot_color}; border: none; background: transparent; padding-top: 1px;")
        row.addWidget(dot, alignment=Qt.AlignmentFlag.AlignTop)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        vbox.setContentsMargins(0, 0, 0, 0)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold if active else QFont.Weight.Normal))
        t_color = TEXT_WHITE if active else TEXT_MUTED
        t_lbl.setStyleSheet(f"color: {t_color}; border: none; background: transparent;")
        vbox.addWidget(t_lbl)

        time_lbl = QLabel(time_str)
        time_lbl.setFont(QFont("Segoe UI", 8))
        time_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        vbox.addWidget(time_lbl)

        row.addLayout(vbox)
        row.addStretch()
        layout.addLayout(row)


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
