"""
core/macos_settings_view.py — macOS Sequoia / Sonoma Style System Settings Window.

Senior Design Engineering Specification (Phase 5):
1. Architecture:
   - macOS System Settings layout: Left Sidebar (210px) + Right Grouped Inset Content Area.
   - Grouped Inset Cards: 10px continuous corner radius (theme.radii.md), controlBackground fill,
     1px separator border, divided rows.
2. Row Items:
   - Left: Rounded icon badge + Title (Headline 13) + Subtitle (Caption 10).
   - Right: Interactive controls (MacOSToggle, MacOSSegmentedControl, MacOSButton, or disclosure Chevron).
3. Live Configurations:
   - General (Startup, Active Profile, Sound effects).
   - Intelligence & Models (Engine pipeline, temperature, context memory).
   - Voice & Speech (Microphone device, ElevenLabs / Live stream, voice speed).
   - Spatial Vision (Gesture sentry, MediaPipe optical tracking).
   - Appearance & Motion (Dark/Light mode, Accent color palette, prefers-reduced-motion).
   - Shortcuts & Spotlight (Global chord, push-to-talk trigger).
"""
from __future__ import annotations

from typing import Optional, List, Callable, Union

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QIcon
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QScrollArea, QLineEdit
)

from core.theme_provider import theme
from core.macos_components import (
    MacOSButton,
    MacOSSegmentedControl,
    MacOSToggle,
    MacOSTextField,
    MacOSSearchField,
    MacOSScrollArea,
    render_lucide_icon,
)
from core.macos_motion import motion, SpringPresets


