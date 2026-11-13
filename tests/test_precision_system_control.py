"""
tests/test_precision_system_control.py — Test suite for 3-Tier Precision System Control.

Tests:
1. Native Windows UI Automation (UIA) Control Extraction & Matching
2. Set-of-Marks (SoM) Candidate Extraction, Badge Drawing & Mark Resolution
3. Closed-Loop UI Action Verification (Snapshots, deltas, verification scoring)
4. Visual Grounding Action Integration (Tiered resolution & verified clicks)
"""
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from core.neo_ui_automation import UIControl, WindowsUIAutomationEngine
from core.neo_set_of_marks import Mark, SetOfMarksEngine
from core.neo_ui_verifier import UIStateSnapshot, UIActionVerifier, VerificationResult
from core.neo_visual_grounding import VisualGroundingEngine, UIElement
import actions.visual_grounding_action as vga


class TestPrecisionSystemControl(unittest.TestCase):

    def setUp(self):
        self.uia = WindowsUIAutomationEngine()
        self.som = SetOfMarksEngine()
        self.verifier = UIActionVerifier()

    def test_ui_control_dataclass_properties(self):
        ctrl = UIControl(
            name="Search",
            control_type="Button",
            rect=(100, 200, 250, 240),
            center=(175, 220),
            handle=12345,
            automation_id="SearchBtn",
        )
        self.assertEqual(ctrl.width, 150)
        self.assertEqual(ctrl.height, 40)
        self.assertEqual(ctrl.area, 6000)
        self.assertEqual(ctrl.center, (175, 220))

    def test_uia_matching_exact_and_fuzzy(self):
        c1 = UIControl("Google Search", "Button", (10, 10, 60, 30), (35, 20), 101, automation_id="btn_search")
        c2 = UIControl("Address and search bar", "Edit", (70, 10, 300, 30), (185, 20), 101, automation_id="omnibox")
        c3 = UIControl("Settings", "MenuItem", (310, 10, 350, 30), (330, 20), 101)

        with patch.object(self.uia, "get_interactive_controls", return_value=[c1, c2, c3]):
            # Exact automation_id match
            res1 = self.uia.find_control("btn_search", search_all_windows=False)
            self.assertIsNotNone(res1)
            self.assertEqual(res1.name, "Google Search")

            # Direct substring match
            res2 = self.uia.find_control("search bar", search_all_windows=False)
            self.assertIsNotNone(res2)
            self.assertEqual(res2.name, "Address and search bar")

            # Token overlap match
            res3 = self.uia.find_control("settings menu", search_all_windows=False)
            self.assertIsNotNone(res3)
            self.assertEqual(res3.name, "Settings")

            # Non-existent query
            res4 = self.uia.find_control("nonexistent_element_xyz", search_all_windows=False)
            self.assertIsNone(res4)

    def test_som_candidate_extraction_and_annotation(self):
        # Create a test synthetic screenshot
        im = Image.new("RGB", (800, 600), color=(30, 30, 30))
        c1 = UIControl("Submit", "Button", (100, 100, 200, 140), (150, 120), 101)
        c2 = UIControl("Email Input", "Edit", (100, 160, 400, 200), (250, 180), 101)

        annotated, marks = self.som.annotate_screenshot(im, uia_controls=[c1, c2])

        self.assertGreaterEqual(len(marks), 2)
        # Verify mark centers match UIControl rect centers
        mark_centers = [m.center for m in marks.values()]
        self.assertIn((150, 120), mark_centers)
        self.assertIn((250, 180), mark_centers)
        self.assertEqual(annotated.size, (800, 600))

    def test_som_query_mark_resolution(self):
        m1 = Mark(id=1, rect=(50, 50, 120, 80), center=(85, 65), label="Profile", control_type="Button")
        m2 = Mark(id=2, rect=(130, 50, 200, 80), center=(165, 65), label="Notifications", control_type="Button")
        marks = {1: m1, 2: m2}

        test_img = Image.new("RGB", (300, 200), color=(50, 50, 50))

        # Direct label match
        found = self.som.query_mark("Profile", test_img, marks)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, 1)
        self.assertEqual(found.center, (85, 65))

        # Gemini response mock
        with patch("core.gemini.multimodal", return_value='{"found": true, "mark_id": 2, "confidence": 0.95}'):
            found2 = self.som.query_mark("bell icon", test_img, marks)
            self.assertIsNotNone(found2)
            self.assertEqual(found2.id, 2)
            self.assertEqual(found2.center, (165, 65))

    def test_closed_loop_ui_verifier(self):
        snap1 = UIStateSnapshot(
            timestamp=100.0,
            hwnd=1001,
            window_title="GitHub - Repository",
            cursor_pos=(100, 100),
            roi_hash="aaaa1111",
            control_count=10,
        )

        # 1. Window transition test
        snap2 = UIStateSnapshot(
            timestamp=100.1,
            hwnd=1002,
            window_title="Settings - Account",
            cursor_pos=(200, 200),
            roi_hash="bbbb2222",
            control_count=15,
        )
        res = self.verifier.verify_action(snap1, snap2, target_pos=(200, 200))
        self.assertTrue(res.verified)
        self.assertTrue(res.window_changed)
        self.assertTrue(res.visual_changed)
        self.assertTrue(res.cursor_confirmed)
        self.assertGreaterEqual(res.confidence, 0.7)

        # 2. Visual change test without window change (e.g. dropdown open)
        snap3 = UIStateSnapshot(
            timestamp=100.1,
            hwnd=1001,
            window_title="GitHub - Repository",
            cursor_pos=(100, 100),
            roi_hash="cccc3333",  # Pixel delta in ROI
            control_count=14,      # 4 new menu items appeared
        )
        res2 = self.verifier.verify_action(snap1, snap3, target_pos=(100, 100))
        self.assertTrue(res2.verified)
        self.assertTrue(res2.visual_changed)
        self.assertEqual(res2.control_count_delta, 4)

    def test_visual_grounding_action_execution(self):
        # Test Tier 1 (UIA match)
        c = UIControl("GitHub Profile", "Button", (500, 20, 540, 50), (520, 35), 999)
        with patch.object(self.uia, "find_control", return_value=c):
            with patch("core.neo_visual_grounding.ui_automation.find_control", return_value=c):
                with patch("core.neo_visual_grounding.VisualGroundingEngine.click_element", return_value=True):
                    out = vga.visual_screen_grounding({"action": "click", "query": "GitHub Profile"})
                    self.assertIn("verified=true", out)
                    self.assertIn("method=uia", out)
                    self.assertIn("x=520", out)
                    self.assertIn("y=35", out)

    def test_ui_verifier_rl_bridge_integration(self):
        snap1 = UIStateSnapshot(100.0, 101, "Window A", (50, 50), "hash1", 5)
        snap2 = UIStateSnapshot(100.1, 102, "Window B", (50, 50), "hash2", 8)
        with patch("core.neo_reinforcement_learning.rl_learner.record_tool_outcome") as mock_rl:
            res = self.verifier.verify_action(snap1, snap2, expected_action="click", target_pos=(50, 50))
            self.assertTrue(res.verified)
            mock_rl.assert_called_once()
            call_args = mock_rl.call_args[1]
            self.assertEqual(call_args["tool_name"], "click")
            self.assertTrue(call_args["success"])

    def test_clamp_coords_robustness(self):
        from actions.computer_control import _clamp_coords
        cx, cy = _clamp_coords("500.5", "300.2")
        self.assertIsNotNone(cx)
        self.assertIsNotNone(cy)
        self.assertEqual(cx, 500)
        self.assertEqual(cy, 300)

        cx2, cy2 = _clamp_coords(None, 100)
        self.assertIsNone(cx2)
        self.assertIsNone(cy2)

    def test_send_message_contact_matching_safety(self):
        from actions.send_message import _resolve_contact
        # Single char query should not false-match unrelated names
        fake_contacts = {
            "al": {"name": "Alex", "phone": "111"},
            "boss": {"name": "Boss", "phone": "222"},
        }
        with patch("actions.send_message._load_contacts", return_value=fake_contacts):
            res = _resolve_contact("b")
            # Should not match 'boss' because 'b' is 1 char
            self.assertNotEqual(res["phone"], "222")

            # But full match or 3-char should match
            res2 = _resolve_contact("boss")
            self.assertEqual(res2["phone"], "222")


if __name__ == "__main__":
    unittest.main()
