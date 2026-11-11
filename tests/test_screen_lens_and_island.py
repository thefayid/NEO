"""
tests/test_screen_lens_and_island.py — Verification Suite for Dynamic Island 2.0 and Omnipresent Screen Lens.
"""
import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

_qapp = QApplication.instance() or QApplication(sys.argv)

from core.floating_island import NeoFloatingIsland, MiniWaveformWidget
from core.neo_screen_lens import NeoScreenLens, get_screen_lens
from actions.screen_lens_action import screen_lens


class TestScreenLensAndIsland(unittest.TestCase):

    def setUp(self):
        self.island = NeoFloatingIsland(None)
        self.lens = NeoScreenLens(None)

    def tearDown(self):
        self.island.deleteLater()
        self.lens.deleteLater()

    # ── Dynamic Island 2.0 Tests ─────────────────────────────────────────────

    def test_dynamic_island_states(self):
        """Verifies dynamic island handles speaking, listening, thinking, and idle states."""
        self.island.set_state("SPEAKING")
        self.assertEqual(self.island._current_state, "SPEAKING")
        self.assertIn("Speaking", self.island.status_lbl.text())

        self.island.set_state("LISTENING")
        self.assertEqual(self.island._current_state, "LISTENING")
        self.assertIn("Listening", self.island.status_lbl.text())

        self.island.set_state("THINKING")
        self.assertEqual(self.island._current_state, "THINKING")
        self.assertIn("Thinking", self.island.status_lbl.text())

    def test_dynamic_island_waveform_level(self):
        """Verifies mini waveform receives audio levels without errors."""
        self.island.set_audio_level(0.75)
        self.assertAlmostEqual(self.island.waveform._level, 0.75, places=2)

    def test_dynamic_island_expand_collapse(self):
        """Verifies inline Spotlight command input expands and collapses correctly."""
        self.assertFalse(self.island._is_expanded)
        self.island.expand_input()
        self.assertTrue(self.island._is_expanded)
        self.assertEqual(self.island.width(), self.island._expanded_width)

        self.island.collapse_input()
        self.assertFalse(self.island._is_expanded)
        self.assertEqual(self.island.width(), self.island._normal_width)

    def test_dynamic_island_proactive_chip(self):
        """Verifies rendering and click dispatch of proactive chips."""
        self.island.set_proactive_chip("⚡ Merge Conflict", "git_resolve")
        self.assertFalse(self.island.proactive_btn.isHidden())
        self.assertEqual(self.island.proactive_btn.text(), "⚡ Merge Conflict")

        received = []
        self.island.chip_action_requested.connect(lambda p: received.append(p))
        self.island._on_proactive_clicked()
        self.assertIn("git_resolve", received)

    # ── Screen Lens Tests ───────────────────────────────────────────────────

    def test_screen_lens_initialization(self):
        """Verifies Screen Lens components and singleton instantiation."""
        lens = get_screen_lens()
        self.assertIsNotNone(lens)
        self.assertIsNotNone(lens.query_input)
        self.assertIsNotNone(lens.result_view)

    def test_screen_lens_action_dispatch(self):
        """Verifies screen_lens action tool handler extracts parameters and returns confirmation."""
        resp_debug = screen_lens({"action": "debug"})
        self.assertIn("Screen Lens", resp_debug)
        self.assertIn("inspect", resp_debug)

        resp_ocr = screen_lens({"action": "ocr"})
        self.assertIn("Screen Lens", resp_ocr)
        self.assertIn("clipboard", resp_ocr)

        resp_click = screen_lens({"action": "click", "query": "Save button"})
        self.assertIn("Save button", resp_click)


if __name__ == "__main__":
    unittest.main()
