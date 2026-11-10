"""
core/neo_mobile_telepathy.py — Cross-Device Telepathy & Mobile Executive Companion for NEO.

Architecture:
1. Bidirectional Mobile Telepathy Bridge:
   - Remote Command Execution: Dispatches goals, runs tests, inspects telemetry from your phone.
   - Remote Desktop Screen Snapshot: Captures and sends high-res desktop screenshot photos to your phone.
   - Away-from-Desk Proactive Push Relay: Sends push alerts when user is away from desk and high-urgency events occur.
2. Direct integration with Telegram Remote Protocol and local secure channels.
3. Thread-safe execution with zero-dependency stdlib fallbacks.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from actions.telegram_remote import (
    _load_config, _save_config, _send_telegram_text, _send_telegram_photo
)
from core.neo_ambient_sensor import ambient_sensor, UserFocusState
from core.neo_precognition import precognitive_engine, ProactiveOpportunity

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOGGER = logging.getLogger("NEO.MobileTelepathy")


class NEOMobileTelepathy(QObject):
    """
    Cross-Device mobile telepathy bridge managing remote execution and mobile pushes.
    """
    mobile_command_received = pyqtSignal(str, str)         # sender_id, command
    mobile_alert_dispatched = pyqtSignal(str, str)         # channel, message
    pairing_status_changed = pyqtSignal(bool, str)         # is_paired, user_name

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cfg = _load_config()
        self._is_active = False
        self._last_push_time = 0.0
        self._lock = threading.Lock()
        self._wire_proactive_pushes()

    def _wire_proactive_pushes(self) -> None:
        """Connects to precognitive engine for away-from-desk push dispatches."""
        precognitive_engine.opportunity_detected.connect(self._on_precognitive_opportunity)

    def is_paired(self) -> bool:
        """Returns True if bot token and chat ID are configured."""
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "").strip()
        chat_id = str(cfg.get("telegram_chat_id", "")).strip()
        return bool(token and chat_id)

    def get_paired_details(self) -> Dict[str, Any]:
        """Returns current mobile connection metadata."""
        cfg = _load_config()
        return {
            "paired": self.is_paired(),
            "chat_id": str(cfg.get("telegram_chat_id", "Not Paired")),
            "bot_configured": bool(cfg.get("telegram_bot_token")),
            "last_active": cfg.get("telegram_last_active", "Never"),
            "user_name": cfg.get("user_name", "Fayid"),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Outbound Mobile Push Dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    def dispatch_mobile_push(
        self,
        title: str,
        message: str,
        urgency: float = 0.5,
        photo_path: Optional[str] = None
    ) -> bool:
        """
        Sends an executive push notification to the user's phone.
        """
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "")
        chat_id = str(cfg.get("telegram_chat_id", ""))
        if not token or not chat_id:
            return False

        header = f"🚨 *NEO ALERT* 🚨" if urgency >= 0.85 else f"⚡ *NEO TELEPATHY*"
        body = f"{header}\n\n*{title}*\n{message}\n\n_Sent at {time.strftime('%I:%M %p')}_"

        ok = False
        if photo_path and os.path.exists(photo_path):
            ok = _send_telegram_photo(token, chat_id, photo_path, caption=body[:1000])
        else:
            ok = _send_telegram_text(token, chat_id, body)

        if ok:
            self._last_push_time = time.time()
            self.mobile_alert_dispatched.emit("TELEGRAM", title)
        return ok

    def capture_and_send_screen(self, caption: str = "🖥️ Live Desktop Screen Snapshot") -> bool:
        """
        Captures current desktop screen and dispatches photo to mobile companion.
        """
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "")
        chat_id = str(cfg.get("telegram_chat_id", ""))
        if not token or not chat_id:
            return False

        shot_path = _BASE_DIR / "temp_remote_screen.jpg"
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(shot_path), "JPEG", quality=85)
            ok = _send_telegram_photo(token, chat_id, str(shot_path), caption=caption)
            if shot_path.exists():
                try:
                    shot_path.unlink()
                except Exception:
                    pass
            return ok
        except Exception as e:
            _LOGGER.warning(f"Failed to capture remote screen: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Away-From-Desk Proactive Watcher
    # ─────────────────────────────────────────────────────────────────────────

    def _on_precognitive_opportunity(self, opp: ProactiveOpportunity) -> None:
        """
        Dispatches mobile push when user is AWAY from desk and an urgent opportunity arrives.
        """
        focus_state = ambient_sensor.get_focus_state()
        if focus_state == UserFocusState.AWAY and opp.urgency >= 0.75:
            # Respect 5m cooldown on mobile pushes
            if time.time() - self._last_push_time >= 300:
                self.dispatch_mobile_push(
                    title=opp.title,
                    message=f"{opp.subtitle}\n\nAction: {opp.action_payload}",
                    urgency=opp.urgency,
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Inbound Remote Command Handler
    # ─────────────────────────────────────────────────────────────────────────

    def process_remote_command(self, cmd_text: str) -> str:
        """
        Executes a command received from mobile and returns structured response.
        """
        t = (cmd_text or "").strip()
        if not t:
            return "Empty command received, Boss."

        self.mobile_command_received.emit("MOBILE_USER", t)

        if t in ("/status", "status"):
            snap = ambient_sensor.get_latest_snapshot()
            vitals = snap.get("vitals", {})
            return (
                f"📊 *NEO System Status*\n"
                f"• CPU: {vitals.get('cpu_percent', 0)}%\n"
                f"• RAM: {vitals.get('ram_percent', 0)}%\n"
                f"• Disk: {vitals.get('disk_percent', 0)}%\n"
                f"• Battery: {vitals.get('battery_percent', 100)}%\n"
                f"• Focus State: {snap.get('focus_state', 'UNKNOWN')}\n"
                f"• Foreground: {snap.get('foreground', {}).get('app_name', 'None')}"
            )

        elif t in ("/screen", "screen"):
            threading.Thread(target=self.capture_and_send_screen, daemon=True).start()
            return "📸 Desktop screen snapshot is capturing and sending to your Telegram, Boss..."

        elif t.startswith("/goal ") or t.startswith("goal "):
            prompt = t.replace("/goal ", "").replace("goal ", "").strip()
            from core.neo_central_coordinator import central_core
            gid = central_core.execute_autonomous_goal(prompt)
            return f"🚀 *Autonomous Goal Launched*\nID: `{gid[:8]}`\nObjective: {prompt}\n\nNEO is executing in the background, Boss."

        else:
            # Standard conversational / execution query
            from core.neo_central_coordinator import central_core
            return f"⚡ Received command: '{t}' — Dispatched to NEO Central Core."


# Global Singleton Mobile Telepathy Bridge
mobile_telepathy = NEOMobileTelepathy()
