"""
tests/test_ambient_and_meeting_copilot.py — Verification suite for Ambient HUD Copilot Lens & Meeting Copilot.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.ambient_copilot import (
    AmbientCopilotClassifier,
    AmbientCopilotEngine,
    ContentKind,
    copilot_engine,
)
from actions.ambient_copilot_action import run as run_ambient_copilot
from core.meeting_copilot import (
    MeetingSession,
    MeetingCopilotManager,
    find_loopback_device,
    meeting_manager,
)
from actions.meeting_copilot import run as run_meeting_copilot


class TestAmbientCopilotClassifier(unittest.TestCase):
    def test_classify_python_traceback(self):
        tb = (
            'Traceback (most recent call last):\n'
            '  File "core/gemini.py", line 42, in process_stream\n'
            '    result = 10 / 0\n'
            'ZeroDivisionError: division by zero'
        )
        res = AmbientCopilotClassifier.classify(tb)
        self.assertEqual(res.kind, ContentKind.STACK_TRACE)
        self.assertIn("ZeroDivisionError", res.title)
        self.assertEqual(res.badge_color, "#ef4444")
        self.assertTrue(len(res.actions) >= 2)
        self.assertEqual(res.metadata.get("file"), "gemini.py")
        self.assertEqual(res.metadata.get("line"), "42")

    def test_classify_js_error(self):
        js_err = (
            "TypeError: Cannot read properties of undefined (reading 'map')\n"
            "    at renderList (app.js:142:18)"
        )
        res = AmbientCopilotClassifier.classify(js_err)
        self.assertEqual(res.kind, ContentKind.STACK_TRACE)
        self.assertIn("TypeError", res.title)
        self.assertEqual(res.metadata.get("file"), "app.js")
        self.assertEqual(res.metadata.get("line"), "142")

    def test_classify_rust_panic(self):
        panic_text = "thread 'main' panicked at 'index out of bounds: the len is 3 but the index is 5', src/main.rs:24:9"
        res = AmbientCopilotClassifier.classify(panic_text)
        self.assertEqual(res.kind, ContentKind.STACK_TRACE)
        self.assertEqual(res.badge_label, "RUST PANIC")
        self.assertEqual(res.metadata.get("file"), "main.rs")
        self.assertEqual(res.metadata.get("line"), "24")

    def test_classify_cpp_error(self):
        cpp_err = "src/engine/renderer.cpp:88:14: fatal error: 'vulkan/vulkan.h' file not found"
        res = AmbientCopilotClassifier.classify(cpp_err)
        self.assertEqual(res.kind, ContentKind.STACK_TRACE)
        self.assertEqual(res.metadata.get("file"), "renderer.cpp")
        self.assertEqual(res.metadata.get("line"), "88")

    def test_classify_sql_query(self):
        sql = "SELECT u.id, u.username, count(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id;"
        res = AmbientCopilotClassifier.classify(sql)
        self.assertEqual(res.kind, ContentKind.SQL_QUERY)
        self.assertEqual(res.badge_label, "SQL QUERY")
        self.assertEqual(res.badge_color, "#f59e0b")

    def test_classify_github_repo(self):
        url = "https://github.com/astral-sh/uv"
        res = AmbientCopilotClassifier.classify(url)
        self.assertEqual(res.kind, ContentKind.WEB_RESOURCE)
        self.assertEqual(res.badge_label, "GIT REPO")
        self.assertIn("uv", res.title)

    def test_classify_web_url(self):
        url = "https://docs.python.org/3/library/unittest.html"
        res = AmbientCopilotClassifier.classify(url)
        self.assertEqual(res.kind, ContentKind.WEB_RESOURCE)
        self.assertEqual(res.badge_label, "WEB LINK")

    def test_classify_source_code(self):
        code = "def calculate_telemetry(data: list) -> float:\n    total = sum(data)\n    return total / len(data)\n"
        res = AmbientCopilotClassifier.classify(code)
        self.assertEqual(res.kind, ContentKind.SOURCE_CODE)
        self.assertIn("Python", res.title)

    def test_classify_json_data(self):
        data = '{"service": "auth_gateway", "port": 8080, "healthy": true}'
        res = AmbientCopilotClassifier.classify(data)
        self.assertEqual(res.kind, ContentKind.DATA_RECORDS)
        self.assertEqual(res.badge_label, "JSON DATA")


class TestAmbientCopilotEngine(unittest.TestCase):
    def setUp(self):
        copilot_engine.clear_errors()

    def test_process_and_retrieve_error(self):
        sample_error = (
            'Traceback (most recent call last):\n'
            '  File "main.py", line 110, in bootstrap\n'
            'ValueError: invalid configuration value'
        )
        analysis = copilot_engine.process_content(sample_error)
        self.assertEqual(analysis.kind, ContentKind.STACK_TRACE)

        err = copilot_engine.get_latest_error()
        self.assertIsNotNone(err)
        self.assertEqual(err.get("error_type"), "ValueError")
        self.assertEqual(err.get("file"), "main.py")
        self.assertEqual(err.get("line"), "110")

        all_errs = copilot_engine.get_recent_errors()
        self.assertEqual(len(all_errs), 1)

    def test_ambient_copilot_action_tool(self):
        sample_error = (
            'Traceback (most recent call last):\n'
            '  File "test.py", line 12, in run\n'
            'KeyError: "token"'
        )
        copilot_engine.process_content(sample_error)

        # 1. get_recent_error
        res = run_ambient_copilot({"action": "get_recent_error"})
        self.assertIn("status=done", res)
        self.assertIn("found=true", res)
        self.assertIn("error_type=KeyError", res)

        # 2. list_errors
        res_list = run_ambient_copilot({"action": "list_errors"})
        self.assertIn("status=done", res_list)
        self.assertIn("count=1", res_list)

        # 3. analyze_text
        res_analyze = run_ambient_copilot({
            "action": "analyze_text",
            "text": "SELECT * FROM telemetry WHERE status = 'err';"
        })
        self.assertIn("status=done", res_analyze)
        self.assertIn("kind=sql_query", res_analyze)

        # 4. clear_errors
        res_clear = run_ambient_copilot({"action": "clear_errors"})
        self.assertIn("status=done", res_clear)
        self.assertIsNone(copilot_engine.get_latest_error())


class TestMeetingCopilot(unittest.TestCase):
    def setUp(self):
        if meeting_manager.get_active_session():
            meeting_manager.stop_meeting()

    def tearDown(self):
        if meeting_manager.get_active_session():
            meeting_manager.stop_meeting()

    def test_find_loopback_device(self):
        dev_idx, dev_name = find_loopback_device(prefer_loopback=True)
        # Should return an integer index or None if no audio hardware
        if dev_idx is not None:
            self.assertIsInstance(dev_idx, int)
            self.assertIsInstance(dev_name, str)

    def test_session_lifecycle_and_minutes_generation(self):
        session = MeetingSession(topic="Q4 Architecture & Security Review")
        # Test without opening live stream thread
        session.active = True
        session.start_time = 1700000000.0
        session.end_time = 1700001200.0  # 20 minutes

        # Pin notes
        session.pin_note("Agreed to enforce zero-trust token rotation.")
        session.pin_note("Decision: Migrate legacy endpoints to gRPC.")

        # Add action items
        session.add_action_item("Deploy updated IAM policy to staging cluster", owner="Rahman")
        session.append_transcript("TODO: Review firewall rule changes before Friday", speaker="Security Lead")

        # Conclude and generate minutes
        res = session.generate_minutes()
        self.assertEqual(res["topic"], "Q4 Architecture & Security Review")
        self.assertEqual(res["action_items_count"], 2)
        self.assertEqual(res["decisions_count"], 2)

        # Verify Markdown file on disk
        md_path = Path(res["md_path"])
        self.assertTrue(md_path.exists())
        content = md_path.read_text(encoding="utf-8")
        self.assertIn("EXECUTIVE MEETING MINUTES: Q4 ARCHITECTURE & SECURITY REVIEW", content)
        self.assertIn("Deploy updated IAM policy to staging cluster", content)
        self.assertIn("Migrate legacy endpoints to gRPC", content)

    def test_meeting_manager_and_action(self):
        def mock_start(sess):
            sess.active = True
            sess.device_name = "Stereo Mix (Mock)"

        # 1. Start meeting via action
        with patch.object(MeetingSession, "start", side_effect=mock_start, autospec=True):
            res_start = run_meeting_copilot({"action": "start", "topic": "Sprint Sync"})
            self.assertIn("status=done", res_start)
            self.assertIn("topic=\"Sprint Sync\"", res_start)

            # 2. Pin note
            res_note = run_meeting_copilot({
                "action": "pin_note",
                "note": "Decision: Finalize release candidate v2.4.0 tonight."
            })
            self.assertIn("status=done", res_note)

            # 3. Add action item
            res_item = run_meeting_copilot({
                "action": "add_action_item",
                "action_item": "Conduct smoke tests across Windows and Linux runners",
                "owner": "Rahman"
            })
            self.assertIn("status=done", res_item)

            # 4. Status
            res_status = run_meeting_copilot({"action": "status"})
            self.assertIn("status=done", res_status)
            self.assertIn("active=true", res_status)
            self.assertIn("action_items_count=1", res_status)
            self.assertIn("decisions_count=1", res_status)

            # 5. Stop meeting
            res_stop = run_meeting_copilot({"action": "stop"})
            self.assertIn("status=done", res_stop)
            self.assertIn("topic=\"Sprint Sync\"", res_stop)


if __name__ == "__main__":
    unittest.main()
