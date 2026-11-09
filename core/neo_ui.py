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
import re
import time
import json
import subprocess
import webbrowser
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient, QPainterPath,
    QPen, QBrush, QFont, QCursor, QPixmap, QImage, QAction
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTextBrowser, QProgressBar, QFrame, QScrollArea,
    QCheckBox, QListWidget, QListWidgetItem, QSizePolicy,
    QStackedWidget, QGridLayout, QDialog, QComboBox, QButtonGroup, QMenu,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter, QFileDialog
)
import psutil
import random

try:
    from core.avatar import HoloAvatar
except Exception:
    HoloAvatar = None

EMOTION_PALETTES = {
    "listening": (QColor(91, 141, 239), QColor(122, 165, 245), "Listening"),
    "attuned":   (QColor(91, 141, 239), QColor(122, 165, 245), "Listening"),
    "thinking":  (QColor(217, 164, 65), QColor(217, 164, 65), "Thinking..."),
    "speaking":  (QColor(122, 165, 245), QColor(91, 141, 239), "Speaking"),
    "happy":     (QColor(76, 175, 125), QColor(91, 141, 239), "Pleased"),
    "curious":   (QColor(122, 165, 245), QColor(91, 141, 239), "Curious"),
    "empathy":   (QColor(154, 161, 173), QColor(91, 141, 239), "Empathetic"),
    "muted":     (QColor(95, 102, 114), QColor(217, 83, 79),  "Muted"),
}

def _lerp_color(c1: QColor, c2: QColor, factor: float) -> QColor:
    r = int(c1.red() + (c2.red() - c1.red()) * factor)
    g = int(c1.green() + (c2.green() - c1.green()) * factor)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * factor)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * factor)
    return QColor(r, g, b, a)

def font_display(size: int = 24, weight: QFont.Weight = QFont.Weight.Medium) -> QFont:
    """Refined executive typography (Segoe UI Variable Display / Inter)."""
    f = QFont("Segoe UI Variable Display", size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f

def font_text(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal, letter_spacing: float = 0.0) -> QFont:
    """Human-designed body typography with precision tracking."""
    f = QFont("Segoe UI Variable Text", size)
    f.setWeight(weight)
    if letter_spacing > 0.0:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f

# ── Base Surfaces & Steel Blue Design System ──────────────────────────────────
BG_OBSIDIAN    = "#0E1013"   # Cool graphite background (avoids OLED/LCD harsh contrast)
SIDEBAR_BG     = "#14171C"   # Surface 1 (panels, sidebar)
CARD_BG        = "#1B1F26"   # Surface 2 (cards, inputs)
CARD_BORDER    = "#262B34"   # 1px subtle border / divider
CARD_HOVER     = "#222731"   # Hover state
NAV_ACTIVE_BG  = "#222731"   # Surface 2 active state
TEXT_WHITE     = "#E6E8EC"   # Primary text (avoids glare of pure #FFFFFF)
TEXT_MUTED     = "#9AA1AD"   # Secondary text
TEXT_DIM       = "#5F6672"   # Disabled / hint text

# Signature Single Accent: Steel Blue
ACCENT_PRIMARY = "#5B8DEF"   # Trustworthy, Windows-native Steel Blue
ACCENT_HOVER   = "#7AA5F5"   # Softer hover variant
ACCENT_PRESSED = "#4376D6"   # Pressed / active variant
ACCENT_BLUE    = "#5B8DEF"
ACCENT_CYAN    = "#5B8DEF"
SEND_BTN_BG    = "#5B8DEF"

# Semantic Colours (desaturated)
SEMANTIC_SUCCESS = "#4CAF7D"
SEMANTIC_WARNING = "#D9A441"
SEMANTIC_ERROR   = "#D9534F"
SEMANTIC_INFO    = "#5B8DEF"

CURRENT_NEO_THEME = "dark"

def set_neo_ui_theme(mode: str) -> None:
    """Dynamically update global styling tokens in core.neo_ui for dark/white themes."""
    global CURRENT_NEO_THEME
    global BG_OBSIDIAN, SIDEBAR_BG, CARD_BG, CARD_BORDER, CARD_HOVER, NAV_ACTIVE_BG
    global TEXT_WHITE, TEXT_MUTED, TEXT_DIM, ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_PRESSED
    global ACCENT_BLUE, ACCENT_CYAN, SEND_BTN_BG

    is_white = str(mode or "dark").lower().strip() in ("white", "light")
    CURRENT_NEO_THEME = "white" if is_white else "dark"
    if is_white:
        BG_OBSIDIAN    = "#F5F6F8"   # Crisp light background
        SIDEBAR_BG     = "#FFFFFF"   # Surface 1
        CARD_BG        = "#FFFFFF"   # Surface 2
        CARD_BORDER    = "#DFE2E7"   # 1px border
        CARD_HOVER     = "#EBEDF2"   # Hover
        NAV_ACTIVE_BG  = "#EBEDF2"   # Active navigation item
        TEXT_WHITE     = "#1A1D23"   # Primary text (charcoal, high contrast)
        TEXT_MUTED     = "#5F6672"   # Secondary text
        TEXT_DIM       = "#8B949E"   # Disabled / hint
        ACCENT_PRIMARY = "#3F6FD1"   # Deep steel blue for high contrast on white
        ACCENT_HOVER   = "#5B8DEF"
        ACCENT_PRESSED = "#2B58B4"
        ACCENT_BLUE    = "#3F6FD1"
        ACCENT_CYAN    = "#3F6FD1"
        SEND_BTN_BG    = "#3F6FD1"
    else:
        BG_OBSIDIAN    = "#0E1013"   # Cool graphite background
        SIDEBAR_BG     = "#14171C"   # Surface 1
        CARD_BG        = "#1B1F26"   # Surface 2
        CARD_BORDER    = "#262B34"   # 1px subtle divider
        CARD_HOVER     = "#222731"   # Hover
        NAV_ACTIVE_BG  = "#222731"   # Active navigation item
        TEXT_WHITE     = "#E6E8EC"   # Primary text (soft off-white)
        TEXT_MUTED     = "#9AA1AD"   # Secondary text
        TEXT_DIM       = "#5F6672"   # Disabled / hint
        ACCENT_PRIMARY = "#5B8DEF"   # Signature steel blue
        ACCENT_HOVER   = "#7AA5F5"
        ACCENT_PRESSED = "#4376D6"
        ACCENT_BLUE    = "#5B8DEF"
        ACCENT_CYAN    = "#5B8DEF"
        SEND_BTN_BG    = "#5B8DEF"


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
        ring_col = QColor(255, 255, 255, 14) if CURRENT_NEO_THEME == "dark" else QColor(38, 43, 52, 28)
        p.setPen(QPen(ring_col, 1.0))
        p.drawEllipse(circ_rect)

        # Outer rim glow
        arc_pen_outer = QPen(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 75 if CURRENT_NEO_THEME == "dark" else 45), 7.0)
        p.setPen(arc_pen_outer)
        p.drawArc(circ_rect, 25 * 16, 130 * 16)

        # Mid radiant rim
        arc_pen_mid = QPen(QColor(self.cur_acc.red(), self.cur_acc.green(), self.cur_acc.blue(), 145 if CURRENT_NEO_THEME == "dark" else 180), 3.5)
        p.setPen(arc_pen_mid)
        p.drawArc(circ_rect, 32 * 16, 116 * 16)

        # Core rim highlight
        core_rim_col = QColor(245, 250, 255, 250) if CURRENT_NEO_THEME == "dark" else self.cur_pri
        arc_pen_core = QPen(core_rim_col, 1.8)
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
            avatar_back = QColor(14, 16, 19) if CURRENT_NEO_THEME == "dark" else QColor(245, 246, 248)
            self.avatar.paint(p, cx, head_cy, head_r, self.cur_pri, self.cur_acc, avatar_back)

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
            top_wave_col = QColor(255, 255, 255, 240) if CURRENT_NEO_THEME == "dark" else self.cur_pri
            grad.setColorAt(0.0, top_wave_col)
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
        if CURRENT_NEO_THEME == "dark":
            p.setBrush(QBrush(QColor(15, 23, 42, 160)))
            p.setPen(QPen(QColor(self.cur_pri.red(), self.cur_pri.green(), self.cur_pri.blue(), 42), 1.0))
        else:
            p.setBrush(QBrush(QColor(255, 255, 255, 240)))
            p.setPen(QPen(QColor(223, 226, 231, 240), 1.0))
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
        pill_text_col = QColor(226, 232, 240, 240) if CURRENT_NEO_THEME == "dark" else QColor(26, 29, 35, 240)
        p.setPen(QPen(pill_text_col))
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
                border-radius: 8px;
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
                background: rgba(91, 141, 239, 0.16);
                color: {ACCENT_BLUE};
                border: 1px solid rgba(91, 141, 239, 0.35);
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: rgba(91, 141, 239, 0.32);
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
                border-radius: 8px;
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
                background: {CARD_BORDER};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {ACCENT_PRIMARY};
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
                border: 1.5px solid rgba(91, 141, 239, 0.38);
                border-radius: 8px;
            }
        """)

        frame = QFrame(self)
        frame.setGeometry(0, 0, 500, 410)
        frame.setStyleSheet("""
            QFrame {
                background: #0b0f19;
                border: none;
                border-radius: 8px;
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
            QPushButton:hover { color: #ffffff; background: rgba(239, 68, 68, 0.25); border-color: #D9534F; }
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
        f_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
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
            QLineEdit:focus { border: 1.5px solid #5B8DEF; }
        """)
        lay.addWidget(self.url_input)

        sync_row = QHBoxLayout()
        self.sync_btn = QPushButton("⚡  Sync Feed Now")
        self.sync_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_btn.setFixedHeight(30)
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4376D6, stop:1 #5B8DEF);
                color: #080c14; border: none; border-radius: 6px; padding: 4px 16px;
            }
            QPushButton:hover { background: #5B8DEF; }
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
            QLineEdit:focus { border: 1.5px solid #5B8DEF; }
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
                border-radius: 8px;
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
                background: rgba(91, 141, 239, 0.2);
                border-color: #5B8DEF;
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
                    badge_info = ("● Now", "rgba(91, 141, 239, 0.18)", "#a5b4fc")
                    is_active = True
                    is_done = False
                elif 0 < s_mins - now_mins <= 60:
                    badge_info = (f"In {s_mins - now_mins}m", "rgba(91, 141, 239, 0.18)", "#a5b4fc")
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
                badge_info = ("Tomorrow", "rgba(91, 141, 239, 0.15)", "#60a5fa") if days_away == 1 else None
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
                border-radius: 8px;
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
                    background: rgba(91, 141, 239, 0.3);
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
    """Left navigation panel with Home, Chat, Tasks, Notes, Tools, Settings, and Theme Toggle."""
    tab_changed = pyqtSignal(str)
    settings_requested = pyqtSignal()
    theme_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(205)
        self.setStyleSheet(f"""
            QWidget {{
                background: {SIDEBAR_BG};
                border-right: 1px solid {CARD_BORDER};
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

        lay.addStretch()

        # Theme Mode Toggle Button
        is_white = CURRENT_NEO_THEME == "white"
        self.btn_theme = QPushButton("  🌙   Dark Mode" if is_white else "  ☀️   Light Mode")
        self.btn_theme.setFixedHeight(34)
        self.btn_theme.setFont(QFont("Segoe UI", 9))
        self.btn_theme.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_theme.setToolTip("Toggle Light / Dark Mode [F7]")
        self.btn_theme.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background: {CARD_HOVER};
                color: {TEXT_WHITE};
                border-color: {ACCENT_PRIMARY};
            }}
        """)
        self.btn_theme.clicked.connect(self.theme_toggled.emit)
        lay.addWidget(self.btn_theme)

        self.btn_settings = self._create_nav_item("⚙", "Settings", active=False)
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        lay.addWidget(self.btn_settings)

    def update_theme_button(self, is_white: bool):
        """Update toggle button text and styling based on active theme."""
        if is_white:
            self.btn_theme.setText("  🌙   Dark Mode")
            self.btn_theme.setToolTip("Switch to Dark Mode [F7]")
        else:
            self.btn_theme.setText("  ☀️   Light Mode")
            self.btn_theme.setToolTip("Switch to Light Mode [F7]")

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
                    border: 1px solid rgba(91, 141, 239, 0.35);
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: none;
                border-radius: 6px;
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
        self.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
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
                border: 1px solid rgba(91, 141, 239, 0.35);
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
        cam_title.setStyleSheet("color: #5B8DEF; letter-spacing: 1px; border: none; background: transparent;")
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
                border-radius: 8px;
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
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {ACCENT_PRIMARY};
            }}
        """)
        bar_lay = QHBoxLayout(self.input_frame)
        bar_lay.setContentsMargins(12, 0, 10, 0)
        bar_lay.setSpacing(10)

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(30, 30)
        plus_btn.setFont(QFont("Segoe UI", 15))
        plus_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        plus_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER};
                border-radius: 15px;
            }}
            QPushButton:hover {{
                background: {CARD_HOVER};
                color: {TEXT_WHITE};
            }}
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
                color: #ffffff;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
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
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: rgba(28, 38, 58, 0.85);
                border-color: rgba(91, 141, 239, 0.35);
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
                    background: rgba(91, 141, 239, 0.18);
                    color: #60a5fa;
                    border: 1px solid rgba(91, 141, 239, 0.38);
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background: rgba(91, 141, 239, 0.28);
                }
            """)
        else:
            self.cc_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #526078;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
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
                    background: rgba(91, 141, 239, 0.15);
                    border-radius: 15px;
                }
            """)

    def set_audio_level(self, level: float):
        self.eclipse.set_audio_level(level)


# ─────────────────────────────────────────────────────────────────────────────
#  5. INTERACTIVE FUNCTIONAL VIEWS (Tasks, Notes, Projects, Knowledge, Files)
# ─────────────────────────────────────────────────────────────────────────────
_TASKS_FILE = Path(__file__).resolve().parent.parent / "memory" / "tasks.json"
_NOTES_FILE = Path(__file__).resolve().parent.parent / "memory" / "notes.json"
_PROJECTS_FILE = Path(__file__).resolve().parent.parent / "memory" / "projects.json"

IGNORED_WORKSPACE_PATTERNS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".pytest_cache", ".idea", ".vscode", ".mypy_cache", ".ruff_cache",
    ".DS_Store", "build", "dist"
}

FILE_TYPE_ICONS = {
    ".py": "🐍",
    ".json": "📜",
    ".md": "📄",
    ".txt": "📄",
    ".html": "🌐",
    ".css": "🎨",
    ".js": "⚡",
    ".ts": "⚡",
    ".tsx": "⚛️",
    ".jsx": "⚛️",
    ".sh": "🖥️",
    ".bat": "🖥️",
    ".ps1": "🖥️",
    ".toml": "⚙️",
    ".yaml": "⚙️",
    ".yml": "⚙️",
    ".env": "🔒",
    ".png": "🖼️",
    ".jpg": "🖼️",
    ".jpeg": "🖼️",
    ".svg": "🖼️",
    ".ico": "🖼️",
    ".pdf": "📕",
    ".zip": "📦",
    ".tar": "📦",
    ".gz": "📦",
}

NOTE_CATEGORY_COLORS = {
    "Dev":        ("#5B8DEF", "rgba(91, 141, 239, 0.12)"),
    "Security":   ("#34d399", "rgba(52, 211, 153, 0.12)"),
    "Ideas":      ("#D9A441", "rgba(245, 158, 11, 0.12)"),
    "Research":   ("#a78bfa", "rgba(167, 139, 250, 0.12)"),
    "Quick Note": ("#94a3b8", "rgba(148, 163, 184, 0.12)"),
}

NOTE_TEMPLATES = {
    "🛡️ CTF & Security Vulnerability Assessment": {
        "title": "Security Audit & Vulnerability Assessment #security #ctf",
        "category": "Security",
        "content": """# Security Audit: [Target System / Service]

## Executive Summary
Brief summary of the security audit, target scope, and primary vulnerability posture.

### Target & Scope
- **Host / URL:** `https://target.local`
- **Methodology:** Black-box / Reverse Engineering / Dynamic Fuzzing
- **Severity Rating:** Critical / High / Medium

## Vulnerability Findings
### 1. [Vulnerability Title]
- **CVSS Score:** 8.8 (High)
- **Endpoint:** `POST /api/v1/auth/verify`
- **Proof of Concept (PoC):**
```bash
curl -X POST https://target/api/v1/auth/verify \\
  -H "Content-Type: application/json" \\
  -d '{"payload": "test_input"}'
```

## Remediation & Hardening Steps
- [ ] Implement parameterized input validation
- [ ] Restrict CORS headers to authorized origins
- [ ] Enforce rate-limiting and WAF protection rules
- [ ] Rotate exposed API tokens and refresh secrets
"""
    },
    "🏛️ System Architecture RFC Blueprint": {
        "title": "RFC: High-Performance Architecture Blueprint #dev #arch",
        "category": "Dev",
        "content": """# RFC: [System / Architecture Name]

## 1. Context & Business Value
Why this system is required, performance thresholds, and architectural goals.

## 2. High-Level Architecture
- **Transport Layer:** HTTP/2 & WebSockets with zero-latency duplex
- **State & Database:** SQLite with WAL mode + in-memory cache
- **Workers:** Parallel subagent background task queue

## 3. Data Schema & Contracts
```json
{
  "event": "state_sync",
  "payload": {
    "id": "uuid-v4",
    "timestamp": 1731170000,
    "status": "HEALTHY"
  }
}
```

## 4. Tactical Implementation Milestones
- [ ] Build core schemas and data persistence
- [ ] Connect event bus and telemetry hooks
- [ ] Benchmark sub-50ms latency under 1,000 req/sec load
- [ ] Deploy production health monitors and automated alerts
"""
    },
    "🎓 Academic Revision & Cheat Sheet": {
        "title": "Exam Revision & Formulas Cheat Sheet #exam #academic",
        "category": "Research",
        "content": """# Academic Revision: [Subject / Course Name]

## Core Principles & Theorems
Essential theoretical concepts, definitions, and mental models to master.

## Critical Formulas & Equations
- **Formula 1:** $E = mc^2$
- **Formula 2:** Net Present Value: $NPV = \\sum_{t=1}^n \\frac{CF_t}{(1+r)^t} - C_0$
- **Formula 3:** Shannon Entropy: $H(X) = -\\sum P(x) \\log_2 P(x)$

## High-Probability Exam Topics
- [ ] Review Chapter 3 deep-dive and case problem derivations
- [ ] Complete previous year exam sample questions
- [ ] Memorize formula boundary conditions and edge cases
"""
    },
    "🎯 Daily Tactical Standup Log": {
        "title": "Daily Tactical Execution Log #daily #ops",
        "category": "Quick Note",
        "content": """# Tactical Log: [Date]

## 🎯 Top 3 High-Leverage Priorities
- [ ] Complete core module refactoring and tests
- [ ] Verify zero-data-loss persistence and edge cases
- [ ] Submit pull request and sync origin main

## 🚧 Blockers & Impediments
- None currently active.

## 💡 Notes & Research Takeaways
Observations, technical insights, and key decisions from today's sprint.
"""
    }
}

TASK_CATEGORY_COLORS = {
    "Academic": ("🎓 ACADEMIC", "#a78bfa", "rgba(167, 139, 250, 0.14)"),
    "Dev":      ("💻 DEV",      "#5B8DEF", "rgba(91, 141, 239, 0.14)"),
    "SIH":      ("🏆 SIH",      "#D9A441", "rgba(245, 158, 11, 0.14)"),
    "Security": ("🛡️ SEC",      "#34d399", "rgba(52, 211, 153, 0.14)"),
    "Ops":      ("⚡ OPS",      "#D9534F", "rgba(244, 63, 94, 0.14)"),
    "General":  ("📋 TASK",     "#94a3b8", "rgba(148, 163, 184, 0.14)"),
}

