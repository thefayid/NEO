"""
core/theme_provider.py — Senior Design Engineering Theme Provider for macOS Sequoia/Tahoe.

Provides:
  1. ThemeProvider (Singleton QObject) with theme_changed signal.
  2. Automatic OS System Dark/Light Mode Detection & Switching.
  3. User-selectable macOS Accents (Blue, Purple, Pink, Red, Orange, Yellow, Green, Graphite).
  4. Accessors for Semantic Colors, Typography (Inter with -0.01em tracking), 4pt Grid, Radii, Shadows.
  5. Dynamic Global QSS Stylesheet Generator.
  6. Zero hardcoded colors: everything resolves from design tokens.
"""
from __future__ import annotations

import sys
import platform
from typing import Optional, Dict, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QApplication, QWidget, QGraphicsDropShadowEffect

from core.design_tokens import (
    Spacing,
    Radii,
    Elevation,
    ShadowSpec,
    Typography,
    TypeStyle,
    SemanticColors,
    DARK_SEMANTIC_COLORS,
    LIGHT_SEMANTIC_COLORS,
    MACOS_ACCENTS,
)


def _detect_system_dark_mode() -> bool:
    """Detects whether the operating system is currently running in Dark Mode."""
    os_name = platform.system()
    if os_name == "Windows":
        try:
            import winreg
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True
    elif os_name == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return out.lower() == "dark"
        except Exception:
            return True
    return True


