"""
tests/test_macos_ui_standard.py — Rigorous Verification for Apple macOS HIG UI Standard.
Verifies:
  1. Palette color tokens (Dark Vibrancy #161618, Source List #1C1C1E, Cards #252529, Accent #0A84FF, etc.)
  2. MainWindow macOS unified toolbar & traffic lights (🔴 #FF5F56, 🟡 #FFBD2E, 🟢 #27C93F)
  3. Overlay scrollbar styling (7px width, transparent track, rounded handle)
  4. macOS Source List sidebar (APPS, STUDIOS, SYSTEM categorized sections & capsule pills)
  5. Studio designs (Terminal mini traffic lights, Files search capsule, Chat code block dots)
"""
import os
import sys
import unittest
from pathlib import Path

# Ensure root path is accessible
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import Qt

# Headless Qt setup
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class TestMacOSUIStandard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from core.theme_provider import theme
        theme.set_accent("blue")

    def test_01_macos_palette_tokens(self):
        from ui import C, DARK_MODE_PALETTE, WHITE_MODE_PALETTE

        # macOS Dark Vibrancy
        self.assertEqual(C.BG.upper(), "#161618")
        self.assertEqual(C.PRI.upper(), "#0A84FF")
        self.assertEqual(C.ACCENT.upper(), "#0A84FF")
        self.assertEqual(C.GREEN.upper(), "#30D158")
        self.assertEqual(C.RED.upper(), "#FF453A")
        self.assertEqual(C.ACC2.upper(), "#FFD60A")
        self.assertEqual(C.TEXT.upper(), "#F5F5F7")

        # Dark Mode Palette dictionary
        self.assertEqual(DARK_MODE_PALETTE["BG"].upper(), "#161618")
        self.assertEqual(DARK_MODE_PALETTE["PRI"].upper(), "#0A84FF")
        self.assertEqual(DARK_MODE_PALETTE["GREEN"].upper(), "#30D158")
        self.assertEqual(DARK_MODE_PALETTE["RED"].upper(), "#FF453A")

        # White / Light Mode Palette dictionary
        self.assertEqual(WHITE_MODE_PALETTE["BG"].upper(), "#F5F6F8")
        self.assertEqual(WHITE_MODE_PALETTE["PRI"].upper(), "#007AFF")
        self.assertEqual(WHITE_MODE_PALETTE["PANEL"].upper(), "#FFFFFF")

    def test_02_macos_toolbar_and_traffic_lights(self):
        from ui import MainWindow

        win = MainWindow(face_path="")
        try:
            # Verify traffic lights exist on window
            self.assertTrue(hasattr(win, "btn_traffic_close"), "Missing macOS close traffic light")
            self.assertTrue(hasattr(win, "btn_traffic_min"), "Missing macOS min traffic light")
            self.assertTrue(hasattr(win, "btn_traffic_zoom"), "Missing macOS zoom traffic light")

            # Check dimensions (12px circular buttons)
            self.assertEqual(win.btn_traffic_close.width(), 12)
            self.assertEqual(win.btn_traffic_close.height(), 12)
            self.assertEqual(win.btn_traffic_min.width(), 12)
            self.assertEqual(win.btn_traffic_min.height(), 12)
            self.assertEqual(win.btn_traffic_zoom.width(), 12)
            self.assertEqual(win.btn_traffic_zoom.height(), 12)

            # Check traffic light styles contain Apple HIG colors
            self.assertIn("#FF5F56", win.btn_traffic_close.styleSheet().upper())
            self.assertIn("#FFBD2E", win.btn_traffic_min.styleSheet().upper())
            self.assertIn("#27C93F", win.btn_traffic_zoom.styleSheet().upper())

            # Verify global central widget stylesheet has macOS overlay scrollbar
            cw_ss = win.centralWidget().styleSheet()
            self.assertIn("QScrollBar:vertical", cw_ss)
            self.assertIn("width: 7px", cw_ss)
            self.assertIn("-apple-system", cw_ss)
        finally:
            try:
                from core.camera_service import get_camera_service
                get_camera_service().stop()
                from core.neo_central_coordinator import central_core
                central_core.stop_proactive_subsystems()
            except Exception:
                pass
            win.close()

    def test_03_macos_source_list_sidebar(self):
        from core.neo_ui import NeoNavSidebar

        sidebar = NeoNavSidebar()
        try:
            # Check width (macOS 220px standard)
            self.assertIn(sidebar.width(), (210, 220))

            # Check all category section header labels
            labels = [w.text() for w in sidebar.findChildren(QLabel)]
            self.assertIn("APPS", labels, "Source list missing APPS category")
            self.assertIn("STUDIOS", labels, "Source list missing STUDIOS category")
            self.assertIn("SYSTEM", labels, "Source list missing SYSTEM category")

            # Check navigation buttons exist and have Apple HIG styling
            self.assertTrue(hasattr(sidebar, "btn_home"))
            self.assertTrue(hasattr(sidebar, "btn_chat"))
            self.assertTrue(hasattr(sidebar, "btn_tasks"))
            self.assertTrue(hasattr(sidebar, "btn_notes"))
            self.assertTrue(hasattr(sidebar, "btn_projects"))
            self.assertTrue(hasattr(sidebar, "btn_knowledge"))
            self.assertTrue(hasattr(sidebar, "btn_files"))
            self.assertTrue(hasattr(sidebar, "btn_terminal"))
            self.assertTrue(hasattr(sidebar, "btn_swarm"))
            self.assertTrue(hasattr(sidebar, "btn_vision"))
            self.assertTrue(hasattr(sidebar, "btn_sentinels"))
            self.assertTrue(hasattr(sidebar, "btn_settings"))

            # Active style uses macOS Accent #0A84FF
            active_style = sidebar._nav_style(True)
            self.assertIn("#0A84FF", active_style.upper())
            self.assertIn("-apple-system", active_style)
        finally:
            sidebar.close()

    def test_04_terminal_studio_macos_styling(self):
        from core.neo_terminal_studio import NeoTerminalStudio, CARD_BG, ACCENT_PRIMARY

        term = NeoTerminalStudio(cwd=str(ROOT))
        try:
            self.assertEqual(CARD_BG.upper(), "#232327")
            self.assertEqual(ACCENT_PRIMARY.upper(), "#0A84FF")

            # Check console has macOS SF Mono typography
            c_ss = term.console.styleSheet()
            self.assertIn("SF Mono", c_ss)
            self.assertIn("#121214", c_ss)

            # Check prompt label
            self.assertIn("neo-mac", term.prompt_lbl.text())
        finally:
            term.close()

    def test_05_files_view_macos_styling(self):
        from core.neo_files_view import NeoFilesView, CARD_BG, ACCENT_PRIMARY

        files_v = NeoFilesView(initial_root=str(ROOT))
        try:
            self.assertEqual(CARD_BG.upper(), "#232327")
            self.assertEqual(ACCENT_PRIMARY.upper(), "#0A84FF")

            # Check search field styling has rounded capsule
            s_ss = files_v.search_in.styleSheet()
            self.assertIn("border-radius: 7px", s_ss)
            self.assertIn("#1C1C1E", s_ss)
        finally:
            files_v.close()

    def test_06_chat_code_block_macos_dots(self):
        from core.neo_chat import CodeBlockWidget, BG_OBSIDIAN, ACCENT_PRIMARY

        code_w = CodeBlockWidget("print('hello macOS')", language="python")
        try:
            self.assertEqual(BG_OBSIDIAN.upper(), "#161618")
            self.assertEqual(ACCENT_PRIMARY.upper(), "#0A84FF")

            # Verify traffic light dots exist in CodeBlock
            dots = code_w.findChildren(QLabel)
            dot_styles = [d.styleSheet().upper() for d in dots if "border-radius" in d.styleSheet()]
            self.assertTrue(any("#FF5F56" in s for s in dot_styles), "Missing red traffic dot in code block")
            self.assertTrue(any("#FFBD2E" in s for s in dot_styles), "Missing yellow traffic dot in code block")
            self.assertTrue(any("#27C93F" in s for s in dot_styles), "Missing green traffic dot in code block")
        finally:
            code_w.close()


if __name__ == "__main__":
    unittest.main()
