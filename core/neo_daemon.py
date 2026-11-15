"""
core/neo_daemon.py — Headless NeoCore Daemon & High-Speed Local IPC Bus for NEO.

Decouples the core intelligence, voice streaming, and autonomous computer operator
from the GUI presentation layer.

Key Architecture:
1. Headless Daemon Runtime:
   - Manages audio telemetry, Live sessions, Key Rotator, Memory, and MCP servers.
   - Runs continuously in the background even if the UI restarts or crashes.
2. Local Fast IPC Server (ws://127.0.0.1:8181/ipc):
   - Transmits real-time events to connected clients:
     • transcript (user/assistant speech)
     • audio_state (listening, thinking, speaking, idle)
     • tool_lifecycle (started, executed, verified)
     • system_telemetry (cpu, memory, latency)
   - Accepts commands: send_user_message, interrupt, execute_tool, status, ping.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("NEO.Daemon")

DEFAULT_IPC_HOST = "127.0.0.1"
DEFAULT_IPC_PORT = 8181


@dataclass
class DaemonStatus:
    is_running: bool
    connected_clients: int
    audio_state: str
    active_tools_count: int
    uptime_seconds: float


class NeoDaemonService:
    """Headless core daemon orchestrating assistant operations and IPC broadcasting."""

    _instance: Optional["NeoDaemonService"] = None

    def __new__(cls, host: str = DEFAULT_IPC_HOST, port: int = DEFAULT_IPC_PORT) -> "NeoDaemonService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.host = host
            cls._instance.port = port
            cls._instance._connected_clients: Set[Any] = set()
            cls._instance._audio_state = "idle"
            cls._instance._start_time = time.time()
            cls._instance._lock = threading.Lock()
            cls._instance._server_thread: Optional[threading.Thread] = None
            cls._instance._loop: Optional[asyncio.AbstractEventLoop] = None
            cls._instance._is_running = False
            cls._instance._callbacks: Dict[str, List[Callable]] = {
                "user_message": [],
                "interrupt": [],
                "tool_call": [],
            }
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def audio_state(self) -> str:
        return self._audio_state

    def start(self) -> bool:
        """Starts the IPC server daemon in a dedicated thread."""
        with self._lock:
            if self._is_running:
                return True
            self._is_running = True
            self._start_time = time.time()
            self._server_thread = threading.Thread(
                target=self._run_server_thread,
                name="neocore-daemon-ipc",
                daemon=True,
            )
            self._server_thread.start()
            logger.info(f"NeoDaemonService started on ws://{self.host}:{self.port}/ipc")
            return True

    def stop(self) -> None:
        """Stops the daemon service and disconnects clients."""
        with self._lock:
            self._is_running = False
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._connected_clients.clear()

    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Registers a handler for incoming IPC client commands."""
        with self._lock:
            if command not in self._callbacks:
                self._callbacks[command] = []
            self._callbacks[command].append(handler)

    def _run_server_thread(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.warning("websockets not installed; IPC server unavailable.")
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            with self._lock:
                self._connected_clients.add(websocket)
            logger.info("IPC Client connected to NeoDaemon.")

            # Send initial handshake state
            await websocket.send(json.dumps({
                "type": "event",
                "event": "handshake",
                "payload": {
                    "audio_state": self._audio_state,
                    "uptime": time.time() - self._start_time,
                    "version": "2.0-headless",
                }
            }))

            try:
                async for message in websocket:
                    try:
                        req = json.loads(message)
                        res = await self._dispatch_incoming_ipc_command(req)
                        if res is not None:
                            await websocket.send(json.dumps(res))
                    except Exception as e:
                        logger.error(f"IPC message error: {e}")
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                with self._lock:
                    self._connected_clients.discard(websocket)
                logger.info("IPC Client disconnected from NeoDaemon.")

        async def run_server():
            async with websockets.serve(handler, self.host, self.port):
                await asyncio.Future()

        try:
            self._loop.run_until_complete(run_server())
        except Exception as e:
            logger.debug(f"IPC loop stopped: {e}")

    async def _dispatch_incoming_ipc_command(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        action = req.get("action", "")
        payload = req.get("payload", {})

        if action == "ping":
            return {"type": "response", "id": req_id, "success": True, "message": "pong"}

        if action == "status":
            summary = self.get_status()
            return {
                "type": "response",
                "id": req_id,
                "success": True,
                "payload": {
                    "is_running": summary.is_running,
                    "connected_clients": summary.connected_clients,
                    "audio_state": summary.audio_state,
                    "uptime": summary.uptime_seconds,
                }
            }

        # Route to registered handlers
        handlers = self._callbacks.get(action, [])
        for h in handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    asyncio.create_task(h(payload))
                else:
                    h(payload)
            except Exception as e:
                logger.error(f"Handler error for '{action}': {e}")

        return {"type": "response", "id": req_id, "success": True, "message": f"Action '{action}' dispatched."}

    # ─────────────────────────────────────────────────────────────────────────
    # Broadcast Events to Connected UI Clients
    # ─────────────────────────────────────────────────────────────────────────

    def broadcast_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Broadcasts an event asynchronously to all connected frontends."""
        if not self._is_running or not self._loop:
            return

        envelope = {
            "type": "event",
            "event": event_name,
            "timestamp": time.time(),
            "payload": payload,
        }
        msg = json.dumps(envelope)

        with self._lock:
            clients = list(self._connected_clients)

        for client in clients:
            try:
                asyncio.run_coroutine_threadsafe(client.send(msg), self._loop)
            except Exception:
                pass

    def emit_transcript(self, role: str, text: str, is_final: bool = True) -> None:
        """Emits user or assistant speech transcript."""
        self.broadcast_event("transcript", {
            "role": role,
            "text": text,
            "is_final": is_final,
        })

    def emit_audio_state(self, state: str) -> None:
        """Emits audio engine state change ('listening', 'thinking', 'speaking', 'idle')."""
        with self._lock:
            self._audio_state = state
        self.broadcast_event("audio_state", {"state": state})

    def emit_tool_call(self, tool_name: str, status: str, details: str = "") -> None:
        """Emits tool lifecycle events for HUD action cards and pills."""
        self.broadcast_event("tool_call", {
            "tool": tool_name,
            "status": status,
            "details": details,
        })

    def emit_telemetry(self, telemetry_data: Dict[str, Any]) -> None:
        """Emits system telemetry for UI meters."""
        self.broadcast_event("telemetry", telemetry_data)

    def get_status(self) -> DaemonStatus:
        with self._lock:
            return DaemonStatus(
                is_running=self._is_running,
                connected_clients=len(self._connected_clients),
                audio_state=self._audio_state,
                active_tools_count=0,
                uptime_seconds=time.time() - self._start_time,
            )


daemon_service = NeoDaemonService()