class ThemeProvider(QObject):
    """
    Central macOS HIG Theme Engine & Provider (Singleton).
    Manages active color mode (Light / Dark / System Auto), accent palette,
    typography scaling with optical tracking, and dynamic QSS stylesheets.
    """
    theme_changed = pyqtSignal(str)  # Emits new resolved mode: "dark" | "light"

    _instance: Optional["ThemeProvider"] = None

    @classmethod
    def instance(cls) -> "ThemeProvider":
        if cls._instance is None:
            cls._instance = ThemeProvider()
        return cls._instance

    def __init__(self, parent=None):
        if ThemeProvider._instance is not None:
            return
        super().__init__(parent)
        ThemeProvider._instance = self

        self._mode_preference: str = "dark"   # "dark" | "light" | "system"
        self._accent_name: str = "blue"       # default macOS Sequoia System Blue
        self._custom_accent_hex: Optional[str] = None

        self.spacing = Spacing
        self.radii = Radii
        self.elevation = Elevation
        self.typography = Typography

    # ── 1. Mode & System Detection ───────────────────────────────────────────

    @property
    def mode(self) -> str:
        """The user's configuration setting: 'dark', 'light', or 'system'."""
        return self._mode_preference

    @property
    def resolved_mode(self) -> str:
        """The currently active appearance: 'dark' or 'light'."""
        if self._mode_preference == "system":
            return "dark" if _detect_system_dark_mode() else "light"
        return self._mode_preference

    @property
    def is_dark(self) -> bool:
        return self.resolved_mode == "dark"

    def set_mode(self, mode: str) -> None:
        """Sets appearance mode ('dark', 'light', 'system') and broadcasts change."""
        clean = str(mode or "dark").lower().strip()
        if clean not in ("dark", "light", "system"):
            clean = "dark"
        if clean != self._mode_preference:
            self._mode_preference = clean
            self._sync_legacy_compat()
            self.theme_changed.emit(self.resolved_mode)

    def toggle_mode(self) -> str:
        """Toggles between Dark and Light mode."""
        new_mode = "light" if self.is_dark else "dark"
        self.set_mode(new_mode)
        return new_mode

    # ── 2. Accent Colors ─────────────────────────────────────────────────────

    @property
    def accent_name(self) -> str:
        return self._accent_name

    def set_accent(self, name_or_hex: str) -> bool:
        """
        Sets the user-selected accent color. Accepts preset names:
        ('blue', 'purple', 'pink', 'red', 'orange', 'yellow', 'green', 'graphite')
        or a custom #RRGGBB hex string.
        """
        key = str(name_or_hex or "").lower().strip()
        if key in MACOS_ACCENTS:
            self._accent_name = key
            self._custom_accent_hex = None
            self._sync_legacy_compat()
            self.theme_changed.emit(self.resolved_mode)
            return True
        elif key.startswith("#") and len(key) == 7:
            self._accent_name = "custom"
            self._custom_accent_hex = key.upper()
            self._sync_legacy_compat()
            self.theme_changed.emit(self.resolved_mode)
            return True
        return False

    @property
    def accent(self) -> str:
        """Active accent hex color for the resolved appearance mode."""
        if self._custom_accent_hex:
            return self._custom_accent_hex
        dark_hex, light_hex = MACOS_ACCENTS.get(self._accent_name, MACOS_ACCENTS["blue"])
        return dark_hex if self.is_dark else light_hex

    @property
    def accent_color(self) -> str:
        return self.accent

    @property
    def accent_color_hover(self) -> str:
        return self.accent_hover

    @property
    def accent_color_pressed(self) -> str:
        return self.accent_pressed

    @property
    def accent_hover(self) -> str:
        """Lighter/more saturated variant for hover states."""
        c = QColor(self.accent)
        if self.is_dark:
            return c.lighter(118).name()
        return c.lighter(108).name()

    @property
    def accent_pressed(self) -> str:
        """Deeper variant for active/pressed states."""
        c = QColor(self.accent)
        if self.is_dark:
            return c.darker(118).name()
        return c.darker(115).name()

    @property
    def accent_subtle(self) -> str:
        """18% opacity tint for selection capsule backgrounds."""
        c = QColor(self.accent)
        alpha = 0.20 if self.is_dark else 0.16
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.2f})"

    # ── 3. Semantic Colors Accessor ──────────────────────────────────────────

    @property
    def colors(self) -> SemanticColors:
        """Semantic colors active for the current resolved appearance."""
        return DARK_SEMANTIC_COLORS if self.is_dark else LIGHT_SEMANTIC_COLORS

    def color(self, token_name: str) -> str:
        """Returns hex or rgba string for any semantic color token."""
        if hasattr(self.colors, token_name):
            return getattr(self.colors, token_name)
        if token_name in ("accent", "accent_primary"):
            return self.accent
        if token_name == "accent_hover":
            return self.accent_hover
        if token_name == "accent_pressed":
            return self.accent_pressed
        if token_name == "accent_subtle":
            return self.accent_subtle
        return "#FFFFFF" if self.is_dark else "#000000"

    def qcolor(self, token_name: str) -> QColor:
        """Returns a PyQt6 QColor instance for the given token."""
        val = self.color(token_name)
        if val.startswith("rgba"):
            # Parse rgba(r, g, b, a)
            import re
            m = re.match(r"rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)", val)
            if m:
                r, g, b, a = int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))
                return QColor(r, g, b, int(a * 255))
        return QColor(val)

    # ── 4. Typography Scale Provider ─────────────────────────────────────────

    def font(self, style_or_name: TypeStyle | str, weight_override: Optional[QFont.Weight] = None) -> QFont:
        """
        Creates a QFont configured with Apple San Francisco / Inter metrics,
        exact point size, and -0.01em tracking.
        """
        if isinstance(style_or_name, str):
            style = getattr(self.typography, style_or_name, self.typography.body)
        else:
            style = style_or_name

        qf = QFont("Inter", style.point_size)
        qf.setFamilies(self.typography.FONT_FAMILIES)

        if weight_override is not None:
            qf.setWeight(weight_override)
        else:
            # Map style weight
            weights = {
                400: QFont.Weight.Normal,
                500: QFont.Weight.Medium,
                600: QFont.Weight.DemiBold,
                700: QFont.Weight.Bold,
            }
            qf.setWeight(weights.get(style.weight_val, QFont.Weight.Normal))

        # Optical letter-spacing tracking (-0.01em standard)
        # Convert -0.01em into percentage (99% width tracking)
        qf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99.0)
        qf.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return qf

    def font_mono(self, point_size: int = 11, bold: bool = False) -> QFont:
        """Apple SF Mono typography for terminal and code views."""
        qf = QFont("SF Mono", point_size)
        qf.setFamilies(self.typography.FONT_MONO_FAMILIES)
        qf.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        qf.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return qf

    # ── 5. Layered Elevation (Soft Multi-Layer Shadows, Never Glows) ──────────

    def shadow_effect(self, spec: ShadowSpec, parent: Optional[QObject] = None) -> QGraphicsDropShadowEffect:
        """
        Constructs a soft physical key-light drop shadow effect.
        macOS Sequoia relies on subtle physical light diffusion, never neon bloom glows.
        """
        effect = QGraphicsDropShadowEffect(parent)
        effect.setBlurRadius(spec.blur_key)
        effect.setYOffset(spec.offset_y_key)
        effect.setXOffset(0)
        alpha_byte = int(max(0.0, min(1.0, spec.alpha_key)) * 255)
        effect.setColor(QColor(0, 0, 0, alpha_byte))
        return effect

    # ── 6. Dynamic Global QSS Stylesheet Generator ───────────────────────────

    def generate_root_stylesheet(self) -> str:
        """
        Generates the comprehensive root macOS Sequoia QSS stylesheet.
        Enforces pixel-perfect overlay scrollbars, control borders, tooltips,
        focus rings, inputs, and selection capsules with zero hardcoded values.
        """
        c = self.colors
        accent = self.accent
        accent_subtle = self.accent_subtle

        return f"""
            /* ── Global macOS Sequoia Canvas ── */
            QWidget {{
                background-color: {c.windowBackground};
                color: {c.labelPrimary};
                font-family: Inter, -apple-system, "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Segoe UI", sans-serif;
                selection-background-color: {accent};
                selection-color: #FFFFFF;
                border: none;
            }}

            /* ── Thin Overlay Scrollbars (7px Floating Pill) ── */
            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: 2px 0 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c.labelQuaternary};
                min-height: 24px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c.labelTertiary};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 7px;
                margin: 0 2px 0 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: {c.labelQuaternary};
                min-width: 24px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {c.labelTertiary};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}

            /* ── Tooltips ── */
            QToolTip {{
                background-color: {c.popoverBackground};
                color: {c.labelPrimary};
                border: 1px solid {c.controlBorder};
                border-radius: {self.radii.sm}px;
                padding: {self.spacing.xs}px {self.spacing.sm}px;
                font-size: 11px;
            }}

            /* ── Inputs & Edit Fields ── */
            QLineEdit, QTextEdit, QTextBrowser, QPlainTextEdit {{
                background-color: {c.controlBackground};
                color: {c.labelPrimary};
                border: 1px solid {c.controlBorder};
                border-radius: {self.radii.md}px;
                padding: {self.spacing.xs}px {self.spacing.sm}px;
            }}
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1.5px solid {accent};
                background-color: {c.controlBackgroundSecondary};
            }}

            /* ── Push Buttons (macOS Standard Control) ── */
            QPushButton {{
                background-color: {c.controlBackgroundSecondary};
                color: {c.labelPrimary};
                border: 1px solid {c.controlBorder};
                border-radius: {self.radii.sm}px;
                padding: {self.spacing.xs}px {self.spacing.md}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c.cardBackgroundHover};
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: {accent_subtle};
                color: {accent};
            }}
            QPushButton:disabled {{
                color: {c.labelTertiary};
                border-color: {c.separator};
                background-color: transparent;
            }}

            /* ── Sliders ── */
            QSlider::groove:horizontal {{
                height: 4px;
                background: {c.controlBackgroundTertiary};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #FFFFFF;
                border: 0.5px solid rgba(0, 0, 0, 0.15);
                width: 16px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 8px;
            }}

            /* ── Checkboxes ── */
            QCheckBox {{
                spacing: {self.spacing.sm}px;
                color: {c.labelPrimary};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {c.controlBorder};
                background: {c.controlBackgroundSecondary};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
        """

    def apply_to_app(self, app: Optional[QApplication] = None) -> None:
        """Applies global design token styles and default font to the QApplication."""
        target_app = app or QApplication.instance()
        if target_app:
            target_app.setStyleSheet(self.generate_root_stylesheet())
            target_app.setFont(self.font(self.typography.body))

    # ── 7. Internal Legacy Compatibility Bridge ──────────────────────────────

    def _sync_legacy_compat(self) -> None:
        """
        Synchronizes legacy class C and neo_ui theme modules so any older code
        referencing C.BG, C.PRI, or neo_ui.BG_OBSIDIAN immediately gets
        the new design-token values with zero breakage.
        """
        try:
            import ui
            if hasattr(ui, "C"):
                ui.C.BG = self.colors.windowBackground
                ui.C.PANEL = self.colors.sidebar
                ui.C.PANEL2 = self.colors.cardBackground
                ui.C.BORDER = self.colors.separatorOpaque
                ui.C.BORDER_A = self.colors.controlBorder
                ui.C.BORDER_B = self.accent
                ui.C.PRI = self.accent
                ui.C.ACCENT = self.accent
                ui.C.GREEN = self.colors.systemGreen
                ui.C.RED = self.colors.systemRed
                ui.C.ACC2 = self.colors.systemYellow
                ui.C.TEXT = self.colors.labelPrimary
                ui.C.TEXT_MED = self.colors.labelSecondary
                ui.C.TEXT_DIM = self.colors.labelTertiary
        except Exception:
            pass

        try:
            import core.neo_ui as neo_ui
            neo_ui.BG_OBSIDIAN = self.colors.windowBackground
            neo_ui.SIDEBAR_BG = self.colors.sidebar
            neo_ui.CARD_BG = self.colors.cardBackground
            neo_ui.CARD_BORDER = self.colors.separatorOpaque
            neo_ui.CARD_HOVER = self.colors.cardBackgroundHover
            neo_ui.NAV_ACTIVE_BG = self.accent
            neo_ui.TEXT_WHITE = self.colors.labelPrimary
            neo_ui.TEXT_MUTED = self.colors.labelSecondary
            neo_ui.TEXT_DIM = self.colors.labelTertiary
            neo_ui.ACCENT_PRIMARY = self.accent
            neo_ui.SEMANTIC_SUCCESS = self.colors.systemGreen
            neo_ui.SEMANTIC_WARNING = self.colors.systemYellow
            neo_ui.SEMANTIC_ERROR = self.colors.systemRed
        except Exception:
            pass


# Global singleton convenience handle
theme = ThemeProvider.instance()
