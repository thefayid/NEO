import math
import os
import tempfile
import time
import unittest
from pathlib import Path

from core.neo_reinforcement_learning import NEOReinforcementLearner, QEntry


class TestNEOReinforcementLearning(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp_dir.name) / "test_rl_q.json"
        self.rl = NEOReinforcementLearner(store_path=self.store_path)

    def tearDown(self):
        time.sleep(0.05)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_state_key_extraction(self):
        key1 = self.rl.get_state_key("open YouTube in Chrome", active_app="chrome.exe")
        self.assertIn("open_youtube", key1)
        self.assertIn("browser", key1)

        key2 = self.rl.get_state_key("read messages on whatsapp", active_app="WhatsApp.Root.exe")
        self.assertIn("read_whatsapp", key2)
        self.assertIn("comm", key2)

    def test_tool_outcome_reward_and_q_update(self):
        # Initial positive outcome
        reward = self.rl.record_tool_outcome(
            tool_name="browser_control",
            outcome_result="status=done action=browser_control verified=true",
            user_command="open YouTube",
            active_app="chrome",
        )
        self.assertGreater(reward, 0)

        # Allow async worker thread to complete
        time.sleep(0.1)

        state_key = self.rl.get_state_key("open YouTube", "chrome")
        entry = self.rl._q_table.get(state_key, {}).get("browser_control")
        self.assertIsNotNone(entry)
        self.assertGreater(entry.q_value, 0)
        self.assertEqual(entry.visits, 1)
        self.assertEqual(entry.successes, 1)

    def test_failure_penalty(self):
        reward = self.rl.record_tool_outcome(
            tool_name="bad_tool",
            outcome_result="status=failed action=bad_tool error='App crashed'",
            user_command="open broken app",
            active_app="desktop",
        )
        self.assertLess(reward, 0)
        time.sleep(0.1)

        state_key = self.rl.get_state_key("open broken app", "desktop")
        entry = self.rl._q_table.get(state_key, {}).get("bad_tool")
        self.assertIsNotNone(entry)
        self.assertLess(entry.q_value, 0)
        self.assertEqual(entry.failures, 1)

    def test_user_praise_and_penalty_feedback(self):
        self.rl.record_tool_start("spotify_control", user_command="play song", active_app="spotify")
        reward_praise = self.rl.record_user_feedback("thanks that was perfect!")
        self.assertEqual(reward_praise, 2.0)

        self.rl.record_tool_start("wrong_tool", user_command="play song", active_app="spotify")
        reward_penalty = self.rl.record_user_feedback("no stop that was wrong")
        self.assertEqual(reward_penalty, -3.0)

    def test_policy_recommendation(self):
        state_key = self.rl.get_state_key("play song", "spotify")
        # Populate Q-table with two candidate tools
        self.rl._q_table[state_key] = {
            "spotify_control": QEntry(q_value=3.5, visits=5, successes=5, failures=0),
            "web_search": QEntry(q_value=-1.2, visits=3, successes=0, failures=3),
        }

        rec = self.rl.get_policy_recommendation("play song", "spotify")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.action_name, "spotify_control")
        self.assertGreater(rec.confidence, 0.8)

        prompt_block = self.rl.synthesize_rl_prompt("play song", "spotify")
        self.assertIn("REINFORCEMENT LEARNING POLICY", prompt_block)
        self.assertIn("spotify_control", prompt_block)


if __name__ == "__main__":
    unittest.main()

