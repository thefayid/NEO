"""
tests/test_macos_phase1_tokens.py — Unit Tests for Phase 1 Design Token System & Theme Provider.

Verifies:
  1. Semantic color tokens for light and dark modes (windowBackground, controlBackground, sidebar, separator, labelPrimary/Secondary/Tertiary/Quaternary).
  2. Accent color switching with default #0A84FF (Dark) / #007AFF (Light) and user-selectable accents.
  3. Typography scale mirroring SF (Large Title 26, Title 22, Headline 13 semibold, Body 13, Callout 12, Caption 10) with Inter and -0.01em tracking.
  4. 4pt spacing grid (4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 64).
  5. Continuous-corner radii (6, 10, 14, 20, 9999).
  6. Layered elevation soft shadows (no neon/cyan bloom glows).
  7. ThemeProvider singleton, mode switching, and dynamic stylesheet generator.
"""
import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Headless Qt environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QColor


class TestMacOSPhase1Tokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_4pt_spacing_grid(self):
        from core.design_tokens import Spacing

        self.assertEqual(Spacing.xs, 4)
        self.assertEqual(Spacing.sm, 8)
        self.assertEqual(Spacing.md, 12)
        self.assertEqual(Spacing.base, 16)
        self.assertEqual(Spacing.lg, 20)
        self.assertEqual(Spacing.xl, 24)
        self.assertEqual(Spacing.xxl, 28)
        self.assertEqual(Spacing.xxxl, 32)
        self.assertEqual(Spacing.g40, 40)
        self.assertEqual(Spacing.g48, 48)
        self.assertEqual(Spacing.g64, 64)

        # Confirm all are strictly divisible by 4
        for attr in ["xs", "sm", "md", "base", "lg", "xl", "xxl", "xxxl", "g40", "g48", "g64"]:
            val = getattr(Spacing, attr)
            self.assertEqual(val % 4, 0, f"Spacing.{attr} ({val}) is not on 4pt grid!")

    def test_02_continuous_corner_radii(self):
        from core.design_tokens import Radii

        self.assertEqual(Radii.sm, 6)
        self.assertEqual(Radii.md, 10)
        self.assertEqual(Radii.lg, 14)
        self.assertEqual(Radii.xl, 20)
        self.assertEqual(Radii.pill, 9999)

    def test_03_elevation_soft_shadows_no_glows(self):
        from core.design_tokens import Elevation

        # Verify specs exist and are physical shadows (not glows)
        self.assertEqual(Elevation.none.blur_key, 0)

        # Low, Medium, High must have positive blur and vertical Y offset (downward key light)
        self.assertGreater(Elevation.low.blur_key, 0)
        self.assertGreater(Elevation.low.offset_y_key, 0)
        self.assertLessEqual(Elevation.low.alpha_key, 0.40)

        self.assertGreater(Elevation.medium.blur_key, Elevation.low.blur_key)
        self.assertGreater(Elevation.high.blur_key, Elevation.medium.blur_key)

    def test_04_typography_scale_and_tracking(self):
        from core.design_tokens import Typography

        # Verify sizes
        self.assertEqual(Typography.large_title.point_size, 26)
        self.assertEqual(Typography.title_1.point_size, 22)
        self.assertEqual(Typography.headline.point_size, 13)
        self.assertEqual(Typography.headline.weight_val, 600)  # Semibold
        self.assertEqual(Typography.body.point_size, 13)
        self.assertEqual(Typography.body.weight_val, 400)      # Regular
        self.assertEqual(Typography.callout.point_size, 12)
        self.assertEqual(Typography.caption_1.point_size, 10)

        # Verify optical tracking (-0.01em standard)
        self.assertAlmostEqual(Typography.headline.tracking, -0.010, places=3)
        self.assertAlmostEqual(Typography.body.tracking, -0.010, places=3)
        self.assertIn("Inter", Typography.FONT_FAMILIES)

    def test_05_semantic_color_tokens(self):
        from core.design_tokens import DARK_SEMANTIC_COLORS, LIGHT_SEMANTIC_COLORS

        # Required semantic tokens
        required_keys = [
            "windowBackground",
            "controlBackground",
            "sidebar",
            "separator",
            "labelPrimary",
            "labelSecondary",
            "labelTertiary",
            "labelQuaternary",
            "systemGreen",
            "systemYellow",
            "systemRed",
            "trafficClose",
            "trafficMin",
            "trafficZoom"
        ]

        for k in required_keys:
            self.assertTrue(hasattr(DARK_SEMANTIC_COLORS, k), f"Missing {k} in DARK_SEMANTIC_COLORS")
            self.assertTrue(hasattr(LIGHT_SEMANTIC_COLORS, k), f"Missing {k} in LIGHT_SEMANTIC_COLORS")

        # Dark Mode specifications
        self.assertEqual(DARK_SEMANTIC_COLORS.windowBackground, "#161618")
        self.assertEqual(DARK_SEMANTIC_COLORS.trafficClose, "#FF5F56")
        self.assertEqual(DARK_SEMANTIC_COLORS.trafficMin, "#FFBD2E")
        self.assertEqual(DARK_SEMANTIC_COLORS.trafficZoom, "#27C93F")

        # Light Mode specifications
        self.assertEqual(LIGHT_SEMANTIC_COLORS.windowBackground, "#F6F6F6")
        self.assertEqual(LIGHT_SEMANTIC_COLORS.controlBackground, "#FFFFFF")

    def test_06_theme_provider_singleton_and_mode_switching(self):
        from core.theme_provider import ThemeProvider, theme

        self.assertIs(ThemeProvider.instance(), theme)

        # Test mode switching
        theme.set_mode("dark")
        self.assertEqual(theme.resolved_mode, "dark")
        self.assertTrue(theme.is_dark)
        self.assertEqual(theme.color("windowBackground"), "#161618")

        theme.set_mode("light")
        self.assertEqual(theme.resolved_mode, "light")
        self.assertFalse(theme.is_dark)
        self.assertEqual(theme.color("windowBackground"), "#F6F6F6")

        # Reset back to dark
        theme.set_mode("dark")
        self.assertTrue(theme.is_dark)

    def test_07_accent_colors_and_user_selection(self):
        from core.theme_provider import theme

        theme.set_mode("dark")
        # Default accent
        self.assertEqual(theme.accent, "#0A84FF")

        theme.set_mode("light")
        self.assertEqual(theme.accent, "#007AFF")

        # Switch to Purple
        theme.set_mode("dark")
        self.assertTrue(theme.set_accent("purple"))
        self.assertEqual(theme.accent, "#BF5AF2")

        # Switch to Green
        self.assertTrue(theme.set_accent("green"))
        self.assertEqual(theme.accent, "#30D158")

        # Switch to custom hex
        self.assertTrue(theme.set_accent("#5E5CE6"))
        self.assertEqual(theme.accent, "#5E5CE6")

        # Reset to default blue
        theme.set_accent("blue")
        self.assertEqual(theme.accent, "#0A84FF")

    def test_08_font_generation_and_tracking(self):
        from core.theme_provider import theme

        qf_headline = theme.font("headline")
        self.assertEqual(qf_headline.pointSize(), 13)
        self.assertEqual(qf_headline.weight(), QFont.Weight.DemiBold)
        self.assertEqual(qf_headline.letterSpacingType(), QFont.SpacingType.PercentageSpacing)
        self.assertEqual(qf_headline.letterSpacing(), 99.0)

        qf_title = theme.font(theme.typography.large_title)
        self.assertEqual(qf_title.pointSize(), 26)
        self.assertEqual(qf_title.weight(), QFont.Weight.Bold)

        qf_mono = theme.font_mono(10)
        self.assertEqual(qf_mono.pointSize(), 10)
        self.assertIn("SF Mono", qf_mono.families())

    def test_09_shadow_generation_no_glows(self):
        from core.theme_provider import theme

        effect = theme.shadow_effect(theme.elevation.medium)
        self.assertGreater(effect.blurRadius(), 0)
        self.assertGreater(effect.yOffset(), 0)
        self.assertEqual(effect.xOffset(), 0)

        # Color must be physical shadow (neutral black with opacity), not neon glow!
        c = effect.color()
        self.assertEqual(c.red(), 0)
        self.assertEqual(c.green(), 0)
        self.assertEqual(c.blue(), 0)
        self.assertGreater(c.alpha(), 0)

    def test_10_root_qss_stylesheet_generator(self):
        from core.theme_provider import theme

        theme.set_mode("dark")
        theme.set_accent("blue")
        qss = theme.generate_root_stylesheet()

        # Check required components in generated stylesheet
        self.assertIn("QScrollBar:vertical", qss)
        self.assertIn("width: 7px", qss)
        self.assertIn("QToolTip", qss)
        self.assertIn("QLineEdit", qss)
        self.assertIn("QPushButton", qss)
        self.assertIn("QSlider", qss)
        self.assertIn("QCheckBox", qss)
        self.assertIn("#0A84FF", qss)


if __name__ == "__main__":
    unittest.main()
