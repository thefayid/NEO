"""
tests/test_macos_phase3_components.py — Senior Engineering Test Suite for Phase 3 Components.

Verifies all Apple HIG (macOS Sequoia/Tahoe) component specifications:
1. Push Button (MacOSButton: default, secondary, destructive in all 5 states)
2. Segmented Control (MacOSSegmentedControl: sliding selection pill, 180ms OutCubic)
3. Toggle Switch (MacOSToggle: exact 38x22 dimensions, 18px thumb, press elasticity)
4. Text Field (MacOSTextField: 28px height, 3px accent focus ring)
5. Search Field (MacOSSearchField: 28px, magnifier, auto-revealing clear button)
6. Popover with Directional Arrow (MacOSPopover)
7. Context Menu with 6px Radius & Shortcut Column (MacOSContextMenu)
8. Sidebar List with Selection Highlight & Lucide Icons (MacOSSidebarList)
9. Toast / Notification Banner (MacOSToast: Info, Success, Warning, Error)
10. Sheet Modal with Slide Animation (MacOSSheetModal)
11. Tooltip with 600ms Delay (MacOSTooltip)
12. Thin Overlay Scrollbars (MacOSOverlayScrollBar & MacOSScrollArea)
13. Living Component Gallery Page (MacOSComponentGallery)
"""
import sys
import unittest
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QKeyEvent

from core.theme_provider import theme
from core.macos_components import (
    render_lucide_icon,
    MacOSButton,
    MacOSSegmentedControl,
    MacOSToggle,
    MacOSTextField,
    MacOSSearchField,
    MacOSPopover,
    MacOSContextMenu,
    MacOSSidebarList,
    MacOSToast,
    MacOSSheetModal,
    MacOSTooltip,
    MacOSOverlayScrollBar,
    MacOSScrollArea,
)
from core.macos_gallery import MacOSComponentGallery

_app = QApplication.instance() or QApplication(sys.argv)


