import os
import tempfile
import unittest
from pathlib import Path

from core.neo_self_training import NEOSelfTrainingEngine


class TestSelfTrainingEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.tmp_dir.name) / "test_ledger.json"
        self.engine = NEOSelfTrainingEngine(ledger_path=self.ledger_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_record_preference_from_input(self):
        self.engine._process_raw_input("Open Chrome and take YouTube")
        self.assertIn("media_site", self.engine._preferences)
        self.assertEqual(self.engine._preferences["media_site"]["key"], "youtube")
        self.assertIn("browser_for_youtube", self.engine._preferences)

    def test_record_command_turn_and_pattern_learning(self):
        # Turn 1: user requests YouTube, tool invoked
        self.engine._learn_from_turn(
            "Open Chrome and take YouTube",
            "Opening YouTube in Chrome, Boss.",
            [{"name": "browser_control", "args": {"action": "go_to", "url": "https://www.youtube.com"}}],
        )
        self.assertGreater(len(self.engine._command_patterns), 0)

        # Turns 2 & 3: reinforce pattern
        for _ in range(2):
            self.engine._learn_from_turn(
                "Open Chrome and take YouTube",
                "Opening YouTube in Chrome, Boss.",
                [{"name": "browser_control", "args": {"action": "go_to"}}],
            )

        directives = self.engine.synthesize_self_training_directives()
        self.assertIn("Zero-Reflection Rule", directives)
        self.assertIn("browser_control", directives)

    def test_correction_detection(self):
        # Initial turn
        self.engine._learn_from_turn(
            "play music",
            "Playing music on web player.",
            [{"name": "web_search", "args": {}}],
        )

        # Correction turn
        self.engine._learn_from_turn(
            "no, use spotify instead",
            "Switching to Spotify.",
            [{"name": "spotify_control", "args": {"action": "play"}}],
        )

        self.assertGreater(len(self.engine._correction_rules), 0)
        self.assertEqual(self.engine._correction_rules[0]["trigger_command"], "play music")
        directives = self.engine.synthesize_self_training_directives()
        self.assertIn("Avoid previous misstep", directives)


if __name__ == "__main__":
    unittest.main()