class MacOSSettingsRow(QFrame):
    """
    Single row inside a macOS Grouped Inset List card.
    Contains icon badge, title, subtitle, and an interactive right-hand control.
    """
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon_name: Optional[str] = None,
        icon_bg: Optional[str] = None,
        control_widget: Optional[QWidget] = None,
        has_disclosure: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setFixedHeight(50)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(12)

        # Optional Icon Container
        if icon_name:
            bg_col = icon_bg or theme.accent_color
            icon_box = QFrame(self)
            icon_box.setFixedSize(26, 26)
            icon_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_col};
                    border-radius: 6px;
                }}
            """)
            ib_lay = QVBoxLayout(icon_box)
            ib_lay.setContentsMargins(0, 0, 0, 0)
            ib_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_ic = QLabel(icon_box)
            lbl_ic.setPixmap(render_lucide_icon(icon_name, color="#FFFFFF", size=15))
            ib_lay.addWidget(lbl_ic)
            lay.addWidget(icon_box)

        # Title & Subtitle column
        v_box = QVBoxLayout()
        v_box.setContentsMargins(0, 2, 0, 2)
        v_box.setSpacing(1)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setFont(theme.font(theme.typography.headline))
        self.lbl_title.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        v_box.addWidget(self.lbl_title)

        if subtitle:
            self.lbl_sub = QLabel(subtitle, self)
            self.lbl_sub.setFont(theme.font(theme.typography.caption_1))
            self.lbl_sub.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
            v_box.addWidget(self.lbl_sub)

        lay.addLayout(v_box, stretch=1)

        # Control Widget on Right
        if control_widget:
            lay.addWidget(control_widget, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if has_disclosure:
            disc_lbl = QLabel(self)
            disc_lbl.setPixmap(render_lucide_icon("chevron-right", color=theme.colors.labelTertiary, size=14))
            lay.addWidget(disc_lbl)

        self.setStyleSheet("background: transparent; border: none;")


class MacOSSettingsGroup(QFrame):
    """
    Apple Grouped Inset List Container.
    Features 10px continuous radius, controlBackground, and 1px dividers between rows.
    """
    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title = title

        self._rows: List[MacOSSettingsRow] = []

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)

        self._apply_style()
        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        r = theme.radii.md
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)

    def add_row(self, row: MacOSSettingsRow) -> None:
        if self._rows:
            # Add 1px divider between rows
            div = QFrame(self)
            div.setFixedHeight(1)
            div.setStyleSheet(f"background-color: {theme.colors.separator}; margin-left: 48px; border: none;")
            self.lay.addWidget(div)

        self.lay.addWidget(row)
        self._rows.append(row)


class MacOSSettingsView(QWidget):
    """
    Complete macOS Sequoia Style System Settings Window.
    Sidebar of categories + Grouped Inset Lists content area.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("macOSSettingsView")

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── 1. Left Sidebar (210px) ──────────────────────────────────────────
        self.sidebar_frame = QFrame(self)
        self.sidebar_frame.setFixedWidth(210)
        self.sidebar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-right: 1px solid {theme.colors.separator};
            }}
        """)

        sb_lay = QVBoxLayout(self.sidebar_frame)
        sb_lay.setContentsMargins(10, 14, 10, 14)
        sb_lay.setSpacing(8)

        # Search field
        self.search_field = MacOSSearchField("Search Settings", parent=self.sidebar_frame)
        sb_lay.addWidget(self.search_field)

        # Categories List
        self.category_list = QVBoxLayout()
        self.category_list.setSpacing(2)
        sb_lay.addLayout(self.category_list)
        sb_lay.addStretch()

        root_lay.addWidget(self.sidebar_frame)

        # ── 2. Right Content Scroll Area ─────────────────────────────────────
        self.scroll_area = MacOSScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        root_lay.addWidget(self.scroll_area, stretch=1)

        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        self.content_lay = QVBoxLayout(self.content_widget)
        self.content_lay.setContentsMargins(28, 24, 28, 36)
        self.content_lay.setSpacing(20)

        # Initialize Categories & Views
        self._category_buttons: List[QPushButton] = []
        self._active_category = "General"

        self._build_sidebar_items()
        self._show_category("General")

        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        self.sidebar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-right: 1px solid {theme.colors.separator};
            }}
        """)
        self._highlight_active_button()

    def _build_sidebar_items(self):
        categories = [
            ("General", "sliders", "#0A84FF"),
            ("Intelligence & Models", "cpu", "#BF5AF2"),
            ("Voice & Audio", "message-square", "#30D158"),
            ("Spatial Vision", "eye", "#FF9F0A"),
            ("Appearance & Motion", "sun", "#0A84FF"),
            ("Shortcuts & Spotlight", "terminal", "#FF453A"),
        ]

        for name, icon, col in categories:
            btn = QPushButton(f"  {name}", self.sidebar_frame)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(theme.font(theme.typography.body))
            btn.setIcon(QIcon(render_lucide_icon(icon, color=theme.colors.labelSecondary, size=15)))
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 8px;
                    border: none;
                    border-radius: {theme.radii.sm}px;
                    color: {theme.colors.labelPrimary};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: {theme.colors.cardBackgroundHover};
                }}
            """)
            btn.clicked.connect(lambda ch, n=name: self._show_category(n))
            self.category_list.addWidget(btn)
            self._category_buttons.append(btn)

    def _highlight_active_button(self):
        for btn in self._category_buttons:
            if btn.text().strip() == self._active_category:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding-left: 8px;
                        border: none;
                        border-radius: {theme.radii.sm}px;
                        color: #FFFFFF;
                        background-color: {theme.accent_color};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding-left: 8px;
                        border: none;
                        border-radius: {theme.radii.sm}px;
                        color: {theme.colors.labelPrimary};
                        background: transparent;
                    }}
                    QPushButton:hover {{
                        background-color: {theme.colors.cardBackgroundHover};
                    }}
                """)

    def _show_category(self, name: str):
        self._active_category = name
        self._highlight_active_button()

        # Clear existing content
        while self.content_lay.count():
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Header Title
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(2)

        t_lbl = QLabel(name, self.content_widget)
        t_lbl.setFont(theme.font(theme.typography.title_1))
        t_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        hdr_box.addWidget(t_lbl)

        sub_desc = {
            "General": "System preferences, default runtime configurations, and startup behavior.",
            "Intelligence & Models": "Autonomous reasoning engine models, temperature, and context length.",
            "Voice & Audio": "Live speech synthesis, audio input sampling, and real-time streaming.",
            "Spatial Vision": "Realtime optical sentinel, OpenCV tracking, and gesture recognition.",
            "Appearance & Motion": "Interface theme mode, accent palette, and CoreAnimation spring physics.",
            "Shortcuts & Spotlight": "Global keyboard summon chords, push-to-talk keys, and hotkey listeners.",
        }

        s_lbl = QLabel(sub_desc.get(name, ""), self.content_widget)
        s_lbl.setFont(theme.font(theme.typography.callout))
        s_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
        hdr_box.addWidget(s_lbl)

        self.content_lay.addLayout(hdr_box)

        # Render Grouped Inset Lists based on category
        if name == "General":
            self._render_general_section()
        elif name == "Appearance & Motion":
            self._render_appearance_section()
        elif name == "Intelligence & Models":
            self._render_models_section()
        elif name == "Voice & Audio":
            self._render_voice_section()
        elif name == "Spatial Vision":
            self._render_vision_section()
        else:
            self._render_shortcuts_section()

        self.content_lay.addStretch()

    # ── Grouped Inset Sections ───────────────────────────────────────────────

    def _render_general_section(self):
        group = MacOSSettingsGroup("General Preferences", self.content_widget)

        t_startup = MacOSToggle(checked=True)
        r1 = MacOSSettingsRow("Launch at Login", "Automatically start NEO assistant background engine on system boot", "sliders", "#0A84FF", t_startup)
        group.add_row(r1)

        t_sounds = MacOSToggle(checked=True)
        r2 = MacOSSettingsRow("System Sound Effects", "Play subtle tactile Apple audio cues for actions and alerts", "bell", "#FF9F0A", t_sounds)
        group.add_row(r2)

        seg_mode = MacOSSegmentedControl(["Balanced", "Performance", "Stealth"])
        r3 = MacOSSettingsRow("System Performance Profile", "Dynamically adjust background subagent thread limits", "cpu", "#30D158", seg_mode)
        group.add_row(r3)

        self.content_lay.addWidget(group)

    def _render_appearance_section(self):
        group = MacOSSettingsGroup("Appearance & Motion", self.content_widget)

        # Dark / Light Mode Segmented Control
        mode_idx = 0 if theme.is_dark else 1
        seg_theme = MacOSSegmentedControl(["Dark", "Light"], selected_index=mode_idx)
        seg_theme.selection_changed.connect(lambda i: theme.set_dark_mode(i == 0))
        r1 = MacOSSettingsRow("Appearance Mode", "Select interface appearance or sync with system setting", "sun", "#FFD60A", seg_theme)
        group.add_row(r1)

        # prefers-reduced-motion Switch
        t_motion = MacOSToggle(checked=motion.is_reduced_motion())
        t_motion.toggled.connect(motion.set_reduced_motion)
        r2 = MacOSSettingsRow("Reduce Motion", "Swap Apple spring physics to simple 100ms fades", "sliders", "#BF5AF2", t_motion)
        group.add_row(r2)

        self.content_lay.addWidget(group)

        # Accent Palette Group
        acc_group = MacOSSettingsGroup("Accent Color Palette", self.content_widget)
        acc_row = QHBoxLayout()
        acc_row.setSpacing(8)
        accents = [
            ("Blue", "blue", "#0A84FF"),
            ("Purple", "purple", "#BF5AF2"),
            ("Pink", "pink", "#FF375F"),
            ("Red", "red", "#FF453A"),
            ("Orange", "orange", "#FF9F0A"),
            ("Green", "green", "#30D158"),
            ("Graphite", "graphite", "#8E8E93"),
        ]
        for name, key, hex_v in accents:
            b = QPushButton(self.content_widget)
            b.setFixedSize(22, 22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"{name} Accent")
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_v};
                    border: 2px solid rgba(255, 255, 255, 0.4);
                    border-radius: 11px;
                }}
                QPushButton:hover {{ border: 2px solid #FFFFFF; }}
            """)
            b.clicked.connect(lambda ch, k=key: theme.set_accent(k))
            acc_row.addWidget(b)
        acc_row.addStretch()

        acc_container = QWidget()
        acc_container.setLayout(acc_row)
        r_acc = MacOSSettingsRow("Accent Highlight", "Tint buttons, focus halos, waveforms, and selections", "eye", "#0A84FF", acc_container)
        acc_group.add_row(r_acc)
        self.content_lay.addWidget(acc_group)

    def _render_models_section(self):
        group = MacOSSettingsGroup("Intelligence Pipeline", self.content_widget)

        seg_engine = MacOSSegmentedControl(["Gemini 3.1 Live", "GPT-4o Pro", "Local Ollama"])
        r1 = MacOSSettingsRow("Primary Engine", "Default multi-modal reasoning pipeline for live voice and vision", "cpu", "#BF5AF2", seg_engine)
        group.add_row(r1)

        t_swarm = MacOSToggle(checked=True)
        r2 = MacOSSettingsRow("Autonomous Subagent Swarm", "Permit background multi-agent task execution and self-healing", "terminal", "#0A84FF", t_swarm)
        group.add_row(r2)

        self.content_lay.addWidget(group)

    def _render_voice_section(self):
        group = MacOSSettingsGroup("Audio Pipeline", self.content_widget)

        t_echo = MacOSToggle(checked=True)
        r1 = MacOSSettingsRow("Acoustic Echo Cancellation", "Filter speaker output from microphone input in real-time", "sliders", "#30D158", t_echo)
        group.add_row(r1)

        t_stream = MacOSToggle(checked=True)
        r2 = MacOSSettingsRow("Low-Latency WebSocket Audio", "16kHz bi-directional live audio stream with <260ms response", "message-square", "#0A84FF", t_stream)
        group.add_row(r2)

        self.content_lay.addWidget(group)

    def _render_vision_section(self):
        group = MacOSSettingsGroup("Vision Watchdog", self.content_widget)

        t_gesture = MacOSToggle(checked=True)
        r1 = MacOSSettingsRow("MediaPipe Hand Gestures", "Pinch, thumbs-up, wave, and optical tracking triggers", "eye", "#FF9F0A", t_gesture)
        group.add_row(r1)

        t_screen = MacOSToggle(checked=False)
        r2 = MacOSSettingsRow("Continuous Screen Sentinel", "Periodic visual desktop analysis for proactive assistance", "shield", "#FF453A", t_screen)
        group.add_row(r2)

        self.content_lay.addWidget(group)

    def _render_shortcuts_section(self):
        group = MacOSSettingsGroup("Global Hotkeys", self.content_widget)

        btn_chord = MacOSButton("Ctrl + Space", variant="secondary")
        r1 = MacOSSettingsRow("Summon Spotlight Command Bar", "Global system-wide hotkey to summon assistant bar", "search", "#0A84FF", btn_chord)
        group.add_row(r1)

        btn_ptt = MacOSButton("Hold Ctrl", variant="secondary")
        r2 = MacOSSettingsRow("Push-to-Talk Hotkey", "Hold key to stream voice without wake-word requirement", "message-square", "#30D158", btn_ptt)
        group.add_row(r2)

        self.content_lay.addWidget(group)
