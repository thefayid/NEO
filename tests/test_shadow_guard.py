"""
tests/test_shadow_guard.py — Unit tests for NEO Shadow Mode & Action Safety Guard.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.neo_shadow_guard import (
    ActionRisk,
    NEOActionShadowGuard,
    RiskAssessment,
    shadow_guard,
)
from actions.computer_control import computer_control


class TestNEOShadowGuard(unittest.TestCase):
    def setUp(self):
        shadow_guard.set_modes(shadow_mode=False, dry_run=False)

    def tearDown(self):
        shadow_guard.set_modes(shadow_mode=False, dry_run=False)

    def test_risk_classification(self):
        # 1. Critical deletion / termination
        crit = shadow_guard.evaluate_risk("click", {"description": "Delete all user records"}, "Delete Button")
        self.assertEqual(crit.level, ActionRisk.CRITICAL)
        self.assertTrue(crit.requires_confirmation)
        self.assertIn("critical", crit.reason.lower())

        # 2. High risk keywords
        high = shadow_guard.evaluate_risk("click", {"button": "left"}, "Quit Application")
        self.assertEqual(high.level, ActionRisk.HIGH)

        # 3. Read-only safe actions
        safe = shadow_guard.evaluate_risk("screenshot", {})
        self.assertEqual(safe.level, ActionRisk.SAFE)
        self.assertFalse(safe.requires_confirmation)

    def test_dry_run_interception(self):
        shadow_guard.set_modes(shadow_mode=True, dry_run=True)

        allowed, msg = shadow_guard.guard_action_execution(
            "click",
            {"x": 500, "y": 300},
            target_coords=(500, 300),
            target_label="Settings Tab",
        )
        self.assertFalse(allowed)
        self.assertIn("[SHADOW-MODE DRY-RUN]", msg)
        self.assertIn("withheld for safe simulation", msg)

    def test_computer_control_shadow_mode_toggle(self):
        res = computer_control({"action": "shadow_mode", "shadow_mode": True, "dry_run": True})
        self.assertIn("shadow_mode=True", res)
        self.assertIn("dry_run=True", res)
        self.assertTrue(shadow_guard.dry_run_mode)

        # Test dry-run interception in computer_control click
        click_res = computer_control({"action": "click", "x": 100, "y": 200})
        self.assertIn("[SHADOW-MODE DRY-RUN]", click_res)

        # Restore
        computer_control({"action": "shadow_mode", "shadow_mode": False, "dry_run": False})
        self.assertFalse(shadow_guard.dry_run_mode)

    def test_ghost_highlight_rendering(self):
        test_out = Path("memory") / "test_ghost_preview.png"
        out_path = shadow_guard.render_ghost_highlight(
            image_path="assets/temp_screen_snapshot.png",
            bbox=(100, 100, 300, 250),
            label="OK Button",
            output_path=test_out,
        )
        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 100)
        # Cleanup
        try:
            out_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
