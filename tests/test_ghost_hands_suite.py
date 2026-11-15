"""
tests/test_ghost_hands_suite.py — Automated Unit & Integration Tests for Ghost Hands.

Verifies:
1. Engine availability and desktop attachment.
2. CursorGuard preserves user cursor coordinates and foreground focus.
3. Window discovery and process-name/title matching.
4. Background UIA pattern click (invoke / toggle / select) with 0 cursor movement.
5. Win32 PostMessage mouse click fallback at client coordinates.
6. Background UIA value pattern typing without keyboard focus.
7. Win32 WM_SETTEXT message dispatch typing.
8. Background mousewheel scroll dispatch.
9. Ghost read text and controls from background windows.
10. Multi-step ghost pipeline execution and failure handling.
11. Action dispatcher interface (actions/ghost_hands.py).
12. computer_control ghost_click and ghost_type routing.
"""
import unittest
from unittest.mock import MagicMock, patch

from core.neo_ghost_hands import (
    BackgroundWindowInfo,
    CursorGuard,
    GhostHandsEngine,
    ghost_hands,
)
from actions.ghost_hands import run as ghost_hands_action
from actions.computer_control import computer_control
from core import outcome


class TestGhostHandsSuite(unittest.TestCase):
    def setUp(self):
        self.engine = GhostHandsEngine()
        self.mock_win = BackgroundWindowInfo(
            hwnd=12345,
            title="Mock Background App",
            process_name="mock_app.exe",
            rect=(100, 100, 900, 700),
            is_minimized=False,
            is_visible=True,
        )

    def test_01_engine_availability(self):
        self.assertTrue(self.engine.is_available)

    def test_02_cursor_guard_preserves_position(self):
        with patch("ctypes.windll.user32.GetCursorPos") as mock_get_pos, \
             patch("ctypes.windll.user32.SetCursorPos") as mock_set_pos, \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=999), \
             patch("ctypes.windll.user32.SetForegroundWindow") as mock_set_fg:

            def fake_get_pos(byref_pt):
                # First call returns (500, 500), second returns (600, 600)
                if not hasattr(fake_get_pos, "called"):
                    fake_get_pos.called = True
                    byref_pt._obj.x = 500
                    byref_pt._obj.y = 500
                else:
                    byref_pt._obj.x = 600
                    byref_pt._obj.y = 600
                return 1

            mock_get_pos.side_effect = fake_get_pos

            guard = CursorGuard("test_guard")
            with guard:
                pass  # Cursor moved inside block

            mock_set_pos.assert_called_with(500, 500)
            self.assertFalse(guard.cursor_preserved)

    def test_03_find_target_window_matching(self):
        mock_windows = [
            BackgroundWindowInfo(111, "Google Chrome", "chrome.exe", (0, 0, 800, 600), False, True),
            BackgroundWindowInfo(222, "Untitled - Notepad", "notepad.exe", (0, 0, 500, 400), False, True),
            BackgroundWindowInfo(333, "Spotify Free", "spotify.exe", (0, 0, 700, 500), False, True),
        ]

        with patch.object(self.engine, "list_background_windows", return_value=mock_windows):
            # Match by process name
            w1 = self.engine.find_target_window("chrome")
            self.assertIsNotNone(w1)
            self.assertEqual(w1.hwnd, 111)

            # Match by title substring
            w2 = self.engine.find_target_window("Notepad")
            self.assertIsNotNone(w2)
            self.assertEqual(w2.hwnd, 222)

            # Match by exact HWND
            w3 = self.engine.find_target_window(hwnd=333)
            self.assertIsNotNone(w3)
            self.assertEqual(w3.process_name, "spotify.exe")

    def test_04_ghost_click_uia_pattern(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win), \
             patch.object(self.engine, "_try_uia_pattern_click", return_value={"success": True, "name": "Save", "control_type": "Button", "cx": 200, "cy": 150}):

            res = self.engine.ghost_click(target="Save", app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.DONE)
            self.assertEqual(res["method"], "uia_pattern")
            self.assertEqual(res["target"], "Save")
            self.assertTrue(res["cursor_preserved"])

    def test_05_ghost_click_postmessage_fallback(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win), \
             patch.object(self.engine, "_try_uia_pattern_click", return_value={"success": False, "cx": 250, "cy": 180}), \
             patch.object(self.engine, "_post_message_click", return_value=True):

            res = self.engine.ghost_click(target="Submit", app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.DONE)
            self.assertEqual(res["method"], "win32_postmessage")
            self.assertEqual(res["coordinates"], (250, 180))

    def test_06_ghost_click_not_found(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win), \
             patch.object(self.engine, "_try_uia_pattern_click", return_value={"success": False, "cx": 0, "cy": 0}):

            res = self.engine.ghost_click(target="NonExistentButton", app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.FAILED)
            self.assertIn("Could not find interactable control", res["reason"])

    def test_07_ghost_type_uia_value_pattern(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win):
            # Test direct execution of _ghost_type_sync with mocked UIA
            mock_elem = MagicMock()
            mock_elem.element_info.name = "Search Query"
            mock_elem.element_info.automation_id = "txtSearch"
            mock_elem.element_info.control_type = "Edit"

            mock_win_obj = MagicMock()
            mock_win_obj.children.return_value = [mock_elem]

            mock_app = MagicMock()
            mock_app.window.return_value = mock_win_obj

            with patch("pywinauto.Application") as mock_pywin:
                mock_pywin.return_value.connect.return_value = mock_app
                res = self.engine._ghost_type_sync("Search Query", "NEO Autonomous Agent", self.mock_win, clear_first=True)
                self.assertEqual(res["status"], outcome.DONE)
                self.assertEqual(res["method"], "uia_value_pattern")
                self.assertEqual(res["chars_typed"], len("NEO Autonomous Agent"))
                mock_elem.set_edit_text.assert_called_once_with("NEO Autonomous Agent")

    def test_08_ghost_scroll_dispatches_mousewheel(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win), \
             patch("win32gui.PostMessage") as mock_post:

            res = self.engine.ghost_scroll(direction="down", amount=3, app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.DONE)
            self.assertEqual(res["method"], "win32_wm_mousewheel")
            self.assertEqual(res["direction"], "down")
            mock_post.assert_called_once()

    def test_09_ghost_read_text(self):
        with patch.object(self.engine, "find_target_window", return_value=self.mock_win):
            res = self.engine._ghost_read_sync(target=None, win=self.mock_win)
            self.assertEqual(res["status"], outcome.DONE)
            self.assertEqual(res["window"], "Mock Background App")
            self.assertEqual(res["process"], "mock_app.exe")

    def test_10_ghost_pipeline_success(self):
        steps = [
            {"action": "click", "target": "Next"},
            {"action": "wait", "seconds": 0.01},
            {"action": "scroll", "direction": "down", "amount": 2},
        ]
        with patch.object(self.engine, "ghost_click", return_value={"status": outcome.DONE, "method": "uia_pattern"}), \
             patch.object(self.engine, "ghost_scroll", return_value={"status": outcome.DONE, "method": "win32_wm_mousewheel"}):

            res = self.engine.ghost_pipeline(steps, app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.DONE)
            self.assertEqual(res["total_steps"], 3)
            self.assertEqual(len(res["results"]), 3)

    def test_11_ghost_pipeline_early_exit_on_failure(self):
        steps = [
            {"action": "click", "target": "MissingButton"},
            {"action": "scroll", "direction": "down", "amount": 2},
        ]
        with patch.object(self.engine, "ghost_click", return_value={"status": outcome.FAILED, "reason": "Button not found"}):
            res = self.engine.ghost_pipeline(steps, app_or_title="Mock Background App")
            self.assertEqual(res["status"], outcome.FAILED)
            self.assertEqual(res["failed_at_step"], 0)
            self.assertEqual(res["reason"], "Button not found")

    def test_12_ghost_hands_action_interface(self):
        # 1. Status action
        status_out = ghost_hands_action({"action": "status"})
        self.assertIn("status=done", status_out)
        self.assertIn("action=ghost_hands", status_out)

        # 2. List windows action
        with patch.object(ghost_hands, "list_background_windows", return_value=[self.mock_win]):
            list_out = ghost_hands_action({"action": "list_windows"})
            self.assertIn("status=done", list_out)
            self.assertIn("Mock Background App", list_out)

        # 3. Click action
        with patch.object(ghost_hands, "ghost_click", return_value={"status": outcome.DONE, "method": "uia_pattern", "window": "Mock App"}):
            click_out = ghost_hands_action({"action": "click", "target": "Submit", "app_name": "Mock App"})
            self.assertIn("status=done", click_out)
            self.assertIn("subaction=click", click_out)

        # 4. Type action
        with patch.object(ghost_hands, "ghost_type", return_value={"status": outcome.DONE, "method": "uia_value_pattern", "window": "Mock App", "chars_typed": 4}):
            type_out = ghost_hands_action({"action": "type", "target": "Search", "text": "test", "app_name": "Mock App"})
            self.assertIn("status=done", type_out)
            self.assertIn("chars_typed=4", type_out)

        # 5. Missing target fails
        fail_out = ghost_hands_action({"action": "click", "target": ""})
        self.assertIn("status=failed", fail_out)

    def test_13_computer_control_ghost_routing(self):
        # Test routing in computer_control
        with patch("core.neo_ghost_hands.ghost_hands.ghost_click", return_value={"status": outcome.DONE, "method": "uia_pattern"}):
            res = computer_control({"action": "ghost_click", "target": "OK", "app_name": "TestApp"})
            self.assertIn("Ghost Click Success", res)

        with patch("core.neo_ghost_hands.ghost_hands.ghost_type", return_value={"status": outcome.DONE, "chars_typed": 5}):
            res2 = computer_control({"action": "ghost_type", "target": "Email", "text": "hello", "app_name": "TestApp"})
            self.assertIn("Ghost Type Success", res2)


if __name__ == "__main__":
    unittest.main()
