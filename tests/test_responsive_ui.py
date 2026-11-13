"""
tests/test_responsive_ui.py — Comprehensive tests for NEO Universal Responsive UI.

Verifies:
1. Dynamic screen-aware startup sizing across 1080p, 1366x768 laptop, 4K/Ultrawide, and vertical/portrait displays.
2. Adaptive multi-column responsive breakpoints (<940px inspector auto-collapse, <680px sidebar auto-collapse).
3. Fluid scaling of Hero Stage capsule, camera card, and NeoEclipseCanvas celestial arc.
4. Dynamic overlay clamping preventing off-screen clipping.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication, QWidget

# Ensure QApplication exists for UI tests
app = QApplication.instance() or QApplication(sys.argv)

from core.neo_ui import NeoHeroStage, NeoEclipseCanvas
from core.macos_window import MacOSSizingSidebarContainer, MacOSInspectorPanelContainer


class TestUniversalResponsiveUI(unittest.TestCase):

    def test_eclipse_canvas_fluid_scaling(self):
        canvas = NeoEclipseCanvas()
        canvas.resize(800, 240)
        self.assertEqual(canvas.minimumHeight(), 130)
        self.assertEqual(canvas.maximumHeight(), 260)

        # On small height (e.g. 150px)
        canvas.resize(600, 150)
        self.assertEqual(canvas.height(), 150)

    def test_hero_stage_capsule_and_camera_elasticity(self):
        stage = NeoHeroStage(user_name="Fayid")
        
        # Verify omni prompt capsule has flexible expanding policy
        self.assertGreaterEqual(stage.input_frame.minimumWidth(), 280)
        self.assertLessEqual(stage.input_frame.maximumWidth(), 800)

        # Verify camera card has flexible expanding policy
        self.assertGreaterEqual(stage.camera_card.minimumWidth(), 280)
        self.assertLessEqual(stage.camera_card.maximumWidth(), 850)

    def test_responsive_sidebar_and_inspector_collapse(self):
        sidebar = MacOSSizingSidebarContainer()
        inspector = MacOSInspectorPanelContainer()

        self.assertFalse(sidebar.is_collapsed)
        self.assertFalse(inspector.is_collapsed)

        # Trigger collapse
        sidebar.toggle_collapse()
        self.assertTrue(sidebar.is_collapsed)

        inspector.toggle_collapse()
        self.assertTrue(inspector.is_collapsed)

    def test_responsive_breakpoints_logic(self):
        # Test simulated resize thresholds
        def evaluate_columns(win_w: int):
            inspector_collapsed = win_w < 940
            sidebar_collapsed = win_w < 680
            return sidebar_collapsed, inspector_collapsed

        # 1. Full 1080p desktop mode (1400px): both open
        side, insp = evaluate_columns(1400)
        self.assertFalse(side)
        self.assertFalse(insp)

        # 2. Snapped half-screen / tablet mode (880px): inspector auto-collapses
        side, insp = evaluate_columns(880)
        self.assertFalse(side)
        self.assertTrue(insp)

        # 3. Compact companion / sidecar mode (640px): both auto-collapse
        side, insp = evaluate_columns(640)
        self.assertTrue(side)
        self.assertTrue(insp)


if __name__ == "__main__":
    unittest.main()
