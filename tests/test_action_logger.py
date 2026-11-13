import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from core.neo_action_logger import NEOActionLogger, ActionLogEntry
from actions.action_log_action import manage_action_log, TOOL
from core.action_loader import discover_actions


class TestNEOActionLogger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.json_path = Path(self.tmp_dir.name) / "test_action_log.json"
        self.txt_path = Path(self.tmp_dir.name) / "test_action_log.txt"
        self.logger = NEOActionLogger(
            json_path=self.json_path,
            txt_path=self.txt_path,
        )

    def tearDown(self):
        time.sleep(0.05)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_record_action_format(self):
        entry = self.logger.record_action(
            tool_called="open_app",
            parameters={"app_name": "notepad"},
            result="status=done window opened",
            step=1,
            evidence="Screenshot ID: screenshot_001.png",
            verified=True,
        )

        line = entry.to_line()
        # Verify exact requested format:
        # [time] | step | tool called | parameters | result | evidence (screenshot ID or output) | verified: yes/no
        parts = [p.strip() for p in line.split("|")]
        self.assertEqual(len(parts), 7)
        self.assertTrue(parts[0].startswith("[") and parts[0].endswith("]"))
        self.assertEqual(parts[1], "1")
        self.assertEqual(parts[2], "open_app")
        self.assertIn("notepad", parts[3])
        self.assertIn("status=done", parts[4])
        self.assertEqual(parts[5], "Screenshot ID: screenshot_001.png")
        self.assertEqual(parts[6], "verified: yes")

    def test_persistence_and_reload(self):
        self.logger.record_action(
            tool_called="computer_control",
            parameters={"action": "click", "x": 500, "y": 300},
            result="status=done clicked",
            step=1,
        )
        self.logger.record_action(
            tool_called="computer_control",
            parameters={"action": "type", "text": "hello"},
            result="status=done typed 5 chars",
            step=2,
        )

        # Reload in a new instance
        reloaded = NEOActionLogger(
            json_path=self.json_path,
            txt_path=self.txt_path,
        )
        entries = reloaded.get_last_entries(10)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].step, 1)
        self.assertEqual(entries[1].step, 2)
        self.assertEqual(entries[1].tool_called, "computer_control")

    def test_show_log_entries(self):
        for i in range(1, 6):
            self.logger.record_action(
                tool_called=f"tool_{i}",
                parameters={"index": i},
                result=f"result_{i}",
                step=i,
            )

        last_3 = self.logger.get_last_entries(3)
        self.assertEqual(len(last_3), 3)
        self.assertEqual(last_3[-1].tool_called, "tool_5")

        formatted = self.logger.format_last_entries(3)
        self.assertEqual(len(formatted.splitlines()), 3)
        self.assertIn("tool_5", formatted)

    def test_answer_what_did_you_do(self):
        # Empty log behavior
        empty_answer = self.logger.answer_what_did_you_do()
        self.assertIn("The log does not contain any recorded entries", empty_answer)

        # Populated log behavior
        self.logger.record_action(
            tool_called="file_controller",
            parameters={"action": "read", "path": "test.txt"},
            result="status=done read 100 bytes",
            step=1,
            evidence="Output: '100 bytes'",
            verified=True,
        )
        answer = self.logger.answer_what_did_you_do()
        self.assertIn("Here are the verified actions recorded in the log", answer)
        self.assertIn("file_controller", answer)
        self.assertIn("Reported strictly from the immutable audit log", answer)

    def test_action_tool_handler(self):
        from core.neo_action_logger import action_logger
        old_json = action_logger.json_path
        old_txt = action_logger.txt_path
        try:
            action_logger.json_path = self.json_path
            action_logger.txt_path = self.txt_path
            action_logger._entries = []
            action_logger._step_counter = 0

            # Test record
            res_rec = manage_action_log({
                "operation": "record",
                "tool_called": "browser_control",
                "parameters": {"url": "https://google.com"},
                "result": "status=done navigated",
                "step": 1,
                "evidence": "Screenshot ID: screen_01.png",
                "verified": "yes",
            })
            self.assertIn("status=done action=log_recorded", res_rec)

            # Test show_log
            res_show = manage_action_log({
                "operation": "show_log",
                "n": 5,
            })
            self.assertIn("browser_control", res_show)
            self.assertIn("verified: yes", res_show)

            # Test what_did_you_do
            res_what = manage_action_log({
                "operation": "what_did_you_do",
            })
            self.assertIn("browser_control", res_what)
            self.assertIn("Reported strictly from the immutable audit log", res_what)
        finally:
            action_logger.json_path = old_json
            action_logger.txt_path = old_txt
            action_logger._load()

    def test_action_loader_discovers_action_log(self):
        reg = discover_actions(Path("actions"))
        decls = reg.get_tool_declarations()
        tool_names = [d["name"] for d in decls]
        self.assertIn("action_log", tool_names)


if __name__ == "__main__":
    unittest.main()

