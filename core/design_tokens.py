"""
core/design_tokens.py — Apple Human Interface Guidelines Design Tokens (macOS Sequoia/Tahoe Standard).

Senior Design Engineering Specification:
1. Semantic Color Tokens:
   - Window & Surface Hierarchy: windowBackground, controlBackground, controlBackgroundSecondary,
     controlBackgroundTertiary, sidebar, cardBackground, cardBackgroundHover, popoverBackground.
   - Separators & Borders: separator, separatorOpaque, controlBorder, focusRing.
   - Label Hierarchy: labelPrimary (high-contrast), labelSecondary (medium),
     labelTertiary (subtle disabled), labelQuaternary (watermark/ghost).
   - Semantic Feedback: systemGreen, systemYellow, systemOrange, systemRed, systemPurple,
     systemPink, systemTeal, systemIndigo, systemGray.
2. Accent Color Palette:
   - Default: #0A84FF (Dark) / #007AFF (Light)
   - User-selectable accents: Blue, Purple, Pink, Red, Orange, Yellow, Green, Graphite.
3. Typography Scale (Mirroring Apple San Francisco / Inter):
   - Scale: Large Title (26), Title 1 (22), Title 2 (17), Title 3 (15), Headline (13 semibold),
     Body (13 regular), Callout (12), Subheadline (11), Footnote (10), Caption 1 (10), Caption 2 (9).
   - Tracking: -0.01em (-0.13px tracking at body, -0.26px at display).
   - Font family priority: Inter, -apple-system, SF Pro Text, SF Pro Display, Helvetica Neue, Segoe UI, sans-serif.
4. 4pt Spacing Grid:
   - 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 64pt.
5. Continuous-Corner Radii:
   - sm (6px), md (10px), lg (14px), xl (20px), pill (9999px).
6. Layered Elevation (Soft Multi-Layer Shadows, Never Harsh Neon Glows):
   - None, Low, Medium, High.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


# ── 1. 4pt Spacing Grid ───────────────────────────────────────────────────────
class Spacing:
    """Strict 4pt modular layout grid conforming to Apple macOS HIG."""
    none: int = 0
    xs: int   = 4    # 4pt  — micro gaps, badge margins, inline tags
    sm: int   = 8    # 8pt  — compact item padding, icon-text gap
    md: int   = 12   # 12pt — standard element margin, card interior gap
    base: int = 16   # 16pt — standard content padding, container gutter
    lg: int   = 20   # 20pt — card separation, section spacing
    xl: int   = 24   # 24pt — major block margin, panel padding
    xxl: int  = 28   # 28pt — breathing room for dashboard blocks
    xxxl: int = 32   # 32pt — spacious view boundaries
    g40: int  = 40   # 40pt — large stage margins
    g48: int  = 48   # 48pt — hero header padding
    g64: int  = 64   # 64pt — macroscopic layout gutter


# ── 2. Continuous-Corner Radii ────────────────────────────────────────────────
class Radii:
    """Continuous squircle corner radii replicating macOS Sequoia surfaces."""
    none: int = 0
    sm: int   = 6     # 6px  — micro controls, subagent tags, inline chips, status pills
    md: int   = 10    # 10px — cards, source list selection capsules, inputs, buttons
    lg: int   = 14    # 14px — grouped section containers, popovers, media tiles
    xl: int   = 20    # 20px — modal dialogs, hero stages, prominent floating sheets
    pill: int = 9999  # Pill — search capsules, omni-bar, audio waveforms


# ── 3. Layered Elevation (Soft Multi-Layer Shadows, Never Glows) ──────────────
@dataclass(frozen=True)
class ShadowSpec:
    """Multi-layer shadow specification (blur radius, y-offset, opacity 0.0-1.0)."""
    blur_ambient: int
    offset_y_ambient: int
    alpha_ambient: float
    blur_key: int
    offset_y_key: int
    alpha_key: float


class Elevation:
    """
    Subtle ambient-occlusion + key-light elevation models.
    macOS Sequoia never uses neon or cyan bloom glows; it employs physical light diffusion.
    """
    none = ShadowSpec(
        blur_ambient=0, offset_y_ambient=0, alpha_ambient=0.0,
        blur_key=0, offset_y_key=0, alpha_key=0.0
    )
    # Low: Standard cards, resting list items, source list rows
    low = ShadowSpec(
        blur_ambient=6, offset_y_ambient=1, alpha_ambient=0.12,
        blur_key=12, offset_y_key=3, alpha_key=0.18
    )
    # Medium: Hovered cards, dropdown menus, quick-action sheets
    medium = ShadowSpec(
        blur_ambient=12, offset_y_ambient=2, alpha_ambient=0.16,
        blur_key=24, offset_y_key=8, alpha_key=0.26
    )
    # High: Floating Island capsule, modal dialogs, command palette
    high = ShadowSpec(
        blur_ambient=20, offset_y_ambient=4, alpha_ambient=0.20,
        blur_key=40, offset_y_key=16, alpha_key=0.34
    )


# ── 4. Typography Scale Specification ─────────────────────────────────────────
@dataclass(frozen=True)
class TypeStyle:
    """Apple HIG Typography token with size, weight, line-height, and tracking."""
    point_size: int
    weight_name: str    # "Regular" | "Medium" | "Semibold" | "Bold"
    weight_val: int     # 400 | 500 | 600 | 700
    line_height: int    # in points
    tracking: float     # in em units (-0.01em = Apple standard optical tightening)


class Typography:
    """Apple macOS HIG San Francisco Typography scale executed with Inter / -apple-system."""
    FONT_FAMILIES = [
        "Inter",
        "-apple-system",
        "SF Pro Text",
        "SF Pro Display",
        "Helvetica Neue",
        "Segoe UI Variable Text",
        "Segoe UI",
        "sans-serif"
    ]
    FONT_MONO_FAMILIES = [
        "SF Mono",
        "Menlo",
        "Monaco",
        "Consolas",
        "Courier New",
        "monospace"
    ]

    large_title = TypeStyle(point_size=26, weight_name="Bold", weight_val=700, line_height=32, tracking=-0.015)
    title_1     = TypeStyle(point_size=22, weight_name="Bold", weight_val=700, line_height=28, tracking=-0.012)
    title_2     = TypeStyle(point_size=17, weight_name="Semibold", weight_val=600, line_height=22, tracking=-0.010)
    title_3     = TypeStyle(point_size=15, weight_name="Semibold", weight_val=600, line_height=20, tracking=-0.010)
    headline    = TypeStyle(point_size=13, weight_name="Semibold", weight_val=600, line_height=18, tracking=-0.010)
    body        = TypeStyle(point_size=13, weight_name="Regular", weight_val=400, line_height=18, tracking=-0.010)
    callout     = TypeStyle(point_size=12, weight_name="Regular", weight_val=400, line_height=16, tracking=-0.008)
    subheadline = TypeStyle(point_size=11, weight_name="Regular", weight_val=400, line_height=14, tracking=-0.006)
    footnote    = TypeStyle(point_size=10, weight_name="Regular", weight_val=400, line_height=13, tracking=-0.005)
    caption_1   = TypeStyle(point_size=10, weight_name="Regular", weight_val=400, line_height=13, tracking=-0.005)
    caption_2   = TypeStyle(point_size=9,  weight_name="Medium",  weight_val=500, line_height=12, tracking=-0.004)
    code        = TypeStyle(point_size=11, weight_name="Regular", weight_val=400, line_height=16, tracking=0.0)


# ── 5. User-Selectable macOS Accent Colors ─────────────────────────────────────
# (Dark Hex, Light Hex)
MACOS_ACCENTS: Dict[str, Tuple[str, str]] = {
    "blue":     ("#0A84FF", "#007AFF"),  # macOS Sequoia System Blue (Default)
    "purple":   ("#BF5AF2", "#AF52DE"),  # macOS System Purple
    "pink":     ("#FF375F", "#FF2D55"),  # macOS System Pink
    "red":      ("#FF453A", "#FF3B30"),  # macOS System Red
    "orange":   ("#FF9F0A", "#FF9500"),  # macOS System Orange
    "yellow":   ("#FFD60A", "#FFCC00"),  # macOS System Yellow
    "green":    ("#30D158", "#34C759"),  # macOS System Green
    "graphite": ("#8E8E93", "#8E8E93"),  # macOS System Neutral Graphite
}


# ── 6. Semantic Color Tokens Data Model ───────────────────────────────────────
@dataclass
class SemanticColors:
    # ── Surfaces & Backgrounds ──
    windowBackground: str            # Base application window canvas
    controlBackground: str           # Standard control & card surface
    controlBackgroundSecondary: str  # Subtle secondary input / chip background
    controlBackgroundTertiary: str   # Deep nested container surface
    sidebar: str                     # macOS Source List sidebar surface
    sidebarSelected: str             # Selected item capsule fill
    cardBackground: str              # Elevated card surface
    cardBackgroundHover: str         # Hover state for interactive cards
    popoverBackground: str           # Floating sheets & dropdown popovers
    trafficClose: str                # macOS Window Close dot
    trafficMin: str                  # macOS Window Minimize dot
    trafficZoom: str                 # macOS Window Zoom dot

    # ── Separators, Dividers & Outlines ──
    separator: str                   # 1px translucent divider
    separatorOpaque: str             # Solid fallback separator
    controlBorder: str               # Boundary border around controls
    focusRing: str                   # Keyboard navigation focus ring

    # ── Typography & Foreground Labels ──
    labelPrimary: str                # 100% primary high-contrast text
    labelSecondary: str              # 60% secondary text (subtitles, metadata)
    labelTertiary: str               # 35% disabled or placeholder text
    labelQuaternary: str             # 18% ghost watermark / subtle icons

    # ── Semantic Feedback ──
    systemGreen: str                 # Success, online, nominal status
    systemYellow: str                # Warning, thinking, caution
    systemOrange: str                # Attention required, queued
    systemRed: str                   # Critical, error, muted, aborted
    systemPurple: str                # AI agent dispatch, neural swarm
    systemPink: str                  # Empathy, special alerts
    systemTeal: str                  # Optical / vision telemetry
    systemIndigo: str                # Knowledge graph, memory
    systemGray: str                  # Disabled, neutral state


# ── 7. Apple macOS Sequoia/Tahoe Color Palettes ────────────────────────────────

DARK_SEMANTIC_COLORS = SemanticColors(
    windowBackground           = "#161618",
    controlBackground          = "#222225",
    controlBackgroundSecondary = "#2A2A2E",
    controlBackgroundTertiary  = "#323236",
    sidebar                    = "#1A1A1D",
    sidebarSelected            = "rgba(10, 132, 255, 0.20)",
    cardBackground             = "#232327",
    cardBackgroundHover        = "#2C2C31",
    popoverBackground          = "#28282D",
    trafficClose               = "#FF5F56",
    trafficMin                 = "#FFBD2E",
    trafficZoom                = "#27C93F",
    separator                  = "rgba(255, 255, 255, 0.08)",
    separatorOpaque            = "#2C2C2F",
    controlBorder              = "rgba(255, 255, 255, 0.10)",
    focusRing                  = "#0A84FF",
    labelPrimary               = "#F5F5F7",
    labelSecondary             = "rgba(235, 235, 245, 0.60)",
    labelTertiary              = "rgba(235, 235, 245, 0.42)",
    labelQuaternary            = "rgba(235, 235, 245, 0.18)",
    systemGreen                = "#30D158",
    systemYellow               = "#FFD60A",
    systemOrange               = "#FF9F0A",
    systemRed                  = "#FF453A",
    systemPurple               = "#BF5AF2",
    systemPink                 = "#FF375F",
    systemTeal                 = "#40C8E0",
    systemIndigo               = "#5E5CE6",
    systemGray                 = "#8E8E93",
)

LIGHT_SEMANTIC_COLORS = SemanticColors(
    windowBackground           = "#F6F6F6",
    controlBackground          = "#FFFFFF",
    controlBackgroundSecondary = "#EFEFF4",
    controlBackgroundTertiary  = "#E5E5EA",
    sidebar                    = "#EBEBF0",
    sidebarSelected            = "rgba(0, 122, 255, 0.16)",
    cardBackground             = "#FFFFFF",
    cardBackgroundHover        = "#F8F8FA",
    popoverBackground          = "#FFFFFF",
    trafficClose               = "#FF5F56",
    trafficMin                 = "#FFBD2E",
    trafficZoom                = "#27C93F",
    separator                  = "rgba(0, 0, 0, 0.09)",
    separatorOpaque            = "#D1D1D6",
    controlBorder              = "rgba(0, 0, 0, 0.12)",
    focusRing                  = "#007AFF",
    labelPrimary               = "#1D1D1F",
    labelSecondary             = "rgba(60, 60, 67, 0.72)",
    labelTertiary              = "rgba(60, 60, 67, 0.56)",
    labelQuaternary            = "rgba(60, 60, 67, 0.22)",
    systemGreen                = "#248A3D",
    systemYellow               = "#A05A00",
    systemOrange               = "#C95100",
    systemRed                  = "#D70015",
    systemPurple               = "#AF52DE",
    systemPink                 = "#FF2D55",
    systemTeal                 = "#30B0C7",
    systemIndigo               = "#5856D6",
    systemGray                 = "#8E8E93",
)