TASK_PRIORITY_META = {
    "High":   ("🔴 CRITICAL", "#D9534F", "rgba(244, 63, 94, 0.16)", "#D9534F"),
    "Medium": ("🟡 MEDIUM",   "#D9A441", "rgba(245, 158, 11, 0.16)", "#D9A441"),
    "Low":    ("🔵 ROUTINE",  "#5B8DEF", "rgba(91, 141, 239, 0.14)", "#5B8DEF"),
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
                border: 1px solid rgba(91, 141, 239, 0.3);
                border-radius: 8px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        hdr = QLabel("✎ Edit Tactical Objective")
        hdr.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        lay.addWidget(hdr)

        self.title_edit = QLineEdit(self.task.get("title", ""))
        self.title_edit.setFont(QFont("Segoe UI", 10))
        self.title_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.05); color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #5B8DEF; }
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
                background: #5B8DEF; color: #070b14;
                border: none; border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background: #5B8DEF; }
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
    """Linear / Raycast grade minimalist task row with priority dot, clean typography, and hover actions."""

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

        dot_colors = {"High": "#D9534F", "Medium": "#D9A441", "Low": "#5B8DEF"}
        dot_color = dot_colors.get(priority, "#94a3b8")

        has_notes = bool(notes)
        self.setFixedHeight(48 if has_notes else 40)
        self.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: {CARD_HOVER};
                border-color: {ACCENT_PRIMARY};
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(10)

        # 1. Modern Minimalist Checkbox
        self.cb = QCheckBox()
        self.cb.setChecked(done)
        self.cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1.5px solid rgba(255, 255, 255, 0.25);
                background: #0c101a;
            }
            QCheckBox::indicator:hover {
                border-color: #5B8DEF;
                background: rgba(91, 141, 239, 0.12);
            }
            QCheckBox::indicator:checked {
                background: #5B8DEF;
                border-color: #5B8DEF;
            }
        """)
        self.cb.toggled.connect(self._handle_toggle)
        lay.addWidget(self.cb)

        # 2. Priority Dot
        prio_dot = QLabel("●")
        prio_dot.setFont(QFont("Segoe UI", 7))
        prio_dot.setToolTip(f"Priority: {priority}")
        prio_dot.setStyleSheet(f"color: {dot_color if not done else '#475569'}; border: none; background: transparent;")
        lay.addWidget(prio_dot)

        # 3. Title & Optional Subtitle Column
        col = QVBoxLayout()
        col.setContentsMargins(0, 2, 0, 2)
        col.setSpacing(1)

        self.title_lbl = QLabel(task.get("title", ""))
        self.title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium if not done else QFont.Weight.Normal))
        self._apply_title_style(done)
        col.addWidget(self.title_lbl)

        if has_notes:
            note_lbl = QLabel(f"↳ {notes[:70]}" + ("..." if len(notes) > 70 else ""))
            note_lbl.setFont(QFont("Segoe UI", 7))
            note_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
            col.addWidget(note_lbl)

        lay.addLayout(col, stretch=1)

        # 4. Quiet Category Label
        cat_lbl = QLabel(category)
        cat_lbl.setFont(QFont("Segoe UI", 8))
        cat_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        lay.addWidget(cat_lbl)

        # 5. Due Date Indicator
        is_urgent = (due.lower() in ("today", "now") and not done and priority == "High")
        due_lbl = QLabel(due)
        due_lbl.setFont(QFont("Segoe UI", 8))
        due_lbl.setStyleSheet(f"color: {'#D9534F' if is_urgent else '#64748b'}; border: none; background: transparent; padding-left: 6px;")
        lay.addWidget(due_lbl)

        # 6. Action Buttons
        if not done:
            run_btn = QPushButton("⚡ Run")
            run_btn.setToolTip("Execute objective with NEO in Chat")
            run_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            run_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            run_btn.setFixedHeight(22)
            run_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(91, 141, 239, 0.1);
                    color: #5B8DEF;
                    border: 1px solid rgba(91, 141, 239, 0.25);
                    border-radius: 4px;
                    padding: 0 8px;
                }
                QPushButton:hover {
                    background: rgba(91, 141, 239, 0.25);
                    color: #ffffff;
                }
            """)
            run_btn.clicked.connect(lambda: self.on_execute(self.task))
            lay.addWidget(run_btn)

        edit_btn = QPushButton("✎")
        edit_btn.setToolTip("Edit details")
        edit_btn.setFixedSize(20, 20)
        edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        edit_btn.setStyleSheet("QPushButton { color: #475569; border: none; background: transparent; font-size: 10px; } QPushButton:hover { color: #5B8DEF; }")
        edit_btn.clicked.connect(lambda: self.on_edit(self.task))
        lay.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setToolTip("Delete")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet("QPushButton { color: #475569; border: none; background: transparent; font-size: 10px; } QPushButton:hover { color: #D9534F; }")
        del_btn.clicked.connect(lambda: self.on_delete(self.task))
        lay.addWidget(del_btn)

    def _apply_title_style(self, done: bool):
        if done:
            self.title_lbl.setStyleSheet("color: #64748b; text-decoration: line-through; background: transparent; border: none;")
        else:
            self.title_lbl.setStyleSheet("color: #e2e8f0; text-decoration: none; background: transparent; border: none;")

    def _handle_toggle(self, checked: bool):
        self.task["done"] = checked
        if checked:
            self.task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._apply_title_style(checked)
        self.on_toggle(self.task)


