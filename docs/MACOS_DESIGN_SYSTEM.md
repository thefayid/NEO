# Apple macOS HIG Design Token System (macOS Sequoia / Tahoe Standard)

A centralized design token engine and theme provider replicating Apple's Human Interface Guidelines for the desktop interface.

---

## 1. Quick Start

```python
from core.theme_provider import theme

# Access semantic colors
canvas_bg = theme.color("windowBackground")
card_bg   = theme.color("cardBackground")
text_pri  = theme.color("labelPrimary")
text_sec  = theme.color("labelSecondary")
accent    = theme.accent

# Access typography (Inter / Apple SF with -0.01em optical tracking)
lbl_title = QLabel("Overview")
lbl_title.setFont(theme.font(theme.typography.title_1))

lbl_body = QLabel("Content text...")
lbl_body.setFont(theme.font(theme.typography.body))

# Access 4pt spacing grid & continuous corner radii
layout.setContentsMargins(theme.spacing.base, theme.spacing.md, theme.spacing.base, theme.spacing.md)
layout.setSpacing(theme.spacing.sm)
widget.setStyleSheet(f"border-radius: {theme.radii.md}px;")

# Access soft layered elevation shadows (No glows!)
shadow = theme.shadow_effect(theme.elevation.medium, parent=card_widget)
card_widget.setGraphicsEffect(shadow)
```

---

## 2. Semantic Color Tokens

Colors adapt automatically between Light and Dark appearances:

| Token | Dark Appearance | Light Appearance | Usage |
| :--- | :--- | :--- | :--- |
| `windowBackground` | `#161618` | `#F6F6F6` | Base application canvas |
| `sidebar` | `#1A1A1D` | `#EBEBF0` | macOS Source List sidebar |
| `cardBackground` | `#232327` | `#FFFFFF` | Elevated cards and surfaces |
| `cardBackgroundHover`| `#2C2C31` | `#F8F8FA` | Interactive hover state |
| `controlBackground`| `#222225` | `#FFFFFF` | Inputs, edit fields, controls |
| `separator` | `rgba(255, 255, 255, 0.08)` | `rgba(0, 0, 0, 0.09)` | Translucent 1px dividers |
| `separatorOpaque` | `#2C2C2F` | `#D1D1D6` | Solid structural borders |
| `controlBorder` | `rgba(255, 255, 255, 0.10)` | `rgba(0, 0, 0, 0.12)` | Element bounding stroke |
| `labelPrimary` | `#F5F5F7` | `#1D1D1F` | High-contrast body text & titles |
| `labelSecondary` | `rgba(235, 235, 245, 0.60)` | `rgba(60, 60, 67, 0.60)` | Subtitles, metadata, timestamps |
| `labelTertiary` | `rgba(235, 235, 245, 0.35)` | `rgba(60, 60, 67, 0.35)` | Hints, disabled labels |
| `labelQuaternary`| `rgba(235, 235, 245, 0.18)` | `rgba(60, 60, 67, 0.18)` | Watermarks, scrollbar thumbs |
| `systemGreen` | `#30D158` | `#34C759` | Status online, success |
| `systemYellow` | `#FFD60A` | `#FFCC00` | Warning, thinking status |
| `systemRed` | `#FF453A` | `#FF3B30` | Critical alerts, errors, muted |
| `trafficClose` | `#FF5F56` | `#FF5F56` | macOS Close traffic light |
| `trafficMin` | `#FFBD2E` | `#FFBD2E` | macOS Minimize traffic light |
| `trafficZoom` | `#27C93F` | `#27C93F` | macOS Zoom traffic light |

---

## 3. User-Selectable Accent Colors

Change accents system-wide with immediate dynamic updates:

```python
# Set one of the standard macOS presets
theme.set_accent("blue")      # Default: #0A84FF Dark / #007AFF Light
theme.set_accent("purple")    # #BF5AF2 Dark / #AF52DE Light
theme.set_accent("pink")      # #FF375F Dark / #FF2D55 Light
theme.set_accent("red")       # #FF453A Dark / #FF3B30 Light
theme.set_accent("orange")    # #FF9F0A Dark / #FF9500 Light
theme.set_accent("yellow")    # #FFD60A Dark / #FFCC00 Light
theme.set_accent("green")     # #30D158 Dark / #34C759 Light
theme.set_accent("graphite")  # #8E8E93 Dark / #8E8E93 Light

# Or provide a custom hex color
theme.set_accent("#5E5CE6")
```

---

## 4. Typography Scale & Optical Tracking

Mirroring Apple San Francisco using `Inter` with `-0.01em` optical tracking:

| Style | Point Size | Weight | Line Height | Tracking |
| :--- | :--- | :--- | :--- | :--- |
| `large_title` | 26pt | Bold (700) | 32pt | `-0.015em` |
| `title_1` | 22pt | Bold (700) | 28pt | `-0.012em` |
| `title_2` | 17pt | Semibold (600) | 22pt | `-0.010em` |
| `title_3` | 15pt | Semibold (600) | 20pt | `-0.010em` |
| `headline` | 13pt | Semibold (600) | 18pt | `-0.010em` |
| `body` | 13pt | Regular (400) | 18pt | `-0.010em` |
| `callout` | 12pt | Regular (400) | 16pt | `-0.008em` |
| `subheadline` | 11pt | Regular (400) | 14pt | `-0.006em` |
| `footnote` | 10pt | Regular (400) | 13pt | `-0.005em` |
| `caption_1` | 10pt | Regular (400) | 13pt | `-0.005em` |
| `caption_2` | 9pt | Medium (500) | 12pt | `-0.004em` |
| `code` | 11pt | Regular (400) | 16pt | `0.000em` |

```python
label.setFont(theme.font(theme.typography.headline))
terminal.setFont(theme.font_mono(10))
```

---

## 5. 4pt Spacing Grid

Use strictly modular 4pt spacing tokens for paddings, margins, and gaps:

```python
theme.spacing.xs    # 4pt
theme.spacing.sm    # 8pt
theme.spacing.md    # 12pt
theme.spacing.base  # 16pt
theme.spacing.lg    # 20pt
theme.spacing.xl    # 24pt
theme.spacing.xxl   # 28pt
theme.spacing.xxxl  # 32pt
theme.spacing.g40   # 40pt
theme.spacing.g48   # 48pt
theme.spacing.g64   # 64pt
```

---

## 6. Continuous-Corner Radii

Continuous squircle curvature replicating macOS Sequoia:

```python
theme.radii.sm    # 6px   — micro controls, subagent tags, inline chips
theme.radii.md    # 10px  — cards, source list selection capsules, inputs
theme.radii.lg    # 14px  — grouped section containers, popovers
theme.radii.xl    # 20px  — modal dialogs, hero stages, prominent sheets
theme.radii.pill  # 9999px — search capsules, omni-bar, status pills
```

---

## 7. Layered Elevation (Physical Shadows, Never Glows)

macOS Sequoia utilizes physical light diffusion rather than sci-fi neon glows:

```python
# Low: Standard cards, resting list items
card.setGraphicsEffect(theme.shadow_effect(theme.elevation.low, parent=card))

# Medium: Hovered cards, dropdown popovers
popover.setGraphicsEffect(theme.shadow_effect(theme.elevation.medium, parent=popover))

# High: Floating Island, modal dialogs
dialog.setGraphicsEffect(theme.shadow_effect(theme.elevation.high, parent=dialog))
```

---

## 8. Automatic System Appearance Switching

```python
# Automatic system mode (tracks OS Dark/Light mode in real-time)
theme.set_mode("system")

# Manual overrides
theme.set_mode("dark")
theme.set_mode("light")

# Toggle on hotkey [F7] or button click
theme.toggle_mode()

# Listen to theme changes
theme.theme_changed.connect(lambda mode: print(f"Theme switched to {mode}"))
```
