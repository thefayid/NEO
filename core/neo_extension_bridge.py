"""
core/neo_extension_bridge.py — Hybrid Daily Browser Extension Bridge for NEO.

Bridges authenticated Chrome/Edge browser sessions (GitHub, AWS, Jira, Docs)
without requiring --remote-debugging-port flags.

Architecture:
1. Local WebSocket Endpoint (ws://127.0.0.1:8765/extension):
   - Accepts connection from the NEO Companion browser extension.
   - Maintains real-time active tab inventory.
2. Synchronous Command Dispatcher:
   - Evaluates JavaScript, clicks DOM selectors, fills input fields, and reads page text.
   - Thread-safe correlation via request IDs and threading.Event.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("NEO.ExtensionBridge")


@dataclass
class BrowserTabInfo:
    id: int
    title: str
    url: str
    active: bool = False


class NEOExtensionBridge:
    """Server bridge managing WebSocket communication with the browser extension."""

    _instance: Optional["NEOExtensionBridge"] = None

    def __new__(cls, host: str = "127.0.0.1", port: int = 8765) -> "NEOExtensionBridge":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.host = host
            cls._instance.port = port
            cls._instance._connected_client = None
            cls._instance._tabs: List[BrowserTabInfo] = []
            cls._instance._active_tab: Optional[BrowserTabInfo] = None
            cls._instance._pending_requests: Dict[int, Dict[str, Any]] = {}
            cls._instance._req_id = 0
            cls._instance._lock = threading.Lock()
            cls._instance._server_thread: Optional[threading.Thread] = None
            cls._instance._loop: Optional[asyncio.AbstractEventLoop] = None
            cls._instance._is_running = False
            cls._instance.start()
        return cls._instance

    @property
    def is_connected(self) -> bool:
        return self._connected_client is not None

    @property
    def active_tab(self) -> Optional[BrowserTabInfo]:
        return self._active_tab

    @property
    def tabs(self) -> List[BrowserTabInfo]:
        return list(self._tabs)

    def start(self) -> None:
        """Starts the WebSocket bridge server in a background thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._server_thread = threading.Thread(
                target=self._run_server_thread,
                name="neo-extension-bridge",
                daemon=True,
            )
            self._server_thread.start()

    def _run_server_thread(self) -> None:
        """Event loop thread for the WebSocket server."""
        try:
            import websockets
        except ImportError:
            logger.warning("websockets package not available for ExtensionBridge.")
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            logger.info("Browser extension companion connected.")
            with self._lock:
                self._connected_client = websocket

            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "tab_inventory":
                            raw_tabs = data.get("tabs", [])
                            raw_active = data.get("activeTab")
                            with self._lock:
                                self._tabs = [
                                    BrowserTabInfo(id=t.get("id", 0), title=t.get("title", ""), url=t.get("url", ""), active=t.get("active", False))
                                    for t in raw_tabs
                                ]
                                if raw_active:
                                    self._active_tab = BrowserTabInfo(
                                        id=raw_active.get("id", 0),
                                        title=raw_active.get("title", ""),
                                        url=raw_active.get("url", ""),
                                        active=True,
                                    )

                        elif msg_type == "response":
                            req_id = data.get("id")
                            with self._lock:
                                holder = self._pending_requests.get(req_id)
                            if holder:
                                holder["response"] = data
                                holder["event"].set()

                    except Exception as e:
                        logger.error(f"Error handling extension message: {e}")

            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                with self._lock:
                    if self._connected_client == websocket:
                        self._connected_client = None
                logger.info("Browser extension companion disconnected.")

        async def run_ws():
            async with websockets.serve(handler, self.host, self.port):
                await asyncio.Future()  # run forever

        try:
            self._loop.run_until_complete(run_ws())
        except Exception as e:
            logger.debug(f"Extension bridge server stopped: {e}")

    def _send_command(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 8.0) -> Dict[str, Any]:
        """Dispatches a command to the browser extension and waits for response."""
        if not self.is_connected or not self._loop:
            return {"success": False, "message": "Browser extension is not connected. Open Chrome/Edge with NEO Companion installed."}

        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            event = threading.Event()
            holder = {"event": event, "response": None}
            self._pending_requests[req_id] = holder
            client = self._connected_client

        payload = {"id": req_id, "action": action}
        if params:
            payload.update(params)

        try:
            future = asyncio.run_coroutine_threadsafe(client.send(json.dumps(payload)), self._loop)
            future.result(timeout=2.0)
        except Exception as e:
            with self._lock:
                self._pending_requests.pop(req_id, None)
            return {"success": False, "message": f"Failed sending to extension: {e}"}

        # Wait for response
        signaled = event.wait(timeout=timeout)
        with self._lock:
            self._pending_requests.pop(req_id, None)

        if not signaled:
            return {"success": False, "message": f"Timeout waiting for browser response ({timeout}s)"}

        return holder.get("response", {"success": False, "message": "Empty response from browser"})

    def click_selector(self, selector: str = "", text: str = "") -> Tuple[bool, str]:
        """Clicks an element by CSS selector or text in the active tab."""
        res = self._send_command("click", {"selector": selector, "text": text})
        return res.get("success", False), res.get("message", "No message")

    def type_selector(self, selector: str, text: str) -> Tuple[bool, str]:
        """Types text into an input selector in the active tab."""
        res = self._send_command("type", {"selector": selector, "text": text})
        return res.get("success", False), res.get("message", "No message")

    def get_page_content(self) -> Dict[str, Any]:
        """Extracts title, URL, and visible text from the active tab."""
        res = self._send_command("get_page_content")
        return res.get("data", {}) if res.get("success") else {"error": res.get("message")}

    def query_dom(self, selector: str = "") -> List[Dict[str, Any]]:
        """Queries interactive elements from the active tab."""
        res = self._send_command("query_dom", {"selector": selector})
        return res.get("data", {}).get("elements", []) if res.get("success") else []

    def eval_js(self, script: str) -> str:
        """Evaluates JavaScript in the active tab."""
        res = self._send_command("eval_js", {"script": script})
        if res.get("success"):
            return res.get("data", {}).get("result", "undefined")
        return f"Error: {res.get('message')}"

    def list_tabs(self) -> List[Dict[str, Any]]:
        """Retrieves list of all open tabs."""
        res = self._send_command("list_tabs")
        return res.get("data", {}).get("tabs", []) if res.get("success") else []


extension_bridge = NEOExtensionBridge()
