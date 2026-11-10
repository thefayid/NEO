"""
tests/test_neo_proactive_intelligence.py — Verification Suite for NEO Proactive Intelligence System.

Tests all 5 Pillars:
1. Ambient Sensory Nervous System (Active window, vitals, git, calendar, focus state machine).
2. Pre-Cognitive Intent & Context Graph (Urgency evaluation, meeting anticipation, error spotting).
3. Non-Intrusive Delivery Etiquette (Silent chips vs. toast vs. voice DND respect).
4. Smart Affordances & macOS UI (NeoSmartChipBar rendering & click callbacks).
5. Habit Learning & Dynamic Tool Macro Synthesis.
"""
import os
import sys
import time
import unittest
from pathlib import Path

# Ensure application root is on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt6.QtWidgets import QApplication

# Headless Qt Application for UI component testing
_qapp = QApplication.instance()
if _qapp is None:
    _qapp = QApplication(sys.argv)

from core.neo_ambient_sensor import ambient_sensor, NEOAmbientSensor, UserFocusState
from core.neo_precognition import precognitive_engine, NEOPrecognitiveEngine, ProactiveOpportunity
from core.neo_habit_learner import habit_learner, NEOHabitLearner
from core.neo_central_coordinator import central_core
from core.neo_ui import NeoSmartChipBar


