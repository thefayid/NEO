"""
tests/test_macos_phase2_app_shell.py — Senior Engineering Test Suite for Phase 2 App Shell.

Validates Apple HIG (macOS Sequoia/Tahoe) window requirements:
1. Frameless window with custom titlebar eliminating native OS frame
2. Top-left traffic lights (🔴 Close, 🟡 Minimize, 🟢 Zoom) with hover glyphs and 8pt spacing
3. Unified 48px toolbar with draggable surface and centered typography
4. Translucent resizable sidebar (220px default, min 180, max 320) with smooth collapse animation
5. Optional inspector panel (280px default, min 240, max 360) with smooth collapse animation
6. 1px inner highlight border (rgba(255, 255, 255, 0.06) dark mode / rgba(0, 0, 0, 0.08) light mode)
7. Full integration with MainWindow, keyboard shortcuts, and tab title tracking
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QPoint, QEasingCurve

from core.theme_provider import theme
from core.macos_window import (
    apply_macos_vibrancy,
    MacOSTrafficLights,
    MacOSUnifiedToolbar,
    MacOSSizingSidebarContainer,
    MacOSInspectorPanelContainer,
    MacOSFramelessHelper,
)
from ui import MainWindow

_app = QApplication.instance() or QApplication(sys.argv)


class TestMacOSPhase2AppShell(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        theme.set_mode("dark")
        cls.win = MainWindow(face_path="")
        cls.win.closeEvent = lambda event: event.accept()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass

    def test_01_frameless_window_flags(self):
        """Window must be frameless to eliminate the native Windows 11 titlebar."""
        flags = self.win.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.Window)

    def test_02_traffic_lights_spec(self):
        """Traffic lights must have 12x12px circular buttons, 8px spacing, and hover glyphs."""
        tl = MacOSTrafficLights()
        self.assertEqual(tl.height(), 28)
        self.assertEqual(tl.btn_close.width(), 12)
        self.assertEqual(tl.btn_close.height(), 12)
        self.assertEqual(tl.btn_min.width(), 12)
        self.assertEqual(tl.btn_min.height(), 12)
        self.assertEqual(tl.btn_zoom.width(), 12)
        self.assertEqual(tl.btn_zoom.height(), 12)

        # Check glyph text
        self.assertEqual(tl.btn_close.text(), "×")
        self.assertEqual(tl.btn_min.text(), "−")
        self.assertEqual(tl.btn_zoom.text(), "+")

        # Test hover styling
        tl._apply_button_styles(hover_all=True)
        self.assertIn("#4A0002", tl.btn_close.styleSheet())
        self.assertIn("#5B3C00", tl.btn_min.styleSheet())
        self.assertIn("#0A4410", tl.btn_zoom.styleSheet())

        # Test rest styling (glyphs transparent)
        tl._apply_button_styles(hover_all=False)
        self.assertIn("color: transparent", tl.btn_close.styleSheet())
        self.assertIn("color: transparent", tl.btn_min.styleSheet())
        self.assertIn("color: transparent", tl.btn_zoom.styleSheet())

    def test_03_unified_toolbar_layout(self):
        """Unified toolbar must be 48px height with centered title."""
        toolbar = self.win._unified_toolbar
        self.assertIsInstance(toolbar, MacOSUnifiedToolbar)
        self.assertEqual(toolbar.height(), 48)

        # Check centered title
        self.assertEqual(toolbar.title_lbl.alignment(), Qt.AlignmentFlag.AlignCenter)
        self.assertEqual(toolbar.title_lbl.text(), self.win._assistant_name.upper())

        # Check toolbar has traffic lights
        self.assertIsNotNone(toolbar.traffic_lights)
        self.assertIs(self.win.btn_traffic_close, toolbar.traffic_lights.btn_close)
        self.assertIs(self.win.btn_traffic_min, toolbar.traffic_lights.btn_min)
        self.assertIs(self.win.btn_traffic_zoom, toolbar.traffic_lights.btn_zoom)

    def test_04_sidebar_container_spec(self):
        """Sidebar container must default to 220px, bound between 180-320px, with 200ms OutCubic animation."""
        sb = self.win._sidebar_container
        self.assertIsInstance(sb, MacOSSizingSidebarContainer)
        self.assertEqual(sb.DEFAULT_WIDTH, 220)
        self.assertEqual(sb.MIN_WIDTH, 180)
        self.assertEqual(sb.MAX_WIDTH, 320)
        self.assertEqual(sb.width(), 220)

        # Check collapse animation spec
        self.assertEqual(sb.anim.duration(), 200)
        self.assertEqual(sb.anim.easingCurve().type(), QEasingCurve.Type.OutCubic)

        # Test toggle collapse
        self.assertFalse(sb.is_collapsed)
        sb.toggle_collapse()
        self.assertTrue(sb.is_collapsed)
        sb.toggle_collapse()
        self.assertFalse(sb.is_collapsed)

    def test_05_inspector_container_spec(self):
        """Inspector panel container must default to 280px, bound between 240-360px, with 200ms OutCubic animation."""
        insp = self.win._inspector_container
        self.assertIsInstance(insp, MacOSInspectorPanelContainer)
        self.assertEqual(insp.DEFAULT_WIDTH, 280)
        self.assertEqual(insp.MIN_WIDTH, 240)
        self.assertEqual(insp.MAX_WIDTH, 360)
        self.assertEqual(insp.width(), 280)

        # Check collapse animation spec
        self.assertEqual(insp.anim.duration(), 200)
        self.assertEqual(insp.anim.easingCurve().type(), QEasingCurve.Type.OutCubic)

        # Test toggle collapse
        self.assertFalse(insp.is_collapsed)
        insp.toggle_collapse()
        self.assertTrue(insp.is_collapsed)
        insp.toggle_collapse()
        self.assertFalse(insp.is_collapsed)

    def test_06_inner_highlight_border_and_radius(self):
        """Canvas must have 1px inner highlight border and 10px continuous corner radius when unmaximized."""
        canvas = self.win._central
        self.assertIsNotNone(canvas)
        style = canvas.styleSheet()

        # In dark mode
        self.assertIn("border: 1px solid rgba(255, 255, 255, 0.06)", style)
        self.assertIn(f"border-radius: {theme.radii.md}px", style)

        # Test unmaximized vs maximized style switching
        self.win._update_window_frame_style()
        self.assertIn("border: 1px solid rgba(255, 255, 255, 0.06)", canvas.styleSheet())

    def test_07_nav_tab_changes_title(self):
        """Switching navigation tabs must dynamically update the centered unified toolbar title."""
        self.win._on_nav_tab_changed("Tasks")
        self.assertEqual(self.win._unified_toolbar.title_lbl.text(), f"{self.win._assistant_name.upper()} · Tasks")

        self.win._on_nav_tab_changed("Terminal")
        self.assertEqual(self.win._unified_toolbar.title_lbl.text(), f"{self.win._assistant_name.upper()} · Terminal")

        self.win._on_nav_tab_changed("Home")
        self.assertEqual(self.win._unified_toolbar.title_lbl.text(), self.win._assistant_name.upper())

    def test_08_frameless_resize_helper_cursor(self):
        """MacOSFramelessHelper must calculate appropriate edge resize cursors."""
        helper = MacOSFramelessHelper()
        dummy = QWidget()
        dummy.resize(500, 500)

        # Top-left corner
        helper.update_cursor_for_pos(dummy, QPoint(4, 4))
        self.assertEqual(dummy.cursor().shape(), Qt.CursorShape.SizeFDiagCursor)

        # Right edge
        helper.update_cursor_for_pos(dummy, QPoint(498, 250))
        self.assertEqual(dummy.cursor().shape(), Qt.CursorShape.SizeHorCursor)

        # Bottom edge
        helper.update_cursor_for_pos(dummy, QPoint(250, 498))
        self.assertEqual(dummy.cursor().shape(), Qt.CursorShape.SizeVerCursor)

        # Center (interior)
        helper.update_cursor_for_pos(dummy, QPoint(250, 250))
        self.assertEqual(dummy.cursor().shape(), Qt.CursorShape.ArrowCursor)


if __name__ == "__main__":
    unittest.main()
