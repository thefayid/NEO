"""
tests/test_core_system_control_suite.py — Unit & Integration tests for Core System Control & Automation.
Covers:
1. Direct OS & Shell Automation (WindowManager & SystemResourceManager)
2. Native UIA Fast-Path Integration (computer_control)
3. Autonomous Computer-Operator Closed-Loop Agent
4. Deterministic Workflow Routines & Macro Engine
"""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.neo_os_automation import window_manager, resource_manager
from actions.os_control import run as run_os_control

from actions.computer_control import computer_control, _screen_find
from core.neo_ui_automation import UIControl

from core.neo_computer_operator import ComputerOperatorSession, computer_operator_registry
from actions.computer_operator_action import run as run_computer_operator

from core.neo_workflow_engine import workflow_engine
from actions.workflow_engine_action import run as run_workflow_engine


class TestDirectOSAutomation(unittest.TestCase):
    def test_get_work_area(self):
        l, t, r, b = window_manager.get_work_area()
        self.assertGreaterEqual(r, l)
        self.assertGreaterEqual(b, t)
        self.assertGreater(r - l, 300)
        self.assertGreater(b - t, 200)

    def test_system_health(self):
        health = resource_manager.get_health()
        self.assertIn("cpu_percent", health)
        self.assertIn("memory_percent", health)
        self.assertIn("memory_total_gb", health)
        self.assertGreater(health["memory_total_gb"], 0)

    def test_os_control_action_tool(self):
        # 1. system_health
        res_health = run_os_control({"action": "system_health"})
        self.assertIn("status=done", res_health)
        self.assertIn("action=os_control", res_health)
        self.assertIn("cpu=", res_health)

        # 2. list_windows
        res_list = run_os_control({"action": "list_windows"})
        self.assertIn("status=done", res_list)
        self.assertIn("count=", res_list)

        # 3. find_port
        res_port = run_os_control({"action": "find_port", "port": 54321})
        self.assertIn("status=done", res_port)
        self.assertIn("port=54321", res_port)

        # 4. create_desktop_folder
        res_folder = run_os_control({"action": "create_desktop_folder", "folder_name": "NeoTestAutomation"})
        self.assertIn("status=done", res_folder)
        test_dir = Path.home() / "Desktop" / "NeoTestAutomation"
        self.assertTrue(test_dir.exists())
        # Clean up
        try:
            test_dir.rmdir()
        except Exception:
            pass


class TestUIAFastPath(unittest.TestCase):
    @patch("core.neo_ui_automation.ui_automation.find_control")
    def test_screen_find_prefers_uia(self, mock_find):
        mock_ctrl = UIControl(
            name="Save",
            control_type="Button",
            rect=(100, 200, 160, 230),
            center=(130, 215),
            handle=12345
        )
        mock_find.return_value = mock_ctrl

        coords = _screen_find("Save")
        self.assertEqual(coords, (130, 215))

    @patch("core.neo_ui_automation.ui_automation.click_control_by_name")
    def test_computer_control_uia_click(self, mock_click):
        mock_click.return_value = (True, "Clicked Button 'Submit' at (200, 300)", (200, 300))
        res = computer_control({"action": "uia_click", "description": "Submit"})
        self.assertIn("UIA Success", res)

    @patch("core.neo_ui_automation.ui_automation.get_interactive_controls")
    def test_computer_control_uia_list(self, mock_list):
        mock_ctrl = UIControl(
            name="OK",
            control_type="Button",
            rect=(10, 20, 50, 40),
            center=(30, 30),
            handle=111
        )
        mock_list.return_value = [mock_ctrl]
        res = computer_control({"action": "uia_list"})
        self.assertIn("Found 1 interactive controls", res)
        self.assertIn("OK", res)


class TestComputerOperatorClosedLoop(unittest.TestCase):
    def test_operator_session_lifecycle(self):
        session = ComputerOperatorSession(goal="Find and open audio settings")
        self.assertTrue(len(session.stages) >= 3)
        self.assertEqual(session.current_stage_idx, 0)
        self.assertFalse(session.concluded)

    def test_hard_handoff_security_gate(self):
        # When goal or observation contains sensitive keywords, it must halt and ask_user
        session = ComputerOperatorSession(goal="Enter payment card number and complete checkout")
        turn = session.step()
        self.assertEqual(turn["action"], "ask_user")
        self.assertIn("card number", turn["plan"])
        self.assertTrue(session.concluded)
        self.assertTrue(session.handoff_required)

    def test_operator_action_tool(self):
        res = run_computer_operator({"action": "start", "goal": "Find volume control", "max_turns": 2})
        self.assertIn("status=done", res)
        self.assertIn("action=computer_operator", res)
        self.assertIn("turns_executed=", res)


class TestWorkflowEngine(unittest.TestCase):
    def test_default_routines_loaded(self):
        routines = workflow_engine.list_routines()
        names = [r["name"] for r in routines]
        self.assertIn("dev_workspace", names)
        self.assertIn("focus_mode", names)
        self.assertIn("system_tuneup", names)
        self.assertIn("meeting_prep", names)

    def test_execute_system_tuneup_routine(self):
        res = workflow_engine.execute_routine("system_tuneup")
        self.assertTrue(res["success"])
        self.assertEqual(res["routine"], "system_tuneup")
        self.assertEqual(res["steps_count"], 2)

    def test_create_and_execute_custom_routine(self):
        custom_steps = [
            {"tool": "os_control", "params": {"action": "system_health"}, "description": "Check initial health"},
            {"tool": "os_control", "params": {"action": "list_windows"}, "description": "List visible windows"},
        ]
        ok = workflow_engine.register_routine("test_custom_routine", "A test automation pipeline", custom_steps)
        self.assertTrue(ok)

        # Execute
        res = workflow_engine.execute_routine("test_custom_routine")
        self.assertTrue(res["success"])
        self.assertEqual(res["steps_count"], 2)

    def test_workflow_engine_action_tool(self):
        # 1. list_routines
        res_list = run_workflow_engine({"action": "list_routines"})
        self.assertIn("status=done", res_list)
        self.assertIn("count=", res_list)

        # 2. execute_routine
        res_exec = run_workflow_engine({"action": "execute_routine", "routine_name": "dev_workspace"})
        self.assertIn("status=done", res_exec)
        self.assertIn("routine=dev_workspace", res_exec)


if __name__ == "__main__":
    unittest.main()
