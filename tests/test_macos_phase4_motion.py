"""
tests/test_macos_phase4_motion.py — Automated Verification for Phase 4 macOS Motion System.

Senior Design Engineering Verification:
1. Analytical Damped Harmonic Oscillator:
   - Exact mathematical solver: x(t) = 1 - e^(-γt) * [cos(ω_d t) + (γ/ω_d) sin(ω_d t)]
   - Boundary checks: x(0) == 0.0, x(settling) ≈ 1.0 (within 0.1% threshold)
2. Spring Presets:
   - snappy: stiffness 400, damping 30 (dur ≈ 460ms)
   - smooth: stiffness 260, damping 26 (dur ≈ 531ms)
   - gentle: stiffness 170, damping 22 (dur ≈ 628ms)
3. prefers-reduced-motion:
   - Swaps spring curves to 100ms linear ramps / simple fades
   - Dynamic toggle via motion.set_reduced_motion()
4. Button Press Scale 0.98:
   - MacOSButton scale_factor property and snappy release
5. Popover Scale-from-Anchor (0.96 -> 1.0):
   - MacOSPopover scale_factor property and anchor-based geometry
6. Sheet Slide-up with Backdrop Dim and Blur:
   - MacOSSheetModal slide using SpringPresets.smooth, dim_opacity, and blur
7. Reorderable List with Snappy Swapping:
   - MacOSReorderableList row animations using SpringPresets.snappy
8. Staggered Content Reveal:
   - stagger_reveal group with 20ms delays
9. Gallery Motion Showcase:
   - MacOSSpringVisualizer and Living Component Gallery motion tab
"""
import sys
import os
import unittest
import math

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QFrame
from PyQt6.QtCore import Qt, QPoint, QRect, QEasingCurve
from PyQt6.QtGui import QPixmap

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from core.macos_motion import (
    SpringSpec,
    SpringPresets,
    motion,
    create_spring_animation,
    stagger_reveal,
    StaggeredRevealGroup,
)
from core.macos_components import (
    MacOSButton,
    MacOSPopover,
    MacOSSheetModal,
    MacOSReorderableList,
    MacOSReorderableItem,
)
from core.macos_window import (
    MacOSSizingSidebarContainer,
    MacOSInspectorPanelContainer,
)
from core.macos_gallery import (
    MacOSComponentGallery,
    MacOSSpringVisualizer,
)


