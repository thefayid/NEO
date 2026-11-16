"""
NEO — Deterministic Windows Personal-Assistant Agent.

5-Level Architecture:
1. Direct APIs/commands/COM (files, Office, launching apps)
2. Browser DOM control (Playwright)
3. Windows UI Automation (real named elements, readable values)
4. Keyboard shortcuts
5. Vision + coordinates (last resort only)
"""
from __future__ import annotations

__version__ = "1.0.0"

from neo.config import NeoSettings, get_settings, load_settings
from neo.logging_setup import StepLogger, StepRecord, get_step_logger
from neo.safety.emergency_stop import (
    EmergencyStop,
    EmergencyStopTriggeredError,
    emergency_stop,
)

__all__ = [
    "NeoSettings",
    "get_settings",
    "load_settings",
    "StepLogger",
    "StepRecord",
    "get_step_logger",
    "EmergencyStop",
    "EmergencyStopTriggeredError",
    "emergency_stop",
]
