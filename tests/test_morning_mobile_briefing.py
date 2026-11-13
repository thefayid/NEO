import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path

from actions.executive_briefing import (
    _get_comprehensive_hardware_health,
    _get_github_pr_and_repo_status,
    build_stark_morning_briefing_card,
    dispatch_morning_briefing,
    executive_briefing,
    TOOL,
)
from actions.proactive import ProactiveEngine


class TestMorningMobileBriefing(unittest.TestCase):
    def test_tool_declaration(self):
        self.assertEqual(TOOL["name"], "executive_briefing")
        self.assertIn("mobile_dispatch", TOOL["parameters"]["properties"]["action"]["description"])
        self.assertIn("platform", TOOL["parameters"]["properties"])

    def test_get_hardware_health(self):
        hw = _get_comprehensive_hardware_health()
        self.assertIn("cpu", hw)
        self.assertIn("ram", hw)
        self.assertIn("disk_free_gb", hw)
        self.assertIn("uptime", hw)
        self.assertGreater(hw["disk_free_gb"], 0)
        self.assertTrue(isinstance(hw["uptime"], str))

    def test_get_github_status(self):
        gh = _get_github_pr_and_repo_status()
        self.assertIn("repo", gh)
        self.assertIn("branch", gh)
        self.assertIn("open_prs", gh)
        self.assertTrue(isinstance(gh["open_prs"], int))

    def test_build_stark_card(self):
        card = build_stark_morning_briefing_card()
        self.assertIn("STARK INDUSTRIES · MORNING BRIEF", card)
        self.assertIn("WEATHER & ATMOSPHERE", card)
        self.assertIn("TODAY'S SCHEDULE", card)
        self.assertIn("REMINDERS & ACTIVE TASKS", card)
        self.assertIn("GITHUB & REPOSITORY HEALTH", card)
        self.assertIn("SYSTEM HARDWARE & TELEMETRY", card)

    @patch("actions.telegram_remote.send_remote_alert")
    def test_dispatch_telegram(self, mock_alert):
        mock_alert.return_value = True
        res = dispatch_morning_briefing(platform="telegram", card_text="Test Card")
        self.assertTrue(res["success"])
        self.assertIn("Telegram", res["delivered_channels"])
        mock_alert.assert_called_once_with("Test Card")

    @patch("actions.send_message.send_message")
    def test_dispatch_whatsapp(self, mock_send):
        mock_send.return_value = "status=done action=send_message verified=true"
        res = dispatch_morning_briefing(platform="whatsapp", receiver="Fayid", card_text="Test Card")
        self.assertTrue(res["success"])
        self.assertIn("WhatsApp", res["delivered_channels"])

    @patch("actions.executive_briefing.dispatch_morning_briefing")
    def test_executive_briefing_action_dispatch(self, mock_disp):
        mock_disp.return_value = {
            "success": True,
            "delivered_channels": ["Telegram"],
            "errors": [],
            "card": "Sample Card",
        }
        res = executive_briefing({"action": "mobile_dispatch", "platform": "telegram"})
        self.assertIn("status=done", res)
        self.assertIn("mobile_dispatch", res)
        mock_disp.assert_called_once()

    def test_proactive_engine_trigger_evaluation(self):
        engine = ProactiveEngine()
        # Mock datetime to 8:35 AM on a new day
        mock_dt = datetime(2026, 11, 14, 8, 35, 0)
        with patch("actions.proactive.datetime") as mock_datetime, \
             patch("actions.proactive._read_config", return_value={"morning_brief_enabled": True, "last_morning_dispatch_date": "2026-11-13"}):
            mock_datetime.now.return_value = mock_dt
            should_fire, reason, snapshot = engine.evaluate_triggers(last_user_speech=0.0)
            self.assertTrue(should_fire)
            self.assertEqual(reason, "AUTONOMOUS_MORNING_MOBILE_DISPATCH")


if __name__ == "__main__":
    unittest.main()

