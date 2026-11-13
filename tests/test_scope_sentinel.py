import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from core.neo_scope_sentinel import NEOScopeSentinel
from actions.task_scope_action import manage_task_scope, TOOL
from core.action_loader import discover_actions


class TestNEOScopeSentinel(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.scope_file = Path(self.tmp_dir.name) / "test_scope.json"
        self.sentinel = NEOScopeSentinel(scope_file=self.scope_file)

    def tearDown(self):
        time.sleep(0.05)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_default_unlocked_state(self):
        self.assertFalse(self.sentinel.is_locked)
        allowed, msg = self.sentinel.is_action_allowed("any_tool", {"action": "anything"})
        self.assertTrue(allowed)

    def test_lock_and_enforce_scope(self):
        self.sentinel.lock_scope(
            task_name="edit_notes",
            allowed_apps=["notepad"],
            allowed_folders=[self.tmp_dir.name],
            allowed_websites=["docs.python.org"],
            allowed_actions=["file_controller", "open_app", "browser_control"],
        )
        self.assertTrue(self.sentinel.is_locked)

        # 1. Allowed tool & app
        allowed, _ = self.sentinel.is_action_allowed(
            "open_app",
            {"app_name": "notepad"}
        )
        self.assertTrue(allowed)

        # 2. Blocked tool (not in allowed_actions)
        allowed_tool, reason_tool = self.sentinel.is_action_allowed(
            "dangerous_cmd",
            {}
        )
        self.assertFalse(allowed_tool)
        self.assertIn("not in the allowed actions", reason_tool)

        # 3. Blocked app (not in allowed_apps)
        allowed_app, reason_app = self.sentinel.is_action_allowed(
            "open_app",
            {"app_name": "calc.exe"}
        )
        self.assertFalse(allowed_app)
        self.assertIn("outside the locked allowed apps", reason_app)

        # 4. Allowed folder
        test_file = str(Path(self.tmp_dir.name) / "notes.txt")
        allowed_file, _ = self.sentinel.is_action_allowed(
            "file_controller",
            {"file_path": test_file, "action": "read"}
        )
        self.assertTrue(allowed_file)

        # 5. Blocked folder
        bad_file = "C:/Windows/System32/drivers/etc/hosts"
        allowed_bad, reason_bad = self.sentinel.is_action_allowed(
            "file_controller",
            {"file_path": bad_file, "action": "read"}
        )
        self.assertFalse(allowed_bad)
        self.assertIn("outside the locked allowed folders", reason_bad)

        # 6. Blocked website
        allowed_web, reason_web = self.sentinel.is_action_allowed(
            "browser_control",
            {"url": "https://malicious-site.com"}
        )
        self.assertFalse(allowed_web)
        self.assertIn("outside the locked allowed websites", reason_web)

    def test_expand_scope(self):
        self.sentinel.lock_scope(
            task_name="browse_docs",
            allowed_apps=["chrome"],
            allowed_websites=["docs.python.org"],
            allowed_actions=["browser_control"],
        )

        # Initially blocked website
        allowed, _ = self.sentinel.is_action_allowed("browser_control", {"url": "https://github.com"})
        self.assertFalse(allowed)

        # Expand scope upon user permission
        self.sentinel.expand_scope(allowed_websites=["github.com"])
        allowed_now, _ = self.sentinel.is_action_allowed("browser_control", {"url": "https://github.com"})
        self.assertTrue(allowed_now)

    def test_reset_scope(self):
        self.sentinel.lock_scope(
            task_name="temp_task",
            allowed_apps=["notepad"],
            allowed_actions=["open_app"],
        )
        self.assertTrue(self.sentinel.is_locked)

        # Reset scope at task completion
        self.sentinel.reset_scope()
        self.assertFalse(self.sentinel.is_locked)
        self.assertEqual(len(self.sentinel.allowed_apps), 0)

        # Any action allowed again
        allowed, _ = self.sentinel.is_action_allowed("any_tool", {})
        self.assertTrue(allowed)

    def test_task_scope_action_handler(self):
        from core.neo_scope_sentinel import scope_sentinel
        old_file = scope_sentinel.scope_file
        try:
            scope_sentinel.scope_file = self.scope_file
            scope_sentinel.reset_scope()

            # Test lock_scope
            res_lock = manage_task_scope({
                "operation": "lock_scope",
                "task_name": "unit_test_task",
                "allowed_apps": ["notepad"],
                "allowed_actions": ["open_app"],
            })
            self.assertIn("status=done action=lock_scope", res_lock)
            self.assertTrue(scope_sentinel.is_locked)

            # Test get_scope
            res_get = manage_task_scope({"operation": "get_scope"})
            self.assertIn("is_locked=true", res_get)
            self.assertIn("notepad", res_get)

            # Test expand_scope
            res_exp = manage_task_scope({
                "operation": "expand_scope",
                "allowed_apps": ["calc"],
            })
            self.assertIn("status=done action=expand_scope", res_exp)
            self.assertIn("calc", scope_sentinel.allowed_apps)

            # Test reset_scope
            res_reset = manage_task_scope({"operation": "reset_scope"})
            self.assertIn("status=done action=reset_scope", res_reset)
            self.assertFalse(scope_sentinel.is_locked)
        finally:
            scope_sentinel.scope_file = old_file
            scope_sentinel._load()

    def test_action_loader_discovers_task_scope(self):
        reg = discover_actions(Path("actions"))
        decls = reg.get_tool_declarations()
        tool_names = [d["name"] for d in decls]
        self.assertIn("task_scope", tool_names)


if __name__ == "__main__":
    unittest.main()
