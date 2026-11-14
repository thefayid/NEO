"""
tests/test_advanced_computer_control_suite.py — Verification suite for Advanced Computer Control Pillars:
1. DPI-Aware Physical Coordinate Transformer & Element Detector
2. Set-of-Marks (SoM) Interactive Grid Engine
3. Headful Browser Chrome DevTools Protocol (CDP) Bridge
4. Deep Windows OS Orchestrator (ms-settings: URIs & Power Schemes)
5. Visual Diff Oracle & Adaptive Settle Watchdog
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from core.neo_dpi_ocr import DpiCoordinateTransformer, LocalVisualElementDetector, dpi_transformer
from core.neo_som_engine import som_engine
from actions.computer_control import computer_control
from core.neo_cdp_bridge import ChromeDevToolsBridge, cdp_bridge
from actions.browser_cdp import run as run_browser_cdp
from core.neo_win_orchestrator import WindowsDeepOrchestrator, win_orchestrator
from actions.os_control import run as run_os_control
from core.neo_visual_diff_oracle import VisualDiffOracle


class TestDpiCoordinateTransformer(unittest.TestCase):
    def test_dpi_scale_factor_and_transforms(self):
        transformer = DpiCoordinateTransformer()
        # Scale factor should be positive float
        self.assertGreater(transformer.scale_factor, 0.5)

        # Test with known scale factor of 1.25
        with patch.object(transformer, "_scale_factor", 1.25):
            lx, ly = transformer.physical_to_logical(1250, 625)
            self.assertEqual((lx, ly), (1000, 500))

            px, py = transformer.logical_to_physical(1000, 500)
            self.assertEqual((px, py), (1250, 625))

            # Bounding box
            rect_phys = (100, 200, 300, 400)
            rect_log = transformer.physical_rect_to_logical(rect_phys)
            self.assertEqual(rect_log, (80, 160, 240, 320))

    def test_local_visual_element_detector(self):
        detector = LocalVisualElementDetector(dpi_transformer)
        # Create a synthetic image with a button
        sample = np.zeros((300, 500, 3), dtype=np.uint8)
        sample[50:110, 80:240] = 220  # Bright button-like box

        elements = detector.detect_elements(sample)
        self.assertTrue(len(elements) >= 1)
        first = elements[0]
        self.assertIn(first.kind, ("button", "input", "text_block", "icon"))
        self.assertGreater(first.area, 0)
        self.assertEqual(len(first.center_logical), 2)


class TestSetOfMarksEngine(unittest.TestCase):
    def test_som_generation_and_mark_lookup(self):
        test_img = Path("core/test_som_tmp.png")
        img = Image.new("RGB", (600, 400), color=(35, 35, 40))
        img.save(str(test_img))

        try:
            tagged_path, marks = som_engine.generate_som_grid(test_img)
            self.assertTrue(tagged_path.exists())
            # Marks can be listed
            summary = som_engine.list_marks_summary()
            self.assertIsInstance(summary, list)

            # Test computer_control som_tag_screen and som_click
            res_tag = computer_control({"action": "som_tag_screen", "path": str(test_img)})
            self.assertIn("Generated Set-of-Marks grid", res_tag)

            # som_click on missing mark reports graceful message
            res_click = computer_control({"action": "som_click", "mark_id": 9999})
            self.assertIn("Error: Mark [9999] not found", res_click)
        finally:
            if test_img.exists():
                test_img.unlink()


class TestBrowserCDPBridge(unittest.TestCase):
    def test_cdp_status_when_offline(self):
        bridge = ChromeDevToolsBridge(port=65432)  # Non-listening port
        self.assertFalse(bridge.is_connected())
        self.assertEqual(bridge.get_tabs(), [])

        # Action tool status
        with patch.object(cdp_bridge, "is_connected", return_value=False):
            res = run_browser_cdp({"action": "status"})
            self.assertIn("status=done", res)
            self.assertIn("connected=false", res)

    def test_cdp_eval_and_click_mock(self):
        with patch.object(cdp_bridge, "eval_js") as mock_eval:
            mock_eval.return_value = {"success": True, "tag": "BUTTON", "text": "Submit"}
            res = run_browser_cdp({"action": "click_selector", "selector": "#btn-submit"})
            self.assertIn("status=done", res)
            self.assertIn("clicked=#btn-submit", res)

    def test_cdp_type_selector_mock(self):
        with patch.object(cdp_bridge, "eval_js") as mock_eval:
            mock_eval.return_value = {"success": True, "value": "test@example.com"}
            res = run_browser_cdp({"action": "type_selector", "selector": "input#email", "text": "test@example.com"})
            self.assertIn("status=done", res)
            self.assertIn("typed=test@example.com", res)


class TestDeepWindowsOrchestrator(unittest.TestCase):
    def test_settings_uri_resolution(self):
        orchestrator = WindowsDeepOrchestrator()
        self.assertIn("wifi", orchestrator.SETTINGS_URIS)
        self.assertIn("sound", orchestrator.SETTINGS_URIS)
        self.assertIn("display", orchestrator.SETTINGS_URIS)
        self.assertIn("bluetooth", orchestrator.SETTINGS_URIS)

    def test_os_control_deep_actions(self):
        # 1. open_settings
        with patch.object(win_orchestrator, "open_settings_page", return_value=(True, "Opened Windows settings for 'wifi'.")):
            res = run_os_control({"action": "open_settings", "page": "wifi"})
            self.assertIn("status=done", res)
            self.assertIn("page=wifi", res)

        # 2. power_plan query
        with patch.object(win_orchestrator, "get_active_power_scheme", return_value="high_performance"):
            res = run_os_control({"action": "power_plan"})
            self.assertIn("status=done", res)
            self.assertIn("active_plan=high_performance", res)

        # 3. audio_devices
        with patch.object(win_orchestrator, "list_audio_endpoints", return_value=[{"index": 0, "name": "Headphones", "inputs": 0, "outputs": 2}]):
            res = run_os_control({"action": "audio_devices"})
            self.assertIn("status=done", res)
            self.assertIn("count=1", res)


class TestVisualDiffOracle(unittest.TestCase):
    def test_compute_visual_diff(self):
        oracle = VisualDiffOracle()
        img1 = np.zeros((100, 100, 3), dtype=np.uint8)
        img2 = np.zeros((100, 100, 3), dtype=np.uint8)

        # Identical images must have 0 diff
        diff_zero = oracle.compute_visual_diff(img1, img2)
        self.assertEqual(diff_zero, 0.0)

        # Differing image
        img2[20:60, 20:60] = 255
        diff_changed = oracle.compute_visual_diff(img1, img2)
        self.assertGreater(diff_changed, 0.1)

    def test_adaptive_settle_watchdog_stable(self):
        oracle = VisualDiffOracle()
        # With zero screen variance, should stabilize quickly
        with patch.object(oracle, "capture_fullscreen") as mock_screen:
            mock_screen.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
            with patch("pyautogui.screenshot", return_value=Image.new("RGB", (50, 50))):
                settled = oracle.wait_until_settled(max_wait_sec=0.5, check_interval_sec=0.05)
                self.assertTrue(settled)


if __name__ == "__main__":
    unittest.main()