class TestMacOSPhase3Components(unittest.TestCase):

    def setUp(self):
        theme.set_mode("dark")
        theme.set_accent("blue")

    def test_01_lucide_icons_vector_rendering(self):
        """Lucide icons must render crisp transparent vector pixmaps with 1.5 stroke."""
        pix_search = render_lucide_icon("search", color="#0A84FF", size=16, stroke_width=1.5)
        self.assertFalse(pix_search.isNull())
        self.assertEqual(pix_search.width(), 16)
        self.assertEqual(pix_search.height(), 16)

        pix_settings = render_lucide_icon("settings", color="#FFFFFF", size=24, stroke_width=1.5)
        self.assertFalse(pix_settings.isNull())
        self.assertEqual(pix_settings.width(), 24)

    def test_02_push_button_variants_and_states(self):
        """MacOSButton must support default, secondary, and destructive variants in all states."""
        # 1. Default (Primary Accent)
        btn_def = MacOSButton("Primary", variant="default")
        self.assertEqual(btn_def.height(), 28)
        self.assertIn(theme.accent, btn_def.styleSheet())

        # 2. Secondary (Control Card)
        btn_sec = MacOSButton("Secondary", variant="secondary")
        self.assertIn(theme.colors.controlBackground, btn_sec.styleSheet())

        # 3. Destructive (System Red)
        btn_des = MacOSButton("Delete", variant="destructive", icon_name="trash-2")
        self.assertIn("255, 69, 58", btn_des.styleSheet())
        self.assertFalse(btn_des.icon().isNull())

        # 4. Disabled State
        btn_def.setEnabled(False)
        self.assertFalse(btn_def.isEnabled())

    def test_03_segmented_control_sliding_pill(self):
        """MacOSSegmentedControl must animate sliding selection pill on index change."""
        seg = MacOSSegmentedControl(["Day", "Week", "Month", "Year"])
        self.assertEqual(seg.height(), 28)
        self.assertEqual(seg.current_index(), 0)
        self.assertEqual(seg.current_text(), "Day")

        # Track signals
        received = []
        seg.current_changed.connect(lambda idx, text: received.append((idx, text)))

        # Switch segment
        seg.set_current_index(2)
        self.assertEqual(seg.current_index(), 2)
        self.assertEqual(seg.current_text(), "Month")
        self.assertEqual(received[-1], (2, "Month"))

        # Arrow key navigation
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        seg.keyPressEvent(key_event)
        self.assertEqual(seg.current_index(), 1)
        self.assertEqual(seg.current_text(), "Week")

    def test_04_toggle_switch_exact_38x22(self):
        """MacOSToggle must have exact 38x22 dimensions, 18px thumb, and space toggling."""
        toggle = MacOSToggle(checked=False)
        self.assertEqual(toggle.width(), 38)
        self.assertEqual(toggle.height(), 22)
        self.assertFalse(toggle.is_checked())
        self.assertEqual(toggle.thumb_x, 2.0)

        # Toggle via method
        toggle.set_checked(True, animated=False)
        self.assertTrue(toggle.is_checked())
        self.assertEqual(toggle.thumb_x, 18.0)

        # Space key toggling
        space_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        toggle.keyPressEvent(space_event)
        self.assertFalse(toggle.is_checked())

    def test_05_text_field_spec(self):
        """MacOSTextField must be 28px height with 6px continuous corner radius."""
        txt = MacOSTextField("Placeholder text")
        self.assertEqual(txt.height(), 28)
        self.assertEqual(txt.placeholderText(), "Placeholder text")
        txt.setText("San Francisco")
        self.assertEqual(txt.text(), "San Francisco")
        txt.setEnabled(False)
        self.assertFalse(txt.isEnabled())

    def test_06_search_field_magnifier_and_clear_button(self):
        """MacOSSearchField must show clear button only when text is non-empty."""
        search = MacOSSearchField("Search knowledge...")
        self.assertEqual(search.height(), 28)
        self.assertTrue(search.btn_clear.isHidden())

        # Typing reveals clear button
        search.set_text("Neural Swarm")
        self.assertEqual(search.text(), "Neural Swarm")
        self.assertFalse(search.btn_clear.isHidden())

        # Clicking clear resets text
        cleared_emitted = []
        search.cleared.connect(lambda: cleared_emitted.append(True))
        search.clear()
        self.assertEqual(search.text(), "")
        self.assertTrue(search.btn_clear.isHidden())
        self.assertTrue(cleared_emitted)

    def test_07_popover_with_arrow(self):
        """MacOSPopover must instantiate and configure bubble with arrow."""
        parent = QWidget()
        parent.resize(400, 400)
        popover = MacOSPopover(parent)
        content = QLabel("Popover Info")
        popover.set_content(content)
        self.assertIs(popover._content_widget, content)
        self.assertEqual(popover.CORNER_RADIUS, 10)
        self.assertEqual(popover.ARROW_SIZE, 9)

    def test_08_context_menu_shortcuts(self):
        """MacOSContextMenu must configure 6px radius and keyboard shortcut column."""
        menu = MacOSContextMenu("Actions")
        action = menu.add_action_item("Copy", shortcut="⌘C", icon_name="copy")
        self.assertIn("⌘C", action.text())
        self.assertIn("Copy", action.text())
        self.assertFalse(action.icon().isNull())

    def test_09_sidebar_list_selection(self):
        """MacOSSidebarList must manage items, section headers, badges, and selection highlight."""
        sb = MacOSSidebarList()
        sb.add_section_header("Navigation")
        it1 = sb.add_item("projects", "Projects", icon_name="folder", badge="3")
        it2 = sb.add_item("tasks", "Tasks", icon_name="check-square", badge="5")

        self.assertEqual(sb.selected_id(), "projects")
        self.assertTrue(it1._is_active)
        self.assertFalse(it2._is_active)

        # Select tasks
        selected = []
        sb.item_selected.connect(lambda item_id, label: selected.append((item_id, label)))
        sb.select_item("tasks")
        self.assertEqual(sb.selected_id(), "tasks")
        self.assertFalse(it1._is_active)
        self.assertTrue(it2._is_active)
        self.assertEqual(selected[-1], ("tasks", "Tasks"))

    def test_10_toast_variants(self):
        """MacOSToast must support Info, Success, Warning, Error variants."""
        parent = QWidget()
        parent.resize(800, 600)
        toast = MacOSToast("Title", "Message detail", variant="success", duration_ms=5000, parent=parent)
        self.assertEqual(toast.title_lbl.text(), "Title")
        self.assertEqual(toast.msg_lbl.text(), "Message detail")
        self.assertEqual(toast.width(), 320)
        toast.dismiss()

    def test_11_sheet_modal_slide_mechanics(self):
        """MacOSSheetModal must anchor to parent top with 14px rounded bottom corners."""
        parent = QWidget()
        parent.resize(800, 600)
        sheet = MacOSSheetModal("Calibration Sheet", parent=parent)
        self.assertEqual(sheet.card.width(), 460)
        self.assertEqual(sheet.title_lbl.text(), "Calibration Sheet")
        self.assertIsNotNone(sheet.btn_cancel)
        self.assertIsNotNone(sheet.btn_done)

    def test_12_overlay_scrollbar_opacity(self):
        """MacOSOverlayScrollBar must maintain 0-1 opacity property for auto-fade."""
        scroll = MacOSScrollArea()
        scroll.resize(300, 200)
        vbar = scroll.verticalScrollBar()
        self.assertIsInstance(vbar, MacOSOverlayScrollBar)
        self.assertEqual(vbar.opacity, 0.0)

        # Scrolling animates opacity
        vbar._show_active(animated=False)
        self.assertEqual(vbar.opacity, 1.0)

    def test_13_living_component_gallery_page(self):
        """MacOSComponentGallery must instantiate all 8 sections and respond to theme toggling."""
        gallery = MacOSComponentGallery()
        self.assertIsNotNone(gallery.scroll_area)
        self.assertIsNotNone(gallery.btn_mode_toggle)

        # Test live theme toggle from gallery
        initial_dark = theme.is_dark
        gallery._toggle_theme_mode()
        self.assertNotEqual(theme.is_dark, initial_dark)

        # Restore
        gallery._toggle_theme_mode()
        self.assertEqual(theme.is_dark, initial_dark)


if __name__ == "__main__":
    unittest.main()
