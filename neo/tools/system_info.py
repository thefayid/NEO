"""
neo/tools/system_info.py — System Inspection and Clipboard Tools.

Architectural Guarantees:
1. Every result includes an explicit ISO/epoch timestamp and a source identifier.
2. System info: current datetime, battery, disk usage, network status, running apps.
3. Clipboard get/set using Win32 API with retry mechanics against transient locks.
4. Emergency stop check on every tool execution.
"""
from __future__ import annotations

import datetime
import logging
import os
import platform
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psutil

from neo.safety.emergency_stop import emergency_stop

logger = logging.getLogger("neo.tools.system_info")

try:
    import win32clipboard
    _HAS_CLIPBOARD = True
except ImportError:
    _HAS_CLIPBOARD = False


@dataclass
class ToolResult:
    """Standardized result returned by any tool execution."""
    ok: bool
    data: Any = None
    error: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "source": self.source,
        }


def get_current_datetime() -> ToolResult:
    """Returns local and UTC time with timezone information."""
    emergency_stop.check_stop()
    now_local = datetime.datetime.now().astimezone()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts = time.time()

    data = {
        "local_iso": now_local.isoformat(),
        "utc_iso": now_utc.isoformat(),
        "timestamp": ts,
        "timezone": str(now_local.tzinfo),
        "formatted": now_local.strftime("%A, %B %d, %Y %I:%M:%S %p"),
    }
    return ToolResult(
        ok=True,
        data=data,
        timestamp=ts,
        source="system.datetime",
        evidence={"timezone": str(now_local.tzinfo)},
    )


def get_battery() -> ToolResult:
    """Returns battery percentage, power plug status, and runtime estimate."""
    emergency_stop.check_stop()
    ts = time.time()
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            data = {"has_battery": False, "percent": 100.0, "power_plugged": True, "secsleft": "unlimited"}
        else:
            data = {
                "has_battery": True,
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
            }
        return ToolResult(ok=True, data=data, timestamp=ts, source="system.battery", evidence=data)
    except Exception as e:
        logger.error("Failed querying battery: %s", e)
        return ToolResult(ok=False, error=str(e), timestamp=ts, source="system.battery")


def get_disk(path: str = "C:\\") -> ToolResult:
    """Returns total, used, and free disk space for the partition containing path."""
    emergency_stop.check_stop()
    ts = time.time()
    try:
        usage = psutil.disk_usage(path)
        data = {
            "path": path,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent_used": usage.percent,
        }
        return ToolResult(ok=True, data=data, timestamp=ts, source="system.disk", evidence=data)
    except Exception as e:
        logger.error("Failed querying disk usage for '%s': %s", path, e)
        return ToolResult(ok=False, error=str(e), timestamp=ts, source="system.disk")


def get_network() -> ToolResult:
    """Returns active network connectivity, IP addresses, and hostname."""
    emergency_stop.check_stop()
    ts = time.time()
    try:
        hostname = socket.gethostname()
        local_ip = "127.0.0.1"
        try:
            # Connect UDP socket to detect primary route IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        interfaces = {}
        for iface, addrs in psutil.net_if_addrs().items():
            ip_list = [a.address for a in addrs if a.family == socket.AF_INET]
            if ip_list:
                interfaces[iface] = ip_list

        data = {
            "hostname": hostname,
            "primary_ip": local_ip,
            "active_interfaces": interfaces,
            "connected": local_ip != "127.0.0.1",
        }
        return ToolResult(ok=True, data=data, timestamp=ts, source="system.network", evidence={"primary_ip": local_ip})
    except Exception as e:
        logger.error("Failed querying network: %s", e)
        return ToolResult(ok=False, error=str(e), timestamp=ts, source="system.network")


def get_running_apps() -> ToolResult:
    """Returns list of currently running GUI application processes."""
    emergency_stop.check_stop()
    ts = time.time()
    try:
        from neo.windows.core import list_windows
        win_res = list_windows(only_visible=True)
        apps = []
        if win_res.ok and win_res.data:
            seen_pids = set()
            for w in win_res.data:
                if w.pid not in seen_pids and w.title:
                    seen_pids.add(w.pid)
                    apps.append({
                        "pid": w.pid,
                        "process_name": w.process_name,
                        "title": w.title,
                        "hwnd": w.hwnd,
                    })

        data = {"count": len(apps), "apps": apps}
        return ToolResult(ok=True, data=data, timestamp=ts, source="system.running_apps", evidence={"count": len(apps)})
    except Exception as e:
        logger.error("Failed listing running applications: %s", e)
        return ToolResult(ok=False, error=str(e), timestamp=ts, source="system.running_apps")


def clipboard_get() -> ToolResult:
    """
    Reads Unicode text from Windows clipboard.
    Retries across transient locks.
    """
    emergency_stop.check_stop()
    ts = time.time()
    if not _HAS_CLIPBOARD:
        return ToolResult(ok=False, error="win32clipboard is not available.", timestamp=ts, source="system.clipboard")

    for attempt in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                else:
                    text = ""
                return ToolResult(
                    ok=True,
                    data=text,
                    timestamp=ts,
                    source="system.clipboard",
                    evidence={"char_count": len(text), "format": "CF_UNICODETEXT"},
                )
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            time.sleep(0.04)

    return ToolResult(
        ok=False,
        error="Could not open Windows clipboard: locked by another process.",
        timestamp=ts,
        source="system.clipboard",
    )


def clipboard_set(text: str) -> ToolResult:
    """
    Writes Unicode text to Windows clipboard.
    Empirically verifies write by reading back the clipboard content.
    """
    emergency_stop.check_stop()
    ts = time.time()
    if not _HAS_CLIPBOARD:
        return ToolResult(ok=False, error="win32clipboard is not available.", timestamp=ts, source="system.clipboard")

    for attempt in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()

            # Empirical readback verification
            readback = clipboard_get()
            verified = readback.ok and (readback.data == text)

            return ToolResult(
                ok=verified,
                data={"chars_written": len(text)},
                timestamp=ts,
                source="system.clipboard",
                evidence={"char_count": len(text), "verified": verified},
            )
        except Exception as e:
            time.sleep(0.04)

    return ToolResult(
        ok=False,
        error="Could not set Windows clipboard: locked by another process.",
        timestamp=ts,
        source="system.clipboard",
    )