class NeoTasksView(QWidget):
    """
    Senior-dev executive Task & Execution Engine for NEO.
    Clean, minimalist, distraction-free UI inspired by Linear, Raycast, and Apple.
    """
    task_action_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        self.active_status_filter = "ALL"
        self.active_category_filter = "All"
        self.search_keyword = ""

        self.tasks_data = self._load_tasks()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 18, 28, 18)
        lay.setSpacing(10)

        # 1. Clean Breathing Header
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        t_lbl = QLabel("Tasks")
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent; letter-spacing: -0.3px;")
        hdr.addWidget(t_lbl)

        self.count_badge = QLabel("0 pending")
        self.count_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.count_badge.setStyleSheet("""
            color: #94a3b8; background: rgba(255, 255, 255, 0.05);
            border-radius: 9px; padding: 2px 8px; border: none;
        """)
        hdr.addWidget(self.count_badge)

        hdr.addStretch()

        sync_btn = QPushButton("⚡ Sync with NEO")
        sync_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sync_btn.setFixedHeight(28)
        sync_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.1);
                color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.28);
                border-radius: 6px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: rgba(91, 141, 239, 0.22);
                color: #ffffff;
            }
        """)
        sync_btn.clicked.connect(self._on_sync_requested)
        hdr.addWidget(sync_btn)

        clear_btn = QPushButton("Clear Done")
        clear_btn.setFont(QFont("Segoe UI", 8))
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: none; padding: 4px 8px; } QPushButton:hover { color: #D9534F; }")
        clear_btn.clicked.connect(self._clear_completed_tasks)
        hdr.addWidget(clear_btn)

        refresh_btn = QPushButton("↺")
        refresh_btn.setToolTip("Reload tasks from memory")
        refresh_btn.setFont(QFont("Segoe UI", 9))
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet("QPushButton { background: transparent; color: #475569; border: none; padding: 4px; } QPushButton:hover { color: #5B8DEF; }")
        refresh_btn.clicked.connect(self._reload_from_disk)
        hdr.addWidget(refresh_btn)

        lay.addLayout(hdr)

        # 2. Sleek Hairline Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.05);
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5B8DEF, stop:1 #5B8DEF);
            }
        """)
        lay.addWidget(self.progress_bar)

        # 3. Unified Single-Row Toolbar (Segmented Filters + Category + Search)
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.status_btn_group = QButtonGroup(self)
        self.status_btns = {}
        statuses = [
            ("ALL", "All"),
            ("IN_PROGRESS", "Active"),
            ("COMPLETED", "Completed"),
            ("HIGH_PRIO", "High Priority"),
        ]
        for key, label in statuses:
            b = QPushButton(label)
            b.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium if key == "ALL" else QFont.Weight.Normal))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setFixedHeight(26)
            b.setCheckable(True)
            if key == "ALL":
                b.setChecked(True)
            self._update_tab_style(b, b.isChecked())
            b.clicked.connect(lambda _, k=key: self._on_status_filter_changed(k))
            self.status_btn_group.addButton(b)
            self.status_btns[key] = b
            bar.addWidget(b)

        bar.addSpacing(10)

        # Category dropdown filter
        self.cat_filter_combo = QComboBox()
        self.cat_filter_combo.addItems(["All Categories", "Academic", "Dev", "SIH", "Security", "Ops", "General"])
        self.cat_filter_combo.setFont(QFont("Segoe UI", 8))
        self.cat_filter_combo.setFixedHeight(26)
        self.cat_filter_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.04);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 2px 8px;
            }
            QComboBox:hover {
                color: #cbd5e1;
                border-color: rgba(91, 141, 239, 0.3);
            }
            QComboBox QAbstractItemView {
                background: #0d1322;
                color: #f8fafc;
                border: 1px solid rgba(91, 141, 239, 0.25);
            }
        """)
        self.cat_filter_combo.currentTextChanged.connect(self._on_category_combo_changed)
        bar.addWidget(self.cat_filter_combo)

        bar.addStretch()

        # Search filter
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter...")
        self.search_input.setFont(QFont("Segoe UI", 8))
        self.search_input.setFixedWidth(150)
        self.search_input.setFixedHeight(26)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;
                padding: 2px 8px;
            }
            QLineEdit:focus { border-color: #5B8DEF; }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        bar.addWidget(self.search_input)

        lay.addLayout(bar)

        # 4. Minimalist Quick Add Bar
        self.add_frame = QFrame()
        self.add_frame.setFixedHeight(38)
        self.add_frame.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {ACCENT_PRIMARY};
            }}
        """)
        add_lay = QHBoxLayout(self.add_frame)
        add_lay.setContentsMargins(10, 0, 8, 0)
        add_lay.setSpacing(6)

        self.new_task_edit = QLineEdit()
        self.new_task_edit.setPlaceholderText("Add a new task... (press Enter to save)")
        self.new_task_edit.setFont(QFont("Segoe UI", 9))
        self.new_task_edit.setStyleSheet("""
            QLineEdit {
                background: transparent; border: none;
                color: #ffffff; padding: 0 4px;
            }
            QLineEdit::placeholder { color: #64748b; }
        """)
        self.new_task_edit.returnPressed.connect(self._add_task)
        add_lay.addWidget(self.new_task_edit, stretch=1)

        def _compact_combo(items, w):
            cb = QComboBox()
            cb.addItems(items)
            cb.setFont(QFont("Segoe UI", 8))
            cb.setFixedWidth(w)
            cb.setStyleSheet("""
                QComboBox {
                    background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                    border: none; border-radius: 4px; padding: 2px 6px;
                }
                QComboBox:hover { color: #f8fafc; }
                QComboBox QAbstractItemView { background: #0d1322; color: #f8fafc; }
            """)
            return cb

        self.prio_combo = _compact_combo(["🔴 High", "🟡 Med", "🔵 Low"], 80)
        add_lay.addWidget(self.prio_combo)

        self.cat_combo = _compact_combo(["Academic", "Dev", "SIH", "Security", "Ops", "General"], 85)
        add_lay.addWidget(self.cat_combo)

        self.due_combo = _compact_combo(["Today", "Tomorrow", "This Week", "Later"], 85)
        add_lay.addWidget(self.due_combo)

        add_b = QPushButton("+ Add")
        add_b.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        add_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_b.setFixedHeight(26)
        add_b.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 5px; padding: 0 12px;
            }
            QPushButton:hover { background: #5B8DEF; }
        """)
        add_b.clicked.connect(self._add_task)
        add_lay.addWidget(add_b)

        lay.addWidget(self.add_frame)

        # 5. Tasks List Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(91, 141, 239, 0.25); border-radius: 3px; min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(91, 141, 239, 0.6);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.tasks_container = QWidget()
        self.tasks_container.setStyleSheet("background: transparent;")
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 4, 4, 4)
        self.tasks_layout.setSpacing(5)
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
                border: 1px solid #5B8DEF;
                border-radius: 8px;
                padding: 4px 18px;
            }
        """)
        self.toast_lbl.setVisible(False)

        self._refresh_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_toast()

    def _reposition_toast(self):
        w = self.toast_lbl.sizeHint().width() + 20
        h = 28
        self.toast_lbl.setGeometry((self.width() - w) // 2, 10, w, h)

    def _show_toast(self, text: str):
        self.toast_lbl.setText(text)
        self.toast_lbl.adjustSize()
        self._reposition_toast()
        self.toast_lbl.show()
        self.toast_lbl.raise_()
        QTimer.singleShot(2500, self.toast_lbl.hide)

    def _update_tab_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(91, 141, 239, 0.15);
                    color: #5B8DEF;
                    border: 1px solid rgba(91, 141, 239, 0.3);
                    border-radius: 6px;
                    padding: 3px 10px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #94a3b8;
                    border: 1px solid transparent;
                    border-radius: 6px;
                    padding: 3px 10px;
                }
                QPushButton:hover {
                    color: #ffffff;
                }
            """)

    # ─────────────────────────────────────────────────────────────────────────
    # Storage & State (Zero-Data-Loss Persistent Engine)
    # ─────────────────────────────────────────────────────────────────────────
    def _load_tasks(self) -> list[dict]:
        """Loads tasks directly from disk. Never overwrites user state with mock data."""
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _TASKS_FILE.exists():
            try:
                with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "tasks" in data:
                        tasks = data.get("tasks")
                        if isinstance(tasks, list):
                            return tasks
            except Exception:
                pass

        # If file does not exist, initialize empty persistent database
        self._write_tasks([])
        return []

    def _write_tasks(self, tasks: list[dict]):
        """Atomic write with physical fsync to prevent loss across abrupt exits."""
        try:
            _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = _TASKS_FILE.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, _TASKS_FILE)
        except Exception:
            try:
                with open(_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _save_tasks(self):
        self._write_tasks(self.tasks_data)

    def _reload_from_disk(self):
        """Cleanly reloads tasks from storage without touching or resetting user items."""
        self.tasks_data = self._load_tasks()
        self._refresh_ui()
        self._show_toast("✓ Tasks reloaded from memory")

    # ─────────────────────────────────────────────────────────────────────────
    # UI Refresh & Filtering
    # ─────────────────────────────────────────────────────────────────────────
    def _refresh_ui(self):
        total = len(self.tasks_data)
        done_cnt = sum(1 for t in self.tasks_data if t.get("done"))
        pending_cnt = total - done_cnt

        pct = int((done_cnt / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.count_badge.setText(f"{pending_cnt} active" if pending_cnt > 0 else "All completed")

        # Clear current task cards (keep stretch)
        for i in reversed(range(self.tasks_layout.count())):
            item = self.tasks_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                self.tasks_layout.removeWidget(w)
                w.deleteLater()

        # Filter
        filtered = []
        kw = self.search_keyword.lower().strip()
        for t in self.tasks_data:
            t_done = bool(t.get("done", False))
            t_prio = str(t.get("priority", "Medium"))
            t_cat = str(t.get("category", "General"))
            t_title = str(t.get("title", "")).lower()
            t_notes = str(t.get("notes", "")).lower()

            if self.active_status_filter == "IN_PROGRESS" and t_done:
                continue
            elif self.active_status_filter == "COMPLETED" and not t_done:
                continue
            elif self.active_status_filter == "HIGH_PRIO" and (t_prio != "High" or t_done):
                continue

            if self.active_category_filter != "All" and t_cat.lower() != self.active_category_filter.lower():
                continue

            if kw and (kw not in t_title and kw not in t_notes):
                continue

            filtered.append(t)

        if not filtered:
            empty_card = QFrame()
            empty_card.setFixedHeight(70)
            empty_card.setStyleSheet("QFrame { background: rgba(14, 20, 32, 0.4); border: 1px dashed rgba(255, 255, 255, 0.08); border-radius: 8px; }")
            e_lay = QVBoxLayout(empty_card)
            e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lbl = QLabel("No tasks found matching current filter.")
            e_lbl.setFont(QFont("Segoe UI", 9))
            e_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
            e_lay.addWidget(e_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
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

    def _on_category_combo_changed(self, text: str):
        self.active_category_filter = "All" if text == "All Categories" else text
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
        self._show_toast("Task removed")

    def _on_task_edited(self, task: dict):
        dlg = TaskEditDialog(task, self)
        if dlg.exec():
            for i, t in enumerate(self.tasks_data):
                if t.get("id") == task.get("id"):
                    self.tasks_data[i] = dlg.task
                    break
            self._save_tasks()
            self._refresh_ui()
            self._show_toast("Task updated")

    def _on_task_executed(self, task: dict):
        title = task.get("title", "")
        category = task.get("category", "")
        cmd = f"Execute objective: '{title}' (Category: {category}). Formulate an actionable execution blueprint, generate required code or materials, and assist me in completing it, Boss."
        self._show_toast(f"⚡ Dispatched: '{title[:24]}...'")
        self.task_action_triggered.emit(cmd)

    def _on_sync_requested(self):
        self._show_toast("⚡ Syncing with NEO...")
        self.task_action_triggered.emit("Sync and prioritize my current tasks from the Task Engine, Boss. Give me the top 3 tactical actions to focus on now.")

    def _reset_input_style(self):
        self.new_task_edit.setStyleSheet("""
            QLineEdit {
                background: transparent; border: none;
                color: #ffffff; padding: 0 4px;
            }
            QLineEdit::placeholder { color: #64748b; }
        """)
        self.new_task_edit.setPlaceholderText("Add a new task... (press Enter to save)")

    def _add_task(self):
        title = self.new_task_edit.text().strip()
        if not title:
            self.new_task_edit.setStyleSheet("""
                QLineEdit {
                    background: rgba(244, 63, 94, 0.12);
                    border: 1px solid #D9534F;
                    border-radius: 4px;
                    color: #ffffff;
                    padding: 0 4px;
                }
            """)
            self.new_task_edit.setPlaceholderText("Please enter a task title...")
            self.new_task_edit.setFocus()
            QTimer.singleShot(1500, self._reset_input_style)
            return

        cat_raw = self.cat_combo.currentText()
        category = cat_raw if cat_raw in ("Academic", "Dev", "SIH", "Security", "Ops") else "General"

        prio_raw = self.prio_combo.currentText()
        priority = "High" if "High" in prio_raw else ("Low" if "Low" in prio_raw else "Medium")

        due = self.due_combo.currentText().strip()

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
        self._show_toast("Task added")
        self._refresh_ui()

    def _clear_completed_tasks(self):
        self.tasks_data = [t for t in self.tasks_data if not t.get("done")]
        self._save_tasks()
        self._refresh_ui()
        self._show_toast("Completed tasks cleared")


# ─────────────────────────────────────────────────────────────────────────────
#  6. SENIOR-DEV EXECUTIVE NOTES & KNOWLEDGE STUDIO
# ─────────────────────────────────────────────────────────────────────────────

class NeoNoteCard(QFrame):
    """Sleek minimalist note card for the Notes sidebar list."""
    clicked = pyqtSignal(dict)
    deleted = pyqtSignal(dict)
    archived = pyqtSignal(dict)

    def __init__(self, note: dict, is_active: bool = False, parent=None):
        super().__init__(parent)
        self.note = note
        self.is_active = is_active
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        bg = "rgba(91, 141, 239, 0.12)" if is_active else CARD_BG
        border = ACCENT_PRIMARY if is_active else CARD_BORDER
        left_border = f"3px solid {ACCENT_PRIMARY};" if is_active else f"1px solid {CARD_BORDER};"

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-left: {left_border}
                border-radius: 7px;
            }}
            QFrame:hover {{
                background: {CARD_HOVER};
                border-color: {ACCENT_PRIMARY};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        # Top row: [Pinned] [Archived] Title
        top_r = QHBoxLayout()
        top_r.setSpacing(5)
        if note.get("pinned"):
            p_lbl = QLabel("📌")
            p_lbl.setFont(QFont("Segoe UI", 7))
            p_lbl.setStyleSheet("border: none; background: transparent;")
            top_r.addWidget(p_lbl)
        if note.get("archived"):
            a_lbl = QLabel("📦")
            a_lbl.setFont(QFont("Segoe UI", 7))
            a_lbl.setStyleSheet("border: none; background: transparent;")
            top_r.addWidget(a_lbl)

        title_text = (note.get("title") or "Untitled Note").strip()
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #f1f5f9; border: none; background: transparent;")
        top_r.addWidget(self.title_lbl, stretch=1)
        lay.addLayout(top_r)

        # Snippet preview
        content = (note.get("content") or "").strip().replace("\n", " ")
        snippet = (content[:50] + "...") if len(content) > 50 else (content or "Empty note...")
        self.snip_lbl = QLabel(snippet)
        self.snip_lbl.setFont(QFont("Segoe UI", 7))
        self.snip_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        lay.addWidget(self.snip_lbl)

        # Meta row: Category pill + Tag chip + Time + Delete button
        meta_r = QHBoxLayout()
        meta_r.setSpacing(5)
        cat = note.get("category", "Quick Note")
        cfg, cbg = NOTE_CATEGORY_COLORS.get(cat, ("#94a3b8", "rgba(148, 163, 184, 0.12)"))
        cat_b = QLabel(cat)
        cat_b.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
        cat_b.setStyleSheet(f"color: {cfg}; background: {cbg}; border-radius: 3px; padding: 1px 5px; border: none;")
        meta_r.addWidget(cat_b)

        # Show first hashtag if present
        tags = re.findall(r"#([a-zA-Z0-9_\-]+)", (note.get("title", "") + " " + (note.get("content", ""))))
        if tags:
            tag_chip = QLabel(f"#{tags[0]}")
            tag_chip.setFont(QFont("Segoe UI", 7))
            tag_chip.setStyleSheet("color: #5B8DEF; background: rgba(91, 141, 239, 0.08); border-radius: 3px; padding: 1px 4px; border: none;")
            meta_r.addWidget(tag_chip)

        time_str = note.get("updated_at") or note.get("created_at") or "Today"
        time_l = QLabel(time_str.split(" ")[0] if " " in time_str else time_str)
        time_l.setFont(QFont("Segoe UI", 7))
        time_l.setStyleSheet("color: #475569; border: none; background: transparent;")
        meta_r.addWidget(time_l)
        meta_r.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFont(QFont("Segoe UI", 7))
        del_btn.setFixedSize(16, 16)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet("QPushButton { color: #475569; background: transparent; border: none; } QPushButton:hover { color: #D9534F; }")
        del_btn.clicked.connect(lambda: self.deleted.emit(self.note))
        meta_r.addWidget(del_btn)

        lay.addLayout(meta_r)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.note)
        super().mousePressEvent(event)


class NeoNotesView(QWidget):
    """
    Senior-dev executive Notes & Knowledge Studio for NEO.
    Provides Master-Detail split navigation, Markdown live preview & syntax,
    Zen focus mode, 4 executive templates, action item task extraction,
    multi-format export studio (.md, .txt, .html), dynamic hashtags,
    zero-data-loss atomic storage, and autonomous AI analysis.
    """
    note_saved = pyqtSignal(str)            # For long-term memory
    note_action_triggered = pyqtSignal(str) # For AI analysis in Chat

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        self.notes_data: list[dict] = self._load_notes()
        self.active_note_id: Optional[str] = self.notes_data[0]["id"] if self.notes_data else None
        self.active_filter_cat: str = "All"
        self.active_tag_filter: Optional[str] = None
        self.search_keyword: str = ""
        self._is_loading_note: bool = False
        self.is_zen: bool = False
        self.is_preview: bool = False

        # Debounced auto-save timer
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self._auto_save_active)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        # ── 1. Header Row ──
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        t_lbl = QLabel("Notes")
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(t_lbl)

        self.count_badge = QLabel(f"{len(self.notes_data)} notes")
        self.count_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.count_badge.setStyleSheet("color: #94a3b8; background: rgba(255,255,255,0.05); border-radius: 9px; padding: 2px 8px; border: none;")
        hdr.addWidget(self.count_badge)

        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("""
            QLabel {
                background: rgba(15, 23, 42, 0.95); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 6px;
                padding: 4px 12px; font-size: 11px;
            }
        """)
        self.toast_lbl.hide()
        hdr.addWidget(self.toast_lbl)

        hdr.addStretch()

        # Zen Focus Mode Button
        self.zen_btn = QPushButton("⛶ Zen")
        self.zen_btn.setToolTip("Toggle distraction-free Zen focus canvas")
        self.zen_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.zen_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.zen_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        self.zen_btn.clicked.connect(self._toggle_zen)
        hdr.addWidget(self.zen_btn)

        # Templates Dropdown Menu
        self.template_btn = QPushButton("📑 Templates ▾")
        self.template_btn.setToolTip("Insert senior-dev executive note blueprints")
        self.template_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.template_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.template_btn.setStyleSheet("""
            QPushButton {
                background: rgba(167, 139, 250, 0.1); color: #a78bfa;
                border: 1px solid rgba(167, 139, 250, 0.28); border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(167, 139, 250, 0.2); color: #ffffff; }
        """)
        self._init_template_menu()
        hdr.addWidget(self.template_btn)

        # AI Polish & Structure Button
        polish_btn = QPushButton("✨ Polish")
        polish_btn.setToolTip("Ask NEO to format, polish prose, and structure this note")
        polish_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        polish_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        polish_btn.setStyleSheet("""
            QPushButton {
                background: rgba(245, 158, 11, 0.1); color: #D9A441;
                border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(245, 158, 11, 0.22); color: #ffffff; }
        """)
        polish_btn.clicked.connect(self._polish_note)
        hdr.addWidget(polish_btn)

        # AI Review & Brainstorm Button
        review_btn = QPushButton("⚡ Ask NEO")
        review_btn.setToolTip("Brainstorm, expand, or get executive feedback from NEO")
        review_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        review_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        review_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.1); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 6px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.22); color: #ffffff; }
        """)
        review_btn.clicked.connect(self._ask_neo_review)
        hdr.addWidget(review_btn)

        # + New Note Button
        new_btn = QPushButton("+ New Note")
        new_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        new_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_btn.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 6px; padding: 4px 14px;
            }
            QPushButton:hover { background: #4376D6; }
        """)
        new_btn.clicked.connect(self._add_new_note)
        hdr.addWidget(new_btn)
        root.addLayout(hdr)

        # ── 2. Master-Detail Layout ──
        body_lay = QHBoxLayout()
        body_lay.setSpacing(14)

        # Left Column: Note Navigator (~230px compact)
        self.left_panel = QFrame()
        self.left_panel.setFixedWidth(230)
        self.left_panel.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        left_lay = QVBoxLayout(self.left_panel)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(8)

        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Search notes...")
        self.search_edit.setFont(QFont("Segoe UI", 8))
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px; color: #ffffff; padding: 5px 8px;
            }
            QLineEdit:focus { border-color: rgba(91, 141, 239, 0.4); }
        """)
        self.search_edit.textChanged.connect(self._on_search_changed)
        left_lay.addWidget(self.search_edit)

        # Category pills filter (2-row grid to avoid label truncation)
        cats_top = QHBoxLayout()
        cats_top.setSpacing(3)
        cats_bot = QHBoxLayout()
        cats_bot.setSpacing(3)
        self.filter_buttons = {}

        for cat in ["All", "Dev", "Security"]:
            b = QPushButton(cat)
            b.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold if cat == "All" else QFont.Weight.Normal))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if cat == "All":
                b.setStyleSheet("background: rgba(91, 141, 239, 0.15); color: #5B8DEF; border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 4px; padding: 2px 7px;")
            else:
                b.setStyleSheet("background: rgba(255, 255, 255, 0.02); color: #64748b; border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 4px; padding: 2px 6px;")
            b.clicked.connect(lambda _, c=cat: self._set_category_filter(c))
            self.filter_buttons[cat] = b
            cats_top.addWidget(b)
        cats_top.addStretch()
        left_lay.addLayout(cats_top)

        for cat in ["Ideas", "Research", "Archive"]:
            lbl = "📦 Archive" if cat == "Archive" else cat
            b = QPushButton(lbl)
            b.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet("background: rgba(255, 255, 255, 0.02); color: #64748b; border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 4px; padding: 2px 6px;")
            b.clicked.connect(lambda _, c=cat: self._set_category_filter(c))
            self.filter_buttons[cat] = b
            cats_bot.addWidget(b)
        cats_bot.addStretch()
        left_lay.addLayout(cats_bot)

        # Dynamic Hashtags Filter Bar
        self.tags_frame = QFrame()
        self.tags_frame.setStyleSheet("background: transparent; border: none;")
        self.tags_lay = QHBoxLayout(self.tags_frame)
        self.tags_lay.setContentsMargins(0, 0, 0, 0)
        self.tags_lay.setSpacing(4)
        left_lay.addWidget(self.tags_frame)

        # Scrollable Cards Area
        self.notes_scroll = QScrollArea()
        self.notes_scroll.setWidgetResizable(True)
        self.notes_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_cont = QWidget()
        self.cards_cont.setStyleSheet("background: transparent;")
        self.cards_lay = QVBoxLayout(self.cards_cont)
        self.cards_lay.setContentsMargins(0, 4, 0, 4)
        self.cards_lay.setSpacing(6)
        self.cards_lay.addStretch()

        self.notes_scroll.setWidget(self.cards_cont)
        left_lay.addWidget(self.notes_scroll, stretch=1)
        body_lay.addWidget(self.left_panel)

        # Right Column: Note Studio & Editor (Stretch)
        self.editor_panel = QFrame()
        self.editor_panel.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        ed_lay = QVBoxLayout(self.editor_panel)
        ed_lay.setContentsMargins(18, 14, 18, 14)
        ed_lay.setSpacing(10)

        # Editor Toolbar (Responsive & Compact)
        tb = QHBoxLayout()
        tb.setSpacing(6)

        self.cat_box = QComboBox()
        self.cat_box.addItems(["Dev", "Security", "Ideas", "Research", "Quick Note"])
        self.cat_box.setFont(QFont("Segoe UI", 8))
        self.cat_box.setFixedWidth(88)
        self.cat_box.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 2px 6px;
            }
        """)
        self.cat_box.currentIndexChanged.connect(self._on_category_changed)
        tb.addWidget(self.cat_box)

        # Pin Button (Fixed 28x24 icon)
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setToolTip("Toggle pin to top")
        self.pin_btn.setFont(QFont("Segoe UI", 8))
        self.pin_btn.setFixedSize(28, 24)
        self.pin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.pin_btn.setStyleSheet("background: transparent; color: #64748b; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px;")
        self.pin_btn.clicked.connect(self._toggle_active_pin)
        tb.addWidget(self.pin_btn)

        # Markdown Preview Toggle
        self.preview_btn = QPushButton("👁️ Preview")
        self.preview_btn.setToolTip("Toggle live Markdown formatted reading preview")
        self.preview_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.preview_btn.setFixedHeight(24)
        self.preview_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 2px 9px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.15); color: #5B8DEF; }
        """)
        self.preview_btn.clicked.connect(self._toggle_preview)
        tb.addWidget(self.preview_btn)

        # Action Items to Task Engine Button
        self.tasks_btn = QPushButton("⚡ Tasks")
        self.tasks_btn.setToolTip("Extract '- [ ]' checklist items directly into Task Engine")
        self.tasks_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.tasks_btn.setFixedHeight(24)
        self.tasks_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tasks_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.1); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.28); border-radius: 5px; padding: 2px 9px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.22); color: #ffffff; }
        """)
        self.tasks_btn.clicked.connect(self._extract_tasks_to_engine)
        tb.addWidget(self.tasks_btn)

        # Export Dropdown Menu
        self.export_btn = QPushButton("📥 Export ▾")
        self.export_btn.setToolTip("Export note as Markdown, Plain Text, or HTML")
        self.export_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.export_btn.setFixedHeight(24)
        self.export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 2px 9px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #f1f5f9; }
        """)
        self._init_export_menu()
        tb.addWidget(self.export_btn)

        tb.addStretch()

        # Word count & reading metrics
        self.word_metrics_lbl = QLabel("0 words · 0 chars")
        self.word_metrics_lbl.setFont(QFont("Segoe UI", 7))
        self.word_metrics_lbl.setStyleSheet("color: #64748b; border: none; background: transparent; padding: 0 4px;")
        tb.addWidget(self.word_metrics_lbl)

        # Copy Note Button
        copy_btn = QPushButton("📋")
        copy_btn.setToolTip("Copy note as Markdown to clipboard")
        copy_btn.setFont(QFont("Segoe UI", 8))
        copy_btn.setFixedSize(26, 24)
        copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_btn.setStyleSheet("background: transparent; color: #94a3b8; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px;")
        copy_btn.clicked.connect(self._copy_note)
        tb.addWidget(copy_btn)

        # Commit to Long-Term Memory Button
        mem_btn = QPushButton("🧠 Save")
        mem_btn.setToolTip("Commit note to NEO Long-Term Memory")
        mem_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        mem_btn.setFixedHeight(24)
        mem_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        mem_btn.setStyleSheet("""
            QPushButton {
                background: rgba(52, 211, 153, 0.12); color: #34d399;
                border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 5px; padding: 2px 8px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(52, 211, 153, 0.25); color: #ffffff; }
        """)
        mem_btn.clicked.connect(self._commit_to_brain)
        tb.addWidget(mem_btn)

        # Archive Active Note Button
        self.archive_btn = QPushButton("📦")
        self.archive_btn.setToolTip("Toggle Archive status for this note")
        self.archive_btn.setFont(QFont("Segoe UI", 8))
        self.archive_btn.setFixedSize(26, 24)
        self.archive_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.archive_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px; } QPushButton:hover { color: #D9A441; }")
        self.archive_btn.clicked.connect(self._toggle_active_archive)
        tb.addWidget(self.archive_btn)

        # Delete Note Button
        del_active_btn = QPushButton("🗑️")
        del_active_btn.setToolTip("Delete note permanently")
        del_active_btn.setFont(QFont("Segoe UI", 8))
        del_active_btn.setFixedSize(26, 24)
        del_active_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_active_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: none; } QPushButton:hover { color: #D9534F; }")
        del_active_btn.clicked.connect(self._delete_active_note)
        tb.addWidget(del_active_btn)

        ed_lay.addLayout(tb)

        # Hairline divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(255, 255, 255, 0.05);")
        ed_lay.addWidget(div)

        # Note Title Edit
        self.title_in = QLineEdit()
        self.title_in.setPlaceholderText("Untitled Note...")
        self.title_in.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.title_in.setStyleSheet("QLineEdit { background: transparent; border: none; color: #ffffff; padding: 2px 0; }")
        self.title_in.textChanged.connect(self._on_content_changed)
        ed_lay.addWidget(self.title_in)

        # Stacked Editor (Page 0: QTextEdit, Page 1: Live Markdown QTextBrowser)
        self.stacked_ed = QStackedWidget()

        self.body_ed = QTextEdit()
        self.body_ed.setPlaceholderText("Write thoughts, code snippets, research findings, or meeting takeaways...")
        self.body_ed.setFont(QFont("Segoe UI", 10))
        self.body_ed.setStyleSheet("""
            QTextEdit {
                background: transparent; border: none;
                color: #e2e8f0; padding: 4px 0; line-height: 1.5;
            }
        """)
        self.body_ed.textChanged.connect(self._on_content_changed)
        self.stacked_ed.addWidget(self.body_ed)

        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.setStyleSheet("""
            QTextBrowser {
                background: rgba(10, 15, 26, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 12px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        self.stacked_ed.addWidget(self.preview_browser)
        ed_lay.addWidget(self.stacked_ed, stretch=1)

        # Footer Status Row
        ft = QHBoxLayout()
        self.saved_status_lbl = QLabel("✓ Auto-saved to memory")
        self.saved_status_lbl.setFont(QFont("Segoe UI", 7))
        self.saved_status_lbl.setStyleSheet("color: #475569; border: none; background: transparent;")
        ft.addWidget(self.saved_status_lbl)

        ft.addStretch()

        sync_l = QLabel("⚡ Indexed in NEO Semantic Brain")
        sync_l.setFont(QFont("Segoe UI", 7))
        sync_l.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        ft.addWidget(sync_l)
        ed_lay.addLayout(ft)

        body_lay.addWidget(self.editor_panel, stretch=1)
        root.addLayout(body_lay, stretch=1)

        # Initial UI render
        self._refresh_notes_list()
        self._populate_active_note_in_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # Menus: Templates & Exports
    # ─────────────────────────────────────────────────────────────────────────
    def _init_template_menu(self):
        tpl_menu = QMenu(self)
        tpl_menu.setStyleSheet("""
            QMenu {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid rgba(91, 141, 239, 0.25);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background: rgba(91, 141, 239, 0.18);
                color: #ffffff;
            }
        """)
        for name in NOTE_TEMPLATES.keys():
            action = QAction(name, self)
            action.triggered.connect(lambda _, t=name: self._apply_template(t))
            tpl_menu.addAction(action)
        self.template_btn.setMenu(tpl_menu)

    def _init_export_menu(self):
        exp_menu = QMenu(self)
        exp_menu.setStyleSheet("""
            QMenu {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background: rgba(91, 141, 239, 0.18);
                color: #ffffff;
            }
        """)
        for fmt, label in [("md", "Markdown (.md)"), ("txt", "Plain Text (.txt)"), ("html", "Rich Document (.html)")]:
            action = QAction(label, self)
            action.triggered.connect(lambda _, f=fmt: self._export_note(f))
            exp_menu.addAction(action)
        self.export_btn.setMenu(exp_menu)

    def _apply_template(self, template_key: str):
        tpl = NOTE_TEMPLATES.get(template_key)
        if not tpl:
            return

        # Flush any edits
        if self.save_timer.isActive():
            self.save_timer.stop()

        new_id = f"note_{int(time.time() * 1000)}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_note = {
            "id": new_id,
            "title": tpl.get("title", "Untitled Note"),
            "category": tpl.get("category", "Dev"),
            "pinned": False,
            "archived": False,
            "created_at": now_str,
            "updated_at": now_str,
            "content": tpl.get("content", ""),
        }
        self.notes_data.insert(0, new_note)
        self.active_note_id = new_id
        self._save_notes()
        self.count_badge.setText(f"{len(self.notes_data)} notes")
        self._refresh_notes_list()
        self._populate_active_note_in_editor()

        # Switch to Edit mode if currently in Preview
        if self.is_preview:
            self._toggle_preview()

        self.body_ed.setFocus()
        self._show_toast(f"✓ Applied {template_key[:22]}...")

    def _export_note(self, fmt: str):
        note = self._get_active_note()
        title = (note.get("title") if note else "") or self.title_in.text().strip() or "Untitled_Note"
        content = (note.get("content", "") if note else "") or self.body_ed.toPlainText()

        # Sanitize filename
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:40].strip('_') or "note"
        export_dir = Path(__file__).resolve().parent.parent / "memory" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        out_path = export_dir / f"{safe_title}.{fmt}"

        try:
            if fmt == "md":
                out_content = f"# {title}\n\n{content}"
            elif fmt == "txt":
                out_content = f"{title}\n\n{content}"
            elif fmt == "html":
                # Render clean HTML using browser
                self.preview_browser.setMarkdown(f"# {title}\n\n{content}")
                html_body = self.preview_browser.toHtml()
                out_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ background: #070b14; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; max-width: 800px; margin: auto; line-height: 1.6; }}
  h1, h2, h3 {{ color: #5B8DEF; }}
  code {{ background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; font-family: monospace; }}
  pre {{ background: #0d1320; padding: 16px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); overflow-x: auto; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
            else:
                out_content = content

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(out_content)

            self._show_toast(f"✓ Exported to memory/exports/{out_path.name}")
        except Exception as e:
            self._show_toast(f"Export failed: {str(e)[:24]}")

    # ─────────────────────────────────────────────────────────────────────────
    # Zen Focus Mode & Live Preview Toggles
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_zen(self):
        self.is_zen = not self.is_zen
        self.left_panel.setVisible(not self.is_zen)
        if self.is_zen:
            self.zen_btn.setText("⛶ Exit Zen")
            self.zen_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(91, 141, 239, 0.18); color: #5B8DEF;
                    border: 1px solid rgba(91, 141, 239, 0.4); border-radius: 6px;
                    padding: 4px 10px;
                }
            """)
            self._show_toast("Zen Focus Mode Enabled")
        else:
            self.zen_btn.setText("⛶ Zen")
            self.zen_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;
                    padding: 4px 10px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
            """)
            self._show_toast("Zen Focus Mode Disabled")

    def _toggle_preview(self):
        self.is_preview = not self.is_preview
        if self.is_preview:
            # Sync text to preview browser
            body = self.body_ed.toPlainText()
            self.preview_browser.setMarkdown(body if body.strip() else "*Empty note...*")
            self.stacked_ed.setCurrentIndex(1)
            self.preview_btn.setText("✏️ Edit")
            self.preview_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(91, 141, 239, 0.15); color: #5B8DEF;
                    border: 1px solid rgba(91, 141, 239, 0.35); border-radius: 5px; padding: 2px 9px; font-size: 11px;
                }
            """)
        else:
            self.stacked_ed.setCurrentIndex(0)
            self.preview_btn.setText("👁️ Preview")
            self.preview_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 2px 9px; font-size: 11px;
                }
                QPushButton:hover { background: rgba(91, 141, 239, 0.15); color: #5B8DEF; }
            """)

    # ─────────────────────────────────────────────────────────────────────────
    # Task Extraction to Execution Engine
    # ─────────────────────────────────────────────────────────────────────────
    def _extract_tasks_to_engine(self):
        content = self.body_ed.toPlainText()
        if not content.strip():
            self._show_toast("⚠️ Note is empty")
            return

        # Find markdown checklist items: - [ ] Task or - [x] Task or * [ ] Task
        checklist_items = []
        for line in content.splitlines():
            m = re.match(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$", line)
            if m:
                done_char, desc = m.groups()
                desc = desc.strip()
                if desc:
                    checklist_items.append((done_char.lower() == "x", desc))

        # Fallback to bullet points if no explicit checkboxes found
        if not checklist_items:
            for line in content.splitlines():
                m = re.match(r"^\s*[-*]\s+([A-Za-z0-9].+)$", line)
                if m:
                    desc = m.group(1).strip()
                    if desc and not desc.startswith("["):
                        checklist_items.append((False, desc))

        if not checklist_items:
            self._show_toast("⚠️ Add checklist items like '- [ ] task'")
            return

        # Map active note category to valid task category
        note_cat = self.cat_box.currentText()
        if note_cat in ("Academic", "Dev", "SIH", "Security", "Ops", "General"):
            target_cat = note_cat
        elif note_cat == "Research":
            target_cat = "Academic"
        elif note_cat == "Security":
            target_cat = "Security"
        elif note_cat == "Ideas":
            target_cat = "Dev"
        else:
            target_cat = "General"

        # Load tasks from memory/tasks.json
        current_tasks = []
        if _TASKS_FILE.exists():
            try:
                with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                    tdata = json.load(f)
                    if isinstance(tdata, dict) and "tasks" in tdata:
                        current_tasks = tdata.get("tasks", [])
            except Exception:
                current_tasks = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        added_count = 0
        for is_done, desc in checklist_items:
            # Check duplicate in current_tasks
            if any(t.get("title", "").strip().lower() == desc.lower() for t in current_tasks):
                continue

            prio = "High" if ("critical" in desc.lower() or "urgent" in desc.lower()) else "Medium"
            new_task = {
                "id": f"task_{int(time.time() * 1000)}_{added_count}",
                "title": desc,
                "category": target_cat,
                "priority": prio,
                "due_date": "Today",
                "done": is_done,
                "created_at": now_str,
                "notes": f"Extracted from Note: {self.title_in.text().strip() or 'Notes Studio'}",
            }
            current_tasks.insert(0, new_task)
            added_count += 1

        if added_count > 0:
            try:
                _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp_f = _TASKS_FILE.with_suffix(".tmp")
                with open(tmp_f, "w", encoding="utf-8") as f:
                    json.dump({"tasks": current_tasks}, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_f, _TASKS_FILE)
                self._show_toast(f"✓ Extracted {added_count} tasks to Task Engine!")
            except Exception as e:
                self._show_toast(f"Error saving tasks: {str(e)[:20]}")
        else:
            self._show_toast("All tasks already in Task Engine")

    # ─────────────────────────────────────────────────────────────────────────
    # Storage & Persistence (Zero-Data-Loss Atomic Storage, Zero Mock Data)
    # ─────────────────────────────────────────────────────────────────────────
    def _load_notes(self) -> list[dict]:
        _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _NOTES_FILE.exists():
            try:
                with open(_NOTES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "notes" in data:
                        notes = data.get("notes")
                        if isinstance(notes, list):
                            return notes
            except Exception:
                pass

        # Zero mock data: Start completely clean with an empty list
        self._write_notes([])
        return []

    def _write_notes(self, notes: list[dict]):
        try:
            _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = _NOTES_FILE.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump({"notes": notes}, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, _NOTES_FILE)
        except Exception:
            try:
                with open(_NOTES_FILE, "w", encoding="utf-8") as f:
                    json.dump({"notes": notes}, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _save_notes(self):
        self._write_notes(self.notes_data)

    def _show_toast(self, msg: str):
        self.toast_lbl.setText(msg)
        self.toast_lbl.show()
        QTimer.singleShot(2200, self.toast_lbl.hide)

    # ─────────────────────────────────────────────────────────────────────────
    # Active Note Handling & Live Auto-Save
    # ─────────────────────────────────────────────────────────────────────────
    def _get_active_note(self) -> Optional[dict]:
        if not self.active_note_id:
            return None
        for n in self.notes_data:
            if n.get("id") == self.active_note_id:
                return n
        return None

    def _on_content_changed(self):
        if self._is_loading_note:
            return
        if not self._get_active_note():
            title_text = self.title_in.text().strip()
            body_text = self.body_ed.toPlainText().strip()
            if not title_text and not body_text:
                return
            new_id = f"note_{int(time.time() * 1000)}"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_note = {
                "id": new_id,
                "title": self.title_in.text().strip() or "Untitled Note",
                "category": self.cat_box.currentText() or "Quick Note",
                "pinned": False,
                "archived": False,
                "created_at": now_str,
                "updated_at": now_str,
                "content": self.body_ed.toPlainText(),
            }
            self.notes_data.insert(0, new_note)
            self.active_note_id = new_id
            self.count_badge.setText(f"{len(self.notes_data)} notes")
            self._save_notes()
            self._refresh_notes_list()
            return
        self._update_word_metrics()
        self.save_timer.start()

    def _update_word_metrics(self):
        txt = self.body_ed.toPlainText().strip()
        words = len(txt.split()) if txt else 0
        chars = len(txt)
        read_min = max(1, round(words / 200)) if words > 0 else 0
        self.word_metrics_lbl.setText(f"{words} words · {chars} chars · ~{read_min}m read")

    def _auto_save_active(self):
        note = self._get_active_note()
        if not note:
            return

        new_title = self.title_in.text().strip() or "Untitled Note"
        new_content = self.body_ed.toPlainText()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        note["title"] = new_title
        note["content"] = new_content
        note["updated_at"] = now_str
        self._save_notes()

        self.saved_status_lbl.setText(f"✓ Auto-saved to memory · {now_str}")
        self._refresh_notes_list()

    def _populate_active_note_in_editor(self):
        note = self._get_active_note()
        self._is_loading_note = True
        if note:
            self.editor_panel.setEnabled(True)
            self.title_in.setText(note.get("title", ""))
            self.body_ed.setPlainText(note.get("content", ""))

            # Category
            cat = note.get("category", "Quick Note")
            idx = self.cat_box.findText(cat)
            if idx >= 0:
                self.cat_box.setCurrentIndex(idx)

            # Pin button (Fixed 28x24 icon)
            if note.get("pinned"):
                self.pin_btn.setStyleSheet("background: rgba(245, 158, 11, 0.15); color: #D9A441; border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 5px;")
            else:
                self.pin_btn.setStyleSheet("background: transparent; color: #64748b; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px;")

            # Archive button
            if note.get("archived"):
                self.archive_btn.setStyleSheet("QPushButton { background: rgba(245, 158, 11, 0.15); color: #D9A441; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 5px; }")
            else:
                self.archive_btn.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px; } QPushButton:hover { color: #D9A441; }")

            t = note.get("updated_at") or note.get("created_at") or "Today"
            self.saved_status_lbl.setText(f"✓ Auto-saved to memory · {t}")
            self._update_word_metrics()
        else:
            self.title_in.clear()
            self.title_in.setPlaceholderText("Untitled Note (type to start drafting)...")
            self.body_ed.clear()
            self.body_ed.setPlaceholderText("Write thoughts, code snippets, research findings, or meeting takeaways...")
            self.word_metrics_lbl.setText("0 words · 0 chars")
            self.saved_status_lbl.setText("Ready · Start typing to create a note")
            self.pin_btn.setStyleSheet("background: transparent; color: #64748b; border: 1px solid rgba(255,255,255,0.08); border-radius: 5px;")
            self.editor_panel.setEnabled(True)
        self._is_loading_note = False

    def _select_note(self, note: dict):
        if self.active_note_id == note.get("id"):
            return
        # Flush current edits before switching
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._auto_save_active()

        self.active_note_id = note.get("id")
        self._populate_active_note_in_editor()
        if self.is_preview:
            # Refresh preview content
            body = self.body_ed.toPlainText()
            self.preview_browser.setMarkdown(body if body.strip() else "*Empty note...*")
        self._refresh_notes_list()

    # ─────────────────────────────────────────────────────────────────────────
    # Note Actions (Add, Delete, Pin, Archive, Copy, AI Review, AI Polish, Commit)
    # ─────────────────────────────────────────────────────────────────────────
    def _add_new_note(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._auto_save_active()

        new_id = f"note_{int(time.time() * 1000)}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_note = {
            "id": new_id,
            "title": "",
            "category": self.active_filter_cat if self.active_filter_cat in NOTE_CATEGORY_COLORS else "Quick Note",
            "pinned": False,
            "archived": False,
            "created_at": now_str,
            "updated_at": now_str,
            "content": "",
        }
        self.notes_data.insert(0, new_note)
        self.active_note_id = new_id
        self._save_notes()
        self.count_badge.setText(f"{len(self.notes_data)} notes")
        self._refresh_notes_list()
        self._populate_active_note_in_editor()
        if self.is_preview:
            self._toggle_preview()
        self.title_in.setFocus()
        self._show_toast("✓ New note created")

    def _delete_note(self, note: dict):
        nid = note.get("id")
        self.notes_data = [n for n in self.notes_data if n.get("id") != nid]
        self._save_notes()
        self.count_badge.setText(f"{len(self.notes_data)} notes")

        if self.active_note_id == nid:
            self.active_note_id = self.notes_data[0]["id"] if self.notes_data else None
            self._populate_active_note_in_editor()

        self._refresh_notes_list()
        self._show_toast("Note deleted")

    def _delete_active_note(self):
        note = self._get_active_note()
        if note:
            self._delete_note(note)

    def _toggle_active_pin(self):
        note = self._get_active_note()
        if not note:
            return
        note["pinned"] = not note.get("pinned", False)
        self._save_notes()
        self._populate_active_note_in_editor()
        self._refresh_notes_list()
        self._show_toast("Pinned to top" if note["pinned"] else "Unpinned")

    def _toggle_active_archive(self):
        note = self._get_active_note()
        if not note:
            return
        note["archived"] = not note.get("archived", False)
        self._save_notes()
        self._populate_active_note_in_editor()
        self._refresh_notes_list()
        self._show_toast("Archived note" if note["archived"] else "Unarchived note")

    def _on_category_changed(self):
        if self._is_loading_note:
            return
        note = self._get_active_note()
        if not note:
            return
        note["category"] = self.cat_box.currentText()
        self._save_notes()
        self._refresh_notes_list()

    def _copy_note(self):
        note = self._get_active_note()
        title = (note.get("title") if note else "") or self.title_in.text().strip()
        content = (note.get("content", "") if note else "") or self.body_ed.toPlainText()
        text = f"# {title}\n\n{content}"
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            self._show_toast("📋 Copied note to clipboard")

    def _polish_note(self):
        # Flush any pending edits immediately
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._auto_save_active()

        note = self._get_active_note()
        title = (note.get("title") if note else "") or self.title_in.text().strip()
        content = (note.get("content", "") if note else "") or self.body_ed.toPlainText().strip()

        if not title and not content:
            self._show_toast("⚠️ Enter a note title or text first")
            return

        cmd = (
            f"Please polish, structure, format with clean Markdown headings, and refine the prose of my note '{title}':\n\n"
            f"{content}\n\n"
            "Maintain technical precision, clarity, and senior-dev executive formatting, Boss."
        )
        self._show_toast("✨ Dispatched note to NEO for polishing")
        self.note_action_triggered.emit(cmd)

    def _ask_neo_review(self):
        # Flush any pending edits immediately
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._auto_save_active()

        note = self._get_active_note()
        title = (note.get("title") if note else "") or self.title_in.text().strip()
        content = (note.get("content", "") if note else "") or self.body_ed.toPlainText().strip()

        if not title and not content:
            self._show_toast("⚠️ Enter a note title or text first")
            return

        if not content:
            # Boss entered a title or prompt thought: NEO expands and brainstorms
            cmd = (
                f"I have a note titled '{title}'. "
                "Help me brainstorm, expand on this thought, outline key ideas, and provide insightful reflections and actionable next steps, Boss."
            )
        else:
            # Both title and content present
            cmd = (
                f"Review and analyze my note '{title}':\n\n{content}\n\n"
                "Provide concise executive feedback, highlight key insights, and formulate 3 immediate tactical next steps, Boss."
            )
        display_title = title if title else "Note"
        self._show_toast(f"⚡ Dispatched '{display_title[:20]}...' to NEO")
        self.note_action_triggered.emit(cmd)

    def _commit_to_brain(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._auto_save_active()

        note = self._get_active_note()
        title = (note.get("title") if note else "") or self.title_in.text().strip()
        content = (note.get("content", "") if note else "") or self.body_ed.toPlainText().strip()

        if not title and not content:
            self._show_toast("⚠️ Enter a note title or text first")
            return

        cat = note.get("category", self.cat_box.currentText()) if note else self.cat_box.currentText()
        text_to_save = content if content else f"Concept/Topic: {title}"
        memory_fact = f"Note [{title or 'Quick Note'}] ({cat}): {text_to_save}"
        self.note_saved.emit(f"Remember this note in semantic memory: {memory_fact}")
        self._show_toast("🧠 Committed note to NEO Long-Term Memory")

    # ─────────────────────────────────────────────────────────────────────────
    # Search, Filtering, Dynamic Hashtags & Sidebar Refresh
    # ─────────────────────────────────────────────────────────────────────────
    def _set_category_filter(self, cat: str):
        self.active_filter_cat = cat
        self.active_tag_filter = None
        for c, btn in self.filter_buttons.items():
            if c == cat:
                btn.setStyleSheet("background: rgba(91, 141, 239, 0.15); color: #5B8DEF; border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 4px; padding: 2px 7px;")
                btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            else:
                btn.setStyleSheet("background: rgba(255, 255, 255, 0.02); color: #64748b; border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 4px; padding: 2px 6px;")
                btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
        self._refresh_notes_list()

    def _set_tag_filter(self, tag: Optional[str]):
        self.active_tag_filter = tag
        self._refresh_notes_list()

    def _on_search_changed(self, text: str):
        self.search_keyword = text.lower().strip()
        self._refresh_notes_list()

    def _refresh_hashtags_bar(self):
        # Clear existing hashtag widgets
        for i in reversed(range(self.tags_lay.count())):
            item = self.tags_lay.itemAt(i)
            if item and item.widget():
                w = item.widget()
                self.tags_lay.removeWidget(w)
                w.deleteLater()

        # Extract unique tags from non-archived notes
        all_tags = []
        for n in self.notes_data:
            if not n.get("archived", False):
                t_str = (n.get("title", "") + " " + (n.get("content", "")))
                tags = re.findall(r"#([a-zA-Z0-9_\-]+)", t_str)
                all_tags.extend([t.lower() for t in tags])

        unique_tags = list(dict.fromkeys(all_tags))[:5] # Top 5 tags
        if not unique_tags:
            self.tags_frame.hide()
            return

        self.tags_frame.show()
        # "All tags" button
        all_btn = QPushButton("all")
        all_btn.setFont(QFont("Segoe UI", 7))
        all_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.active_tag_filter is None:
            all_btn.setStyleSheet("background: rgba(91, 141, 239, 0.15); color: #5B8DEF; border-radius: 3px; padding: 1px 5px; border: none;")
        else:
            all_btn.setStyleSheet("background: transparent; color: #64748b; border-radius: 3px; padding: 1px 5px; border: none;")
        all_btn.clicked.connect(lambda: self._set_tag_filter(None))
        self.tags_lay.addWidget(all_btn)

        for tag in unique_tags:
            tb = QPushButton(f"#{tag}")
            tb.setFont(QFont("Segoe UI", 7))
            tb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if self.active_tag_filter == tag:
                tb.setStyleSheet("background: rgba(91, 141, 239, 0.2); color: #5B8DEF; border-radius: 3px; padding: 1px 5px; border: 1px solid rgba(91, 141, 239, 0.4);")
            else:
                tb.setStyleSheet("background: rgba(255, 255, 255, 0.03); color: #94a3b8; border-radius: 3px; padding: 1px 5px; border: none;")
            tb.clicked.connect(lambda _, tg=tag: self._set_tag_filter(tg))
            self.tags_lay.addWidget(tb)
        self.tags_lay.addStretch()

    def _refresh_notes_list(self):
        # Refresh hashtags bar
        self._refresh_hashtags_bar()

        # Clear existing cards
        for i in reversed(range(self.cards_lay.count())):
            item = self.cards_lay.itemAt(i)
            if item and item.widget():
                w = item.widget()
                self.cards_lay.removeWidget(w)
                w.deleteLater()

        # Sort: Pinned first, then by updated_at descending
        sorted_notes = sorted(
            self.notes_data,
            key=lambda n: (not n.get("pinned", False), n.get("updated_at", "")),
            reverse=False
        )

        # Filter
        kw = self.search_keyword
        cat = self.active_filter_cat
        tag = self.active_tag_filter
        filtered = []

        for n in sorted_notes:
            is_archived = n.get("archived", False)
            if cat == "Archive":
                if not is_archived:
                    continue
            else:
                if is_archived:
                    continue
                if cat != "All" and n.get("category") != cat:
                    continue

            # Tag filter
            if tag:
                t_str = (n.get("title", "") + " " + (n.get("content", ""))).lower()
                if f"#{tag.lower()}" not in t_str and tag.lower() not in t_str:
                    continue

            # Search keyword
            if kw:
                title = n.get("title", "").lower()
                body = n.get("content", "").lower()
                if kw not in title and kw not in body:
                    continue
            filtered.append(n)

        if not filtered:
            empty_lbl = QLabel("No notes found.")
            empty_lbl.setFont(QFont("Segoe UI", 8))
            empty_lbl.setStyleSheet("color: #475569; padding: 16px 8px; border: none; background: transparent;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_lay.insertWidget(0, empty_lbl)
            return

        for idx, n in enumerate(filtered):
            is_act = (n.get("id") == self.active_note_id)
            card = NeoNoteCard(n, is_active=is_act, parent=self.cards_cont)
            card.clicked.connect(self._select_note)
            card.deleted.connect(self._delete_note)
            self.cards_lay.insertWidget(idx, card)


# ─────────────────────────────────────────────────────────────────────────────
#  7. SENIOR-DEV PROJECT COMMAND CENTER & AUTONOMOUS GENESIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_BLUEPRINTS = {
    "🤖 AI & Autonomous Agent": {
        "category": "AI/Agent",
        "description": "Python 3.12+ async autonomous agent with tool registry, LLM client wrappers, SQLite memory, and test harness.",
        "run_command": "python main.py",
        "files": {
            "main.py": '''"""
Autonomous Agent Entry Point — Built via NEO Project Genesis Engine.
"""
import asyncio
import os
from dotenv import load_dotenv
from core.agent import AutonomousAgent
from core.tools import search_web, read_file

load_dotenv()

async def main():
    print("🚀 Initializing Autonomous Agent Subsystem...")
    agent = AutonomousAgent(name="{name}", model="gemini-2.5-flash")
    agent.register_tool(search_web)
    agent.register_tool(read_file)
    
    print(f"✓ Agent [{agent.name}] online and listening for missions.")
    result = await agent.run_step("Survey workspace and execute initial diagnostics.")
    print("Mission Output:", result)

if __name__ == "__main__":
    asyncio.run(main())
''',
            "core/agent.py": '''"""
Autonomous Agent Architecture & State Controller.
"""
import os
from typing import Callable, Any

class AutonomousAgent:
    def __init__(self, name: str = "Agent", model: str = "gemini-2.5-flash"):
        self.name = name
        self.model = model
        self.tools: dict[str, Callable] = {}
        self.history: list[dict] = []

    def register_tool(self, func: Callable):
        self.tools[func.__name__] = func

    async def run_step(self, prompt: str) -> str:
        self.history.append({"role": "user", "content": prompt})
        response = f"[{self.name}] Processed: '{prompt}' using model {self.model}. Subsystems operational."
        self.history.append({"role": "assistant", "content": response})
        return response
''',
            "core/tools.py": '''"""
Agent Tool Registry & Execution Wrappers.
"""
def search_web(query: str) -> str:
    """Perform a web search query."""
    return f"Search results for query: {query}"

def read_file(file_path: str) -> str:
    """Read contents of a local file safely."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"
''',
            "config/settings.py": '''"""
Application Configuration & Secret Schemas.
"""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
''',
            "tests/test_agent.py": '''"""
Unit Tests for Autonomous Agent Core.
"""
import pytest
import asyncio
from core.agent import AutonomousAgent

@pytest.mark.asyncio
async def test_agent_run():
    agent = AutonomousAgent(name="TestAgent")
    res = await agent.run_step("ping")
    assert "TestAgent" in res
    assert len(agent.history) == 2
''',
            ".env.example": '''# Environment Secrets & API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
DEBUG=True
ENVIRONMENT=development
''',
            "requirements.txt": '''pydantic>=2.7.0
requests>=2.31.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
python-dotenv>=1.0.0
''',
            "README.md": '''# {name}

> Autonomous AI Agent Subsystem — Scaffolded by **NEO Project Genesis Engine**.

## 🚀 Quickstart
```bash
# 1. Activate virtual environment
source .venv/bin/activate  # Or on Windows: .venv\\Scripts\\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env

# 4. Launch agent
python main.py
```

## 🏛️ Architecture
- `core/agent.py`: Agent state machine & memory loop.
- `core/tools.py`: Extensible tool registry.
- `config/settings.py`: Validated configuration schema.
- `tests/`: Automated pytest unit test suite.
'''
        }
    },
    "⚡ High-Performance FastAPI Backend": {
        "category": "FastAPI/Web",
        "description": "Enterprise-ready modular FastAPI 0.111+ service with Pydantic v2 schemas, CORS, Dockerfile, and pytest suite.",
        "run_command": "uvicorn main:app --reload --port 8000",
        "files": {
            "main.py": '''"""
FastAPI Microservice — Scaffolded via NEO Project Genesis Engine.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.endpoints import router as v1_router
from core.config import settings

app = FastAPI(
    title="{name} API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"service": "{name}", "status": "ONLINE", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
''',
            "api/v1/endpoints.py": '''"""
API Version 1 Endpoint Handlers.
"""
from fastapi import APIRouter
from schemas.payload import HealthResponse, TaskPayload, TaskResult

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="HEALTHY", version="1.0.0")

@router.post("/execute", response_model=TaskResult)
def execute_task(payload: TaskPayload):
    return TaskResult(
        task_id=payload.task_id,
        status="COMPLETED",
        output=f"Processed operation: '{payload.action}' successfully."
    )
''',
            "core/config.py": '''"""
Application Settings Schema.
"""
import os
from pydantic import BaseModel

class Settings(BaseModel):
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change_me_in_production")

settings = Settings()
''',
            "schemas/payload.py": '''"""
Pydantic v2 Contract Data Schemas.
"""
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str
    version: str

class TaskPayload(BaseModel):
    task_id: str
    action: str

class TaskResult(BaseModel):
    task_id: str
    status: str
    output: str
''',
            "tests/test_api.py": '''"""
FastAPI TestClient Verification Suite.
"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ONLINE"

def test_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "HEALTHY"
''',
            "Dockerfile": '''FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
            "docker-compose.yml": '''version: "3.8"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=True
      - PORT=8000
''',
            ".env.example": '''HOST=0.0.0.0
PORT=8000
DEBUG=True
SECRET_KEY=supersecretkeyhere
''',
            "requirements.txt": '''fastapi>=0.111.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
httpx>=0.27.0
pytest>=8.0.0
''',
            "README.md": '''# {name}

> High-Performance Microservice — Scaffolded via **NEO Project Genesis Engine**.

## 🚀 Quickstart
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run with uvicorn auto-reload
python main.py

# 3. Interactive Swagger documentation
# Open http://localhost:8000/docs in your browser
```
'''
        }
    },
    "🛡️ Cybersecurity & CTF Toolkit": {
        "category": "Security/CTF",
        "description": "Modular security toolkit with socket port scanning, HTTP endpoint fuzzing, and automated vulnerability report generator.",
        "run_command": "python main.py --help",
        "files": {
            "main.py": '''"""
Cybersecurity & CTF Operational Toolkit — Built via NEO Project Genesis Engine.
"""
import argparse
from modules.scanner import PortScanner
from modules.fuzzer import HTTPFuzzer
from modules.reporter import generate_assessment_report

def main():
    parser = argparse.ArgumentParser(description="{name} — Security Assessment Suite")
    subparsers = parser.add_subparsers(dest="command", help="Operational Subcommands")

    scan_p = subparsers.add_parser("scan", help="Scan host for open TCP ports")
    scan_p.add_argument("--host", default="127.0.0.1", help="Target IP or hostname")
    scan_p.add_argument("--ports", default="21,22,80,443,8000,8080", help="Comma-separated ports")

    fuzz_p = subparsers.add_parser("fuzz", help="Fuzz web endpoint paths")
    fuzz_p.add_argument("--url", required=True, help="Target URL (e.g. http://target.local)")

    subparsers.add_parser("report", help="Generate executive audit report")

    args = parser.parse_args()

    if args.command == "scan":
        ports = [int(p.strip()) for p in args.ports.split(",") if p.strip().isdigit()]
        scanner = PortScanner(args.host)
        scanner.run_scan(ports)
    elif args.command == "fuzz":
        fuzzer = HTTPFuzzer(args.url)
        fuzzer.fuzz_endpoints()
    elif args.command == "report":
        generate_assessment_report("{name}", "Assessment Report")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
''',
            "modules/scanner.py": '''"""
Concurrent Port & Socket Banner Scanner.
"""
import socket

class PortScanner:
    def __init__(self, target_host: str):
        self.host = target_host

    def run_scan(self, ports: list[int]):
        print(f"[*] Scanning {self.host} across {len(ports)} target ports...")
        for port in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            result = s.connect_ex((self.host, port))
            if result == 0:
                print(f"  [+] Port {port:5d} is OPEN")
            s.close()
        print("[*] Scan complete.")
''',
            "modules/fuzzer.py": '''"""
HTTP Endpoint & Parameter Fuzzing Engine.
"""
import requests

class HTTPFuzzer:
    def __init__(self, target_url: str):
        self.url = target_url.rstrip("/")

    def fuzz_endpoints(self):
        common_paths = ["admin", "api", "login", "config", "backup", "v1", "robots.txt"]
        print(f"[*] Fuzzing endpoints on {self.url}...")
        for path in common_paths:
            target = f"{self.url}/{path}"
            try:
                r = requests.get(target, timeout=2.0)
                if r.status_code in (200, 301, 302, 403):
                    print(f"  [!] Found: {target} (Status: {r.status_code})")
            except Exception:
                pass
        print("[*] Fuzzing complete.")
''',
            "modules/reporter.py": '''"""
Executive Markdown Security Assessment Report Generator.
"""
from datetime import datetime

def generate_assessment_report(target_name: str, out_file: str = "audit_report.md"):
    report_content = f"""# Security Assessment Report: {target_name}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} via NEO Security Studio

## 1. Executive Summary
Brief summary of the security audit, scope, and threat posture.

## 2. Identified Vulnerabilities & Remediation
- [ ] Implement parameterized input validation
- [ ] Enforce rate-limiting and WAF rules
- [ ] Rotate exposed API tokens
"""
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"[✓] Generated executive assessment report: {out_file}")
''',
            "requirements.txt": '''requests>=2.31.0
pytest>=8.0.0
''',
            "README.md": '''# {name} — Cybersecurity & CTF Toolkit

> Tactical Security & Assessment Toolkit — Scaffolded via **NEO Project Genesis Engine**.

## 🚀 Usage
```bash
# Scan target
python main.py scan --host 127.0.0.1 --ports 22,80,443,8000

# Fuzz web endpoints
python main.py fuzz --url http://target.local

# Generate executive report
python main.py report
```
'''
        }
    },
    "💻 Executive CLI Tool": {
        "category": "CLI/Tooling",
        "description": "Standard PEP 621 command-line tool with argument parser, packaging metadata, and test harness.",
        "run_command": "python cli.py --help",
        "files": {
            "cli.py": '''"""
CLI Application Entry Point — Scaffolded via NEO Project Genesis Engine.
"""
import argparse
import sys
from core.engine import execute_operation

def main():
    parser = argparse.ArgumentParser(
        prog="{name}",
        description="Executive Command Line Interface — Built with NEO"
    )
    parser.add_argument("command", choices=["status", "run", "benchmark"], help="Operation to execute")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose diagnostics")
    
    args = parser.parse_args()
    print(f"[{args.command.upper()}] Initializing {args.command}...")
    result = execute_operation(args.command, verbose=args.verbose)
    print("✓ Result:", result)

if __name__ == "__main__":
    main()
''',
            "core/engine.py": '''"""
CLI Core Logic & Operations Engine.
"""
def execute_operation(operation: str, verbose: bool = False) -> str:
    if verbose:
        print(f"[DIAGNOSTIC] Executing operation: {operation}")
    return f"Operation '{operation}' completed successfully."
''',
            "pyproject.toml": '''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = "Executive CLI Tool scaffolded with NEO"
authors = [{{ name="Rahman Fayid" }}]
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
{name} = "cli:main"
''',
            "tests/test_cli.py": '''"""
CLI Unit Tests.
"""
from core.engine import execute_operation

def test_operation():
    res = execute_operation("status")
    assert "status" in res
''',
            "README.md": '''# {name}

> Command-Line Tool — Scaffolded via **NEO Project Genesis Engine**.

## 🚀 Installation & Usage
```bash
# Run locally
python cli.py status

# Install in editable mode
pip install -e .
{name} run
```
'''
        }
    }
}


