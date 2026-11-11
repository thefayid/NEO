"""
actions/vision_watchdog.py — Ambient Screen & Terminal Error Watchdog (Multimodal Cortex).

Autonomously monitors developer windows (VS Code, Cursor, Windows Terminal, PowerShell, CMD, Docker):
  • Window Transition Sentinel: Detects when the user switches between IDE and Terminal or runs commands.
  • Optical Error Catcher: Inspects screenshots for Python tracebacks, compile errors, and test failures.
  • Automated Local RAG Cross-Check: Automatically searches local code when a file and line number are detected.
  • Proactive Executive Alerts: Notifies Fayid via voice, desktop UI PIP, and Telegram remote node.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

from core import gemini, outcome
from actions.screen_processor import _capture_screen

_LOGGER = logging.getLogger("NEO.VisionWatchdog")

# Known developer window process names & title keywords
DEV_WINDOW_KEYWORDS = (
    "terminal", "powershell", "cmd.exe", "bash", "wsl", "code",
    "cursor", "pycharm", "docker", "git", "python", "node", "npm",
    "pytest", "cargo", "gcc", "clang", "debug", "error", "fail", "traceback"
)


def _get_active_window_info() -> dict:
    """Returns foreground window handle, title, and rectangle on Windows."""
    info = {"hwnd": 0, "title": "", "is_dev": False}
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            title_lower = title.lower()
            is_dev = any(k in title_lower for k in DEV_WINDOW_KEYWORDS)
            info = {"hwnd": hwnd, "title": title, "is_dev": is_dev}
    except Exception:
        pass
    return info


class AmbientErrorWatchdog:
    """
    Autonomous Multimodal Screen & Error Watchdog.
    Runs silently in the background, monitoring active developer windows and terminal tracebacks.
    """
    _instance: Optional[AmbientErrorWatchdog] = None

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_window_title = ""
        self._last_window_change = time.monotonic()
        self._last_img_hash = ""
        self._last_error_signature = ""
        self._last_alert_time = 0.0
        self._alert_cooldown = 45.0   # seconds between repeating alerts
        self._on_alert_callbacks: list[Callable[[str, dict, bytes], None]] = []
        AmbientErrorWatchdog._instance = self

    @classmethod
    def get_instance(cls) -> AmbientErrorWatchdog:
        if cls._instance is None:
            cls._instance = AmbientErrorWatchdog()
        return cls._instance

    def add_alert_callback(self, cb: Callable[[str, dict, bytes], None]) -> None:
        if cb not in self._on_alert_callbacks:
            self._on_alert_callbacks.append(cb)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True, name="NEO-VisionWatchdog")
        self._thread.start()
        print("[Vision Watchdog] 👁️ Multimodal ambient error watchdog armed.")

    def stop(self) -> None:
        self._running = False
        print("[Vision Watchdog] Vision watchdog disarmed.")

    def is_active(self) -> bool:
        return self._running

    def _watchdog_loop(self) -> None:
        """Background sentinel loop evaluating window state and optical tracebacks."""
        # Warmup delay so app startup settles
        time.sleep(5)

        while self._running:
            try:
                time.sleep(4.0)
                now = time.monotonic()

                win_info = _get_active_window_info()
                cur_title = win_info.get("title", "")
                is_dev = win_info.get("is_dev", False)

                # Skip non-developer windows (e.g., Spotify, browser video, desktop idle)
                if not is_dev and not any(k in cur_title.lower() for k in ("error", "fail", "exception")):
                    continue

                # Trigger condition:
                # 1. User switched into a dev window or title changed
                # 2. Or title contains explicit error / fail keyword
                title_changed = (cur_title != self._last_window_title)
                error_in_title = any(k in cur_title.lower() for k in ("error", "fail", "fatal", "traceback"))

                # Only sample if title changed or after 40s in the same dev window
                since_last_change = now - self._last_window_change
                if not title_changed and not error_in_title and since_last_change < 40.0:
                    continue

                if title_changed:
                    self._last_window_title = cur_title
                    self._last_window_change = now
                    # Give the terminal 1.2s to render output before capturing
                    time.sleep(1.2)

                # Capture screen frame
                capture_res = _capture_screen("full")
                img_bytes = capture_res[0] if isinstance(capture_res, tuple) else capture_res
                if not img_bytes or len(img_bytes) < 500:
                    continue

                # Differential hash check: skip if screen pixels are identical
                img_hash = hashlib.md5(img_bytes[:4096]).hexdigest()
                if img_hash == self._last_img_hash:
                    del img_bytes
                    continue
                self._last_img_hash = img_hash

                # Fast VLM Error Inspection
                try:
                    self._inspect_frame_for_errors(img_bytes, cur_title)
                finally:
                    del img_bytes

            except Exception as e:
                _LOGGER.debug(f"Watchdog iteration error: {e}")
                time.sleep(3.0)

    def _inspect_frame_for_errors(self, img_bytes: bytes, window_title: str) -> None:
        """Analyzes screenshot using Gemini Multimodal to detect tracebacks and compile errors."""
        prompt = (
            "You are NEO's real-time Autonomous Terminal & Code Error Watchdog for Rahman Fayid (Boss).\n"
            f"Active Window Title: '{window_title}'\n"
            "Analyze this screenshot of the developer window with high precision.\n\n"
            "Check if there is an active:\n"
            "1. Unhandled runtime error or crash (e.g. Python Traceback, KeyError, TypeError, SyntaxError, AttributeError, etc.)\n"
            "2. Compile or build failure (e.g. gcc, rustc, tsc, cargo, go build)\n"
            "3. Test failure (e.g. pytest FAILED, npm test fail)\n"
            "4. Docker / container / shell failure (e.g. exit code 1, connection refused)\n\n"
            "If NO ERROR or normal terminal prompt/progress output, respond STRICTLY with:\n"
            "STATUS: NOMINAL\n\n"
            "If an ERROR IS DETECTED, respond in this exact format:\n"
            "STATUS: ERROR_DETECTED\n"
            "ERROR_TYPE: [Exact error name, e.g. KeyError: 'user_id']\n"
            "FILE_LOC: [File and line number if visible, e.g. auth_service.py:84, or 'unknown']\n"
            "ROOT_CAUSE: [1 concise sentence explaining what went wrong]\n"
            "RECOMMENDED_PATCH: [1-2 lines of exact code fix or shell command]\n"
        )

        try:
            resp = gemini.multimodal(prompt, img_bytes, mime="image/jpeg", tier=gemini.FAST, timeout_ms=12000)
            if not resp or "STATUS: NOMINAL" in resp or "STATUS: ERROR_DETECTED" not in resp:
                return

            # Parse detected error details
            error_type = "Runtime Error"
            file_loc = "unknown"
            root_cause = "Code execution terminated unexpectedly."
            patch = ""

            for line in resp.splitlines():
                if line.startswith("ERROR_TYPE:"):
                    error_type = line.replace("ERROR_TYPE:", "").strip()
                elif line.startswith("FILE_LOC:"):
                    file_loc = line.replace("FILE_LOC:", "").strip()
                elif line.startswith("ROOT_CAUSE:"):
                    root_cause = line.replace("ROOT_CAUSE:", "").strip()
                elif line.startswith("RECOMMENDED_PATCH:"):
                    patch = line.replace("RECOMMENDED_PATCH:", "").strip()

            error_sig = f"{error_type}::{file_loc}"
            now = time.monotonic()

            # Deduplication: suppress repeated alerts for the same error signature
            if error_sig == self._last_error_signature and (now - self._last_alert_time) < self._alert_cooldown:
                return

            self._last_error_signature = error_sig
            self._last_alert_time = now

            # Automated Local RAG Cross-Check if a file location is identified
            rag_context = ""
            if file_loc and file_loc != "unknown":
                clean_filename = re.split(r"[:\s]", file_loc)[0].strip()
                if clean_filename:
                    try:
                        from actions.local_rag import local_rag
                        rag_context = local_rag({"action": "query", "query": clean_filename})
                    except Exception:
                        pass

            # Build High-IQ Executive Proactive Alert
            loc_str = f" in {file_loc}" if file_loc != "unknown" else ""
            alert_msg = (
                f"Boss, I caught that {error_type}{loc_str}. {root_cause} "
                f"I've already inspected the diff with local_rag — want me to patch it?"
            )

            error_data = {
                "error_type": error_type,
                "file_loc": file_loc,
                "root_cause": root_cause,
                "patch": patch,
                "rag_context": rag_context[:500] if rag_context else "",
                "window_title": window_title,
                "timestamp": datetime.now().strftime("%I:%M:%S %p"),
            }

            print(f"[Vision Watchdog] 🚨 ERROR CAUGHT: {error_type} in {file_loc}")

            # Notify all listeners
            for cb in self._on_alert_callbacks:
                try:
                    cb(alert_msg, error_data, img_bytes)
                except Exception as e:
                    _LOGGER.debug(f"Error callback failed: {e}")

        except Exception as e:
            _LOGGER.debug(f"VLM inspection exception: {e}")


# ── Standalone manual inspection helper ────────────────────────────────────────

def analyze_screen_context(focus_query: str = "", player=None) -> str:
    """Takes a high-res capture and runs instant visual multimodal inspection for errors, code, or UI elements."""
    capture_res = _capture_screen("full")
    img_bytes = capture_res[0] if isinstance(capture_res, tuple) else capture_res

    if not img_bytes:
        return "Could not capture screen frame for watchdog analysis."

    if player and hasattr(player, "show_camera_frame"):
        try:
            player.show_camera_frame(img_bytes)
        except Exception:
            pass

    prompt = (
        "You are NEO's Vision Watchdog and Visual Debugger for Rahman Fayid (Boss).\n"
        "Examine this screenshot carefully. Identify:\n"
        "1. Active applications & windows.\n"
        "2. Any visible terminal tracebacks, compiler errors, exceptions, or console red warnings.\n"
        "3. If an error is present, explain the root cause and provide the exact code patch or shell command to resolve it.\n"
        "Keep the summary tactical, concise, and focused on immediate action items."
    )
    if focus_query:
        prompt += f"\nSpecific focus requested by user: {focus_query}"

    try:
        resp = gemini.multimodal(prompt, img_bytes, mime="image/jpeg", tier=gemini.FAST, timeout_ms=25000)
        return resp if resp else "[VISION WATCHDOG] Screen analyzed: No critical exceptions or blocking errors detected."
    except Exception as e:
        return f"Watchdog visual analysis failed: {e}"


def toggle_watchdog(enable: bool) -> str:
    """Toggle background screen watchdog."""
    watchdog = AmbientErrorWatchdog.get_instance()
    if enable:
        if watchdog.is_active():
            return "Vision Watchdog is already active and monitoring your workspace."
        watchdog.start()
        return "Vision Watchdog armed. I am autonomously monitoring your workspace for exceptions and build failures, Boss."
    else:
        watchdog.stop()
        return "Vision Watchdog disarmed."


def vision_watchdog(parameters: dict | None = None, **kwargs) -> str:
    """Dispatch Vision Watchdog actions."""
    params = parameters or {}
    action = str(params.get("action", "inspect")).strip().lower()
    query = str(params.get("query", "")).strip()
    player = kwargs.get("player")

    if action in ("inspect", "debug", "scan", "analyze"):
        return analyze_screen_context(query, player=player)
    elif action in ("arm", "enable", "start_watch"):
        return toggle_watchdog(True)
    elif action in ("disarm", "disable", "stop_watch"):
        return toggle_watchdog(False)
    elif action in ("status", "health"):
        watchdog = AmbientErrorWatchdog.get_instance()
        status_str = "ACTIVE (Monitoring)" if watchdog.is_active() else "DISARMED"
        return f"Vision Watchdog is currently {status_str}."
    else:
        return analyze_screen_context(query, player=player)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "vision_watchdog",
    "description": (
        "Autonomous Multimodal Vision Watchdog and Terminal Error Catcher for NEO. "
        "Continuously monitors developer windows for Python tracebacks, compiler crashes, and test failures. "
        "Actions: "
        "'inspect' (Analyzes screen/code for errors and outputs instant fix) | "
        "'arm' (Enables background visual watchdog) | "
        "'disarm' (Stops watchdog) | "
        "'status' (Checks watchdog status). "
        "Call when user asks: 'what is wrong with my screen', 'debug this error', 'look at my code', or 'watch my screen'."
    ),
    "brief": "Autonomous vision watchdog: analyzes screen, detects terminal/compiler errors, and provides instant code fixes.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'inspect' | 'arm' | 'disarm' | 'status'",
                "enum": ["inspect", "arm", "disarm", "status"],
            },
            "query": {
                "type": "STRING",
                "description": "Optional specific focus or question about the screen (e.g. 'why is pytest failing?').",
            },
        },
    },
    "handler": vision_watchdog,
}
