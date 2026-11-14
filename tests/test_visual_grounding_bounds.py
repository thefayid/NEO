"""
tests/test_visual_grounding_bounds.py — Regression & Boundary Protection Tests for Visual Grounding.

Verifies:
1. UIControl.is_plausible rejects uninitialized or astronomical coordinates (e.g. 65535x60830).
2. MacOSScreenHighlightOverlay clamps coordinates safely and prevents GDI CreateDIBSection overflows.
3. Tier 1 UIA falls back gracefully to Tier 2 (SoM) / Tier 3 (Vision) when controls have invalid rects.
4. click_element rejects out-of-bounds clicks.
5. Set-of-Marks candidate boxes filter full-screen backgrounds and invalid controls.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from core.neo_ui_automation import UIControl, WindowsUIAutomationEngine
from core.neo_visual_grounding import (
    UIElement,
    MacOSScreenHighlightOverlay,
    visual_grounding,
)
from core.neo_set_of_marks import SetOfMarksEngine

from PyQt6.QtWidgets import QApplication

# Ensure single shared QApplication instance
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestVisualGroundingBounds(unittest.TestCase):
    def test_ui_control_plausibility(self):
        # 1. Valid standard button
        valid_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(100, 100, 250, 150),
            center=(175, 125),
            handle=12345,
        )
        self.assertTrue(valid_ctrl.is_plausible)
        self.assertEqual(valid_ctrl.width, 150)
        self.assertEqual(valid_ctrl.height, 50)

        # 2. Astronomical 65535x60830 (the YouTube/Chrome virtualized control bug)
        buggy_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(0, 0, 65535, 60830),
            center=(32767, 30415),
            handle=12345,
        )
        self.assertFalse(buggy_ctrl.is_plausible)

        # 3. Microscopic control (< 6px)
        tiny_ctrl = UIControl(
            name="dot",
            control_type="Button",
            rect=(10, 10, 13, 13),
            center=(11, 11),
            handle=12345,
        )
        self.assertFalse(tiny_ctrl.is_plausible)

        # 4. Deep offscreen negative coordinates
        offscreen_ctrl = UIControl(
            name="hidden",
            control_type="Button",
            rect=(-32000, -32000, -31800, -31800),
            center=(-31900, -31900),
            handle=12345,
        )
        self.assertFalse(offscreen_ctrl.is_plausible)

    def test_find_control_ignores_unplausible_controls(self):
        engine = WindowsUIAutomationEngine()
        astronomical_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(0, 0, 65535, 60830),
            center=(32767, 30415),
            handle=12345,
        )

        with patch.object(engine, "get_interactive_controls", return_value=[astronomical_ctrl]):
            # Exact query
            result = engine.find_control("Skip Ad", hwnd=12345, search_all_windows=False)
            self.assertIsNone(result, "find_control should ignore controls with astronomical rects")

            # Substring query
            result_sub = engine.find_control("Skip", hwnd=12345, search_all_windows=False)
            self.assertIsNone(result_sub, "find_control should ignore unplausible controls on substring match")

    def test_highlight_overlay_astronomical_rect_safety(self):
        overlay = MacOSScreenHighlightOverlay()

        # Calling highlight_target with astronomical dimensions must NOT crash or expand to 65535x60830
        overlay.highlight_target((0, 0, 65535, 60830), label="Skip Ad")

        # Overlay geometry must remain reasonable and bounded
        geo = overlay.geometry()
        self.assertLess(geo.width(), 4000)
        self.assertLess(geo.height(), 3000)

        # Test normal bounding box
        overlay.highlight_target((200, 200, 350, 260), label="Test")
        geo_normal = overlay.geometry()
        self.assertGreater(geo_normal.width(), 20)
        self.assertGreater(geo_normal.height(), 20)
        self.assertLess(geo_normal.width(), 4000)

    def test_click_element_out_of_bounds_protection(self):
        # 1. Out of bounds coordinates (32767, 30415)
        ok = visual_grounding.click_element((32767, 30415), verify=False)
        self.assertFalse(ok, "click_element must reject coordinates far beyond monitor boundaries")

        # 2. Negative coordinates
        ok_neg = visual_grounding.click_element((-500, -500), verify=False)
        self.assertFalse(ok_neg, "click_element must reject negative coordinates")

        # 3. Out-of-bounds UIElement
        elem = UIElement(
            label="Buggy",
            bbox=(0, 0, 65535, 60830),
            confidence=1.0,
        )
        ok_elem = visual_grounding.click_element(elem, verify=False)
        self.assertFalse(ok_elem, "click_element must reject UIElement with astronomical center")

    def test_tier1_falls_back_when_uia_rect_is_invalid(self):
        # Simulate find_control returning a virtualized node with invalid dimensions
        fake_bad_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(0, 0, 65535, 60830),
            center=(32767, 30415),
            handle=12345,
        )

        from core.neo_ui_automation import ui_automation
        with patch.object(ui_automation, "_available", True), \
             patch.object(ui_automation, "find_control", return_value=fake_bad_ctrl), \
             patch.object(visual_grounding, "capture_screen", return_value=(None, (1920, 1080))):

            # Should reject Tier 1 and attempt capture_screen
            res = visual_grounding.ground_target_on_screen("Skip Ad", highlight=False, use_uia=True, use_som=False)
            # Since capture_screen returned (None, ...), it returns None instead of the astronomical UIElement
            self.assertIsNone(res)

    def test_set_of_marks_filters_full_screen_and_unplausible(self):
        import PIL.Image
        som = SetOfMarksEngine()
        img = PIL.Image.new("RGB", (1920, 1080), color="white")

        # 1. Full-screen background box
        full_screen_ctrl = UIControl(
            name="Canvas",
            control_type="Custom",
            rect=(0, 0, 1920, 1080),
            center=(960, 540),
            handle=12345,
        )

        # 2. Valid button box
        btn_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(1600, 900, 1800, 950),
            center=(1700, 925),
            handle=12345,
        )

        # 3. Astronomical box
        astronomical_ctrl = UIControl(
            name="Bug",
            control_type="Button",
            rect=(0, 0, 65535, 60830),
            center=(32767, 30415),
            handle=12345,
        )

        boxes = som.extract_candidate_regions(img, uia_controls=[full_screen_ctrl, btn_ctrl, astronomical_ctrl])
        # full_screen_ctrl and astronomical_ctrl should be excluded; btn_ctrl must be present
        self.assertIn((1600, 900, 1800, 950), boxes)
        self.assertNotIn((0, 0, 1920, 1080), boxes)
        self.assertNotIn((0, 0, 65535, 60830), boxes)

    def test_action_visual_screen_grounding_no_dib_crash(self):
        from actions.visual_grounding_action import visual_screen_grounding
        fake_bad_ctrl = UIControl(
            name="Skip Ad",
            control_type="Button",
            rect=(0, 0, 65535, 60830),
            center=(32767, 30415),
            handle=12345,
        )

        from core.neo_ui_automation import ui_automation
        with patch.object(ui_automation, "_available", True), \
             patch.object(ui_automation, "find_control", return_value=fake_bad_ctrl), \
             patch.object(visual_grounding, "capture_screen", return_value=(None, (1920, 1080))):

            # Invoking visual_screen_grounding with 'Skip Ad' must not raise any CreateDIB error or exception
            res = visual_screen_grounding({"query": "Skip Ad", "action": "click"})
            self.assertIn("Could not locate", res)

    def test_gemini_vision_1000_scale_normalization(self):
        # When Gemini returns bbox in standard [0, 1000] scale
        mock_raw = '{"found": true, "label": "YouTube progress bar", "bbox_norm": [850, 440, 880, 890]}'
        with patch("core.gemini.multimodal", return_value=mock_raw):
            elem = visual_grounding._query_gemini_grounding("YouTube progress bar", b"fake", 1920, 1080)
            self.assertIsNotNone(elem)
            # Physical bbox should be within screen resolution (not 680640, 925020)
            self.assertLessEqual(elem.bbox[0], 1920)
            self.assertLessEqual(elem.bbox[1], 1080)
            self.assertLessEqual(elem.bbox[2], 1920)
            self.assertLessEqual(elem.bbox[3], 1080)
            self.assertGreaterEqual(elem.bbox[0], 0)
            self.assertGreaterEqual(elem.bbox[1], 0)
            # Verify coordinates are approx (844, 918, 1708, 950)
            self.assertEqual(elem.bbox, (844, 918, 1708, 950))

    def test_computer_control_scroll_wheel_delta_on_windows(self):
        from actions.computer_control import _scroll
        with patch("actions.computer_control._require_pyautogui"), \
             patch("actions.computer_control._get_os", return_value="windows"), \
             patch("pyautogui.scroll") as mock_scroll:
            _scroll(direction="down", amount=5)
            # 5 notches on Windows must be scaled by WHEEL_DELTA (120) -> -600
            mock_scroll.assert_called_once_with(-600)

    def test_computer_control_type_uses_clipboard_for_urls(self):
        from actions.computer_control import _type
        with patch("actions.computer_control._require_pyautogui"), \
             patch("actions.computer_control._require_pyperclip", return_value=True), \
             patch("actions.computer_control.pyperclip.copy") as mock_copy, \
             patch("pyautogui.hotkey") as mock_hotkey:
            url = "https://www.linkedin.com/jobs"
            res = _type(url)
            mock_copy.assert_called_once_with(url)
            self.assertIn("Typed: https://www.linkedin.com/jobs", res)

    def test_computer_control_key_normalization(self):
        from actions.computer_control import _press, _hotkey
        with patch("actions.computer_control._require_pyautogui"), \
             patch("pyautogui.press") as mock_press, \
             patch("pyautogui.hotkey") as mock_hotkey:
            _press("ENTER")
            mock_press.assert_called_with("enter")

            _press("Return")
            mock_press.assert_called_with("enter")

            _press("ESC")
            mock_press.assert_called_with("escape")

            _hotkey("CTRL", "SHIFT", "ESC")
            mock_hotkey.assert_called_with("ctrl", "shift", "escape")


if __name__ == "__main__":
    unittest.main()