class TestNeoProactiveIntelligence(unittest.TestCase):

    def setUp(self):
        self.sensor = NEOAmbientSensor(sample_interval_ms=5000)
        self.precog = NEOPrecognitiveEngine()
        self.habit = NEOHabitLearner()
        self.habit._history = []
        self.habit._known_habits = {}

    def tearDown(self):
        self.sensor.stop()

    # ── Pillar 1: Ambient Sensory Nervous System ─────────────────────────────

    def test_ambient_sensor_snapshot(self):
        """Verifies ambient sensor collects vitals, git state, foreground, and focus state."""
        snap = self.sensor._collect_snapshot()
        self.assertIn("timestamp", snap)
        self.assertIn("vitals", snap)
        self.assertIn("git", snap)
        self.assertIn("foreground", snap)
        self.assertIn("focus_state", snap)
        self.assertIsInstance(snap["vitals"], dict)
        self.assertIn("ram_percent", snap["vitals"])

    def test_user_focus_state_transitions(self):
        """Verifies focus state transitions between ACTIVE_TYPING, FOCUSED_IDLE, and AWAY."""
        # Right after activity -> ACTIVE_TYPING
        self.sensor.record_user_input()
        self.assertEqual(self.sensor.get_focus_state(), UserFocusState.ACTIVE_TYPING)

        # Simulated 20s idle -> FOCUSED_IDLE
        self.sensor._last_user_activity = time.time() - 20.0
        self.assertEqual(self.sensor.get_focus_state(), UserFocusState.FOCUSED_IDLE)

        # Simulated 200s idle -> AWAY
        self.sensor._last_user_activity = time.time() - 200.0
        self.assertEqual(self.sensor.get_focus_state(), UserFocusState.AWAY)

    # ── Pillar 2 & 3: Pre-Cognition & Etiquette Delivery ─────────────────────

    def test_precognitive_calendar_meeting_anticipation(self):
        """Verifies meeting within 15m creates a CALENDAR_BRIEF opportunity."""
        fake_agenda = [
            {"title": "Sprint Sync", "start_time": "14:30", "minutes_until": 8}
        ]
        self.precog._evaluate_calendar_agenda(fake_agenda, UserFocusState.FOCUSED_IDLE)
        active = self.precog.get_active_opportunities()
        self.assertGreater(len(active), 0)
        top = active[0]
        self.assertEqual(top["category"], "CALENDAR_BRIEF")
        self.assertIn("Sprint Sync", top["title"])
        self.assertIn("Review and brief me", top["action_payload"])

    def test_precognitive_direct_error_detection(self):
        """Verifies traceback / error triggers a CODE_ERROR opportunity with 1-click fix."""
        fired_opps = []
        self.precog.opportunity_detected.connect(lambda opp: fired_opps.append(opp))

        self.precog._on_direct_error("ModuleNotFoundError", "No module named 'httpx'")
        self.assertGreater(len(fired_opps), 0)
        opp = fired_opps[-1]
        self.assertEqual(opp.category, "CODE_ERROR")
        self.assertIn("ModuleNotFoundError", opp.title)
        self.assertIn("autonomously fix", opp.action_payload)

    def test_precognitive_clipboard_intelligence(self):
        """Verifies copying a GitHub repository URL suggests clone & inspection."""
        self.precog._on_direct_clipboard("github_repo", "https://github.com/anthropics/anthropic-sdk-python")
        active = self.precog.get_active_opportunities()
        matching = [o for o in active if o["category"] == "CLIPBOARD_ACTION"]
        self.assertGreater(len(matching), 0)
        self.assertIn("anthropic-sdk-python", matching[0]["title"])
        self.assertIn("clone", matching[0]["action_payload"].lower())

    def test_etiquette_dnd_respect_during_active_typing(self):
        """Verifies high-urgency events do NOT speak voice when user is actively typing."""
        voice_emissions = []
        self.precog.voice_alert_requested.connect(lambda txt: voice_emissions.append(txt))

        urgent_opp = ProactiveOpportunity(
            opportunity_id="urgent_test",
            category="RESOURCE_PRESSURE",
            urgency=0.92,
            confidence=0.95,
            title="⚡ Memory Alert",
            subtitle="System RAM at 95%",
            action_type="GOAL",
            action_payload="Clean memory",
            icon_name="activity",
            cooldown_key="test_urgent_dnd",
            created_at=time.time(),
        )

        # 1. During ACTIVE_TYPING -> Voice must NOT fire (Do-Not-Disturb)
        self.precog._dispatch_opportunity(urgent_opp, UserFocusState.ACTIVE_TYPING)
        self.assertEqual(len(voice_emissions), 0, "Voice should be suppressed during rapid typing")

        # 2. During FOCUSED_IDLE -> Voice is allowed for high urgency
        urgent_opp_idle = ProactiveOpportunity(
            opportunity_id="urgent_test_2",
            category="RESOURCE_PRESSURE",
            urgency=0.92,
            confidence=0.95,
            title="⚡ Memory Alert",
            subtitle="System RAM at 95%",
            action_type="GOAL",
            action_payload="Clean memory",
            icon_name="activity",
            cooldown_key="test_urgent_dnd_2",
            created_at=time.time(),
        )
        self.precog._dispatch_opportunity(urgent_opp_idle, UserFocusState.FOCUSED_IDLE)
        self.assertGreater(len(voice_emissions), 0, "Voice should fire when user is idle for high urgency")

    def test_cooldown_deduplication(self):
        """Verifies same opportunity key is not spammed within cooldown period."""
        self.precog.set_cooldown("test_key", duration_secs=60)
        self.assertTrue(self.precog.is_on_cooldown("test_key"))
        self.assertFalse(self.precog.is_on_cooldown("unknown_key"))

    # ── Pillar 4: Smart Affordances & macOS UI ───────────────────────────────

    def test_smart_chip_bar_rendering_and_interaction(self):
        """Verifies NeoSmartChipBar displays proactive pills and fires payload callback."""
        chip_bar = NeoSmartChipBar()
        sample_opps = [
            {"title": "🛠 Fix 'httpx'", "action_payload": "pip install httpx"},
            {"title": "📅 Prep Meeting", "action_payload": "Review meeting agenda"},
        ]
        chip_bar.set_opportunities(sample_opps)
        self.assertTrue(chip_bar.isVisible())

        # Test callback emission
        selected_payloads = []
        chip_bar.opportunity_selected.connect(lambda p: selected_payloads.append(p))
        chip_bar._on_chip_clicked("pip install httpx")
        self.assertEqual(selected_payloads, ["pip install httpx"])
        self.assertFalse(chip_bar.isVisible(), "Bar should hide after selection")

    # ── Pillar 5: Habit Learning & Tool Synthesis ────────────────────────────

    def test_habit_recording_and_pattern_mining(self):
        """Verifies repeated commands are tracked in habit ledger."""
        unique_cmd = f"deploy_test_service_{int(time.time())}"
        for _ in range(3):
            self.habit.record_action("GOAL", unique_cmd)

        suggested = self.habit.get_suggested_habits_for_now()
        matching = [h for h in suggested if unique_cmd in h["command"]]
        self.assertGreater(len(matching), 0)

    # ── Central Coordinator Wiring ───────────────────────────────────────────

    def test_central_core_proactive_api(self):
        """Verifies central core provides high-level access to proactive opportunities."""
        central_core.start_proactive_subsystems()
        opps = central_core.get_proactive_opportunities()
        self.assertIsInstance(opps, list)
        central_core.stop_proactive_subsystems()


if __name__ == "__main__":
    unittest.main()
