"""
core/neo_ipc_client.py — PyQt6 IPC Client for Decoupled Frontends.

Connects the PyQt6 HUD or headless client to the NeoDaemonService over local WebSocket IPC.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("NEO.IPCClient")


class NeoIPCClient(QObject):
    """PyQt6-compatible IPC client communicating with NeoDaemonService."""

    transcript_received = pyqtSignal(str, str, bool)     # role, text, is_final
    audio_state_changed = pyqtSignal(str)               # "listening" | "thinking" | "speaking" | "idle"
    tool_event = pyqtSignal(str, str, str)              # tool_name, status, details
    telemetry_received = pyqtSignal(dict)               # metrics dict
    connection_changed = pyqtSignal(bool)               # is_connected

    def __init__(self, host: str = "127.0.0.1", port: int = 8181, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.url = f"ws://{host}:{port}/ipc"
        self._is_connected = False
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_requested = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect_daemon(self) -> None:
        """Starts background connection loop."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_requested = False
            self._thread = threading.Thread(
                target=self._run_client_loop,
                name="neo-ipc-client",
                daemon=True,
            )
            self._thread.start()

    def disconnect_daemon(self) -> None:
        """Gracefully closes IPC client."""
        with self._lock:
            self._stop_requested = True
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_client_loop(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.warning("websockets not installed; cannot connect to NeoDaemon.")
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def client_worker():
            while not self._stop_requested:
                try:
                    async with websockets.connect(self.url) as ws:
                        self._ws = ws
                        self._is_connected = True
                        self.connection_changed.emit(True)
                        logger.info("Connected to NeoDaemon IPC.")

                        async for message in ws:
                            try:
                                data = json.loads(message)
                                self._handle_daemon_event(data)
                            except Exception as e:
                                logger.error(f"Error handling daemon IPC frame: {e}")

                except Exception as e:
                    self._is_connected = False
                    self.connection_changed.emit(False)
                    if self._stop_requested:
                        break
                    await asyncio.sleep(2.0)

        try:
            self._loop.run_until_complete(client_worker())
        except Exception:
            pass

    def _handle_daemon_event(self, data: Dict[str, Any]) -> None:
        msg_type = data.get("type")
        if msg_type != "event":
            return

        event_name = data.get("event")
        payload = data.get("payload", {})

        if event_name == "transcript":
            self.transcript_received.emit(
                payload.get("role", "assistant"),
                payload.get("text", ""),
                payload.get("is_final", True),
            )
        elif event_name == "audio_state":
            self.audio_state_changed.emit(payload.get("state", "idle"))
        elif event_name == "tool_call":
            self.tool_event.emit(
                payload.get("tool", "unknown"),
                payload.get("status", "started"),
                payload.get("details", ""),
            )
        elif event_name == "telemetry":
            self.telemetry_received.emit(payload)

    def send_user_text(self, text: str) -> bool:
        """Sends user input text to the daemon."""
        return self._send_command("user_message", {"text": text})

    def interrupt(self) -> bool:
        """Sends barge-in speech cut interrupt to the daemon."""
        return self._send_command("interrupt", {})

    def _send_command(self, action: str, payload: Dict[str, Any]) -> bool:
        if not self._is_connected or not self._ws or not self._loop:
            return False

        envelope = {
            "type": "command",
            "action": action,
            "payload": payload,
            "timestamp": time.time(),
        }
        try:
            asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(envelope)), self._loop)
            return True
        except Exception as e:
            logger.error(f"Failed sending command '{action}' to daemon: {e}")
            return False
