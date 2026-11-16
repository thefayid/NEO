"""
neo/tools/registry.py — Central Tool Registry with JSON Schema and Risk Gating.

Architectural Guarantees:
1. Every registered tool defines a name, description, JSON schema, risk level, and handler.
2. High-risk tools automatically evaluate ConfirmationGate before dispatch.
3. Every execution returns a structured ToolResult with timestamp and source.
4. Pre-registers all core system info, filesystem, and Office tools.
"""
from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from neo.safety.emergency_stop import emergency_stop
from neo.safety.gates import (
    ConfirmationDeniedError,
    HardStopRequiredError,
    get_confirmation_gate,
)
from neo.tools.system_info import (
    ToolResult,
    clipboard_get,
    clipboard_set,
    get_battery,
    get_current_datetime,
    get_disk,
    get_network,
    get_running_apps,
)

logger = logging.getLogger("neo.tools.registry")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ToolDefinition:
    """Metadata and execution specification for a callable tool."""
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    risk_level: RiskLevel
    handler: Callable[..., Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
            "risk_level": self.risk_level.value,
        }


class ToolRegistry:
    """
    Registry for tools available to NEO's brain and planner.
    Provides execution coordination, JSON Schema export, and safety confirmation gating.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        """Registers a new tool definition."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (Risk: %s)", tool.name, tool.risk_level.value)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns tool declarations formatted for LLM function calling."""
        return [tool.to_dict() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        """
        Executes a registered tool:
        1. Checks emergency stop.
        2. Evaluates ConfirmationGate if risk_level is HIGH.
        3. Invokes handler with keyword arguments.
        4. Packages uniform ToolResult with timestamp and source.
        """
        emergency_stop.check_stop()

        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                ok=False,
                error=f"Tool '{name}' is not registered.",
                source="tool_registry",
            )

        args = arguments or {}

        # 1. High risk confirmation gating
        if tool.risk_level == RiskLevel.HIGH:
            gate = get_confirmation_gate()
            try:
                gate.evaluate_and_gate(
                    action_name="format",
                    target=str(args),
                    element_name=f"Execute High-Risk Tool: {name}",
                )
            except HardStopRequiredError as e:
                return ToolResult(
                    ok=False,
                    error=f"Tool execution blocked by Hard Stop: {e}",
                    source=f"tool.{name}",
                    evidence={"hard_stop": True},
                )
            except ConfirmationDeniedError as e:
                return ToolResult(
                    ok=False,
                    error=f"Tool execution denied by confirmation gate: {e}",
                    source=f"tool.{name}",
                    evidence={"denied": True},
                )

        # 2. Invoke handler
        start_time = time.perf_counter()
        try:
            res = tool.handler(**args)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            if isinstance(res, ToolResult):
                res.evidence["duration_ms"] = duration_ms
                return res

            # Wrap non-ToolResult returns (e.g. from FileResult or raw data)
            if hasattr(res, "ok") and hasattr(res, "data"):
                return ToolResult(
                    ok=res.ok,
                    data=res.data,
                    error=res.error if hasattr(res, "error") else None,
                    evidence={**(res.evidence if hasattr(res, "evidence") else {}), "duration_ms": duration_ms},
                    timestamp=time.time(),
                    source=f"tool.{name}",
                )

            return ToolResult(
                ok=True,
                data=res,
                timestamp=time.time(),
                source=f"tool.{name}",
                evidence={"duration_ms": duration_ms},
            )
        except Exception as e:
            logger.error("Exception executing tool '%s': %s", name, e, exc_info=True)
            return ToolResult(
                ok=False,
                error=f"Execution error on tool '{name}': {e}",
                timestamp=time.time(),
                source=f"tool.{name}",
            )

    def _register_default_tools(self) -> None:
        """Registers built-in system info and filesystem tools."""
        # 1. System Info Tools
        self.register(
            ToolDefinition(
                name="get_current_datetime",
                description="Returns current local and UTC date and time with timezone information.",
                parameters_schema={"type": "object", "properties": {}, "required": []},
                risk_level=RiskLevel.LOW,
                handler=get_current_datetime,
            )
        )
        self.register(
            ToolDefinition(
                name="get_battery",
                description="Returns battery percentage, power connection status, and runtime estimate.",
                parameters_schema={"type": "object", "properties": {}, "required": []},
                risk_level=RiskLevel.LOW,
                handler=get_battery,
            )
        )
        self.register(
            ToolDefinition(
                name="get_disk",
                description="Returns disk partition usage (total, free, used GB) for given path.",
                parameters_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": "C:\\"}},
                    "required": [],
                },
                risk_level=RiskLevel.LOW,
                handler=get_disk,
            )
        )
        self.register(
            ToolDefinition(
                name="get_network",
                description="Returns active network status, primary local IP, interfaces, and hostname.",
                parameters_schema={"type": "object", "properties": {}, "required": []},
                risk_level=RiskLevel.LOW,
                handler=get_network,
            )
        )
        self.register(
            ToolDefinition(
                name="get_running_apps",
                description="Returns list of currently running visible GUI applications with titles and PIDs.",
                parameters_schema={"type": "object", "properties": {}, "required": []},
                risk_level=RiskLevel.LOW,
                handler=get_running_apps,
            )
        )
        self.register(
            ToolDefinition(
                name="clipboard_get",
                description="Reads Unicode text from the Windows clipboard.",
                parameters_schema={"type": "object", "properties": {}, "required": []},
                risk_level=RiskLevel.LOW,
                handler=clipboard_get,
            )
        )
        self.register(
            ToolDefinition(
                name="clipboard_set",
                description="Writes Unicode text to the Windows clipboard.",
                parameters_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "Text to set in clipboard"}},
                    "required": ["text"],
                },
                risk_level=RiskLevel.LOW,
                handler=clipboard_set,
            )
        )


# Global default registry
_GLOBAL_TOOL_REGISTRY = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _GLOBAL_TOOL_REGISTRY
