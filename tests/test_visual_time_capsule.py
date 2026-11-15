"""
tests/test_visual_time_capsule.py — Unit tests for Visual Screen Time Capsule & Memory Indexer.
"""
import time
import unittest
from pathlib import Path

from core.neo_visual_time_capsule import NEOVisualTimeCapsule
from actions.time_capsule_action import time_capsule_action


class TestNEOVisualTimeCapsule(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("memory") / "test_time_capsule.db"
        if self.test_db.exists():
            try:
                self.test_db.unlink()
            except Exception:
                pass
        self.capsule = NEOVisualTimeCapsule(db_path=self.test_db)

    def tearDown(self):
        # Reset back to default
        NEOVisualTimeCapsule(db_path=None)
        if self.test_db.exists():
            try:
                self.test_db.unlink()
            except Exception:
                pass

    def test_record_and_search_capsule(self):
        # Insert test frames
        id1 = self.capsule.record_frame(
            app_name="Google Chrome",
            window_title="FastAPI Documentation - Endpoints and WebSockets",
            ocr_snippet="GET /api/v1/stream WebSocket endpoint implementation",
            display_index=1,
        )
        self.assertGreater(id1, 0)

        id2 = self.capsule.record_frame(
            app_name="VS Code",
            window_title="main.py - NEO Workspace",
            ocr_snippet="def start_server(): port = 8000; uvicorn.run()",
            display_index=2,
        )
        self.assertGreater(id2, 0)

        # Search by keyword
        res = self.capsule.search_history("FastAPI")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].app_name, "Google Chrome")
        self.assertIn("Endpoints", res[0].window_title)

        # Search by OCR content
        res2 = self.capsule.search_history("uvicorn")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0].app_name, "VS Code")
        self.assertEqual(res2[0].display_index, 2)

    def test_time_capsule_action_handler(self):
        self.capsule.record_frame(
            app_name="Slack",
            window_title="Engineering Team - Standup",
            ocr_snippet="Deployment scheduled for 4 PM UTC",
        )
        out = time_capsule_action({"action": "search", "query": "Deployment"})
        self.assertIn("status=done", out)
        self.assertIn("time_capsule", out)


if __name__ == "__main__":
    unittest.main()