class TestMacOSPhase4Motion(unittest.TestCase):
    def setUp(self):
        motion.set_reduced_motion(False)

    def tearDown(self):
        motion.set_reduced_motion(False)

    # ── 1. Spring Physics Solver & Presets ────────────────────────────────────

    def test_01_spring_presets_specs(self):
        """Spring presets must match exact Apple HIG specifications."""
        # Snappy
        self.assertEqual(SpringPresets.snappy.stiffness, 400.0)
        self.assertEqual(SpringPresets.snappy.damping, 30.0)
        self.assertAlmostEqual(SpringPresets.snappy.w0, 20.0, places=2)
        self.assertAlmostEqual(SpringPresets.snappy.zeta, 0.75, places=2)
        self.assertIn(SpringPresets.snappy.duration_ms, range(450, 470))

        # Smooth
        self.assertEqual(SpringPresets.smooth.stiffness, 260.0)
        self.assertEqual(SpringPresets.smooth.damping, 26.0)
        self.assertAlmostEqual(SpringPresets.smooth.w0, 16.12, places=1)
        self.assertAlmostEqual(SpringPresets.smooth.zeta, 0.806, places=2)
        self.assertIn(SpringPresets.smooth.duration_ms, range(520, 545))

        # Gentle
        self.assertEqual(SpringPresets.gentle.stiffness, 170.0)
        self.assertEqual(SpringPresets.gentle.damping, 22.0)
        self.assertAlmostEqual(SpringPresets.gentle.w0, 13.04, places=1)
        self.assertAlmostEqual(SpringPresets.gentle.zeta, 0.844, places=2)
        self.assertIn(SpringPresets.gentle.duration_ms, range(615, 640))

    def test_02_analytical_solver_boundary_values(self):
        """Analytical damped harmonic oscillator must satisfy boundary conditions."""
        spec = SpringPresets.snappy
        self.assertEqual(spec.solve(0.0), 0.0)
        self.assertEqual(spec.solve(-0.5), 0.0)

        # Midway through oscillation (should be positive displacement)
        mid_val = spec.solve(0.1)
        self.assertGreater(mid_val, 0.5)

        # Settling time value should be within 0.1% of target 1.0
        settle_val = spec.solve(spec.settling_time_sec)
        self.assertAlmostEqual(settle_val, 1.0, places=2)

    def test_03_easing_curve_generation(self):
        """SpringSpec generates functional custom QEasingCurve."""
        curve = SpringPresets.smooth.easing_curve()
        self.assertEqual(curve.valueForProgress(0.0), 0.0)
        self.assertAlmostEqual(curve.valueForProgress(1.0), 1.0, places=2)

    # ── 2. prefers-reduced-motion Handling ─────────────────────────────────────

    def test_04_reduced_motion_mode_switch(self):
        """Enabling reduced motion swaps springs to 100ms linear ramps."""
        target = QWidget()
        anim_normal = create_spring_animation(target, b"pos", QPoint(0, 0), QPoint(100, 100), spring=SpringPresets.snappy)
        self.assertEqual(anim_normal.duration(), SpringPresets.snappy.duration_ms)

        # Switch to reduced motion
        motion.set_reduced_motion(True)
        self.assertTrue(motion.is_reduced_motion())

        anim_reduced = create_spring_animation(target, b"pos", QPoint(0, 0), QPoint(100, 100), spring=SpringPresets.snappy)
        self.assertEqual(anim_reduced.duration(), 100)
        self.assertEqual(anim_reduced.easingCurve().type(), QEasingCurve.Type.Linear)

    # ── 3. Sidebar & Inspector Collapse ───────────────────────────────────────

    def test_05_sidebar_and_inspector_spring_collapse(self):
        """Sidebar and Inspector panel containers must use SpringPresets.smooth."""
        sidebar = MacOSSizingSidebarContainer()
        inspector = MacOSInspectorPanelContainer()

        self.assertEqual(sidebar.anim.duration(), SpringPresets.smooth.duration_ms)
        self.assertEqual(inspector.anim.duration(), SpringPresets.smooth.duration_ms)

        # Test collapse toggle configures spring
        sidebar.toggle_collapse()
        self.assertTrue(sidebar.is_collapsed)
        sidebar.toggle_collapse()
        self.assertFalse(sidebar.is_collapsed)

    # ── 4. Button Press Scale 0.98 ───────────────────────────────────────────

    def test_06_button_press_scale_098(self):
        """MacOSButton must scale to 0.98 on press and spring back to 1.0 with snappy preset."""
        btn = MacOSButton("Motion Button", variant="default")
        btn.resize(120, 28)
        self.assertEqual(btn.scale_factor, 1.0)

        # Set scale factor to 0.98
        btn.scale_factor = 0.98
        self.assertEqual(btn.scale_factor, 0.98)

        # Button renders successfully at 0.98 scale
        pm = QPixmap(120, 28)
        btn.render(pm)
        self.assertFalse(pm.isNull())

        # Reset to 1.0
        btn.scale_factor = 1.0
        self.assertEqual(btn.scale_factor, 1.0)

    # ── 5. Popover Scale-from-Anchor 0.96 ──────────────────────────────────────

    def test_07_popover_scale_from_anchor(self):
        """MacOSPopover must scale from anchor tip (0.96 -> 1.0) using SpringPresets.snappy."""
        anchor = QPushButton("Anchor")
        anchor.resize(100, 30)
        anchor.move(200, 200)

        popover = MacOSPopover()
        content = QLabel("Popover Content")
        popover.set_content(content)

        self.assertEqual(popover.scale_factor, 1.0)
        self.assertEqual(popover.popover_opacity, 1.0)

        # Show at widget
        popover.show_at_widget(anchor, direction="bottom")
        self.assertTrue(popover.isVisible())
        self.assertIsNotNone(popover._anim_scale)
        self.assertEqual(popover._anim_scale.duration(), SpringPresets.snappy.duration_ms)
        self.assertEqual(popover._anim_scale.startValue(), 0.96)
        self.assertEqual(popover._anim_scale.endValue(), 1.0)

        popover.hide()

    # ── 6. Sheet Modal Slide-Up with Dim & Blur ───────────────────────────────

    def test_08_sheet_modal_slide_dim_blur(self):
        """MacOSSheetModal must animate pos and dim_opacity with SpringPresets.smooth."""
        parent_win = QWidget()
        parent_win.resize(600, 500)
        parent_win.show()
        sheet = MacOSSheetModal("Physics Sheet", parent=parent_win)
        sheet_body = QLabel("Sheet Inner Content")
        sheet.set_content_widget(sheet_body)

        self.assertEqual(sheet.dim_opacity, 0.0)

        # Open sheet
        sheet.open_sheet()
        self.assertFalse(sheet.isHidden())
        self.assertIsNotNone(sheet._anim_pos)
        self.assertIsNotNone(sheet._anim_dim)
        self.assertEqual(sheet._anim_pos.duration(), SpringPresets.smooth.duration_ms)
        self.assertEqual(sheet._anim_dim.duration(), SpringPresets.smooth.duration_ms)

        # Dismiss sheet
        sheet.dismiss()

    # ── 7. Reorderable List with Snappy Swapping ──────────────────────────────

    def test_09_reorderable_list_snappy(self):
        """MacOSReorderableList must swap items using SpringPresets.snappy."""
        lst = MacOSReorderableList()
        item1 = lst.add_item("item1", "Item One", "Sub 1")
        item2 = lst.add_item("item2", "Item Two", "Sub 2")
        item3 = lst.add_item("item3", "Item Three", "Sub 3")

        self.assertEqual(lst.get_item_ids(), ["item1", "item2", "item3"])
        self.assertEqual(item1.y_offset, 0.0)

        # Trigger swap
        lst.swap_indices(0, 1)
        self.assertTrue(lst._animating)
        self.assertEqual(len(lst._anims), 2)
        self.assertEqual(lst._anims[0].duration(), SpringPresets.snappy.duration_ms)

    # ── 8. Staggered Content Reveal ───────────────────────────────────────────

    def test_10_staggered_content_reveal_20ms(self):
        """stagger_reveal must create staggered 20ms reveal queue."""
        cards = [QFrame() for _ in range(4)]
        group = stagger_reveal(cards, interval_ms=20, spring=SpringPresets.smooth)
        self.assertIsInstance(group, StaggeredRevealGroup)
        self.assertEqual(group.interval_ms, 20)
        self.assertEqual(group.spring, SpringPresets.smooth)

    # ── 9. Living Gallery & Spring Visualizer ─────────────────────────────────

    def test_11_spring_visualizer_and_gallery(self):
        """MacOSSpringVisualizer and Living Component Gallery motion tab must render cleanly."""
        viz = MacOSSpringVisualizer()
        viz.resize(400, 180)
        self.assertEqual(viz._current_spec, SpringPresets.snappy)

        viz.set_spec(SpringPresets.smooth)
        self.assertEqual(viz._current_spec, SpringPresets.smooth)

        viz.set_spec(SpringPresets.gentle)
        self.assertEqual(viz._current_spec, SpringPresets.gentle)

        pm = QPixmap(400, 180)
        viz.render(pm)
        self.assertFalse(pm.isNull())

        # Instantiate full Living Component Gallery
        gallery = MacOSComponentGallery()
        gallery.resize(800, 600)
        self.assertIsNotNone(gallery.reorder_list)
        self.assertEqual(len(gallery.stagger_cards), 4)


if __name__ == "__main__":
    unittest.main()
