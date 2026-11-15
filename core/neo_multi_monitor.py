"""
core/neo_multi_monitor.py — Multi-Monitor Spatial Awareness & Coordinate Mapper for NEO.

Provides deep multi-display management across Windows, macOS, and Linux:
1. Virtual Desktop Coordinate Topology:
   - Enumerates physical and logical geometries of all connected monitors.
   - Maps local per-monitor coordinates to unified virtual desktop space.
2. Spatial Natural Language Disambiguation:
   - Resolves phrases like "left monitor", "right screen", "monitor 2", "primary display".
3. Targeted Per-Monitor Screen Capture:
   - Captures individual displays or unified multi-monitor bounding canvases.
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("NEO.MultiMonitor")

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "memory"


@dataclass
class DisplayInfo:
    index: int                          # 1-based index (1, 2, ...)
    name: str                           # e.g., "Display 1", "\\\\.\\DISPLAY1"
    x: int                              # Virtual desktop top-left X
    y: int                              # Virtual desktop top-left Y
    width: int                          # Physical/Logical width
    height: int                         # Physical/Logical height
    is_primary: bool = False
    scale_factor: float = 1.0

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Returns (left, top, right, bottom)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def contains_point(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


class NEOMultiMonitorManager:
    """Manages multi-monitor spatial coordinates and per-display captures."""

    _instance: Optional["NEOMultiMonitorManager"] = None

    def __new__(cls) -> "NEOMultiMonitorManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._displays: List[DisplayInfo] = []
            cls._instance._refresh_displays()
        return cls._instance

    @property
    def displays(self) -> List[DisplayInfo]:
        if not self._displays:
            self._refresh_displays()
        return self._displays

    def _refresh_displays(self) -> None:
        """Harvests connected display geometries."""
        displays: List[DisplayInfo] = []

        # 1. Try mss (fastest and cross-platform)
        try:
            import mss
            with mss.mss() as sct:
                # mss monitors[0] is the combined virtual screen; 1..N are physical monitors
                raw_mons = sct.monitors
                if len(raw_mons) > 1:
                    for idx, m in enumerate(raw_mons[1:], start=1):
                        displays.append(DisplayInfo(
                            index=idx,
                            name=f"Monitor {idx}",
                            x=m["left"],
                            y=m["top"],
                            width=m["width"],
                            height=m["height"],
                            is_primary=(idx == 1 or (m["left"] == 0 and m["top"] == 0)),
                        ))
        except Exception as e:
            logger.debug(f"mss monitor detection unavailable: {e}")

        # 2. Fallback to PyQt6 QGuiApplication if available
        if not displays:
            try:
                from PyQt6.QtGui import QGuiApplication
                screens = QGuiApplication.screens()
                if screens:
                    primary_screen = QGuiApplication.primaryScreen()
                    for idx, scr in enumerate(screens, start=1):
                        geo = scr.geometry()
                        displays.append(DisplayInfo(
                            index=idx,
                            name=scr.name() or f"Monitor {idx}",
                            x=geo.x(),
                            y=geo.y(),
                            width=geo.width(),
                            height=geo.height(),
                            is_primary=(scr == primary_screen),
                            scale_factor=scr.devicePixelRatio(),
                        ))
            except Exception as e:
                logger.debug(f"PyQt6 screen detection fallback: {e}")

        # 3. Ultimate Fallback to primary 1920x1080 display
        if not displays:
            displays.append(DisplayInfo(
                index=1,
                name="Primary Monitor",
                x=0,
                y=0,
                width=1920,
                height=1080,
                is_primary=True,
                scale_factor=1.0,
            ))

        self._displays = displays

    def get_display(self, target: Union[int, str]) -> Optional[DisplayInfo]:
        """Resolves target index or name to DisplayInfo."""
        displays = self.displays
        if isinstance(target, int):
            for d in displays:
                if d.index == target:
                    return d
            return displays[0] if displays else None

        parsed_idx = self.parse_spatial_reference(str(target))
        if parsed_idx:
            for d in displays:
                if d.index == parsed_idx:
                    return d

        # Primary fallback
        for d in displays:
            if d.is_primary:
                return d
        return displays[0] if displays else None

    def parse_spatial_reference(self, text: str) -> Optional[int]:
        """
        Parses text for monitor references like:
        - "monitor 2", "screen 1", "display 3"
        - "left screen", "right monitor", "secondary display"
        """
        t = text.lower().strip()
        displays = self.displays
        if not displays:
            return 1

        # Direct number match
        match = re.search(r"\b(?:monitor|screen|display)\s*#?([1-9])\b", t)
        if match:
            idx = int(match.group(1))
            if any(d.index == idx for d in displays):
                return idx

        # Primary / Secondary
        if "primary" in t or "main" in t:
            for d in displays:
                if d.is_primary:
                    return d.index
            return 1

        if "secondary" in t or "second" in t:
            for d in displays:
                if not d.is_primary:
                    return d.index
            return 2 if len(displays) > 1 else 1

        # Spatial left / right sorting
        sorted_by_x = sorted(displays, key=lambda d: d.x)
        if "left" in t and sorted_by_x:
            return sorted_by_x[0].index
        if "right" in t and sorted_by_x:
            return sorted_by_x[-1].index

        return None

    def capture_display(
        self,
        target_display: Union[int, str] = 1,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[Path, DisplayInfo]:
        """Captures a specific display and returns the image path and display info."""
        disp = self.get_display(target_display)
        if not disp:
            raise RuntimeError(f"No display found for target '{target_display}'")

        out = Path(output_path) if output_path else _MEMORY_DIR / f"monitor_{disp.index}_capture.png"
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitor_dict = {
                    "left": disp.x,
                    "top": disp.y,
                    "width": disp.width,
                    "height": disp.height,
                }
                sct_img = sct.grab(monitor_dict)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.save(str(out))
                return out, disp
        except Exception:
            # Fallback to pyautogui or PIL
            try:
                import pyautogui
                img = pyautogui.screenshot(region=(disp.x, disp.y, disp.width, disp.height))
                img.save(str(out))
                return out, disp
            except Exception as e:
                logger.error(f"Failed capturing display {disp.index}: {e}")
                from PIL import Image
                img = Image.new("RGB", (disp.width, disp.height), color=(30, 30, 35))
                img.save(str(out))
                return out, disp

    def local_to_virtual_coords(self, local_x: int, local_y: int, display_index: int) -> Tuple[int, int]:
        """Translates local monitor coordinates into global virtual desktop coordinates."""
        disp = self.get_display(display_index)
        if not disp:
            return local_x, local_y
        return disp.x + local_x, disp.y + local_y

    def virtual_to_local_coords(self, virt_x: int, virt_y: int) -> Tuple[int, int, DisplayInfo]:
        """Determines which display contains the virtual coordinate and returns local coords."""
        for d in self.displays:
            if d.contains_point(virt_x, virt_y):
                return virt_x - d.x, virt_y - d.y, d
        primary = self.get_display(1)
        return virt_x, virt_y, primary or self.displays[0]


multi_monitor = NEOMultiMonitorManager()