class ProjectGenesisDialog(QDialog):
    """
    Executive Autonomous Project Genesis & Scaffolding Wizard.
    Provisions complete runnable project repositories with Git, .gitignore,
    virtualenvs, NEO Task Engine milestones, and Notes Architecture RFCs.
    """
    def __init__(self, default_parent_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Autonomous Project Genesis Engine")
        self.setFixedSize(540, 560)
        self.setStyleSheet("""
            QDialog {
                background: #090e1a;
                color: #f1f5f9;
                border: 1px solid rgba(91, 141, 239, 0.3);
                border-radius: 6px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        # Title
        hdr = QHBoxLayout()
        t_lbl = QLabel("⚡ Autonomous Project Genesis")
        t_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        hdr.addWidget(t_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        sub_l = QLabel("Scaffold a complete production-grade repository in seconds.")
        sub_l.setFont(QFont("Segoe UI", 8))
        sub_l.setStyleSheet("color: #64748b; border: none; background: transparent;")
        lay.addWidget(sub_l)

        # Form: Project Name
        lay.addWidget(QLabel("PROJECT NAME:"))
        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("e.g. CipherGuard, AutonomousAgent, SIH-Portal")
        self.name_in.setFont(QFont("Segoe UI", 9))
        self.name_in.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px; color: #ffffff; padding: 6px 10px;
            }
            QLineEdit:focus { border-color: #5B8DEF; }
        """)
        lay.addWidget(self.name_in)

        # Form: Location
        lay.addWidget(QLabel("PARENT LOCATION DIRECTORY:"))
        loc_row = QHBoxLayout()
        self.loc_in = QLineEdit()
        self.loc_in.setText(default_parent_dir)
        self.loc_in.setFont(QFont("Segoe UI", 8))
        self.loc_in.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px; color: #cbd5e1; padding: 6px 10px;
            }
        """)
        loc_row.addWidget(self.loc_in, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setFont(QFont("Segoe UI", 8))
        browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        browse_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 12px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.15); color: #5B8DEF; }
        """)
        browse_btn.clicked.connect(self._browse_location)
        loc_row.addWidget(browse_btn)
        lay.addLayout(loc_row)

        # Form: Stack Blueprint
        lay.addWidget(QLabel("STACK BLUEPRINT:"))
        self.bp_combo = QComboBox()
        self.bp_combo.setFont(QFont("Segoe UI", 8))
        self.bp_combo.addItems(list(PROJECT_BLUEPRINTS.keys()) + ["✨ Custom Prompt Genesis"])
        self.bp_combo.setStyleSheet("""
            QComboBox {
                background: rgba(15, 23, 42, 0.8); color: #f1f5f9;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 6px; padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #0d1322; color: #f1f5f9;
                selection-background-color: rgba(91, 141, 239, 0.2);
            }
        """)
        self.bp_combo.currentIndexChanged.connect(self._on_blueprint_changed)
        lay.addWidget(self.bp_combo)

        # Blueprint Description Banner
        self.desc_lbl = QLabel(list(PROJECT_BLUEPRINTS.values())[0]["description"])
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setFont(QFont("Segoe UI", 7))
        self.desc_lbl.setStyleSheet("""
            QLabel {
                background: rgba(91, 141, 239, 0.05); color: #94a3b8;
                border-left: 2px solid #5B8DEF; border-radius: 4px; padding: 6px;
            }
        """)
        lay.addWidget(self.desc_lbl)

        # Form: Custom Prompt (Optional)
        self.prompt_in = QTextEdit()
        self.prompt_in.setPlaceholderText("Optional: Describe your custom project concept or extra packages (e.g. 'Build Telegram bot with async SQLite')...")
        self.prompt_in.setFont(QFont("Segoe UI", 8))
        self.prompt_in.setFixedHeight(48)
        self.prompt_in.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px; color: #e2e8f0; padding: 4px 8px;
            }
        """)
        lay.addWidget(self.prompt_in)

        # Automated Provisioning Checkboxes
        lay.addWidget(QLabel("AUTOMATED PROVISIONING:"))
        opts_box = QFrame()
        opts_box.setStyleSheet("background: transparent; border: none;")
        opts_lay = QVBoxLayout(opts_box)
        opts_lay.setContentsMargins(0, 0, 0, 0)
        opts_lay.setSpacing(4)

        self.cb_git = QCheckBox("Initialize Git repository && commit initial genesis")
        self.cb_git.setChecked(True)
        self.cb_git.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        opts_lay.addWidget(self.cb_git)

        self.cb_tasks = QCheckBox("Synchronize Phase 1 milestones to NEO Task Engine")
        self.cb_tasks.setChecked(True)
        self.cb_tasks.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        opts_lay.addWidget(self.cb_tasks)

        self.cb_notes = QCheckBox("Generate Architecture RFC blueprint in NEO Notes Studio")
        self.cb_notes.setChecked(True)
        self.cb_notes.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        opts_lay.addWidget(self.cb_notes)
        lay.addWidget(opts_box)

        lay.addStretch()

        # Action Buttons
        btn_r = QHBoxLayout()
        btn_r.setSpacing(10)

        cancel_b = QPushButton("Cancel")
        cancel_b.setFont(QFont("Segoe UI", 8))
        cancel_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_b.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px 14px;
            }
            QPushButton:hover { color: #f1f5f9; }
        """)
        cancel_b.clicked.connect(self.reject)
        btn_r.addWidget(cancel_b)

        btn_r.addStretch()

        self.scaffold_btn = QPushButton("🚀 Scaffold && Launch Project")
        self.scaffold_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.scaffold_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.scaffold_btn.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 6px; padding: 6px 18px;
            }
            QPushButton:hover { background: #4376D6; }
        """)
        self.scaffold_btn.clicked.connect(self.accept)
        btn_r.addWidget(self.scaffold_btn)
        lay.addLayout(btn_r)

    def _browse_location(self):
        d = QFileDialog.getExistingDirectory(self, "Select Parent Folder", self.loc_in.text())
        if d:
            self.loc_in.setText(d)

    def _on_blueprint_changed(self, idx: int):
        bp_name = self.bp_combo.currentText()
        bp = PROJECT_BLUEPRINTS.get(bp_name)
        if bp:
            self.desc_lbl.setText(bp["description"])
        else:
            self.desc_lbl.setText("Custom AI Genesis: Builds tailored project structure & logic based on your custom prompt.")

    def get_data(self) -> dict:
        return {
            "name": re.sub(r'[^a-zA-Z0-9_\-]', '', self.name_in.text().strip()) or "NewProject",
            "parent_dir": Path(self.loc_in.text().strip()).resolve(),
            "blueprint": self.bp_combo.currentText(),
            "custom_prompt": self.prompt_in.toPlainText().strip(),
            "init_git": self.cb_git.isChecked(),
            "sync_tasks": self.cb_tasks.isChecked(),
            "sync_notes": self.cb_notes.isChecked(),
        }


class NeoProjectsView(QWidget):
    """
    Executive Mission Control & Project Command Center for NEO.
    Provides multi-workspace portfolio switching, live Git repository telemetry,
    intelligent filterable file tree with lazy loading, code inspector with AI review hooks,
    KPI analytics (LOC, repo size, modules), run/test docks, and AI architect roadmap generator.
    """
    file_open_requested = pyqtSignal(str)       # Emits absolute file path for assistant ingestion
    project_action_triggered = pyqtSignal(str)  # Emits prompt to NEO chat (architect, review, sprint)

    def __init__(self, workspace_path: str = ".", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        self.default_workspace = Path(workspace_path).resolve()
        self.workspace_path = self.default_workspace
        self.hide_cache_files = True

        # Load projects registry
        self.projects_data = self._load_projects()
        active_proj = self._get_active_project()
        if active_proj and Path(active_proj.get("path", "")).exists():
            self.workspace_path = Path(active_proj["path"]).resolve()

        self._active_file_path: Optional[Path] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        # ── 1. Executive Mission Header ──
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        t_lbl = QLabel("Projects")
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(t_lbl)

        # Project Switcher Dropdown
        self.proj_combo = QComboBox()
        self.proj_combo.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.proj_combo.setFixedHeight(28)
        self.proj_combo.setStyleSheet("""
            QComboBox {
                background: rgba(15, 23, 42, 0.8); color: #f1f5f9;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 6px;
                padding: 2px 10px; min-width: 170px;
            }
            QComboBox:hover { border-color: #5B8DEF; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #0d1322; color: #f1f5f9;
                selection-background-color: rgba(91, 141, 239, 0.2);
                border: 1px solid rgba(91, 141, 239, 0.25); border-radius: 6px; padding: 4px;
            }
        """)
        self._populate_project_selector()
        self.proj_combo.currentIndexChanged.connect(self._on_project_switched)
        hdr.addWidget(self.proj_combo)

        # ⚡ Scaffold Project / Genesis Button
        scaffold_btn = QPushButton("⚡ New Project")
        scaffold_btn.setToolTip("Scaffold a complete production repository from scratch with Git, tests, and blueprints")
        scaffold_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        scaffold_btn.setFixedHeight(28)
        scaffold_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        scaffold_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.15); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.4); border-radius: 6px; padding: 2px 12px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.28); color: #ffffff; }
        """)
        scaffold_btn.clicked.connect(self._open_genesis_wizard)
        hdr.addWidget(scaffold_btn)

        # + Add Project / Open Folder Button
        add_proj_btn = QPushButton("+ Open Folder")
        add_proj_btn.setToolTip("Add and switch to any project folder on your PC")
        add_proj_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        add_proj_btn.setFixedHeight(28)
        add_proj_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_proj_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 2px 10px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.15); color: #5B8DEF; }
        """)
        add_proj_btn.clicked.connect(self._add_new_project)
        hdr.addWidget(add_proj_btn)

        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("""
            QLabel {
                background: rgba(15, 23, 42, 0.95); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 6px;
                padding: 4px 12px; font-size: 11px;
            }
        """)
        self.toast_lbl.hide()
        hdr.addWidget(self.toast_lbl)

        hdr.addStretch()

        # Git Status Pill
        self.git_badge = QPushButton("🌿 git: checking...")
        self.git_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.git_badge.setFixedHeight(28)
        self.git_badge.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.git_badge.setStyleSheet("""
            QPushButton {
                color: #34d399; background: rgba(52, 211, 153, 0.1);
                border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 6px; padding: 2px 10px;
            }
            QPushButton:hover { background: rgba(52, 211, 153, 0.2); }
        """)
        self._init_git_menu()
        hdr.addWidget(self.git_badge)

        # AI Commit Message Generator
        ai_commit_btn = QPushButton("✨ AI Commit")
        ai_commit_btn.setToolTip("Ask NEO to generate an executive conventional commit message from git diff")
        ai_commit_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        ai_commit_btn.setFixedHeight(28)
        ai_commit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ai_commit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(245, 158, 11, 0.1); color: #D9A441;
                border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 2px 10px;
            }
            QPushButton:hover { background: rgba(245, 158, 11, 0.2); color: #ffffff; }
        """)
        ai_commit_btn.clicked.connect(self._ai_generate_commit)
        hdr.addWidget(ai_commit_btn)

        # AI Project Architect Button
        ai_arch_btn = QPushButton("🤖 AI Architect")
        ai_arch_btn.setToolTip("Ask NEO to analyze architecture and generate a 3-phase technical sprint roadmap")
        ai_arch_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        ai_arch_btn.setFixedHeight(28)
        ai_arch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ai_arch_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.12); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.35); border-radius: 6px; padding: 2px 12px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.25); color: #ffffff; }
        """)
        ai_arch_btn.clicked.connect(self._ai_architect_project)
        hdr.addWidget(ai_arch_btn)

        # Refresh Button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Reload workspace files, git status, and metrics")
        refresh_btn.setFont(QFont("Segoe UI", 9))
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        refresh_btn.clicked.connect(self._refresh_all)
        hdr.addWidget(refresh_btn)

        root.addLayout(hdr)

        # ── 2. Master-Detail Center Splitter ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: rgba(255, 255, 255, 0.05); width: 2px;
            }
            QSplitter::handle:hover { background: #5B8DEF; }
        """)

        # Left Column: Workspace File Explorer (~310px)
        left_panel = QFrame()
        left_panel.setMinimumWidth(260)
        left_panel.setMaximumWidth(420)
        left_panel.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(8)

        # File Filter Search Bar & View Controls
        tree_ctrl = QHBoxLayout()
        tree_ctrl.setSpacing(6)

        self.file_search_in = QLineEdit()
        self.file_search_in.setPlaceholderText("🔍 Filter files...")
        self.file_search_in.setFont(QFont("Segoe UI", 8))
        self.file_search_in.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 6px; color: #ffffff; padding: 4px 8px;
            }
            QLineEdit:focus { border-color: rgba(91, 141, 239, 0.4); }
        """)
        self.file_search_in.textChanged.connect(self._on_search_filter_changed)
        tree_ctrl.addWidget(self.file_search_in, stretch=1)

        self.toggle_cache_btn = QPushButton("👁️ Clean")
        self.toggle_cache_btn.setToolTip("Toggle hidden & cache files (__pycache__, .git, etc.)")
        self.toggle_cache_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Medium))
        self.toggle_cache_btn.setFixedSize(54, 24)
        self.toggle_cache_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_cache_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.1); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.25); border-radius: 5px;
            }
        """)
        self.toggle_cache_btn.clicked.connect(self._toggle_cache_visibility)
        tree_ctrl.addWidget(self.toggle_cache_btn)

        left_lay.addLayout(tree_ctrl)

        # Hierarchical Tree Widget with Lazy Loading
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Size"])
        self.tree_widget.setFont(QFont("Segoe UI", 8))
        self.tree_widget.header().setStyleSheet("""
            QHeaderView::section {
                background: rgba(15, 23, 42, 0.6); color: #64748b;
                border: none; padding: 3px 6px; font-size: 10px; font-weight: bold;
            }
        """)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background: transparent; color: #cbd5e1;
                border: none; outline: none;
            }
            QTreeWidget::item {
                padding: 4px 2px; border-radius: 4px;
            }
            QTreeWidget::item:hover {
                background: rgba(91, 141, 239, 0.08); color: #5B8DEF;
            }
            QTreeWidget::item:selected {
                background: rgba(91, 141, 239, 0.18); color: #ffffff;
            }
        """)
        self.tree_widget.itemClicked.connect(self._on_tree_item_clicked)
        self.tree_widget.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.tree_widget.itemExpanded.connect(self._on_tree_item_expanded)
        left_lay.addWidget(self.tree_widget, stretch=1)

        # Path Status Footer
        self.path_lbl = QLabel(str(self.workspace_path))
        self.path_lbl.setFont(QFont("Segoe UI", 7))
        self.path_lbl.setStyleSheet("color: #475569; border: none; background: transparent;")
        left_lay.addWidget(self.path_lbl)

        self.splitter.addWidget(left_panel)

        # Right Column: Project Intelligence & Code Inspector (Dual-Mode Stack)
        self.right_panel = QFrame()
        self.right_panel.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        right_lay = QVBoxLayout(self.right_panel)
        right_lay.setContentsMargins(18, 14, 18, 14)
        right_lay.setSpacing(10)

        self.stack = QStackedWidget()

        # ── Page 0: Project KPI Dashboard & Embedded README ──
        self.overview_page = QWidget()
        ov_lay = QVBoxLayout(self.overview_page)
        ov_lay.setContentsMargins(0, 0, 0, 0)
        ov_lay.setSpacing(12)

        # KPI Stats Grid (4 Cards)
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)

        self.card_files = self._create_kpi_card("📊 FILES & MODULES", "0 files", "0 dirs")
        self.card_loc   = self._create_kpi_card("📝 CODE VOLUME", "0 LOC", "Across codebase")
        self.card_size  = self._create_kpi_card("💾 STORAGE SIZE", "0 MB", "On physical disk")
        self.card_git   = self._create_kpi_card("🌿 GIT REPOSITORY", "Checking...", "Remote: None")

        kpi_grid.addWidget(self.card_files, 0, 0)
        kpi_grid.addWidget(self.card_loc,   0, 1)
        kpi_grid.addWidget(self.card_size,  0, 2)
        kpi_grid.addWidget(self.card_git,   0, 3)
        ov_lay.addLayout(kpi_grid)

        # Action Command Dock
        dock_frame = QFrame()
        dock_frame.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px; padding: 4px;
            }}
        """)
        dock_lay = QHBoxLayout(dock_frame)
        dock_lay.setSpacing(8)

        dock_title = QLabel("⚡ QUICK COMMANDS:")
        dock_title.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        dock_title.setStyleSheet("color: #64748b; border: none; background: transparent;")
        dock_lay.addWidget(dock_title)

        run_btn = QPushButton("▶ Launch Project")
        run_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        run_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        run_btn.setStyleSheet("""
            QPushButton {
                background: rgba(52, 211, 153, 0.12); color: #34d399;
                border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 5px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(52, 211, 153, 0.25); color: #ffffff; }
        """)
        run_btn.clicked.connect(self._launch_project)
        dock_lay.addWidget(run_btn)

        test_btn = QPushButton("🧪 Run Tests")
        test_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        test_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        test_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.1); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.28); border-radius: 5px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.22); color: #ffffff; }
        """)
        test_btn.clicked.connect(self._run_tests)
        dock_lay.addWidget(test_btn)

        clean_btn = QPushButton("🧹 Purge Cache")
        clean_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        clean_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clean_btn.setStyleSheet("""
            QPushButton {
                background: rgba(245, 158, 11, 0.1); color: #D9A441;
                border: 1px solid rgba(245, 158, 11, 0.28); border-radius: 5px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(245, 158, 11, 0.2); color: #ffffff; }
        """)
        clean_btn.clicked.connect(self._purge_cache)
        dock_lay.addWidget(clean_btn)

        gh_btn = QPushButton("🌐 View on GitHub")
        gh_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        gh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        gh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        gh_btn.clicked.connect(self._open_github)
        dock_lay.addWidget(gh_btn)

        dock_lay.addStretch()
        ov_lay.addWidget(dock_frame)

        # Embedded README / Architecture Document View
        readme_hdr = QLabel("📖 PROJECT ARCHITECTURE & README")
        readme_hdr.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        readme_hdr.setStyleSheet("color: #94a3b8; border: none; background: transparent; padding-top: 4px;")
        ov_lay.addWidget(readme_hdr)

        self.readme_browser = QTextBrowser()
        self.readme_browser.setOpenExternalLinks(True)
        self.readme_browser.setStyleSheet("""
            QTextBrowser {
                background: rgba(10, 15, 26, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 14px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        ov_lay.addWidget(self.readme_browser, stretch=1)
        self.stack.addWidget(self.overview_page)

        # ── Page 1: Live Code & File Inspector ──
        self.code_page = QWidget()
        cd_lay = QVBoxLayout(self.code_page)
        cd_lay.setContentsMargins(0, 0, 0, 0)
        cd_lay.setSpacing(8)

        # Inspector Toolbar
        insp_tb = QHBoxLayout()
        insp_tb.setSpacing(8)

        self.insp_file_lbl = QLabel("📄 filename")
        self.insp_file_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.insp_file_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        insp_tb.addWidget(self.insp_file_lbl)

        self.insp_meta_lbl = QLabel("0 KB · 0 lines")
        self.insp_meta_lbl.setFont(QFont("Segoe UI", 8))
        self.insp_meta_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        insp_tb.addWidget(self.insp_meta_lbl)

        insp_tb.addStretch()

        # Ask NEO to review file button
        self.ai_review_file_btn = QPushButton("⚡ Ask NEO to Review")
        self.ai_review_file_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.ai_review_file_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ai_review_file_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.12); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.35); border-radius: 5px; padding: 3px 10px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.25); color: #ffffff; }
        """)
        self.ai_review_file_btn.clicked.connect(self._ask_neo_review_file)
        insp_tb.addWidget(self.ai_review_file_btn)

        # Open in external editor
        open_ext_btn = QPushButton("🚀 Open Editor")
        open_ext_btn.setFont(QFont("Segoe UI", 8))
        open_ext_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_ext_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        open_ext_btn.clicked.connect(self._open_in_external_editor)
        insp_tb.addWidget(open_ext_btn)

        # Copy Path
        copy_p_btn = QPushButton("📋 Path")
        copy_p_btn.setFont(QFont("Segoe UI", 8))
        copy_p_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_p_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { color: #f1f5f9; }
        """)
        copy_p_btn.clicked.connect(self._copy_active_file_path)
        insp_tb.addWidget(copy_p_btn)

        # Close Inspector / Back to Overview
        close_insp_btn = QPushButton("✕ Overview")
        close_insp_btn.setFont(QFont("Segoe UI", 8))
        close_insp_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_insp_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { color: #D9534F; border-color: rgba(244, 63, 94, 0.3); }
        """)
        close_insp_btn.clicked.connect(self._close_inspector)
        insp_tb.addWidget(close_insp_btn)

        cd_lay.addLayout(insp_tb)

        # Monospace Code Viewer
        self.code_viewer = QTextBrowser()
        self.code_viewer.setFont(QFont("Consolas", 10))
        self.code_viewer.setStyleSheet("""
            QTextBrowser {
                background: #090e1a;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 10px;
                line-height: 1.4;
            }
        """)
        cd_lay.addWidget(self.code_viewer, stretch=1)
        self.stack.addWidget(self.code_page)

        right_lay.addWidget(self.stack, stretch=1)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        root.addWidget(self.splitter, stretch=1)

        # Initial Load
        self._refresh_all()

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: Create KPI Stat Card
    # ─────────────────────────────────────────────────────────────────────────
    def _create_kpi_card(self, title: str, main_val: str, sub_val: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px; padding: 10px 12px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        lay.addWidget(t_lbl)

        val_lbl = QLabel(main_val)
        val_lbl.setObjectName("main_val")
        val_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        val_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        lay.addWidget(val_lbl)

        sub_lbl = QLabel(sub_val)
        sub_lbl.setObjectName("sub_val")
        sub_lbl.setFont(QFont("Segoe UI", 7))
        sub_lbl.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        lay.addWidget(sub_lbl)
        return card

    # ─────────────────────────────────────────────────────────────────────────
    # Project Registry & Management
    # ─────────────────────────────────────────────────────────────────────────
    def _load_projects(self) -> dict:
        _PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _PROJECTS_FILE.exists():
            try:
                with open(_PROJECTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "projects" in data:
                        return data
            except Exception:
                pass

        init_data = {
            "active_project_id": "proj_current",
            "projects": [
                {
                    "id": "proj_current",
                    "name": self.default_workspace.name or "NEO Workspace",
                    "path": str(self.default_workspace),
                    "category": "AI/Core",
                    "run_command": "python main.py",
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                    "last_opened": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            ]
        }
        self._write_projects(init_data)
        return init_data

    def _write_projects(self, data: dict):
        try:
            _PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_f = _PROJECTS_FILE.with_suffix(".tmp")
            with open(tmp_f, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_f, _PROJECTS_FILE)
        except Exception:
            pass

    def _get_active_project(self) -> Optional[dict]:
        act_id = self.projects_data.get("active_project_id")
        for p in self.projects_data.get("projects", []):
            if p.get("id") == act_id:
                return p
        return self.projects_data.get("projects", [None])[0]

    def _populate_project_selector(self):
        self.proj_combo.blockSignals(True)
        self.proj_combo.clear()
        act_id = self.projects_data.get("active_project_id")
        active_idx = 0

        for idx, p in enumerate(self.projects_data.get("projects", [])):
            name = p.get("name", "Project")
            cat = p.get("category", "")
            label = f"{name} ({cat})" if cat else name
            self.proj_combo.addItem(f"📁 {label}", p.get("id"))
            if p.get("id") == act_id:
                active_idx = idx

        self.proj_combo.setCurrentIndex(active_idx)
        self.proj_combo.blockSignals(False)

    def _on_project_switched(self, index: int):
        proj_id = self.proj_combo.itemData(index)
        if not proj_id:
            return
        self.projects_data["active_project_id"] = proj_id
        for p in self.projects_data.get("projects", []):
            if p.get("id") == proj_id:
                p["last_opened"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.workspace_path = Path(p.get("path", "")).resolve()
                break
        self._write_projects(self.projects_data)
        self._show_toast(f"Switched to {self.workspace_path.name}")
        self._refresh_all()

    def _add_new_project(self):
        chosen_dir = QFileDialog.getExistingDirectory(self, "Select Project Folder", str(self.workspace_path))
        if not chosen_dir:
            return
        p_path = Path(chosen_dir).resolve()
        for p in self.projects_data.get("projects", []):
            if Path(p.get("path", "")).resolve() == p_path:
                self.projects_data["active_project_id"] = p["id"]
                self._populate_project_selector()
                self._on_project_switched(self.proj_combo.currentIndex())
                return

        new_id = f"proj_{int(datetime.now().timestamp() * 1000)}"
        new_proj = {
            "id": new_id,
            "name": p_path.name,
            "path": str(p_path),
            "category": "Development",
            "run_command": "python main.py" if (p_path / "main.py").exists() else "",
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "last_opened": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.projects_data.setdefault("projects", []).append(new_proj)
        self.projects_data["active_project_id"] = new_id
        self._write_projects(self.projects_data)
        self._populate_project_selector()
        self.workspace_path = p_path
        self._show_toast(f"✓ Added project: {p_path.name}")
        self._refresh_all()

    # ─────────────────────────────────────────────────────────────────────────
    # Autonomous Project Genesis & Scaffolding Engine
    # ─────────────────────────────────────────────────────────────────────────
    def _open_genesis_wizard(self):
        parent_loc = str(self.workspace_path.parent) if self.workspace_path else "."
        dlg = ProjectGenesisDialog(parent_loc, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        p_name = data["name"]
        target_dir = data["parent_dir"] / p_name

        if target_dir.exists() and any(target_dir.iterdir()):
            self._show_toast(f"⚠️ Directory '{p_name}' already exists!")
            return

        target_dir.mkdir(parents=True, exist_ok=True)

        bp_name = data["blueprint"]
        bp = PROJECT_BLUEPRINTS.get(bp_name)
        category = bp["category"] if bp else "AI/Custom"
        run_cmd = bp["run_command"] if bp else "python main.py"
        files_dict = bp["files"] if bp else {}

        # Fallback custom files if custom blueprint selected
        if not files_dict:
            files_dict = {
                "main.py": f'''"""\n{p_name} — Generated via NEO Custom Genesis.\n"""\nimport os\n\ndef main():\n    print("🚀 Initializing {p_name}...")\n    print("Concept: {data["custom_prompt"] or "Custom Genesis"}")\n\nif __name__ == "__main__":\n    main()\n''',
                "requirements.txt": "pydantic>=2.7.0\nrequests>=2.31.0\npytest>=8.0.0\n",
                "README.md": f'''# {p_name}\n\n> Custom Project — Scaffolded via **NEO Project Genesis Engine**.\n\n## Concept\n{data["custom_prompt"] or "Custom autonomous project."}\n'''
            }

        # Write files
        for rel_path, content in files_dict.items():
            out_file = target_dir / rel_path
            out_file.parent.mkdir(parents=True, exist_ok=True)
            formatted_content = content.replace("{name}", p_name)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(formatted_content)

        # 1. Git Initialization & Initial Commit
        if data["init_git"]:
            try:
                gi_file = target_dir / ".gitignore"
                if not gi_file.exists():
                    with open(gi_file, "w", encoding="utf-8") as f:
                        f.write(".venv/\nvenv/\n__pycache__/\n*.pyc\n.env\n*.log\n.pytest_cache/\nnode_modules/\n")
                subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True, timeout=5)
                subprocess.run(["git", "add", "."], cwd=str(target_dir), capture_output=True, timeout=5)
                subprocess.run(["git", "commit", "-m", f"feat: initial genesis of {p_name} via NEO Project Engine"], cwd=str(target_dir), capture_output=True, timeout=5)
            except Exception:
                pass

        # 2. Sync Phase 1 Milestones to Task Engine
        if data["sync_tasks"]:
            try:
                current_tasks = []
                if _TASKS_FILE.exists():
                    with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                        tdata = json.load(f)
                        if isinstance(tdata, dict) and "tasks" in tdata:
                            current_tasks = tdata.get("tasks", [])

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                p1_tasks = [
                    f"[{p_name}] Configure core architecture & verified dependencies",
                    f"[{p_name}] Implement primary execution pipeline & test harness",
                    f"[{p_name}] Run end-to-end integration benchmark & release v0.1.0"
                ]
                for idx, t_title in enumerate(p1_tasks):
                    new_t = {
                        "id": f"task_{int(datetime.now().timestamp()*1000)}_{idx}",
                        "title": t_title,
                        "category": "Dev",
                        "priority": "High" if idx == 0 else "Medium",
                        "due_date": "Today" if idx == 0 else "This Week",
                        "done": False,
                        "created_at": now_str,
                        "notes": f"Scaffolded by NEO Project Genesis for {p_name}"
                    }
                    current_tasks.insert(0, new_t)

                _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp_f = _TASKS_FILE.with_suffix(".tmp")
                with open(tmp_f, "w", encoding="utf-8") as f:
                    json.dump({"tasks": current_tasks}, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_f, _TASKS_FILE)
            except Exception:
                pass

        # 3. Sync Architecture RFC Blueprint to Notes Studio
        if data["sync_notes"]:
            try:
                current_notes = []
                if _NOTES_FILE.exists():
                    with open(_NOTES_FILE, "r", encoding="utf-8") as f:
                        ndata = json.load(f)
                        if isinstance(ndata, dict) and "notes" in ndata:
                            current_notes = ndata.get("notes", [])

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                cat_tag = category.split("/")[0].lower()
                rfc_note = {
                    "id": f"note_{int(datetime.now().timestamp()*1000)}",
                    "title": f"RFC: {p_name} Architecture Blueprint #dev #{cat_tag}",
                    "category": "Dev",
                    "pinned": False,
                    "archived": False,
                    "created_at": now_str,
                    "updated_at": now_str,
                    "content": f"# System Architecture Blueprint: {p_name}\n\n## 1. Executive Summary\nScaffolded using Blueprint: {bp_name}.\nTarget Path: `{target_dir}`\n\n## 2. Core Components\n- Transport / API: `{run_cmd}`\n- Schemas & Verification: `pytest`\n\n## 3. Milestones\n- [ ] Deploy MVP pipeline\n- [ ] Configure CI/CD automated test harness\n"
                }
                current_notes.insert(0, rfc_note)
                _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp_fn = _NOTES_FILE.with_suffix(".tmp")
                with open(tmp_fn, "w", encoding="utf-8") as f:
                    json.dump({"notes": current_notes}, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_fn, _NOTES_FILE)
            except Exception:
                pass

        # 4. Register Project and Switch to It
        new_proj_entry = {
            "id": f"proj_{int(datetime.now().timestamp()*1000)}",
            "name": p_name,
            "path": str(target_dir),
            "category": category,
            "run_command": run_cmd,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "last_opened": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.projects_data.setdefault("projects", []).append(new_proj_entry)
        self.projects_data["active_project_id"] = new_proj_entry["id"]
        self._write_projects(self.projects_data)
        self._populate_project_selector()
        self.workspace_path = target_dir
        self._show_toast(f"✓ Project '{p_name}' scaffolded and active!")
        self._refresh_all()

    # ─────────────────────────────────────────────────────────────────────────
    # Git Telemetry & Source Control Hub
    # ─────────────────────────────────────────────────────────────────────────
    def _run_git(self, args: list[str]) -> str:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.workspace_path),
                capture_output=True,
                text=True,
                timeout=3
            )
            return res.stdout.strip()
        except Exception:
            return ""

    def _refresh_git_status(self):
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if not branch:
            self.git_badge.setText("📁 local folder")
            self.git_badge.setStyleSheet("""
                QPushButton {
                    color: #94a3b8; background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 2px 10px;
                }
            """)
            self._update_kpi_card(self.card_git, "Local Project", "No Git repository detected")
            return

        status_raw = self._run_git(["status", "--porcelain"])
        dirty_lines = [l for l in status_raw.splitlines() if l.strip()]
        dirty_count = len(dirty_lines)

        if dirty_count == 0:
            badge_text = f"🌿 git: {branch} [clean]"
            self.git_badge.setStyleSheet("""
                QPushButton {
                    color: #34d399; background: rgba(52, 211, 153, 0.1);
                    border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 6px; padding: 2px 10px;
                }
                QPushButton:hover { background: rgba(52, 211, 153, 0.2); }
            """)
        else:
            badge_text = f"🌿 git: {branch} [● {dirty_count} modified]"
            self.git_badge.setStyleSheet("""
                QPushButton {
                    color: #D9A441; background: rgba(245, 158, 11, 0.1);
                    border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 2px 10px;
                }
                QPushButton:hover { background: rgba(245, 158, 11, 0.2); }
            """)

        self.git_badge.setText(badge_text)

        remote_url = self._run_git(["remote", "get-url", "origin"])
        remote_display = remote_url.split("/")[-1].replace(".git", "") if remote_url else "Local origin"
        self._update_kpi_card(self.card_git, f"{branch} · {dirty_count} mod", remote_display)

    def _init_git_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0f172a; color: #e2e8f0;
                border: 1px solid rgba(91, 141, 239, 0.25); border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 6px 14px; border-radius: 4px; font-size: 11px; }
            QMenu::item:selected { background: rgba(91, 141, 239, 0.18); color: #ffffff; }
        """)
        menu.aboutToShow.connect(lambda: self._populate_git_menu(menu))
        self.git_badge.setMenu(menu)

    def _populate_git_menu(self, menu: QMenu):
        menu.clear()
        logs_raw = self._run_git(["log", "-n", "5", "--pretty=format:%h|%s|%ar"])
        if logs_raw:
            hdr_act = QAction("Recent Commits:", self)
            hdr_act.setEnabled(False)
            menu.addAction(hdr_act)
            menu.addSeparator()

            for line in logs_raw.splitlines():
                if "|" in line:
                    h, s, r = line.split("|", 2)
                    act = QAction(f"{h} - {s[:35]} ({r})", self)
                    menu.addAction(act)
            menu.addSeparator()

        open_gh_act = QAction("🌐 Open on GitHub", self)
        open_gh_act.triggered.connect(self._open_github)
        menu.addAction(open_gh_act)

        ai_comm_act = QAction("✨ Ask NEO for AI Commit Message", self)
        ai_comm_act.triggered.connect(self._ai_generate_commit)
        menu.addAction(ai_comm_act)

    def _open_github(self):
        remote = self._run_git(["remote", "get-url", "origin"])
        if not remote:
            self._show_toast("No remote GitHub URL configured")
            return
        if remote.startswith("git@github.com:"):
            url = "https://github.com/" + remote.replace("git@github.com:", "").replace(".git", "")
        else:
            url = remote.replace(".git", "")
        webbrowser.open(url)
        self._show_toast(f"Opened {url}")

    def _ai_generate_commit(self):
        diff_stat = self._run_git(["diff", "--stat"])
        status = self._run_git(["status", "--short"])
        if not status:
            self._show_toast("Working tree clean — nothing to commit")
            return

        cmd = (
            f"Generate an executive Conventional Commit message for project '{self.workspace_path.name}'.\n\n"
            f"Git Status:\n{status}\n\n"
            f"Diff Stat:\n{diff_stat}\n\n"
            "Format with type (feat/fix/refactor), short title, and bullet points of key changes, Boss."
        )
        self._show_toast("✨ Dispatched commit request to NEO")
        self.project_action_triggered.emit(cmd)

    def _ai_architect_project(self):
        f_cnt, d_cnt, loc, sz = self._calculate_stats()
        readme_snippet = self.readme_browser.toPlainText()[:400].replace("\n", " ")

        cmd = (
            f"Perform an executive Technical Architecture Review & Roadmap for project '{self.workspace_path.name}'.\n"
            f"- Workspace Path: {self.workspace_path}\n"
            f"- Scope: {f_cnt} files across {d_cnt} modules (~{loc:,} Lines of Code, {sz / (1024*1024):.2f} MB)\n"
            f"- Project Overview: {readme_snippet or 'Custom project'}\n\n"
            "Please deliver:\n"
            "1. Architectural Component Breakdown & System Topology\n"
            "2. Potential Bottlenecks, Technical Debt & Security Posture\n"
            "3. 3-Phase Tactical Sprint Roadmap with immediate next milestones, Boss."
        )
        self._show_toast("🤖 Dispatched Architecture Review to NEO")
        self.project_action_triggered.emit(cmd)

    # ─────────────────────────────────────────────────────────────────────────
    # Workspace File Tree with Lazy Loading & Code Inspection
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_cache_visibility(self):
        self.hide_cache_files = not self.hide_cache_files
        self.toggle_cache_btn.setText("👁️ All" if not self.hide_cache_files else "👁️ Clean")
        self._populate_file_tree()

    def _on_search_filter_changed(self, text: str):
        kw = text.strip().lower()
        def filter_item(item: QTreeWidgetItem):
            matched = False
            item_text = item.text(0).lower()
            if kw in item_text:
                matched = True
            child_matched = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_matched = True
            is_visible = matched or child_matched or not kw
            item.setHidden(not is_visible)
            if child_matched and kw:
                item.setExpanded(True)
            return is_visible

        for i in range(self.tree_widget.topLevelItemCount()):
            filter_item(self.tree_widget.topLevelItem(i))

    def _populate_file_tree(self):
        self.tree_widget.clear()
        if not self.workspace_path.exists():
            return

        try:
            entries = sorted(self.workspace_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return

        for p in entries:
            if self.hide_cache_files and p.name in IGNORED_WORKSPACE_PATTERNS:
                continue
            if self.hide_cache_files and p.name.startswith(".") and p.name != ".env":
                continue

            if p.is_dir():
                node = QTreeWidgetItem([f"📁  {p.name}", ""])
                node.setData(0, Qt.ItemDataRole.UserRole, str(p))
                dummy = QTreeWidgetItem(["loading...", ""])
                node.addChild(dummy)
                self.tree_widget.addTopLevelItem(node)
            else:
                icon = FILE_TYPE_ICONS.get(p.suffix.lower(), "📄")
                try:
                    sz = p.stat().st_size
                    sz_str = f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B"
                except Exception:
                    sz_str = ""
                node = QTreeWidgetItem([f"{icon}  {p.name}", sz_str])
                node.setData(0, Qt.ItemDataRole.UserRole, str(p))
                self.tree_widget.addTopLevelItem(node)

    def _on_tree_item_expanded(self, item: QTreeWidgetItem):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p_dir = Path(path_str)
        if not p_dir.is_dir():
            return

        if item.childCount() == 1 and item.child(0).text(0) == "loading...":
            item.takeChild(0)
            try:
                entries = sorted(p_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for p in entries:
                    if self.hide_cache_files and p.name in IGNORED_WORKSPACE_PATTERNS:
                        continue
                    if self.hide_cache_files and p.name.startswith(".") and p.name != ".env":
                        continue

                    if p.is_dir():
                        node = QTreeWidgetItem([f"📁  {p.name}", ""])
                        node.setData(0, Qt.ItemDataRole.UserRole, str(p))
                        dummy = QTreeWidgetItem(["loading...", ""])
                        node.addChild(dummy)
                        item.addChild(node)
                    else:
                        icon = FILE_TYPE_ICONS.get(p.suffix.lower(), "📄")
                        try:
                            sz = p.stat().st_size
                            sz_str = f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B"
                        except Exception:
                            sz_str = ""
                        node = QTreeWidgetItem([f"{icon}  {p.name}", sz_str])
                        node.setData(0, Qt.ItemDataRole.UserRole, str(p))
                        item.addChild(node)
            except Exception:
                pass

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        if p.is_file():
            self._load_file_in_inspector(p)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        if p.is_file():
            self.file_open_requested.emit(str(p))
            self._show_toast(f"Ingested {p.name} into NEO Assistant")

    def _load_file_in_inspector(self, file_path: Path):
        self._active_file_path = file_path
        icon = FILE_TYPE_ICONS.get(file_path.suffix.lower(), "📄")
        try:
            rel_name = file_path.relative_to(self.workspace_path)
        except Exception:
            rel_name = file_path.name
        self.insp_file_lbl.setText(f"{icon}  {rel_name}")

        try:
            sz = file_path.stat().st_size
            sz_str = f"{sz / (1024*1024):.2f} MB" if sz > 1024*1024 else (f"{sz / 1024:.1f} KB" if sz > 1024 else f"{sz} B")
            if sz > 2 * 1024 * 1024:
                self.code_viewer.setPlainText(f"// File is too large for live preview ({sz_str}).\n// Click '🚀 Open Editor' to view externally.")
                lines_count = 0
            else:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                lines_count = len(content.splitlines())
                self.code_viewer.setPlainText(content)

            self.insp_meta_lbl.setText(f"{sz_str} · {lines_count:,} lines")
            self.stack.setCurrentIndex(1)
        except Exception as e:
            self.code_viewer.setPlainText(f"Error opening file: {e}")
            self.stack.setCurrentIndex(1)

    def _close_inspector(self):
        self._active_file_path = None
        self.stack.setCurrentIndex(0)

    def _ask_neo_review_file(self):
        if not self._active_file_path:
            return
        try:
            rel = self._active_file_path.relative_to(self.workspace_path)
        except Exception:
            rel = self._active_file_path.name
        content_snippet = self.code_viewer.toPlainText()[:1500]

        cmd = (
            f"Review and analyze file '{rel}' in project '{self.workspace_path.name}':\n\n"
            f"```python\n{content_snippet}\n```\n\n"
            "Analyze code structure, edge cases, vulnerabilities, and optimization opportunities, Boss."
        )
        self._show_toast(f"⚡ Dispatched {self._active_file_path.name} to NEO")
        self.project_action_triggered.emit(cmd)

    def _open_in_external_editor(self):
        if not self._active_file_path:
            return
        try:
            os.startfile(str(self._active_file_path))
            self._show_toast(f"Launched {self._active_file_path.name}")
        except Exception as e:
            self._show_toast(f"Launch failed: {str(e)[:24]}")

    def _copy_active_file_path(self):
        if not self._active_file_path:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(str(self._active_file_path))
            self._show_toast("📋 Copied absolute path to clipboard")

    # ─────────────────────────────────────────────────────────────────────────
    # Fast Analytics (os.walk) & Execution Docks
    # ─────────────────────────────────────────────────────────────────────────
    def _calculate_stats(self) -> tuple[int, int, int, int]:
        total_files = 0
        total_dirs = 0
        total_loc = 0
        total_sz = 0

        if not self.workspace_path.exists():
            return 0, 0, 0, 0

        for root, dirs, files in os.walk(str(self.workspace_path), topdown=True):
            dirs[:] = [d for d in dirs if d not in IGNORED_WORKSPACE_PATTERNS and not (self.hide_cache_files and d.startswith('.'))]
            total_dirs += len(dirs)
            for f in files:
                if self.hide_cache_files and f.startswith('.'):
                    continue
                total_files += 1
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    total_sz += sz
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ('.py', '.js', '.ts', '.html', '.css', '.json', '.md'):
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                            total_loc += sum(1 for _ in fl)
                except Exception:
                    pass

        return total_files, total_dirs, total_loc, total_sz

    def _refresh_overview_dashboard(self):
        f_cnt, d_cnt, loc, sz = self._calculate_stats()
        sz_mb = sz / (1024 * 1024)

        self._update_kpi_card(self.card_files, f"{f_cnt:,} files", f"{d_cnt:,} modules / dirs")
        self._update_kpi_card(self.card_loc, f"{loc:,} LOC", "Active code volume")
        self._update_kpi_card(self.card_size, f"{sz_mb:.2f} MB", "Physical disk usage")

        readme_path = self.workspace_path / "README.md"
        if not readme_path.exists():
            readme_path = self.workspace_path / "readme.md"

        if readme_path.exists():
            try:
                with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                    md_text = f.read()
                self.readme_browser.setMarkdown(md_text)
            except Exception:
                self.readme_browser.setMarkdown(f"# {self.workspace_path.name}\n\n*Unable to read README.md*")
        else:
            self.readme_browser.setMarkdown(f"""# {self.workspace_path.name}

Welcome to the **NEO Executive Mission Hub** for this workspace.

- **Workspace Path:** `{self.workspace_path}`
- **Files Count:** {f_cnt}
- **Lines of Code:** {loc:,} LOC

Use **'🤖 AI Architect'** above to generate an instant architecture blueprint and sprint roadmap!
""")

    def _update_kpi_card(self, card: QFrame, main_val: str, sub_val: str):
        mv = card.findChild(QLabel, "main_val")
        if mv:
            mv.setText(main_val)
        sv = card.findChild(QLabel, "sub_val")
        if sv:
            sv.setText(sub_val)

    def _launch_project(self):
        act_proj = self._get_active_project()
        cmd = (act_proj.get("run_command") if act_proj else "") or "python main.py"
        try:
            subprocess.Popen(cmd, shell=True, cwd=str(self.workspace_path))
            self._show_toast(f"▶ Launched: {cmd}")
        except Exception as e:
            self._show_toast(f"Launch failed: {str(e)[:24]}")

    def _run_tests(self):
        self._show_toast("🧪 Executing test suite...")
        try:
            res = subprocess.run(["pytest", "-q"], cwd=str(self.workspace_path), capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                self._show_toast("✓ All unit tests passed!")
            else:
                self._show_toast(f"⚠️ Tests failed (code {res.returncode})")
        except Exception:
            self._show_toast("⚠️ Pytest runner error or timed out")

    def _purge_cache(self):
        purged = 0
        for p in self.workspace_path.rglob("__pycache__"):
            if p.is_dir():
                try:
                    for child in p.iterdir():
                        child.unlink()
                        purged += 1
                    p.rmdir()
                except Exception:
                    pass
        self._show_toast(f"✓ Purged {purged} pycache objects")
        self._populate_file_tree()

    def _refresh_all(self):
        self.path_lbl.setText(str(self.workspace_path))
        self._refresh_git_status()
        self._populate_file_tree()
        self._refresh_overview_dashboard()

    def _show_toast(self, msg: str):
        self.toast_lbl.setText(msg)
        self.toast_lbl.show()
        QTimer.singleShot(2400, self.toast_lbl.hide)



# ═══════════════════════════════════════════════════════════════════════════════
# NEO NEURAL KNOWLEDGE & MEMORY HUB (Senior-Dev Knowledge & Graph Studio)
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_THEMES = {
    "identity": {
        "label": "👤 Identity",
        "short_label": "Identity",
        "color": "#c084fc",
        "bg": "rgba(192, 132, 252, 0.12)",
        "border": "rgba(192, 132, 252, 0.35)",
        "icon": "👤",
    },
    "preferences": {
        "label": "⚙️ Preferences",
        "short_label": "Preferences",
        "color": "#D9A441",
        "bg": "rgba(251, 191, 36, 0.12)",
        "border": "rgba(251, 191, 36, 0.35)",
        "icon": "⚙️",
    },
    "projects": {
        "label": "🗂️ Projects",
        "short_label": "Projects",
        "color": "#5B8DEF",
        "bg": "rgba(91, 141, 239, 0.12)",
        "border": "rgba(91, 141, 239, 0.35)",
        "icon": "🗂️",
    },
    "corrections": {
        "label": "🛡️ Rules & Behavior",
        "short_label": "Rules",
        "color": "#D9534F",
        "bg": "rgba(244, 63, 94, 0.14)",
        "border": "rgba(244, 63, 94, 0.4)",
        "icon": "🛡️",
    },
    "notes": {
        "label": "📝 Notes & Brain",
        "short_label": "Notes",
        "color": "#34d399",
        "bg": "rgba(52, 211, 153, 0.12)",
        "border": "rgba(52, 211, 153, 0.35)",
        "icon": "📝",
    },
    "sessions": {
        "label": "💬 Sessions",
        "short_label": "Sessions",
        "color": "#5B8DEF",
        "bg": "rgba(122, 165, 245, 0.12)",
        "border": "rgba(122, 165, 245, 0.35)",
        "icon": "💬",
    },
    "monitors": {
        "label": "📡 Monitors",
        "short_label": "Monitors",
        "color": "#2dd4bf",
        "bg": "rgba(45, 212, 191, 0.12)",
        "border": "rgba(45, 212, 191, 0.35)",
        "icon": "📡",
    },
    "relationships": {
        "label": "👥 Relationships",
        "short_label": "Relationships",
        "color": "#e879f9",
        "bg": "rgba(232, 121, 249, 0.12)",
        "border": "rgba(232, 121, 249, 0.35)",
        "icon": "👥",
    },
    "wishes": {
        "label": "🎯 Wishes",
        "short_label": "Wishes",
        "color": "#60a5fa",
        "bg": "rgba(91, 141, 239, 0.12)",
        "border": "rgba(91, 141, 239, 0.35)",
        "icon": "🎯",
    },
}


class NeoMemoryCard(QFrame):
    """Executive obsidian glass card for a single neural knowledge fact."""
    delete_requested = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    action_requested = pyqtSignal(str)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.cat = item.get("category", "notes")
        self.key = item.get("key", "")
        self.val = item.get("value", "")
        self.updated = item.get("updated", "")

        theme = CATEGORY_THEMES.get(self.cat, {
            "label": f"🏷️ {self.cat.title()}",
            "color": "#94a3b8",
            "bg": "rgba(148, 163, 184, 0.12)",
            "border": "rgba(148, 163, 184, 0.3)",
            "icon": "🏷️"
        })
        self.theme = theme

        is_critical_rule = (self.cat == "corrections")
        bg_card = "rgba(217, 83, 79, 0.12)" if is_critical_rule else CARD_BG
        border_card = "rgba(217, 83, 79, 0.35)" if is_critical_rule else CARD_BORDER

        self.setStyleSheet(f"""
            NeoMemoryCard {{
                background: {bg_card};
                border: 1px solid {border_card};
                border-radius: 8px;
            }}
            NeoMemoryCard:hover {{
                border: 1px solid {ACCENT_PRIMARY};
                background: {CARD_HOVER};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        # Header Row
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        badge_txt = "🛡️ CRITICAL BEHAVIOR RULE" if is_critical_rule else theme["label"]
        cat_badge = QLabel(badge_txt)
        cat_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        cat_badge.setStyleSheet(f"""
            background: {theme['bg']};
            color: {theme['color']};
            border: 1px solid {theme['border']};
            border-radius: 6px;
            padding: 3px 9px;
        """)
        hdr.addWidget(cat_badge)

        path_lbl = QLabel(f"{self.cat} · {self.key}")
        path_lbl.setFont(QFont("Consolas", 8))
        path_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
        hdr.addWidget(path_lbl)

        hdr.addStretch()

        if self.updated:
            date_lbl = QLabel(f"🕒 {self.updated}")
            date_lbl.setFont(QFont("Segoe UI", 8))
            date_lbl.setStyleSheet("color: #64748b; background: transparent; border: none;")
            hdr.addWidget(date_lbl)

        lay.addLayout(hdr)

        # Title
        if self.cat == "sessions":
            title_text = f"Session Briefing ({self.updated or 'Archived'})"
        elif self.cat == "monitors":
            title_text = f"Monitor: {self.key.replace('_', ' ').title()}"
        else:
            title_text = self.key.replace("_", " ").title()

        title_lbl = QLabel(title_text)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_WHITE}; background: transparent; border: none;")
        lay.addWidget(title_lbl)

        # Value display
        val_lbl = QLabel(self.val)
        val_lbl.setFont(QFont("Segoe UI", 10))
        val_lbl.setStyleSheet("color: #cbd5e1; background: transparent; border: none; line-height: 1.4;")
        val_lbl.setWordWrap(True)
        val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(val_lbl)

        # Actions row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        # Copy button
        self.copy_btn = QPushButton("📋 Copy")
        self.copy_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.12); color: #ffffff; }
        """)
        self.copy_btn.clicked.connect(self._copy_value)
        act_row.addWidget(self.copy_btn)

        # Deep-dive with NEO
        deep_btn = QPushButton("⚡ Deep-Dive in Chat")
        deep_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        deep_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        deep_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.10); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.25); border-radius: 6px; padding: 4px 11px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.20); color: #ffffff; border-color: #5B8DEF; }
        """)
        prompt_text = f"Boss requests knowledge deep-dive on [{self.cat} / {self.key}]: {self.val}. Cross-reference with our active projects and context."
        deep_btn.clicked.connect(lambda: self.action_requested.emit(prompt_text))
        act_row.addWidget(deep_btn)

        act_row.addStretch()

        # Edit button (for editable categories)
        if self.cat not in ("sessions", "monitors"):
            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setFont(QFont("Segoe UI", 8))
            edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            edit_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #94a3b8;
                    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 4px 10px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
            """)
            edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.item))
            act_row.addWidget(edit_btn)

        # Forget / Delete button
        del_btn = QPushButton("🗑️ Forget")
        del_btn.setFont(QFont("Segoe UI", 8))
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #D9534F;
                border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border-color: #D9534F; }
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.item))
        act_row.addWidget(del_btn)

        lay.addLayout(act_row)

    def _copy_value(self):
        try:
            QApplication.clipboard().setText(self.val)
            self.copy_btn.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋 Copy"))
        except Exception:
            pass


