"""
core/neo_reflex_engine.py — Zero-Latency Spontaneous Reflex Execution Engine for NEO.

Provides deterministic, sub-5-millisecond local execution for high-frequency OS,
window management, application launching, volume, and media control commands.

Bypasses cloud round-trip latency entirely for direct commands while keeping
the live session and UI seamlessly synchronized.
"""
from __future__ import annotations

import re
import platform
import ctypes
import threading
from pathlib import Path
from typing import Optional, Tuple

from core.neo_os_automation import window_manager, resource_manager
from core.neo_win_orchestrator import win_orchestrator
from core import audio_devices

_OS = platform.system()


class NeoReflexEngine:
    """Instant local reflex execution engine for spontaneous command handling."""

    def __init__(self):
        self._last_volume: int = 50
        if _OS == "Windows":
            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass
        # Warm up COM audio endpoint on background thread
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self):
        if _OS == "Windows":
            try:
                ctypes.windll.ole32.CoInitialize(None)
                from actions.computer_settings import _win_endpoint_volume
                _win_endpoint_volume()
            except Exception:
                pass
        try:
            v = audio_devices.get_output_volume()
            if v and v > 0:
                self._last_volume = v
        except Exception:
            pass

    def try_execute(self, text: str) -> Optional[Tuple[bool, str]]:
        """
        Attempts to match and execute text as an instant local reflex.
        Returns (success: bool, feedback_message: str) if handled, or None if
        the command requires cognitive reasoning and should be passed to Gemini.
        """
        if not text or not isinstance(text, str):
            return None

        if _OS == "Windows":
            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

        clean = text.strip().lower()
        # Strip polite filler words
        clean = re.sub(r"^(please|hey\s+neo|neo|can\s+you|could\s+you|would\s+you|just|bro|boss|sir)\s+", "", clean).strip()
        clean = re.sub(r"\s+(please|boss|sir|neo|now|right\s+now)$", "", clean).strip()

        # ── 1. Audio & Volume Reflexes (< 2ms) ────────────────────────────────
        if clean in ("mute", "mute audio", "mute sound", "mute volume", "silence"):
            if _OS == "Windows":
                try:
                    VK_VOLUME_MUTE = 0xAD
                    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                    return True, "Muted audio."
                except Exception:
                    pass
            curr = audio_devices.get_output_volume()
            if curr and curr > 0:
                self._last_volume = curr
            audio_devices.set_output_volume(0)
            return True, "Muted audio."

        if clean in ("unmute", "unmute audio", "unmute sound", "unmute volume"):
            if _OS == "Windows":
                try:
                    VK_VOLUME_MUTE = 0xAD
                    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                    return True, "Unmuted audio."
                except Exception:
                    pass
            target = self._last_volume if self._last_volume > 5 else 40
            audio_devices.set_output_volume(target)
            return True, f"Unmuted (Volume: {target}%)."

        # Volume Up / Down
        if clean in ("volume up", "louder", "turn up volume", "increase volume", "raise volume"):
            if _OS == "Windows":
                try:
                    VK_VOLUME_UP = 0xAF
                    for _ in range(5):
                        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
                    return True, "Volume increased."
                except Exception:
                    pass
            curr = audio_devices.get_output_volume() or 50
            nxt = min(100, curr + 10)
            audio_devices.set_output_volume(nxt)
            return True, f"Volume up to {nxt}%."

        if clean in ("volume down", "quieter", "turn down volume", "decrease volume", "lower volume"):
            if _OS == "Windows":
                try:
                    VK_VOLUME_DOWN = 0xAE
                    for _ in range(5):
                        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
                    return True, "Volume decreased."
                except Exception:
                    pass
            curr = audio_devices.get_output_volume() or 50
            nxt = max(0, curr - 10)
            audio_devices.set_output_volume(nxt)
            return True, f"Volume down to {nxt}%."

        # Exact Volume Set
        vol_match = re.match(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?$", clean)
        if vol_match:
            val = max(0, min(100, int(vol_match.group(1))))
            if _OS == "Windows":
                try:
                    from actions.computer_settings import _win_endpoint_volume
                    ep = _win_endpoint_volume()
                    if ep:
                        ep.SetMasterVolumeLevelScalar(val / 100.0, None)
                        self._last_volume = val
                        return True, f"Volume set to {val}%."
                except Exception:
                    pass
            audio_devices.set_output_volume(val)
            self._last_volume = val
            return True, f"Volume set to {val}%."

        # ── 2. Window Management Reflexes (< 3ms) ─────────────────────────────
        # Snapping
        snap_map = {
            "snap left": "left",
            "snap to left": "left",
            "window left": "left",
            "snap right": "right",
            "snap to right": "right",
            "window right": "right",
            "snap top": "top",
            "snap to top": "top",
            "snap bottom": "bottom",
            "snap to bottom": "bottom",
            "maximize": "maximize",
            "maximize window": "maximize",
            "fullscreen": "maximize",
            "minimize": "minimize",
            "minimize window": "minimize",
            "center window": "center",
            "center": "center",
            "restore window": "restore",
            "restore": "restore",
        }
        if clean in snap_map:
            pos = snap_map[clean]
            ok = window_manager.snap_active_window(pos)
            if ok:
                return True, f"Snapped active window to {pos}."
            return False, f"Could not snap window to {pos}."

        # Tiling
        if clean in ("tile windows", "tile top windows", "split screen", "split display", "side by side"):
            ok = window_manager.tile_two_windows(mode="side_by_side")
            if ok:
                return True, "Tiled top two windows side-by-side."
            return False, "Could not tile windows."

        # Close Window
        if clean in ("close window", "close active window", "close current window", "close this window"):
            ok = win_orchestrator.close_window(None)
            if ok:
                return True, "Closed active window."
            return False, "Could not close window."

        # ── 3. Media Playback Controls (< 1ms) ────────────────────────────────
        if _OS == "Windows":
            user32 = ctypes.windll.user32
            VK_MEDIA_NEXT_TRACK = 0xB0
            VK_MEDIA_PREV_TRACK = 0xB1
            VK_MEDIA_PLAY_PAUSE = 0xB3
            KEYEVENTF_EXTENDEDKEY = 0x0001
            KEYEVENTF_KEYUP = 0x0002

            def _tap_key(vk: int):
                user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

            if clean in ("play", "pause", "resume", "play music", "pause music", "stop music", "toggle music", "resume music"):
                _tap_key(VK_MEDIA_PLAY_PAUSE)
                return True, "Toggled media playback."

            if clean in ("next song", "next track", "skip song", "skip track", "next"):
                _tap_key(VK_MEDIA_NEXT_TRACK)
                return True, "Skipped to next track."

            if clean in ("previous song", "previous track", "prev song", "prev track", "previous"):
                _tap_key(VK_MEDIA_PREV_TRACK)
                return True, "Returned to previous track."

        # ── 4. System Utilities (< 5ms) ───────────────────────────────────────
        if clean in ("empty recycle bin", "clean recycle bin", "empty trash", "clean trash"):
            ok = resource_manager.empty_recycle_bin()
            if ok:
                return True, "Recycle bin emptied."
            return False, "Could not empty recycle bin."

        if clean in ("lock screen", "lock workstation", "lock pc", "lock computer"):
            if _OS == "Windows":
                ctypes.windll.user32.LockWorkStation()
                return True, "Workstation locked."

        if clean in ("open explorer", "open file explorer", "open files", "my files"):
            resource_manager.open_explorer_path(str(Path.home()))
            return True, "Opened File Explorer."

        if clean in ("open downloads", "show downloads", "downloads folder"):
            resource_manager.open_explorer_path(str(Path.home() / "Downloads"))
            return True, "Opened Downloads."

        if clean in ("open desktop", "show desktop", "desktop folder"):
            resource_manager.open_explorer_path(str(Path.home() / "Desktop"))
            return True, "Opened Desktop."

        # ── 5. Instant Application Launching (< 1ms Non-Blocking) ─────────────
        app_launch_match = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_\-\.\s]+)$", clean)
        if app_launch_match:
            raw_target = app_launch_match.group(1).strip()
            # Filter out non-app sentences
            non_apps = (
                "settings", "camera", "cam", "files", "explorer", "downloads", "desktop",
                "music", "chat", "terminal", "swarm", "vision", "notes", "tasks", "projects", "knowledge"
            )
            if raw_target in non_apps:
                return None
            # Aliases
            alias_map = {
                "chrome": "Google Chrome",
                "google chrome": "Google Chrome",
                "spotify": "Spotify",
                "code": "Visual Studio Code",
                "vs code": "Visual Studio Code",
                "vscode": "Visual Studio Code",
                "visual studio code": "Visual Studio Code",
                "notepad": "Notepad",
                "calc": "Calculator",
                "calculator": "Calculator",
                "terminal": "Windows Terminal",
                "cmd": "cmd.exe",
                "powershell": "powershell.exe",
                "edge": "Microsoft Edge",
                "ms edge": "Microsoft Edge",
                "whatsapp": "WhatsApp",
                "telegram": "Telegram",
                "discord": "Discord",
                "slack": "Slack",
                "cursor": "Cursor",
            }
            if raw_target in alias_map:
                target_name = alias_map[raw_target]
                try:
                    from actions.open_app import open_app
                    threading.Thread(target=open_app, args=({"app_name": target_name},), daemon=True).start()
                    return True, f"Launching {target_name}..."
                except Exception as e:
                    return False, f"Failed to launch {target_name}: {e}"

        return None


# Global singleton instance
reflex_engine = NeoReflexEngine()
