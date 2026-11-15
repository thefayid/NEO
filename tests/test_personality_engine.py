"""
tests/test_personality_engine.py — Unit tests for Personality, Prosody & Empathy Engine.
"""
import unittest

from core.neo_personality_engine import NEOPersonalityEngine, personality_engine


class TestNEOPersonalityEngine(unittest.TestCase):
    def test_sentiment_and_emotion_mapping(self):
        # 1. Joy / Celebration
        joy = personality_engine.analyze_dialog_turn("That is awesome, all 250 tests passed perfectly!")
        self.assertEqual(joy.emotion, "happy")
        self.assertGreater(joy.confidence, 0.8)
        self.assertGreater(joy.speech_rate_mult, 1.0)

        # 2. Empathy / Exhaustion
        emp = personality_engine.analyze_dialog_turn("I'm so exhausted and tired from debugging this bug.")
        self.assertEqual(emp.emotion, "empathy")
        self.assertLess(emp.speech_rate_mult, 1.0)

        # 3. Curiosity / Exploration
        cur = personality_engine.analyze_dialog_turn("How does the WebRTC signaling hub work?")
        self.assertEqual(cur.emotion, "curious")

        # 4. Pride / Milestone
        prd = personality_engine.analyze_dialog_turn("We did it! We just shipped the new version.")
        self.assertEqual(prd.emotion, "proud")

        # 5. Focus mode
        foc = personality_engine.analyze_dialog_turn("Let's enter focus mode for the next 2 hours.")
        self.assertEqual(foc.emotion, "focused")

    def test_resumption_greeting_and_rapport(self):
        personality_engine.note_topic("WebRTC Mobile Companion")
        greeting = personality_engine.generate_resumption_greeting()
        self.assertIn("Boss", greeting)
        self.assertTrue(len(greeting) > 10)

    def test_shared_milestone_logging(self):
        personality_engine.log_shared_milestone(
            title="Pillars 1-5 Implemented",
            details="Engineered personality, avatar roll, and rapport engine.",
        )
        milestones = personality_engine._rapport_data.get("milestones", [])
        self.assertTrue(any(m["title"] == "Pillars 1-5 Implemented" for m in milestones))


if __name__ == "__main__":
    unittest.main()