class MemoryInjectionDialog(QDialog):
    """Executive modal dialog to inject or edit permanent knowledge in NEO's Neural Graph."""
    def __init__(self, initial_data: dict = None, parent=None):
        super().__init__(parent)
        self.initial_data = initial_data or {}
        self.is_edit = bool(self.initial_data and self.initial_data.get("key"))

        self.setWindowTitle("Edit Knowledge Fact" if self.is_edit else "Teach NEO — Remember Knowledge Fact")
        self.setFixedSize(540, 480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.outer = QFrame(self)
        self.outer.setGeometry(0, 0, 540, 480)
        self.outer.setStyleSheet("""
            QFrame {
                background: #090e1a;
                border: 1px solid rgba(91, 141, 239, 0.35);
                border-radius: 8px;
            }
        """)

        lay = QVBoxLayout(self.outer)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title_txt = "✏️ Edit Neural Knowledge Fact" if self.is_edit else "🧠 Teach NEO — New Knowledge Fact"
        t_lbl = QLabel(title_txt)
        t_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #ffffff; border: none; background: transparent;")
        hdr.addWidget(t_lbl)
        hdr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; font-size: 13px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.2); color: #f87171; border-color: #D9534F; }
        """)
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        desc = QLabel("Inject permanent knowledge, identity traits, preferences, or behavior rules into NEO's long-term neural memory store.")
        desc.setFont(QFont("Segoe UI", 9))
        desc.setStyleSheet("color: #8e9eb5; border: none; background: transparent;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # Category Row
        c_lbl = QLabel("KNOWLEDGE DOMAIN / CATEGORY")
        c_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        c_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        lay.addWidget(c_lbl)

        self.cat_combo = QComboBox()
        self.cat_combo.setFixedHeight(38)
        self.cat_combo.setFont(QFont("Segoe UI", 9))
        self.cat_combo.setStyleSheet("""
            QComboBox {
                background: #101626; color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 4px 12px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background: #0d1424; color: #f8fafc;
                selection-background-color: #1e293b; border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        cats = [
            ("identity", "👤 Identity (Name, Role, Background)"),
            ("preferences", "⚙️ Preferences (Working rhythm, Style, Tools)"),
            ("projects", "🗂️ Projects (Priorities, Tech Stacks, Goals)"),
            ("corrections", "🛡️ Rules & Corrections (Critical behavior rules)"),
            ("notes", "📝 Notes & Brain (Permanent concepts, facts)"),
            ("relationships", "👥 Relationships (Mentors, Team members)"),
            ("wishes", "🎯 Wishes (Future visions, Goals)"),
        ]
        for ckey, clbl in cats:
            self.cat_combo.addItem(clbl, ckey)

        init_cat = self.initial_data.get("category", "identity")
        for idx, (ckey, _) in enumerate(cats):
            if ckey == init_cat:
                self.cat_combo.setCurrentIndex(idx)
                break
        lay.addWidget(self.cat_combo)

        # Key Input
        k_lbl = QLabel("FACT KEY / TOPIC IDENTIFIER")
        k_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        k_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        lay.addWidget(k_lbl)

        self.key_edit = QLineEdit()
        self.key_edit.setFixedHeight(36)
        self.key_edit.setFont(QFont("Consolas", 10))
        self.key_edit.setPlaceholderText("e.g. primary_framework, terminal_emulator, api_key_preference")
        self.key_edit.setText(self.initial_data.get("key", ""))
        self.key_edit.setStyleSheet("""
            QLineEdit {
                background: #101626; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 6px 12px;
            }
            QLineEdit:focus { border: 1px solid #5B8DEF; }
        """)
        lay.addWidget(self.key_edit)

        # Value Input
        v_lbl = QLabel("KNOWLEDGE STATEMENT / FACT VALUE")
        v_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        v_lbl.setStyleSheet("color: #5B8DEF; border: none; background: transparent;")
        lay.addWidget(v_lbl)

        self.val_edit = QTextEdit()
        self.val_edit.setFont(QFont("Segoe UI", 9))
        self.val_edit.setPlaceholderText("Describe the fact or rule clearly so NEO understands and applies it across future interactions...")
        self.val_edit.setText(self.initial_data.get("value", ""))
        self.val_edit.setStyleSheet("""
            QTextEdit {
                background: #101626; color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 4px; padding: 8px;
            }
            QTextEdit:focus { border: 1px solid #5B8DEF; }
        """)
        lay.addWidget(self.val_edit, stretch=1)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(QFont("Segoe UI", 9))
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 8px 18px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Commit to Neural Memory")
        save_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 8px; padding: 8px 22px;
            }
            QPushButton:hover { background: #4376D6; }
        """)
        save_btn.clicked.connect(self._save_memory)
        btn_row.addWidget(save_btn)

        lay.addLayout(btn_row)

    def _save_memory(self):
        cat = self.cat_combo.currentData()
        raw_key = self.key_edit.text().strip().lower()
        key = re.sub(r"[^\w]+", "_", raw_key).strip("_")
        val = self.val_edit.toPlainText().strip()

        if not key or not val:
            return

        from memory.memory_manager import remember, forget

        # If editing and key or category changed, forget old
        if self.is_edit:
            old_cat = self.initial_data.get("category", "")
            old_key = self.initial_data.get("key", "")
            if old_cat and old_key and (old_cat != cat or old_key != key):
                try:
                    forget(old_key, old_cat)
                except Exception:
                    pass

        try:
            remember(key, val, cat)
        except Exception as e:
            print(f"[Knowledge] remember error: {e}")

        self.accept()


class _KnowledgeKpiCard(QFrame):
    def __init__(self, icon: str, title: str, value: str, subtitle: str, color: str = "#5B8DEF", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            _KnowledgeKpiCard {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
            _KnowledgeKpiCard:hover {{
                border: 1px solid {ACCENT_PRIMARY};
                background: {CARD_HOVER};
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(6)
        i_lbl = QLabel(icon)
        i_lbl.setStyleSheet("border: none; background: transparent; font-size: 14px;")
        top.addWidget(i_lbl)

        t_lbl = QLabel(title.upper())
        t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent; letter-spacing: 0.5px;")
        top.addWidget(t_lbl)
        top.addStretch()
        lay.addLayout(top)

        self.v_lbl = QLabel(value)
        self.v_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.v_lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        lay.addWidget(self.v_lbl)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setFont(QFont("Segoe UI", 8))
        self.sub_lbl.setStyleSheet("color: #64748b; border: none; background: transparent;")
        lay.addWidget(self.sub_lbl)


class NeoKnowledgeView(QWidget):
    """
    Executive Neural Knowledge & Long-Term Memory Hub.
    Provides instant semantic lookup, deep-dive recall hooks, live filters across 8 cognitive domains,
    telemetry KPI vitals, inline editing, and seamless fact injection directly into memory/long_term.json.
    """
    search_triggered = pyqtSignal(str)
    knowledge_action_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {BG_OBSIDIAN};")
        self.active_cat = "all"
        self.cards: list[NeoMemoryCard] = []

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(32, 22, 32, 22)
        main_lay.setSpacing(14)

        # ── Header ─────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        icon_lbl = QLabel("🧠")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        k_lbl = QLabel("NEO Knowledge & Neural Memory")
        k_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        k_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        t_row.addWidget(k_lbl)

        self.count_badge = QLabel("0 facts")
        self.count_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.count_badge.setStyleSheet("""
            background: rgba(91, 141, 239, 0.12); color: #5B8DEF;
            border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 9px; padding: 2px 8px;
        """)
        t_row.addWidget(self.count_badge)
        t_row.addStretch()
        title_col.addLayout(t_row)

        sub_lbl = QLabel("Active Cognitive Store • Instant Semantic Recall • Persistent Neural Graph")
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        # Toast Feedback Label
        self.toast_lbl = QLabel("")
        self.toast_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        self.toast_lbl.setStyleSheet("""
            background: rgba(16, 185, 129, 0.15); color: #34d399;
            border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 8px; padding: 5px 12px;
        """)
        self.toast_lbl.hide()
        hdr.addWidget(self.toast_lbl)

        # Header Buttons
        audit_btn = QPushButton("⚡ Neural Audit")
        audit_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        audit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        audit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(91, 141, 239, 0.10); color: #5B8DEF;
                border: 1px solid rgba(91, 141, 239, 0.3); border-radius: 8px; padding: 7px 14px;
            }
            QPushButton:hover { background: rgba(91, 141, 239, 0.22); color: #ffffff; }
        """)
        audit_btn.clicked.connect(self._run_neural_audit)
        hdr.addWidget(audit_btn)

        sync_btn = QPushButton("🔄 Sync")
        sync_btn.setFont(QFont("Segoe UI", 9))
        sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sync_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05); color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 7px 12px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)
        sync_btn.clicked.connect(self._sync_disk)
        hdr.addWidget(sync_btn)

        add_btn = QPushButton("+ Remember Fact")
        add_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 8px; padding: 7px 16px;
            }
            QPushButton:hover { background: #4376D6; }
        """)
        add_btn.clicked.connect(self._add_memory)
        hdr.addWidget(add_btn)

        main_lay.addLayout(hdr)

        # ── KPI Telemetry Row ──────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        self.kpi_total = _KnowledgeKpiCard("🧠", "Total Memories", "0", "Indexed in neural store", "#5B8DEF")
        self.kpi_domains = _KnowledgeKpiCard("🏷️", "Active Domains", "0", "Identity, Rules, Tech...", "#c084fc")
        self.kpi_health = _KnowledgeKpiCard("⚡", "Cognitive Health", "100%", "Graph integrity verified", "#34d399")
        self.kpi_updated = _KnowledgeKpiCard("🕒", "Last Synchronized", "Today", "Auto-persisted to disk", "#D9A441")

        kpi_row.addWidget(self.kpi_total)
        kpi_row.addWidget(self.kpi_domains)
        kpi_row.addWidget(self.kpi_health)
        kpi_row.addWidget(self.kpi_updated)
        main_lay.addLayout(kpi_row)

        # ── Search & Filter Controls ───────────────────────────────────────────
        s_row = QHBoxLayout()
        s_row.setSpacing(10)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search neural memories, identity, tech stack, rules, or sessions...")
        self.search_edit.setFont(QFont("Segoe UI", 10))
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {CARD_BG}; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 9px 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT_PRIMARY};
                background: {CARD_HOVER};
            }}
        """)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.search_edit.returnPressed.connect(self._deep_search_neo)
        s_row.addWidget(self.search_edit, stretch=1)

        search_neo_b = QPushButton("⚡ Deep Search (NEO)")
        search_neo_b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        search_neo_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_neo_b.setStyleSheet(f"""
            QPushButton {{
                background: {SEND_BTN_BG}; color: #ffffff;
                border: none; border-radius: 6px; padding: 9px 18px;
            }}
            QPushButton:hover {{ background: #a4bde5; }}
        """)
        search_neo_b.clicked.connect(self._deep_search_neo)
        s_row.addWidget(search_neo_b)

        main_lay.addLayout(s_row)

        # ── Category Filter Pills Bar ──────────────────────────────────────────
        pills_scroll = QScrollArea()
        pills_scroll.setWidgetResizable(True)
        pills_scroll.setFixedHeight(46)
        pills_scroll.setStyleSheet("background: transparent; border: none;")
        pills_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pills_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        pills_widget = QWidget()
        pills_widget.setStyleSheet("background: transparent; border: none;")
        self.pills_lay = QHBoxLayout(pills_widget)
        self.pills_lay.setContentsMargins(0, 4, 0, 4)
        self.pills_lay.setSpacing(8)

        self.pill_buttons: dict[str, QPushButton] = {}
        self._categories_def = [
            ("all", "🌐 All"),
            ("identity", "👤 Identity"),
            ("preferences", "⚙️ Preferences"),
            ("projects", "🗂️ Projects"),
            ("corrections", "🛡️ Rules && Behavior"),
            ("notes", "📝 Notes && Brain"),
            ("sessions", "💬 Sessions"),
            ("monitors", "📡 Monitors"),
            ("relationships", "👥 Relationships"),
            ("wishes", "🎯 Wishes"),
        ]

        for ckey, clbl in self._categories_def:
            pbtn = QPushButton(clbl)
            pbtn.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            pbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            pbtn.clicked.connect(lambda checked, c=ckey: self._set_category(c))
            self.pill_buttons[ckey] = pbtn
            self.pills_lay.addWidget(pbtn)

        self.pills_lay.addStretch()
        pills_scroll.setWidget(pills_widget)
        main_lay.addWidget(pills_scroll)

        # ── Scrollable Memory Cards Container ──────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(10, 15, 28, 0.4);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(91, 141, 239, 0.25);
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(91, 141, 239, 0.45);
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_lay = QVBoxLayout(self.cards_container)
        self.cards_lay.setContentsMargins(0, 4, 0, 16)
        self.cards_lay.setSpacing(12)

        # Empty state placeholder
        self.empty_card = QFrame()
        self.empty_card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px dashed {CARD_BORDER};
                border-radius: 8px;
                padding: 30px;
            }}
        """)
        empty_lay = QVBoxLayout(self.empty_card)
        empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.setSpacing(8)

        e_icon = QLabel("🔍")
        e_icon.setFont(QFont("Segoe UI", 24))
        e_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_icon.setStyleSheet("border: none; background: transparent;")
        empty_lay.addWidget(e_icon)

        e_title = QLabel("No Matching Neural Knowledge Facts Found")
        e_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        e_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_title.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        empty_lay.addWidget(e_title)

        e_sub = QLabel("Try adjusting your search query, selecting another category, or teach NEO a new fact.")
        e_sub.setFont(QFont("Segoe UI", 9))
        e_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_sub.setStyleSheet("color: #64748b; border: none; background: transparent;")
        empty_lay.addWidget(e_sub)

        e_btn = QPushButton("+ Teach NEO This Fact")
        e_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        e_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        e_btn.setStyleSheet("""
            QPushButton {
                background: #5B8DEF; color: #ffffff;
                border: none; border-radius: 8px; padding: 7px 18px; margin-top: 8px;
            }
            QPushButton:hover { background: #4376D6; }
        """)
        e_btn.clicked.connect(self._add_memory)
        empty_lay.addWidget(e_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cards_lay.addWidget(self.empty_card)
        self.empty_card.hide()

        self.cards_lay.addStretch()
        self.scroll.setWidget(self.cards_container)
        main_lay.addWidget(self.scroll, stretch=1)

        # Initial Load
        self.refresh_memory()
        self._update_pill_styles()

    # ── Memory Loading & Refresh ───────────────────────────────────────────────

    def refresh_memory(self):
        """Reload all real memories from memory/long_term.json and update the entire UI."""
        # Clear existing card widgets
        for card in self.cards:
            self.cards_lay.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

        # Load from disk
        items = []
        try:
            from memory.memory_manager import load_memory
            mem = load_memory()

            for cat, data in mem.items():
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict) and "value" in v:
                            items.append({
                                "category": cat,
                                "key": k,
                                "value": v["value"],
                                "updated": v.get("updated", "")
                            })
                        elif isinstance(v, dict) and "topic" in v:
                            items.append({
                                "category": cat,
                                "key": k,
                                "value": f"Telemetry monitor: {v.get('topic', '')} · Last checked: {v.get('last_check', '')}",
                                "updated": v.get("last_check", "")
                            })
                elif isinstance(data, list) and cat == "sessions":
                    for i, sess in enumerate(data):
                        if isinstance(sess, dict):
                            items.append({
                                "category": "sessions",
                                "key": f"session_{i+1}",
                                "value": sess.get("summary", ""),
                                "updated": sess.get("date", "")
                            })
        except Exception as e:
            print(f"[Knowledge] load error: {e}")

        # Sort: Corrections first, then newest updated
        def _sort_key(it):
            is_rule = 0 if it.get("category") == "corrections" else 1
            upd = it.get("updated") or "0000-00-00"
            return (is_rule, upd)

        items.sort(key=_sort_key, reverse=True)

        # Compute counts by category
        cat_counts: dict[str, int] = {"all": len(items)}
        for it in items:
            c = it.get("category", "")
            cat_counts[c] = cat_counts.get(c, 0) + 1

        # Update Pills Text with dynamic counts
        for ckey, clbl in self._categories_def:
            btn = self.pill_buttons.get(ckey)
            if btn:
                count = cat_counts.get(ckey, 0)
                btn.setText(f"{clbl} ({count})")

        # Update KPI Telemetry Cards
        self.kpi_total.v_lbl.setText(f"{len(items)} Facts")
        active_domains = len([c for c, cnt in cat_counts.items() if c != 'all' and cnt > 0])
        self.kpi_domains.v_lbl.setText(f"{active_domains} Domains")
        self.count_badge.setText(f"{len(items)} facts")

        # Create Cards
        for it in items:
            card = NeoMemoryCard(it, parent=self.cards_container)
            card.delete_requested.connect(self._delete_memory)
            card.edit_requested.connect(self._edit_memory)
            card.action_requested.connect(self._forward_action)
            self.cards.append(card)
            # Insert before empty_card and stretch
            self.cards_lay.insertWidget(self.cards_lay.count() - 2, card)

        self._apply_filter()

    def _sync_disk(self):
        self.refresh_memory()
        self._show_toast("✓ Neural memory synchronized from disk")

    def _show_toast(self, msg: str):
        self.toast_lbl.setText(msg)
        self.toast_lbl.show()
        QTimer.singleShot(2600, self.toast_lbl.hide)

    # ── Category & Filter Logic ────────────────────────────────────────────────

    def _set_category(self, cat: str):
        self.active_cat = cat
        self._update_pill_styles()
        self._apply_filter()

    def _update_pill_styles(self):
        for ckey, btn in self.pill_buttons.items():
            if ckey == self.active_cat:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(91, 141, 239, 0.16);
                        color: #5B8DEF;
                        border: 1px solid rgba(91, 141, 239, 0.45);
                        border-radius: 8px;
                        padding: 5px 13px;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.04);
                        color: #94a3b8;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        border-radius: 8px;
                        padding: 5px 12px;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.09);
                        color: #ffffff;
                    }
                """)

    def _apply_filter(self):
        q = self.search_edit.text().strip().lower()
        visible_count = 0

        for card in self.cards:
            match_cat = (self.active_cat == "all" or card.cat == self.active_cat)
            match_query = True
            if q:
                match_query = (
                    q in card.cat.lower() or
                    q in card.key.lower() or
                    q in card.val.lower() or
                    q in card.key.replace("_", " ").lower()
                )
            show = match_cat and match_query
            card.setVisible(show)
            if show:
                visible_count += 1

        self.empty_card.setVisible(visible_count == 0)
        self.count_badge.setText(f"{visible_count} of {len(self.cards)} facts")

    # ── Actions & Integrations ─────────────────────────────────────────────────

    def _deep_search_neo(self):
        q = self.search_edit.text().strip()
        if q:
            prompt = f"Search your neural memory graph and past context for: {q}"
            self.search_triggered.emit(prompt)
            self.knowledge_action_triggered.emit(prompt)
            self._show_toast(f"Searching memory for '{q}'...")

    def _run_neural_audit(self):
        prompt = (
            "Boss requests a comprehensive Neural Brain Audit: analyze my active identity traits, "
            "preferences, ongoing projects, and learned correction rules, and provide an executive summary "
            "of NEO's cognitive state and recommendations."
        )
        self.knowledge_action_triggered.emit(prompt)
        self._show_toast("⚡ Neural Audit requested — routing to Chat...")

    def _forward_action(self, prompt: str):
        self.knowledge_action_triggered.emit(prompt)
        self._show_toast("Routing query to NEO Chat...")

    def _add_memory(self):
        init = {}
        if self.active_cat != "all" and self.active_cat in ("identity", "preferences", "projects", "corrections", "notes", "relationships", "wishes"):
            init["category"] = self.active_cat
        dlg = MemoryInjectionDialog(initial_data=init, parent=self)
        if dlg.exec():
            self._show_toast("✓ Fact injected into long-term memory")
            self.refresh_memory()

    def _edit_memory(self, item: dict):
        dlg = MemoryInjectionDialog(initial_data=item, parent=self)
        if dlg.exec():
            self._show_toast(f"✓ Memory '{item.get('key')}' updated")
            self.refresh_memory()

    def _delete_memory(self, item: dict):
        cat = item.get("category", "")
        key = item.get("key", "")
        try:
            from memory.memory_manager import load_memory, save_memory, forget
            if cat == "sessions":
                mem = load_memory()
                sessions = mem.get("sessions", [])
                try:
                    idx = int(key.replace("session_", "")) - 1
                    if 0 <= idx < len(sessions):
                        sessions.pop(idx)
                        mem["sessions"] = sessions
                        save_memory(mem)
                except Exception:
                    pass
            elif cat == "monitors":
                mem = load_memory()
                monitors = mem.get("monitors", {})
                if key in monitors:
                    del monitors[key]
                    mem["monitors"] = monitors
                    save_memory(mem)
            else:
                forget(key, cat)
            self._show_toast(f"Fact '{key}' forgotten from neural memory")
            self.refresh_memory()
        except Exception as e:
            self._show_toast(f"Error forgetting fact: {e}")



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
                    background: rgba(91, 141, 239, 0.16);
                    color: #ffffff;
                    border: 1.5px solid #5B8DEF;
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
                    background: rgba(91, 141, 239, 0.08);
                    border-color: rgba(91, 141, 239, 0.35);
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
                        stop:0 rgba(91, 141, 239, 0.16),
                        stop:1 rgba(37, 99, 235, 0.12));
                    border: 1.5px solid #5B8DEF;
                    border-radius: 8px;
                }
            """)
            self.title_lbl.setStyleSheet("color: #ffffff; border: none; background: transparent;")
            self.badge_lbl.setStyleSheet("""
                color: #5B8DEF;
                background: rgba(91, 141, 239, 0.20);
                border: 1px solid rgba(91, 141, 239, 0.4);
                border-radius: 4px;
                padding: 2px 6px;
            """)
            self.desc_lbl.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        else:
            self.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                }
                QFrame:hover {
                    background: rgba(91, 141, 239, 0.06);
                    border-color: rgba(91, 141, 239, 0.3);
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
                border: 1.5px solid rgba(91, 141, 239, 0.32);
                border-radius: 8px;
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
        icon_lbl.setStyleSheet("color: #5B8DEF; background: transparent;")
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
                border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
            }
            QPushButton:hover { color: #ffffff; background: rgba(239, 68, 68, 0.25); border-color: #D9534F; }
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
                        background: rgba(91, 141, 239, 0.18);
                        color: #5B8DEF;
                        border: 1.5px solid #5B8DEF;
                        border-radius: 8px;
                    }
                """)
            elif i < idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(34, 197, 94, 0.12);
                        color: #4ade80;
                        border: 1px solid rgba(34, 197, 94, 0.35);
                        border-radius: 8px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.03);
                        color: #64748b;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        border-radius: 8px;
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
            QLineEdit:focus { border: 1.5px solid #5B8DEF; }
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
                QPushButton:hover { background: rgba(91, 141, 239, 0.1); color: #5B8DEF; border-color: #5B8DEF; }
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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4376D6, stop:1 #5B8DEF);
                color: #080c14; font-weight: bold; border: none; border-radius: 8px; padding: 6px 20px;
            }
            QPushButton:hover { background: #5B8DEF; }
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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4376D6, stop:1 #5B8DEF);
                color: #080c14; font-weight: bold; border: none; border-radius: 8px; padding: 6px 20px;
            }
            QPushButton:hover { background: #5B8DEF; }
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
            QLineEdit:focus { border: 1.5px solid #5B8DEF; }
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
                QPushButton:hover { background: rgba(91, 141, 239, 0.1); color: #5B8DEF; border-color: #5B8DEF; }
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
        get_key_btn.setStyleSheet("color: #5B8DEF; background: transparent; border: none; text-decoration: underline;")
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
            QLineEdit:focus { border: 1.5px solid #5B8DEF; }
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
        self.error_lbl.setStyleSheet("color: #D9534F; background: transparent;")
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
                    stop:0 #5B8DEF, stop:0.5 #5B8DEF, stop:1 #2563eb);
                color: #060911; font-weight: bold; border: none; border-radius: 8px; padding: 6px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5B8DEF, stop:1 #60a5fa);
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
