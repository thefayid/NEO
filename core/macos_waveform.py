"""
core/macos_waveform.py — Apple CoreAudio / Siri-Style Listening & Thinking Waveform Indicator.

Senior Design Engineering Specification (Phase 5):
1. States:
   - IDLE: Subtle calm breathing baseline (low opacity, quiescent).
   - LISTENING: Smooth animated sinusoidal audio waveform in theme.accent_color
     driven by live audio levels or procedural sine oscillation.
   - THINKING: Soft, breathing accent-colored radial pulse expanding and contracting at 60fps.
2. Visual Styling:
   - SF Caption typography with -0.01em tracking for state readout.
   - GPU-accelerated QPainter antialiasing with smooth path interpolation.
   - Zero hardcoded colors; strictly consumes theme.accent_color and theme.colors.*.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout

from core.theme_provider import theme


class WaveformState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"


class MacOSWaveformIndicator(QWidget):
    """
    Apple Siri / CoreAudio Waveform and Thinking Pulse Indicator.
    Renders 60fps dynamic accent waveform or soft breathing pulse.
    """
    state_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setMinimumWidth(160)

        self._state: WaveformState = WaveformState.IDLE
        self._phase: float = 0.0
        self._pulse_scale: float = 1.0
        self._audio_level: float = 0.35  # [0.0, 1.0]
        self._status_text: str = "Ready"

        # 60fps Animation Timer
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

        theme.theme_changed.connect(self.update)

    @property
    def state(self) -> WaveformState:
        return self._state

    def set_state(self, state: WaveformState | str) -> None:
        if isinstance(state, str):
            state = WaveformState(state.lower())
        if self._state != state:
            self._state = state
            if state == WaveformState.IDLE:
                self._status_text = "Ready"
            elif state == WaveformState.LISTENING:
                self._status_text = "Listening..."
            elif state == WaveformState.THINKING:
                self._status_text = "Thinking..."
            self.state_changed.emit(self._state.value)
            self.update()

    def set_audio_level(self, level: float) -> None:
        """Sets external audio input amplitude [0.0, 1.0]."""
        self._audio_level = max(0.05, min(1.0, level))
        self.update()

    def set_status_text(self, text: str) -> None:
        self._status_text = text
        self.update()

    def _on_tick(self) -> None:
        if self._state == WaveformState.LISTENING:
            self._phase += 0.12
            if self._phase > 2.0 * math.pi:
                self._phase -= 2.0 * math.pi
            self.update()
        elif self._state == WaveformState.THINKING:
            self._phase += 0.04
            # Breathing sinusoidal pulse between 0.85 and 1.15
            self._pulse_scale = 1.0 + 0.15 * math.sin(self._phase)
            self.update()
        elif self._state == WaveformState.IDLE:
            self._phase += 0.02
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = (h - 16.0) / 2.0

        accent = QColor(theme.accent_color)

        if self._state == WaveformState.THINKING:
            self._paint_thinking_pulse(painter, cx, cy, accent)
        elif self._state == WaveformState.LISTENING:
            self._paint_listening_waveform(painter, cx, cy, accent, w)
        else:
            self._paint_idle_quiescent(painter, cx, cy, accent, w)

        # Draw Status Text Underneath
        painter.setFont(theme.font(theme.typography.caption_2, QFont.Weight.DemiBold))
        text_col = QColor(theme.colors.labelSecondary)
        painter.setPen(text_col)
        painter.drawText(QRectF(0, h - 16.0, w, 16.0), Qt.AlignmentFlag.AlignCenter, self._status_text)
        painter.end()

    def _paint_listening_waveform(self, painter: QPainter, cx: float, cy: float, accent: QColor, w: float) -> None:
        """Draws multi-bar Apple-style audio waveform."""
        bar_count = 17
        bar_spacing = 6.0
        bar_width = 3.0
        total_w = bar_count * bar_width + (bar_count - 1) * bar_spacing
        start_x = cx - total_w / 2.0

        max_bar_h = 24.0

        for i in range(bar_count):
            norm_x = (i - (bar_count - 1) / 2.0) / ((bar_count - 1) / 2.0)
            # Gaussian bell envelope
            env = math.exp(-2.2 * norm_x * norm_x)

            # Combined sine waves
            wave1 = math.sin(self._phase + i * 0.45)
            wave2 = math.cos(self._phase * 0.8 - i * 0.3)
            osc = 0.5 + 0.5 * (wave1 * 0.6 + wave2 * 0.4)

            bar_h = max(4.0, max_bar_h * env * osc * (0.4 + 0.6 * self._audio_level))
            bx = start_x + i * (bar_width + bar_spacing)
            by = cy - bar_h / 2.0

            # Gradient alpha per bar
            alpha = int(255 * (0.45 + 0.55 * env))
            col = QColor(accent)
            col.setAlpha(alpha)

            painter.setBrush(QBrush(col))
            painter.setPen(Qt.PenStyle.NoPen)
            r = bar_width / 2.0
            painter.drawRoundedRect(QRectF(bx, by, bar_width, bar_h), r, r)

    def _paint_thinking_pulse(self, painter: QPainter, cx: float, cy: float, accent: QColor) -> None:
        """Draws soft breathing radial pulse in accent color."""
        s = self._pulse_scale
        base_r = 10.0 * s

        # Outer soft glow ring
        glow_col = QColor(accent)
        glow_col.setAlpha(int(60 * (s - 0.7)))
        painter.setBrush(QBrush(glow_col))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), base_r * 1.8, base_r * 1.8)

        # Mid breathing ring
        mid_col = QColor(accent)
        mid_col.setAlpha(int(140 * (s - 0.6)))
        painter.setBrush(QBrush(mid_col))
        painter.drawEllipse(QPointF(cx, cy), base_r * 1.3, base_r * 1.3)

        # Core bright dot
        core_col = QColor(accent)
        core_col.setAlpha(250)
        painter.setBrush(QBrush(core_col))
        painter.drawEllipse(QPointF(cx, cy), base_r * 0.7, base_r * 0.7)

    def _paint_idle_quiescent(self, painter: QPainter, cx: float, cy: float, accent: QColor, w: float) -> None:
        """Draws gentle sleeping flatline dot."""
        bar_count = 5
        bar_spacing = 8.0
        bar_width = 3.0
        total_w = bar_count * bar_width + (bar_count - 1) * bar_spacing
        start_x = cx - total_w / 2.0

        for i in range(bar_count):
            norm_x = (i - 2) / 2.0
            env = math.exp(-1.5 * norm_x * norm_x)
            bar_h = 3.0 + 2.0 * math.sin(self._phase + i * 0.5) * env

            bx = start_x + i * (bar_width + bar_spacing)
            by = cy - bar_h / 2.0

            col = QColor(theme.colors.labelTertiary)
            col.setAlpha(int(120 * env))
            painter.setBrush(QBrush(col))
            painter.setPen(Qt.PenStyle.NoPen)
            r = bar_width / 2.0
            painter.drawRoundedRect(QRectF(bx, by, bar_width, bar_h), r, r)
