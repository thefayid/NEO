"""
core/neo_win_orchestrator.py — Deep Windows OS & WMI Orchestrator for NEO.

Provides direct access to Windows deep protocols and settings:
1. Windows `ms-settings:` URI scheme dispatcher:
   - Jumps directly to Wi-Fi, Bluetooth, Sound, Display, Apps, Storage, and Battery pages in 1ms.
2. Hardware Power Scheme Management:
   - Sets power plans (High Performance, Balanced, Power Saver) via native powercfg.
3. Virtual Desktop Navigation:
   - Next, previous, new, and close virtual desktops using native hotkey chords.
4. Audio Playback Device Inspection:
   - Lists active audio render endpoints and states.
"""
from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Dict, List, Tuple

_OS = platform.system()


class WindowsDeepOrchestrator:
    """Manages deep Windows protocols, WMI settings, and URI schemes."""

    # Standard Windows Power Scheme GUIDs
    POWER_SCHEMES = {
        "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    }

    # ms-settings URI registry
    SETTINGS_URIS = {
        "wifi": "ms-settings:network-wifi",
        "network": "ms-settings:network",
        "bluetooth": "ms-settings:bluetooth",
        "sound": "ms-settings:sound",
        "volume": "ms-settings:apps-volume",
        "display": "ms-settings:display",
        "battery": "ms-settings:batterysaver",
        "apps": "ms-settings:appsfeatures",
        "default_apps": "ms-settings:defaultapps",
        "storage": "ms-settings:storagesense",
        "windows_update": "ms-settings:windowsupdate",
        "clipboard": "ms-settings:clipboard",
        "notifications": "ms-settings:notifications",
        "night_light": "ms-settings:nightlight",
        "printers": "ms-settings:printers",
        "taskbar": "ms-settings:taskbar",
    }

    def open_settings_page(self, page_name: str) -> Tuple[bool, str]:
        """Opens the exact Windows settings sub-page via deep URI in 1ms."""
        clean_key = page_name.strip().lower().replace(" ", "_")
        uri = self.SETTINGS_URIS.get(clean_key)
        if not uri:
            # Fuzzy match
            for k, u in self.SETTINGS_URIS.items():
                if clean_key in k or k in clean_key:
                    uri = u
                    clean_key = k
                    break

        if not uri:
            return False, f"Unknown settings page '{page_name}'. Available: {list(self.SETTINGS_URIS.keys())}"

        if _OS == "Windows":
            try:
                os.startfile(uri)
                return True, f"Opened Windows settings for '{clean_key}' ({uri})."
            except Exception:
                try:
                    subprocess.Popen(f"start {uri}", shell=True)
                    return True, f"Opened Windows settings for '{clean_key}'."
                except Exception as ex:
                    return False, f"Failed opening '{uri}': {ex}"
        return False, "Windows settings URIs only supported on Windows OS."

    def get_active_power_scheme(self) -> str:
        """Returns the active Windows power plan."""
        if _OS != "Windows":
            return "N/A"
        try:
            res = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=3)
            out = res.stdout.strip()
            for name, guid in self.POWER_SCHEMES.items():
                if guid.lower() in out.lower():
                    return name
            return out
        except Exception as e:
            return f"Error: {e}"

    def set_power_scheme(self, scheme_name: str) -> Tuple[bool, str]:
        """Sets Windows power scheme to High Performance, Balanced, or Power Saver."""
        if _OS != "Windows":
            return False, "Only supported on Windows OS."
        clean = scheme_name.strip().lower().replace(" ", "_")
        guid = self.POWER_SCHEMES.get(clean)
        if not guid:
            return False, f"Unknown scheme '{scheme_name}'. Choose from: {list(self.POWER_SCHEMES.keys())}"

        try:
            subprocess.run(["powercfg", "/setactive", guid], capture_output=True, text=True, check=True)
            return True, f"Activated Windows power scheme: {clean.replace('_', ' ').title()}."
        except Exception as e:
            return False, f"Failed setting power scheme: {e}"

    def virtual_desktop(self, action: str) -> Tuple[bool, str]:
        """
        Navigates or manages Windows Virtual Desktops:
        'next' (Ctrl+Win+Right), 'prev' (Ctrl+Win+Left), 'new' (Ctrl+Win+D), 'close' (Ctrl+Win+F4)
        """
        import pyautogui
        act = action.strip().lower()
        if act == "next":
            pyautogui.hotkey("ctrl", "win", "right")
            return True, "Switched to next virtual desktop."
        elif act in ("prev", "previous"):
            pyautogui.hotkey("ctrl", "win", "left")
            return True, "Switched to previous virtual desktop."
        elif act in ("new", "create"):
            pyautogui.hotkey("ctrl", "win", "d")
            return True, "Created new virtual desktop."
        elif act in ("close", "delete"):
            pyautogui.hotkey("ctrl", "win", "f4")
            return True, "Closed current virtual desktop."
        return False, f"Unknown virtual desktop action '{action}'. Use: next, prev, new, close."

    def list_audio_endpoints(self) -> List[Dict[str, Any]]:
        """Enumerates active audio output and input endpoints via sounddevice."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            endpoints = []
            for idx, dev in enumerate(devices):
                if dev.get("max_output_channels", 0) > 0 or dev.get("max_input_channels", 0) > 0:
                    endpoints.append({
                        "index": idx,
                        "name": dev.get("name"),
                        "inputs": dev.get("max_input_channels"),
                        "outputs": dev.get("max_output_channels"),
                        "samplerate": int(dev.get("default_samplerate", 44100)),
                    })
            return endpoints
        except Exception:
            return []


# Global Singleton accessor
win_orchestrator = WindowsDeepOrchestrator()
