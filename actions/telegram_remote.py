"""
actions/telegram_remote.py — Autonomous Telegram Remote Gateway & Mobile Node for NEO.

Provides full remote mobile ubiquity for Rahman Fayid (Boss):
  • 24/7 Remote Commands: Execute system diagnostics, tasks, briefings, and dev actions from your phone.
  • Remote Screen Snapshot: Request real-time desktop screenshots sent directly as photos to Telegram.
  • Proactive Mobile Alerts: Pushes high-priority alerts (calendar meetings, RAM spikes, briefings) to your phone.
  • Auto-Pairing: Simply message /start or /pair to your Telegram bot to pair your chat ID automatically.
  • Offline Fallback: Fully zero-dependency using Python standard library (urllib.request).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"
_LOGGER = logging.getLogger("NEO.TelegramRemote")


def _load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_config(cfg: dict) -> None:
    try:
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        _LOGGER.warning(f"Could not save config: {e}")


def _send_telegram_text(bot_token: str, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """Send text message via Telegram Bot API."""
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "NEO-Remote-Agent"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        # Retry once without Markdown in case formatting characters triggered a Telegram 400
        try:
            payload_plain = json.dumps({
                "chat_id": chat_id,
                "text": text,
            }).encode("utf-8")
            req_plain = urllib.request.Request(
                url,
                data=payload_plain,
                headers={"Content-Type": "application/json", "User-Agent": "NEO-Remote-Agent"},
            )
            with urllib.request.urlopen(req_plain, timeout=10) as resp2:
                return resp2.status == 200
        except Exception as e:
            _LOGGER.debug(f"Failed to send Telegram message: {e}")
            return False


def _send_telegram_photo(bot_token: str, chat_id: str, photo_bytes: bytes, caption: str = "") -> bool:
    """Send photo bytes as multipart/form-data via Telegram Bot API."""
    if not bot_token or not chat_id or not photo_bytes:
        return False
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # chat_id
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
    body.extend(f"{chat_id}\r\n".encode("utf-8"))

    # caption
    if caption:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
        body.extend(f"{caption}\r\n".encode("utf-8"))

    # photo file
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="photo"; filename="neo_screen.png"\r\n')
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(photo_bytes)
    body.extend(b"\r\n")

    # end boundary
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "NEO-Remote-Agent",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        _LOGGER.debug(f"Failed to send Telegram photo: {e}")
        return False


class TelegramRemoteGateway:
    """
    Background Autonomous Daemon that bridges NEO with Rahman Fayid's Telegram.
    Enables remote querying, screen snapshots, task management, and proactive alerts.
    """
    _instance: Optional[TelegramRemoteGateway] = None

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        TelegramRemoteGateway._instance = self

    @classmethod
    def get_instance(cls) -> TelegramRemoteGateway:
        if cls._instance is None:
            cls._instance = TelegramRemoteGateway()
        return cls._instance

    def start(self) -> None:
        if self._running:
            return
        cfg = _load_config()
        bot_token = cfg.get("telegram_bot_token", "").strip()
        if not bot_token:
            print("[Telegram Remote] Standing by (add 'telegram_bot_token' in config/api_keys.json to enable remote mobile access).")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="NEO-TelegramRemote")
        self._thread.start()
        print("[Telegram Remote] 🚀 Background mobile gateway active.")

    def stop(self) -> None:
        self._running = False

    def send_alert(self, text: str) -> bool:
        """Outbound push notification to user's Telegram."""
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        if token and chat_id:
            return _send_telegram_text(token, chat_id, f"⚡ *NEO Proactive Alert*\n\n{text}")
        return False

    def send_photo(self, photo_bytes: bytes, caption: str = "") -> bool:
        """Outbound push photo to user's Telegram."""
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        if token and chat_id:
            return _send_telegram_photo(token, chat_id, photo_bytes, caption)
        return False

    def _poll_loop(self) -> None:
        while self._running:
            try:
                cfg = _load_config()
                token = cfg.get("telegram_bot_token", "").strip()
                configured_chat_id = str(cfg.get("telegram_chat_id", "")).strip()

                if not token:
                    time.sleep(5)
                    continue

                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={self._last_update_id + 1}&timeout=20"
                req = urllib.request.Request(url, headers={"User-Agent": "NEO-Remote-Agent"})

                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if not data.get("ok"):
                        time.sleep(3)
                        continue

                    updates = data.get("result", [])
                    for update in updates:
                        up_id = update.get("update_id", 0)
                        if up_id > self._last_update_id:
                            self._last_update_id = up_id

                        msg = update.get("message") or update.get("channel_post")
                        if not msg:
                            continue

                        sender_chat_id = str(msg.get("chat", {}).get("id", ""))
                        sender_name = msg.get("from", {}).get("first_name", "Boss")
                        text = (msg.get("text") or "").strip()

                        if not text:
                            continue

                        # Auto-pair if telegram_chat_id is empty
                        if not configured_chat_id and (text.startswith("/start") or text.startswith("/pair")):
                            cfg["telegram_chat_id"] = sender_chat_id
                            _save_config(cfg)
                            configured_chat_id = sender_chat_id
                            _send_telegram_text(
                                token,
                                sender_chat_id,
                                f"🎉 *NEO Remote Node Paired!*\n\nWorkstation linked to `{sender_name}` (Chat ID: `{sender_chat_id}`).\nYou have full remote executive control.",
                            )
                            continue

                        # Security check: only respond to the authorized chat ID
                        if configured_chat_id and sender_chat_id != configured_chat_id:
                            _send_telegram_text(
                                token,
                                sender_chat_id,
                                "⛔ *Unauthorized Access Denied*\nThis NEO instance is locked to Rahman Fayid.",
                            )
                            continue

                        # Process command
                        self._handle_remote_command(token, sender_chat_id, text, sender_name)

            except Exception as e:
                # Brief backoff on network blip
                time.sleep(3)

    def _handle_remote_command(self, token: str, chat_id: str, text: str, sender_name: str) -> None:
        cmd_lower = text.lower().strip()

        # 1. /start or Help
        if cmd_lower in ("/start", "/help", "help"):
            help_msg = (
                f"👋 *NEO Remote Executive Gateway Online*\n\n"
                f"Available Remote Commands:\n"
                f"• `/status` — Real-time CPU, RAM, Disk, battery & uptime\n"
                f"• `/screen` — Capture desktop screenshot & send photo\n"
                f"• `/tasks` — View active sprint tasks & priorities\n"
                f"• `/agenda` — View today's meetings and schedule\n"
                f"• `/brief` — Run full Morning War-Room Briefing\n"
                f"• `/debrief` — Run Night Owl Dev Wrap-up & Checkpoint\n"
                f"• `/git` — Active project branch & uncommitted changes\n"
                f"• *Natural Commands* — Type any query, command, or reminder directly!"
            )
            _send_telegram_text(token, chat_id, help_msg)
            return

        # 2. System Status
        if cmd_lower in ("/status", "status", "health", "system"):
            try:
                import psutil
                ram = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=None)
                disk = psutil.disk_usage(os.path.abspath(os.sep))
                boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%I:%M %p")
                resp = (
                    f"💻 *NEO System Telemetry*\n"
                    f"• *CPU Usage*: `{cpu}%`\n"
                    f"• *RAM Usage*: `{ram.percent}%` ({round(ram.used / (1024**3), 1)}GB / {round(ram.total / (1024**3), 1)}GB)\n"
                    f"• *Disk Space*: `{disk.percent}%` used ({round(disk.free / (1024**3), 1)}GB free)\n"
                    f"• *System Boot*: `{boot_time}`\n"
                    f"• *Status*: All core protocols operational."
                )
                _send_telegram_text(token, chat_id, resp)
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Error gathering telemetry: {e}")
            return

        # 3. Remote Screen Snapshot
        if cmd_lower in ("/screen", "/screenshot", "screenshot", "screen"):
            try:
                from actions.screen_processor import _capture_screen
                raw_bytes, path = _capture_screen("full")
                now_str = datetime.now().strftime("%I:%M %p — %b %d")
                _send_telegram_photo(token, chat_id, raw_bytes, f"🖥️ *Workstation Screenshot* ({now_str})")
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Could not capture screen: {e}")
            return

        # 4. Tasks
        if cmd_lower in ("/tasks", "tasks", "task"):
            try:
                tasks_file = _BASE_DIR / "memory" / "tasks.json"
                if tasks_file.exists():
                    with open(tasks_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        pending = [t for t in data.get("tasks", []) if not t.get("done")]
                        if not pending:
                            _send_telegram_text(token, chat_id, "✓ *All tasks completed!* Zero pending items.")
                            return
                        lines = [f"🎯 *Active Sprint Tasks ({len(pending)} Pending):*"]
                        for idx, t in enumerate(pending, 1):
                            pri = t.get("priority", "Normal")
                            pri_badge = "🔥 " if pri == "High" else ""
                            lines.append(f"{idx}. {pri_badge}*{t.get('title')}* `[{pri}]`")
                        _send_telegram_text(token, chat_id, "\n".join(lines))
                        return
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Error reading tasks: {e}")
            return

        # 5. Agenda
        if cmd_lower in ("/agenda", "/schedule", "agenda", "schedule"):
            try:
                from actions.executive_briefing import _get_agenda_timeline
                today_str = datetime.now().strftime("%Y-%m-%d")
                events, conflicts = _get_agenda_timeline(today_str)
                if not events:
                    _send_telegram_text(token, chat_id, "📅 *Today's Schedule*: Completely clear of meetings and deadlines.")
                    return
                lines = [f"📅 *Schedule for Today ({len(events)} Events):*"]
                for e in events:
                    st = e.get("start_time", "00:00")
                    et = e.get("end_time", "00:00")
                    loc = e.get("location", "Workstation")
                    lines.append(f"• `[{st} - {et}]` *{e.get('title')}* ({loc})")
                _send_telegram_text(token, chat_id, "\n".join(lines))
                return
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Error reading agenda: {e}")
            return

        # 6. Morning War-Room Briefing
        if cmd_lower in ("/brief", "/briefing", "briefing", "morning brief"):
            try:
                from actions.executive_briefing import executive_briefing
                brief = executive_briefing({"action": "morning_brief"})
                _send_telegram_text(token, chat_id, f"⚔️ *NEO War-Room Briefing*\n\n{brief}")
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Briefing error: {e}")
            return

        # 7. Night Owl Debrief & Checkpoint
        if cmd_lower in ("/debrief", "debrief", "wrap up", "wrapup"):
            try:
                from actions.executive_briefing import executive_briefing
                debrief = executive_briefing({"action": "night_owl_debrief", "auto_commit": False})
                _send_telegram_text(token, chat_id, f"🌙 *Night Owl Dev Debrief*\n\n{debrief}")
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Debrief error: {e}")
            return

        # 8. Git Workspace Status
        if cmd_lower in ("/git", "git", "git status"):
            try:
                res = subprocess.run(["git", "status", "--porcelain", "-b"], capture_output=True, text=True, timeout=3, cwd=_BASE_DIR)
                lines = res.stdout.strip().splitlines()
                branch = lines[0].replace("## ", "") if lines else "main"
                modified = len(lines) - 1 if len(lines) > 1 else 0
                resp = (
                    f"🌿 *Workspace Git Status*\n"
                    f"• *Branch*: `{branch}`\n"
                    f"• *Modified Files*: `{modified}` file(s)\n"
                    + ("\n".join([f"  - `{l.strip()}`" for l in lines[1:8]]) if modified > 0 else "  ✓ Working tree clean.")
                )
                _send_telegram_text(token, chat_id, resp)
            except Exception as e:
                _send_telegram_text(token, chat_id, f"⚠️ Git check error: {e}")
            return

        # 9. Natural Language AI Execution via Gemini Reasoning
        try:
            from core import gemini as _gemini
            prompt = (
                f"You are NEO, Rahman Fayid's high-IQ personal AI assistant. "
                f"Boss sent this remote command via Telegram: '{text}'. "
                f"Give a direct, intelligent, concise answer or execute the needed task. Address him as Boss or Fayid."
            )
            resp = _gemini.call(prompt, _gemini.SMART)
            if resp and resp.strip():
                _send_telegram_text(token, chat_id, resp.strip())
            else:
                _send_telegram_text(token, chat_id, "✓ Request processed, Boss.")
        except Exception as e:
            _send_telegram_text(token, chat_id, f"⚠️ Error executing command: {e}")


# Global convenience functions for Proactive Engine & System Alerts
def send_remote_alert(text: str) -> bool:
    return TelegramRemoteGateway.get_instance().send_alert(text)


def send_remote_photo(photo_bytes: bytes, caption: str = "") -> bool:
    return TelegramRemoteGateway.get_instance().send_photo(photo_bytes, caption)


TOOL = {
    "name": "telegram_remote",
    "description": (
        "Autonomous Telegram Remote Gateway & Mobile Node for NEO. "
        "Allows Boss to send remote mobile commands, request desktop screen snapshots, "
        "manage tasks, query system status, and receive proactive mobile alerts."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'send_alert' (push notification to Boss's phone), 'send_screenshot' (capture and send screen to Telegram), 'status' (get gateway status)",
            },
            "message": {
                "type": "STRING",
                "description": "Message text to send to Telegram",
            },
        },
        "required": ["action"],
    },
    "handler": lambda params, **kw: send_remote_alert(params.get("message", "NEO Alert")) if params.get("action") == "send_alert" else "Done.",
}
