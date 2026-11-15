"""
core/neo_mcp_bridge.py — Model Context Protocol (MCP) Client & Tool Hub for NEO.

Adopts the open Model Context Protocol (MCP) specification to bridge external tools,
databases, and service agents directly into NEO's multimodal live reasoning loop.

Key Capabilities:
1. Native stdio JSON-RPC 2.0 Client:
   - Spawns and manages external MCP server processes over standard I/O.
   - Handles protocol handshake: `initialize` -> `notifications/initialized` -> `tools/list`.
   - Executes calls via `tools/call` with timeout and auto-recovery.
2. Zero-Friction Gemini Live & Local Schema Translation:
   - Converts MCP JSON Schema definitions into Gemini/NEO tool schemas.
   - Automatically prefixes tool names (e.g., `mcp_<server>_<tool>`) to eliminate collisions.
3. Drop-in Tool Dispatch:
   - Exposes `get_tool_declarations()`, `has(name)`, and `run(name, parameters, ctx)`
     mirroring `ActionRegistry` and `PluginRegistry`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("NEO.MCPBridge")

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _BASE_DIR / "config"
_MCP_CONFIG_FILE = _CONFIG_DIR / "mcp_servers.json"


@dataclass
class MCPToolDefinition:
    server_name: str
    original_name: str
    declared_name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class MCPServerStatus:
    name: str
    command: str
    args: List[str]
    enabled: bool
    connected: bool
    tool_count: int
    error: Optional[str] = None


class MCPStdioClient:
    """Manages a single MCP server process communicating via stdio JSON-RPC 2.0."""

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[Union[str, Path]] = None,
        timeout_seconds: float = 15.0,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = str(cwd) if cwd else None
        self.timeout = timeout_seconds

        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._pending_requests: Dict[int, Dict[str, Any]] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._is_connected = False
        self._last_error: Optional[str] = None
        self._tools: Dict[str, MCPToolDefinition] = {}

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self._process is not None and self._process.poll() is None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def tools(self) -> Dict[str, MCPToolDefinition]:
        return self._tools

    def connect(self) -> bool:
        """Launches the server process and performs the MCP initialize handshake."""
        with self._lock:
            if self.is_connected:
                return True

            full_env = os.environ.copy()
            full_env.update(self.env)
            full_cmd = [self.command] + self.args

            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            try:
                self._process = subprocess.Popen(
                    full_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=full_env,
                    cwd=self.cwd,
                    bufsize=0,
                    creationflags=creationflags,
                )
            except Exception as e:
                self._last_error = f"Failed to spawn MCP server '{self.name}': {e}"
                logger.error(self._last_error)
                return False

            self._reader_thread = threading.Thread(
                target=self._read_stdout_loop,
                name=f"mcp-reader-{self.name}",
                daemon=True,
            )
            self._reader_thread.start()

        # Perform MCP initialize handshake
        try:
            init_res = self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "NEO-Assistant", "version": "2.0"},
                },
                timeout=self.timeout,
            )
            if not init_res or "error" in init_res:
                err_msg = init_res.get("error") if init_res else "No response"
                self._last_error = f"Handshake failed with '{self.name}': {err_msg}"
                self.disconnect()
                return False

            # Send notifications/initialized notification
            self._send_notification("notifications/initialized", {})

            # Harvest available tools
            self._fetch_tools()
            self._is_connected = True
            self._last_error = None
            return True
        except Exception as e:
            self._last_error = f"Initialize exception with '{self.name}': {e}"
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """Gracefully terminates the MCP process."""
        with self._lock:
            self._is_connected = False
            proc = self._process
            self._process = None

        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write_payload(payload)

    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        req_id = self._next_id()
        event = threading.Event()
        result_holder: Dict[str, Any] = {"event": event, "response": None}

        with self._lock:
            self._pending_requests[req_id] = result_holder

        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params

        if not self._write_payload(payload):
            with self._lock:
                self._pending_requests.pop(req_id, None)
            return {"error": "Failed to write to server stdin"}

        wait_time = timeout or self.timeout
        signaled = event.wait(timeout=wait_time)
        with self._lock:
            self._pending_requests.pop(req_id, None)

        if not signaled:
            return {"error": f"Timeout waiting for '{method}' response after {wait_time}s"}

        return result_holder.get("response")

    def _write_payload(self, data: Dict[str, Any]) -> bool:
        if not self._process or not self._process.stdin:
            return False
        try:
            line = json.dumps(data) + "\n"
            self._process.stdin.write(line.encode("utf-8"))
            self._process.stdin.flush()
            return True
        except Exception as e:
            self._last_error = f"Stdin write error: {e}"
            return False

    def _read_stdout_loop(self) -> None:
        """Reads JSON-RPC messages from server stdout."""
        proc = self._process
        if not proc or not proc.stdout:
            return

        while proc.poll() is None:
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue

                # Handle optional Content-Length header framing if present
                if raw.startswith("Content-Length:"):
                    # Read following empty line
                    _ = proc.stdout.readline()
                    # Next line is payload
                    line = proc.stdout.readline()
                    raw = line.decode("utf-8", errors="replace").strip()

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Route response to pending request
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._lock:
                        holder = self._pending_requests.get(msg_id)
                    if holder:
                        holder["response"] = msg
                        holder["event"].set()

            except Exception:
                break

    def _fetch_tools(self) -> None:
        """Queries the MCP server for its tool catalog."""
        resp = self._send_request("tools/list", {})
        if not resp or "error" in resp:
            return

        result = resp.get("result", {})
        raw_tools = result.get("tools", [])
        discovered: Dict[str, MCPToolDefinition] = {}

        for item in raw_tools:
            orig_name = item.get("name", "")
            if not orig_name:
                continue

            decl_name = f"mcp_{self.name}_{orig_name}".replace("-", "_")
            desc = item.get("description", f"MCP Tool '{orig_name}' provided by {self.name}")
            schema = item.get("inputSchema", {"type": "OBJECT", "properties": {}})

            # Ensure schema type is upper-case OBJECT for Gemini compatibility
            if isinstance(schema, dict):
                t = str(schema.get("type", "object")).upper()
                if t == "OBJECT":
                    schema["type"] = "OBJECT"
                props = schema.get("properties", {})
                if not isinstance(props, dict):
                    schema["properties"] = {}
            else:
                schema = {"type": "OBJECT", "properties": {}}

            discovered[decl_name] = MCPToolDefinition(
                server_name=self.name,
                original_name=orig_name,
                declared_name=decl_name,
                description=desc,
                parameters=schema,
            )

        self._tools = discovered

    def call_tool(self, original_name: str, arguments: Dict[str, Any]) -> str:
        """Invokes a specific tool on the MCP server via tools/call."""
        if not self.is_connected:
            return f"MCP server '{self.name}' is disconnected."

        resp = self._send_request(
            "tools/call",
            {"name": original_name, "arguments": arguments},
            timeout=self.timeout,
        )

        if not resp:
            return f"Error: No response from MCP server '{self.name}'."

        if "error" in resp:
            err = resp["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return f"MCP Tool Error [{self.name}.{original_name}]: {msg}"

        result = resp.get("result", {})
        # Parse MCP CallToolResult content
        content = result.get("content", [])
        if isinstance(content, list) and content:
            chunks = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    chunks.append(c.get("text", ""))
                elif isinstance(c, str):
                    chunks.append(c)
                else:
                    chunks.append(json.dumps(c))
            return "\n".join(chunks).strip() or "Done (empty content)."

        if isinstance(content, str):
            return content

        if "isError" in result and result["isError"]:
            return f"Tool returned failure: {json.dumps(result)}"

        return json.dumps(result) if result else "Done."


class NEOMCPBridge:
    """Central MCP Bridge managing all configured external servers and tools."""

    _instance: Optional["NEOMCPBridge"] = None

    def __new__(cls) -> "NEOMCPBridge":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._servers: Dict[str, MCPStdioClient] = {}
            cls._tool_map: Dict[str, Tuple[MCPStdioClient, MCPToolDefinition]] = {}
            cls._lock = threading.Lock()
            cls._initialized = False
        return cls._instance

    def initialize(self) -> None:
        """Loads configuration and establishes connections to enabled servers."""
        with self._lock:
            if self._initialized:
                return
            self._ensure_default_config()
            self._load_and_connect_servers()
            self._initialized = True

    def _ensure_default_config(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not _MCP_CONFIG_FILE.exists():
            default_config = {
                "mcp_servers": {
                    "filesystem_local": {
                        "command": "python",
                        "args": ["-c", "print('NEO MCP Stdio Mock Server Ready')"],
                        "env": {},
                        "enabled": False,
                        "description": "Standard local file operations MCP server",
                    }
                }
            }
            try:
                with open(_MCP_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to create default mcp_servers.json: {e}")

    def _load_and_connect_servers(self) -> None:
        if not _MCP_CONFIG_FILE.exists():
            return

        try:
            with open(_MCP_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading {_MCP_CONFIG_FILE}: {e}")
            return

        servers_dict = data.get("mcp_servers", {})
        for s_name, s_cfg in servers_dict.items():
            if not s_cfg.get("enabled", False):
                continue

            cmd = s_cfg.get("command")
            if not cmd:
                continue

            client = MCPStdioClient(
                name=s_name,
                command=cmd,
                args=s_cfg.get("args", []),
                env=s_cfg.get("env", {}),
                cwd=s_cfg.get("cwd", _BASE_DIR),
                timeout_seconds=float(s_cfg.get("timeout", 15.0)),
            )

            if client.connect():
                self._servers[s_name] = client
                for decl_name, tool_def in client.tools.items():
                    self._tool_map[decl_name] = (client, tool_def)
                logger.info(f"Connected MCP server '{s_name}' ({len(client.tools)} tools).")
            else:
                logger.warning(f"Failed to connect MCP server '{s_name}': {client.last_error}")

    def register_client(self, client: MCPStdioClient) -> None:
        """Manually registers an already connected or mock client (useful for plugins/tests)."""
        with self._lock:
            self._servers[client.name] = client
            for decl_name, tool_def in client.tools.items():
                self._tool_map[decl_name] = (client, tool_def)

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Generates tool declaration schemas compatible with Gemini Live & ActionRegistry."""
        declarations = []
        with self._lock:
            for decl_name, (_, tool_def) in self._tool_map.items():
                declarations.append({
                    "name": decl_name,
                    "description": f"[MCP: {tool_def.server_name}] {tool_def.description}",
                    "parameters": tool_def.parameters,
                    "tier": "extra",
                    "brief": f"{tool_def.server_name}: {tool_def.original_name}",
                })
        return declarations

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._tool_map

    def names(self) -> set[str]:
        with self._lock:
            return set(self._tool_map.keys())

    def run(self, name: str, parameters: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None) -> str:
        """Executes an MCP tool call."""
        with self._lock:
            binding = self._tool_map.get(name)

        if not binding:
            return f"MCP Tool '{name}' not found or its server is inactive."

        client, tool_def = binding
        try:
            return client.call_tool(tool_def.original_name, parameters)
        except Exception as e:
            return f"Error executing MCP tool '{name}': {e}"

    def list_servers_summary(self) -> List[MCPServerStatus]:
        """Returns diagnostic status of all known servers."""
        res = []
        with self._lock:
            # Check configured servers on disk
            try:
                if _MCP_CONFIG_FILE.exists():
                    with open(_MCP_CONFIG_FILE, "r", encoding="utf-8") as f:
                        disk_cfg = json.load(f).get("mcp_servers", {})
                else:
                    disk_cfg = {}
            except Exception:
                disk_cfg = {}

            all_names = set(disk_cfg.keys()) | set(self._servers.keys())
            for name in all_names:
                cfg = disk_cfg.get(name, {})
                client = self._servers.get(name)
                is_connected = client.is_connected if client else False
                tool_count = len(client.tools) if client else 0
                err = client.last_error if client else None

                res.append(MCPServerStatus(
                    name=name,
                    command=str(cfg.get("command", client.command if client else "unknown")),
                    args=list(cfg.get("args", client.args if client else [])),
                    enabled=bool(cfg.get("enabled", False)),
                    connected=is_connected,
                    tool_count=tool_count,
                    error=err,
                ))
        return res

    def shutdown(self) -> None:
        """Disconnects all running servers."""
        with self._lock:
            for s in self._servers.values():
                s.disconnect()
            self._servers.clear()
            self._tool_map.clear()
            self._initialized = False


mcp_bridge = NEOMCPBridge()
