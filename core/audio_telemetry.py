"""
NEO Voice & Live Engine Telemetry
Real-time latency tracking, audio pipeline diagnostics, and engine status monitor.

Tracks:
  - TTFA (Time To First Audio): Latency between user speech finish and first synthesized audio chunk
  - TTFT (Time To First Token): Latency between user speech finish and first transcript token
  - E2E Turn Latency: Total turnaround duration
  - Tool Execution Latency: Breakdown of agentic function call overhead
  - Audio Stream Health: In/Out sample rates, jitter buffer depth, underruns/overruns
  - Active Engine State: Gemini Live model vs Local Provider Pipeline
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple


class VoiceEngineTelemetry:
    """Thread-safe singleton tracking live voice latency and audio pipeline telemetry."""

    _instance: Optional["VoiceEngineTelemetry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "VoiceEngineTelemetry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self) -> None:
        self._state_lock = threading.Lock()
        self._listeners: List[Callable[[dict], None]] = []

        # Engine identification
        self.engine_mode: str = "gemini"     # "gemini" | "pipeline"
        self.active_model: str = "models/gemini-3.1-flash-live-preview"
        self.stt_provider: str = ""
        self.llm_provider: str = ""
        self.tts_provider: str = ""

        # Audio stream specs
        self.audio_in_sr: int = 16000
        self.audio_out_sr: int = 24000
        self.hardware_latency_ms: float = 200.0
        self.in_queue_depth: int = 0
        self.out_queue_depth: int = 0
        self.buffer_underruns: int = 0
        self.buffer_overruns: int = 0

        # Turn timestamps (monotonic)
        self._speech_start_t: float = 0.0
        self._speech_end_t: float = 0.0
        self._first_packet_t: float = 0.0
        self._first_transcript_t: float = 0.0
        self._first_audio_t: float = 0.0
        self._turn_complete_t: float = 0.0
        self._tool_start_t: float = 0.0
        self._last_tool_name: str = ""

        # Measured latencies
        self.last_ttfa_ms: float = 0.0
        self.last_ttft_ms: float = 0.0
        self.last_turn_ms: float = 0.0
        self.last_tool_ms: float = 0.0

        # History for rolling analytics (last 20 turns)
        self._ttfa_history = collections.deque(maxlen=20)
        self._ttft_history = collections.deque(maxlen=20)

        # Connection health
        self.connection_status: str = "ONLINE"
        self.last_switch_reason: str = ""
        self.consecutive_reconnects: int = 0

    # ── Listener Management ───────────────────────────────────────────────────

    def add_listener(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for telemetry updates."""
        with self._state_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[dict], None]) -> None:
        """Unregister a telemetry callback."""
        with self._state_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self) -> None:
        snapshot = self.get_snapshot()
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    # ── Engine Configuration ──────────────────────────────────────────────────

    def set_engine_info(
        self,
        mode: str,
        model: str,
        stt: str = "",
        llm: str = "",
        tts: str = "",
        in_sr: int = 16000,
        out_sr: int = 24000,
    ) -> None:
        """Update active engine and model identity."""
        with self._state_lock:
            self.engine_mode = mode
            self.active_model = model
            if stt:
                self.stt_provider = stt
            if llm:
                self.llm_provider = llm
            if tts:
                self.tts_provider = tts
            self.audio_in_sr = in_sr
            self.audio_out_sr = out_sr
        self._notify()

    def set_hardware_latency(self, latency_s: float) -> None:
        """Set sounddevice output latency in seconds."""
        with self._state_lock:
            if 0.0 < latency_s < 2.0:
                self.hardware_latency_ms = round(latency_s * 1000.0, 1)

    def record_engine_switch(self, new_model: str, reason: str = "") -> None:
        """Note when engine or model falls back."""
        with self._state_lock:
            self.active_model = new_model
            self.last_switch_reason = reason
        self._notify()

    # ── Turn Lifecycle Timers ─────────────────────────────────────────────────

    def on_user_speech_start(self) -> None:
        """Mark instant user begins speaking (or mic unmuted)."""
        now = time.monotonic()
        with self._state_lock:
            self._speech_start_t = now
            self._speech_end_t = 0.0
            self._first_packet_t = 0.0
            self._first_transcript_t = 0.0
            self._first_audio_t = 0.0

    def on_user_speech_stop(self) -> None:
        """Mark instant user finishes speaking (silence threshold reached or PTT released)."""
        now = time.monotonic()
        with self._state_lock:
            # If start was not recorded, anchor 1 second back
            if self._speech_start_t <= 0.0:
                self._speech_start_t = now - 1.0
            self._speech_end_t = now

    def on_server_packet_received(self) -> None:
        """Mark first byte/packet received back from AI engine."""
        now = time.monotonic()
        with self._state_lock:
            if self._first_packet_t == 0.0:
                self._first_packet_t = now

    def on_first_transcript(self) -> float:
        """Mark first transcript token/word arrived. Returns TTFT in ms."""
        now = time.monotonic()
        with self._state_lock:
            if self._first_transcript_t == 0.0:
                self._first_transcript_t = now
                anchor = self._speech_end_t if self._speech_end_t > 0 else self._speech_start_t
                if anchor > 0.0:
                    diff = (now - anchor) * 1000.0
                    if 0 < diff < 15000:
                        self.last_ttft_ms = round(diff, 1)
                        self._ttft_history.append(self.last_ttft_ms)
        self._notify()
        return self.last_ttft_ms

    def on_first_audio_chunk(self) -> float:
        """Mark first audio chunk enqueued for playback. Returns TTFA in ms."""
        now = time.monotonic()
        with self._state_lock:
            if self._first_audio_t == 0.0:
                self._first_audio_t = now
                anchor = self._speech_end_t if self._speech_end_t > 0 else self._speech_start_t
                if anchor > 0.0:
                    diff = (now - anchor) * 1000.0
                    if 0 < diff < 15000:
                        self.last_ttfa_ms = round(diff, 1)
                        self._ttfa_history.append(self.last_ttfa_ms)
        self._notify()
        return self.last_ttfa_ms

    def on_turn_completed(self) -> float:
        """Mark turn completed. Returns total turn turnaround in ms."""
        now = time.monotonic()
        with self._state_lock:
            self._turn_complete_t = now
            anchor = self._speech_end_t if self._speech_end_t > 0 else self._speech_start_t
            if anchor > 0.0:
                diff = (now - anchor) * 1000.0
                if 0 < diff < 60000:
                    self.last_turn_ms = round(diff, 1)
        self._notify()
        return self.last_turn_ms

    def on_tool_start(self, tool_name: str) -> None:
        """Mark tool call initiation."""
        with self._state_lock:
            self._tool_start_t = time.monotonic()
            self._last_tool_name = tool_name

    def on_tool_end(self, tool_name: str = "") -> float:
        """Mark tool call completion. Returns tool duration in ms."""
        now = time.monotonic()
        with self._state_lock:
            if self._tool_start_t > 0.0:
                diff = (now - self._tool_start_t) * 1000.0
                self.last_tool_ms = round(diff, 1)
                self._tool_start_t = 0.0
        self._notify()
        return self.last_tool_ms

    def update_buffer_stats(
        self,
        in_depth: int,
        out_depth: int,
        underruns: int = 0,
        overruns: int = 0,
    ) -> None:
        """Update buffer health telemetry."""
        with self._state_lock:
            self.in_queue_depth = in_depth
            self.out_queue_depth = out_depth
            self.buffer_underruns += underruns
            self.buffer_overruns += overruns

    # ── Snapshot & Formatting ─────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Return a dictionary snapshot of current telemetry."""
        with self._state_lock:
            avg_ttfa = (
                round(sum(self._ttfa_history) / len(self._ttfa_history), 1)
                if self._ttfa_history
                else self.last_ttfa_ms
            )
            p95_ttfa = (
                round(sorted(self._ttfa_history)[int(len(self._ttfa_history) * 0.95)], 1)
                if len(self._ttfa_history) >= 5
                else avg_ttfa
            )

            # Determine human-friendly model label
            model_disp = self.active_model.split("/")[-1]
            if "3.1" in model_disp:
                model_name = "Gemini 3.1 Live"
            elif "2.5" in model_disp:
                model_name = "Gemini 2.5 Live"
            elif self.engine_mode == "pipeline":
                model_name = self.llm_provider or "Pipeline"
            else:
                model_name = model_disp

            # Speed tier: Fast (<450ms), Nominal (450-900ms), Heavy (>900ms)
            eff_ttfa = self.last_ttfa_ms or avg_ttfa or 280.0
            if eff_ttfa < 450:
                tier = "ultra"
                color = "#34d399"  # emerald green
            elif eff_ttfa < 900:
                tier = "fast"
                color = "#38bdf8"  # sky blue
            else:
                tier = "heavy"
                color = "#fbbf24"  # amber

            return {
                "engine_mode": self.engine_mode,
                "model_display": model_name,
                "active_model": self.active_model,
                "ttfa_ms": self.last_ttfa_ms,
                "ttft_ms": self.last_ttft_ms,
                "avg_ttfa_ms": avg_ttfa,
                "p95_ttfa_ms": p95_ttfa,
                "turn_ms": self.last_turn_ms,
                "tool_ms": self.last_tool_ms,
                "tool_name": self._last_tool_name,
                "audio_in_sr": self.audio_in_sr,
                "audio_out_sr": self.audio_out_sr,
                "hw_latency_ms": self.hardware_latency_ms,
                "in_q": self.in_queue_depth,
                "out_q": self.out_queue_depth,
                "underruns": self.buffer_underruns,
                "overruns": self.buffer_overruns,
                "tier": tier,
                "color": color,
                "badge_text": f"⚡ {int(eff_ttfa)}ms · {model_name.upper()}",
            }

    def get_badge_text(self) -> str:
        snap = self.get_snapshot()
        return snap["badge_text"]

    def get_badge_tooltip(self) -> str:
        s = self.get_snapshot()
        return (
            f"<b>NEO Live Voice & Engine Telemetry</b><br>"
            f"• <b>Engine:</b> {s['engine_mode'].upper()} ({s['model_display']})<br>"
            f"• <b>TTFA (First Audio):</b> {s['ttfa_ms']:.0f} ms (Avg: {s['avg_ttfa_ms']:.0f} ms | P95: {s['p95_ttfa_ms']:.0f} ms)<br>"
            f"• <b>TTFT (First Token):</b> {s['ttft_ms']:.0f} ms<br>"
            f"• <b>Turn Turnaround:</b> {s['turn_ms']:.0f} ms<br>"
            f"• <b>Audio Pipeline:</b> {s['audio_in_sr']//1000}kHz In → {s['audio_out_sr']//1000}kHz Out (HW Buffer: {s['hw_latency_ms']:.0f} ms)<br>"
            f"• <b>Jitter Depth:</b> In {s['in_q']} | Out {s['out_q']} frames (Drops: {s['overruns']})<br>"
            f"<i>Click to open Engine & Provider Switcher</i>"
        )


# Global singleton instance accessor
telemetry = VoiceEngineTelemetry()
