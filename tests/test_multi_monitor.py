"""
tests/test_multi_monitor.py — Unit tests for Multi-Monitor Spatial Awareness & Coordinate Mapper.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.neo_multi_monitor import (
    DisplayInfo,
    NEOMultiMonitorManager,
    multi_monitor,
)
from actions.computer_control import computer_control


class TestNEOMultiMonitor(unittest.TestCase):
    def test_display_info_properties(self):
        d1 = DisplayInfo(index=1, name="Display 1", x=0, y=0, width=1920, height=1080, is_primary=True)
        self.assertEqual(d1.bbox, (0, 0, 1920, 1080))
        self.assertTrue(d1.contains_point(500, 500))
        self.assertFalse(d1.contains_point(2000, 500))

    def test_spatial_natural_language_parsing(self):
        mgr = NEOMultiMonitorManager()
        # Seed test displays: Monitor 1 (left) and Monitor 2 (right)
        d1 = DisplayInfo(index=1, name="Left Monitor", x=0, y=0, width=1920, height=1080, is_primary=True)
        d2 = DisplayInfo(index=2, name="Right Monitor", x=1920, y=0, width=2560, height=1440, is_primary=False)
        mgr._displays = [d1, d2]

        self.assertEqual(mgr.parse_spatial_reference("click on monitor 2"), 2)
        self.assertEqual(mgr.parse_spatial_reference("look at screen 1"), 1)
        self.assertEqual(mgr.parse_spatial_reference("on the secondary display"), 2)
        self.assertEqual(mgr.parse_spatial_reference("on my primary screen"), 1)
        self.assertEqual(mgr.parse_spatial_reference("check the right screen"), 2)
        self.assertEqual(mgr.parse_spatial_reference("check the left screen"), 1)

    def test_virtual_and_local_coordinate_translation(self):
        mgr = NEOMultiMonitorManager()
        d1 = DisplayInfo(index=1, name="Left Monitor", x=0, y=0, width=1920, height=1080, is_primary=True)
        d2 = DisplayInfo(index=2, name="Right Monitor", x=1920, y=0, width=1920, height=1080, is_primary=False)
        mgr._displays = [d1, d2]

        # Local to virtual
        vx, vy = mgr.local_to_virtual_coords(100, 200, display_index=2)
        self.assertEqual((vx, vy), (2020, 200))

        # Virtual to local
        lx, ly, disp = mgr.virtual_to_local_coords(2020, 200)
        self.assertEqual((lx, ly), (100, 200))
        self.assertEqual(disp.index, 2)

    def test_computer_control_list_monitors(self):
        res = computer_control({"action": "list_monitors"})
        self.assertIn("Found", res)
        self.assertIn("active monitor", res)


if __name__ == "__main__":
    unittest.main()
