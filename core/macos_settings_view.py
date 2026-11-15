"""
core/macos_settings_view.py — macOS Sequoia / Sonoma Style System Settings Window.

Refined Architecture & Design Engineering Specification:
1. QStackedWidget Multi-Page Framework:
   - Each settings category lives on a dedicated, pre-built page.
   - Eliminates layout reconstruction, dangling layout items, and overlapping ghost labels.
2. Responsive Apple Grouped Inset Cards:
   - Dynamic vertical and horizontal layouts.
   - Input rows (API keys, project tokens) use full-width action cards so titles never wrap into 1 word per line.
   - Compact button labels and segmented controls so buttons are never cut off.
3. Clean macOS Typography & Mnemonic Protection:
   - Button text escapes ampersands (&&) to prevent unwanted accelerator underlines (_M, _A, etc.).
4. Real Live Backend Synchronization:
   - Full bidirectional connection to `config/api_keys.json` and `key_rotator`.
   - Live failover key cards with Active, Cooling, and Ready indicators.
"""
from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QLineEdit, QStackedWidget
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
from core.macos_motion import motion
from core.neo_key_rotator import key_rotator

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _BASE_DIR / "config" / "api_keys.json"


def _load_settings_config() -> Dict[str, Any]:
    """Reads current config from config/api_keys.json."""
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_settings_config(patch: Dict[str, Any]) -> None:
    """Updates config/api_keys.json with the given key/value pairs."""
    try:
        cfg = _load_settings_config()
        cfg.update(patch)
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Settings] Error saving config: {e}")


def _is_autostart_active() -> bool:
    """Checks if NEO autostart at login is enabled on Windows."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        val, _ = winreg.QueryValueEx(key, "NEO")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def _set_autostart_active(enabled: bool) -> None:
    """Enables or disables NEO autostart at login via Windows Registry."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enabled:
            exe = sys.executable
            main_script = str(_BASE_DIR / "main.py")
            cmd = f'"{exe}" "{main_script}"'
            winreg.SetValueEx(key, "NEO", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "NEO")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Settings] Autostart error: {e}")


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
        min_height: int = 46,
    ):
        super().__init__(parent)
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
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
        v_box.setContentsMargins(0, 1, 0, 1)
        v_box.setSpacing(2)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setFont(theme.font(theme.typography.headline))
        self.lbl_title.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        self.lbl_title.setWordWrap(False)
        v_box.addWidget(self.lbl_title)

        if subtitle:
            self.lbl_sub = QLabel(subtitle, self)
            self.lbl_sub.setFont(theme.font(theme.typography.caption_1))
            self.lbl_sub.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
            self.lbl_sub.setWordWrap(True)
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
        self._rows: List[QWidget] = []

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

    def add_row(self, row: QWidget) -> None:
        if self._rows:
            div = QFrame(self)
            div.setFixedHeight(1)
            div.setStyleSheet(f"background-color: {theme.colors.separator}; margin-left: 48px; border: none;")
            self.lay.addWidget(div)
        self.lay.addWidget(row)
        self._rows.append(row)


class MacOSKeyInputCard(QFrame):
    """
    Dedicated responsive card for Primary API Key and Add Backup Key.
    Vertically stacks title and full-width input controls so labels never wrap into 1 word per line.
    """
    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_name: str = "cpu",
        icon_bg: str = "#BF5AF2",
        placeholder: str = "Paste Gemini API Key (AIzaSy... / AQ.Ab8...)",
        action_btn_text: str = "Save Key",
        action_btn_variant: str = "default",
        status_text: str = "",
        status_color: str = "#30D158",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        r = theme.radii.md
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.controlBackground};
                border: 1px solid {theme.colors.separator};
                border-radius: {r}px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # Header: Icon + Title + Status Badge
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_box = QFrame(self)
        icon_box.setFixedSize(26, 26)
        icon_box.setStyleSheet(f"background-color: {icon_bg}; border-radius: 6px;")
        ib_lay = QVBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ic = QLabel(icon_box)
        lbl_ic.setPixmap(render_lucide_icon(icon_name, color="#FFFFFF", size=15))
        ib_lay.addWidget(lbl_ic)
        hdr.addWidget(icon_box)

        lbl_t = QLabel(title, self)
        lbl_t.setFont(theme.font(theme.typography.headline))
        lbl_t.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        hdr.addWidget(lbl_t)
        hdr.addStretch(1)

        self.lbl_status = QLabel(status_text, self)
        self.lbl_status.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        self.lbl_status.setStyleSheet(f"color: {status_color}; background: transparent; border: none;")
        self.lbl_status.setVisible(bool(status_text))
        hdr.addWidget(self.lbl_status)
        lay.addLayout(hdr)

        # Subtitle
        if subtitle:
            lbl_s = QLabel(subtitle, self)
            lbl_s.setFont(theme.font(theme.typography.caption_1))
            lbl_s.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
            lbl_s.setWordWrap(True)
            lay.addWidget(lbl_s)

        # Action Input Row: [ Input (stretch=1) ] [ Eye ] [ Button ]
        inp_row = QHBoxLayout()
        inp_row.setSpacing(6)

        self.input_field = MacOSTextField(placeholder=placeholder, parent=self)
        self.input_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        inp_row.addWidget(self.input_field, stretch=1)

        self.btn_eye = MacOSButton("", variant="secondary", parent=self)
        self.btn_eye.setFixedSize(28, 28)
        self.btn_eye.setIcon(QIcon(render_lucide_icon("eye", color=theme.colors.labelSecondary, size=14)))
        self.btn_eye.setToolTip("Show / Hide Key")
        def _toggle_eye():
            mode = self.input_field.echoMode()
            self.input_field.setEchoMode(
                QLineEdit.EchoMode.Normal if mode == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password
            )
        self.btn_eye.clicked.connect(_toggle_eye)
        inp_row.addWidget(self.btn_eye)

        self.btn_action = MacOSButton(action_btn_text, variant=action_btn_variant, parent=self)
        self.btn_action.setFixedHeight(28)
        inp_row.addWidget(self.btn_action)

        lay.addLayout(inp_row)


class MacOSKeyPoolCard(QFrame):
    """Card representing one key in the Multi-Project failover pool."""
    set_active_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    def __init__(
        self,
        index: int,
        masked: str,
        is_active: bool,
        is_cooling: bool,
        cooldown_remaining_sec: int,
        can_remove: bool,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.index = index
        self.setMinimumHeight(42)
        r = theme.radii.sm
        active_border = "rgba(48, 209, 88, 0.45)" if is_active else theme.colors.separator
        bg = "rgba(48, 209, 88, 0.08)" if is_active else "rgba(255, 255, 255, 0.02)"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {active_border};
                border-radius: {r}px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)

        # Index badge
        idx_lbl = QLabel(f"#{index}")
        idx_lbl.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        idx_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary};")
        lay.addWidget(idx_lbl)

        # Masked key
        key_lbl = QLabel(masked)
        key_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Medium))
        key_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary};")
        lay.addWidget(key_lbl)

        # Status badge
        if is_active:
            st_lbl = QLabel("🟢 ACTIVE")
            st_lbl.setFont(theme.font(theme.typography.caption_2, weight_override=QFont.Weight.Bold))
            st_lbl.setStyleSheet("color: #30D158;")
        elif is_cooling:
            mins = max(1, cooldown_remaining_sec // 60)
            st_lbl = QLabel(f"⏳ COOLING ({mins}m)")
            st_lbl.setFont(theme.font(theme.typography.caption_2, weight_override=QFont.Weight.Bold))
            st_lbl.setStyleSheet("color: #FF9F0A;")
        else:
            st_lbl = QLabel("⚪ READY")
            st_lbl.setFont(theme.font(theme.typography.caption_2))
            st_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary};")
        lay.addWidget(st_lbl)

        lay.addStretch(1)

        # Actions
        if not is_active:
            btn_act = MacOSButton("Set Active", variant="secondary")
            btn_act.setFixedHeight(24)
            btn_act.clicked.connect(lambda: self.set_active_requested.emit(self.index - 1))
            lay.addWidget(btn_act)

        if can_remove:
            btn_del = MacOSButton("✕", variant="destructive")
            btn_del.setFixedSize(24, 24)
            btn_del.setToolTip("Remove key from failover pool")
            btn_del.clicked.connect(lambda: self.remove_requested.emit(self.index - 1))
            lay.addWidget(btn_del)


class MacOSSettingsView(QWidget):
    """
    Complete macOS Sequoia Style System Settings Window.
    Uses QStackedWidget for glitch-free page switching and responsive card layouts.
    """
    recalibrate_requested = pyqtSignal()

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

        # Search field with real-time category filtering
        self.search_field = MacOSSearchField("Search Settings", parent=self.sidebar_frame)
        self.search_field.text_changed.connect(self._on_search_text_changed)
        self.search_field.cleared.connect(self._on_search_cleared)
        sb_lay.addWidget(self.search_field)

        # Categories List
        self.category_list = QVBoxLayout()
        self.category_list.setSpacing(2)
        sb_lay.addLayout(self.category_list)
        sb_lay.addStretch()

        root_lay.addWidget(self.sidebar_frame)

        # ── 2. Right Content Scroll Area & Stacked Pages ─────────────────────
        self.scroll_area = MacOSScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        root_lay.addWidget(self.scroll_area, stretch=1)

        self.content_container = QWidget()
        self.scroll_area.setWidget(self.content_container)

        self.main_content_lay = QVBoxLayout(self.content_container)
        self.main_content_lay.setContentsMargins(22, 18, 22, 28)
        self.main_content_lay.setSpacing(10)

        # Banner for status / feedback notifications
        self._banner_lbl = QLabel(self.content_container)
        self._banner_lbl.setVisible(False)
        self._banner_lbl.setWordWrap(True)
        self.main_content_lay.addWidget(self._banner_lbl)

        # QStackedWidget hosts each category on its own page
        self.stack = QStackedWidget(self.content_container)
        self.main_content_lay.addWidget(self.stack)

        self._category_buttons: List[QPushButton] = []
        self._categories_meta: List[Dict[str, Any]] = [
            {
                "id": "Intelligence & Models",
                "label": "Intelligence & Models",
                "icon": "cpu",
                "color": "#BF5AF2",
                "desc": "Autonomous reasoning engine models, Google AI Studio API keys, failover pool, and behavioral directives.",
                "keywords": ["api", "key", "pool", "gemini", "model", "quota", "rotator", "personality", "intelligence", "swarm"],
            },
            {
                "id": "Voice & Audio",
                "label": "Voice & Audio",
                "icon": "message-square",
                "color": "#30D158",
                "desc": "Live speech synthesis voice, proactive audio alerts, push-to-talk mode, and audio device routing.",
                "keywords": ["voice", "audio", "mic", "microphone", "speaker", "push to talk", "sound", "sfx", "aoede", "puck"],
            },
            {
                "id": "General & Profile",
                "label": "General & Profile",
                "icon": "sliders",
                "color": "#0A84FF",
                "desc": "Operator identity, assistant call-sign, autostart at login, morning briefing, and calibration wizard.",
                "keywords": ["general", "profile", "name", "operator", "assistant", "autostart", "login", "briefing", "calibrate", "wizard"],
            },
            {
                "id": "Spatial Vision",
                "label": "Spatial Vision",
                "icon": "eye",
                "color": "#FF9F0A",
                "desc": "Realtime optical sentinel, MediaPipe gesture triggers, desktop screen sentinel, and presence lock.",
                "keywords": ["vision", "camera", "gesture", "mediapipe", "screen", "sentinel", "presence", "lock"],
            },
            {
                "id": "Appearance & Motion",
                "label": "Appearance & Motion",
                "icon": "sun",
                "color": "#FFD60A",
                "desc": "Interface theme appearance (Dark / Light), accent color palette, and CoreAnimation spring physics.",
                "keywords": ["appearance", "theme", "dark", "light", "accent", "color", "motion", "spring", "animation"],
            },
            {
                "id": "Shortcuts & Hotkeys",
                "label": "Shortcuts & Hotkeys",
                "icon": "terminal",
                "color": "#FF453A",
                "desc": "Global keyboard summon chords, push-to-talk keys, instant mute hotkey, and shortcut listeners.",
                "keywords": ["shortcuts", "hotkeys", "chord", "spotlight", "mute", "keyboard", "f4", "f7", "ctrl"],
            },
        ]

        self._active_category = "General & Profile"
        self._pages: Dict[str, QWidget] = {}

        self._build_sidebar_items()
        self._build_all_pages()
        self._show_category("General & Profile")

        theme.theme_changed.connect(self._apply_style)

    def _apply_style(self):
        self.sidebar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.colors.sidebar};
                border-right: 1px solid {theme.colors.separator};
            }}
        """)
        self._highlight_active_button()

    def _show_banner(self, message: str, is_error: bool = False):
        """Displays a clean status banner that auto-hides after 4 seconds."""
        color = "#EF4444" if is_error else "#30D158"
        bg = "rgba(239, 68, 68, 0.12)" if is_error else "rgba(48, 209, 88, 0.12)"
        border = "rgba(239, 68, 68, 0.35)" if is_error else "rgba(48, 209, 88, 0.35)"
        self._banner_lbl.setText(message)
        self._banner_lbl.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        self._banner_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 8px 14px;
            }}
        """)
        self._banner_lbl.setVisible(True)
        QTimer.singleShot(4000, lambda: self._banner_lbl.setVisible(False))

    def _build_sidebar_items(self):
        for meta in self._categories_meta:
            cat_id = meta["id"]
            # Double ampersand escapes mnemonic accelerator underline in Qt
            btn_title = f" {meta['label'].replace('&', '&&')}"
            btn = QPushButton(btn_title, self.sidebar_frame)
            btn.setProperty("category_id", cat_id)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(theme.font(theme.typography.callout))
            btn.setIcon(QIcon(render_lucide_icon(meta["icon"], color=theme.colors.labelSecondary, size=15)))
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 6px;
                    border: none;
                    border-radius: {theme.radii.sm}px;
                    color: {theme.colors.labelPrimary};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: {theme.colors.cardBackgroundHover};
                }}
            """)
            btn.clicked.connect(lambda ch, cid=cat_id: self._show_category(cid))
            self.category_list.addWidget(btn)
            self._category_buttons.append(btn)

    def _highlight_active_button(self):
        for btn in self._category_buttons:
            cat_id = btn.property("category_id")
            if cat_id == self._active_category or (
                self._active_category in ("General", "General & Profile") and "General" in str(cat_id)
            ) or (
                self._active_category in ("Intelligence & Models", "Intelligence") and "Intelligence" in str(cat_id)
            ):
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding-left: 6px;
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
                        padding-left: 6px;
                        border: none;
                        border-radius: {theme.radii.sm}px;
                        color: {theme.colors.labelPrimary};
                        background: transparent;
                    }}
                    QPushButton:hover {{
                        background-color: {theme.colors.cardBackgroundHover};
                    }}
                """)

    def _on_search_text_changed(self, text: str):
        query = text.strip().lower()
        if not query:
            for btn in self._category_buttons:
                btn.setVisible(True)
            return

        matched_category = None
        for i, meta in enumerate(self._categories_meta):
            btn = self._category_buttons[i]
            match = (
                query in meta["id"].lower()
                or query in meta["label"].lower()
                or query in meta["desc"].lower()
                or any(query in kw for kw in meta["keywords"])
            )
            btn.setVisible(match)
            if match and matched_category is None:
                matched_category = meta["id"]

        if matched_category and matched_category != self._active_category:
            self._show_category(matched_category)

    def _on_search_cleared(self):
        for btn in self._category_buttons:
            btn.setVisible(True)

    def _create_section_title(self, text: str, parent: QWidget) -> QLabel:
        lbl = QLabel(text.upper(), parent)
        lbl.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none; margin-top: 10px; margin-bottom: 2px;")
        return lbl

    def _create_page_header(self, title: str, desc: str, parent: QWidget) -> QVBoxLayout:
        hdr = QVBoxLayout()
        hdr.setSpacing(2)
        t_lbl = QLabel(title, parent)
        t_lbl.setFont(theme.font(theme.typography.title_1))
        t_lbl.setStyleSheet(f"color: {theme.colors.labelPrimary}; background: transparent; border: none;")
        hdr.addWidget(t_lbl)

        if desc:
            s_lbl = QLabel(desc, parent)
            s_lbl.setFont(theme.font(theme.typography.callout))
            s_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary}; background: transparent; border: none;")
            s_lbl.setWordWrap(True)
            hdr.addWidget(s_lbl)
        return hdr

    # ── Page Construction (One Time, Glitch-Free) ────────────────────────────

    def _build_all_pages(self):
        self._pages["Intelligence & Models"] = self._build_intelligence_page()
        self._pages["Voice & Audio"] = self._build_voice_page()
        self._pages["General & Profile"] = self._build_general_page()
        self._pages["Spatial Vision"] = self._build_vision_page()
        self._pages["Appearance & Motion"] = self._build_appearance_page()
        self._pages["Shortcuts & Hotkeys"] = self._build_shortcuts_page()

        for page in self._pages.values():
            self.stack.addWidget(page)

    def _build_intelligence_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "Intelligence & Models")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        cfg = _load_settings_config()

        # 1. Primary Active Key (Responsive Vertical Card)
        lay.addWidget(self._create_section_title("Active Gemini Neural API Key", page))
        active_k = key_rotator.get_active_key() or cfg.get("gemini_api_key", "")
        self._card_primary = MacOSKeyInputCard(
            title="Primary Project Key",
            subtitle="Active neural credentials for real-time speech, vision, and tool execution.",
            icon_name="cpu",
            icon_bg="#BF5AF2",
            placeholder="Paste Gemini API Key (AIzaSy... / AQ.Ab8...)",
            action_btn_text="Save Active Key",
            action_btn_variant="default",
            status_text="🟢 ACTIVE / PRIMARY",
            status_color="#30D158",
            parent=page,
        )
        self._card_primary.input_field.setText(active_k)
        self._card_primary.btn_action.clicked.connect(self._on_save_primary_key)
        lay.addWidget(self._card_primary)

        # AI Studio Link
        g_link = MacOSSettingsGroup("Google AI Studio", page)
        link_container = QWidget()
        l_lay = QHBoxLayout(link_container)
        l_lay.setContentsMargins(0, 0, 0, 0)
        btn_aistudio = MacOSButton("Open Google AI Studio ↗", variant="secondary")
        btn_aistudio.clicked.connect(lambda: webbrowser.open("https://aistudio.google.com/app/apikey"))
        l_lay.addWidget(btn_aistudio)

        r_link = MacOSSettingsRow(
            "Acquire Project API Keys",
            "Create free Google Cloud projects in AI Studio (1,500 req/day per project)",
            icon_name="search",
            icon_bg="#0A84FF",
            control_widget=link_container,
        )
        g_link.add_row(r_link)
        lay.addWidget(g_link)

        # 2. Multi-Key Failover Pool
        lay.addWidget(self._create_section_title("Multi-Project API Key Pool (Zero-Downtime Failover)", page))
        self._pool_group = MacOSSettingsGroup("Key Pool", page)
        self._refresh_pool_cards()
        lay.addWidget(self._pool_group)

        # Add Backup Key Card
        self._card_add_key = MacOSKeyInputCard(
            title="Add Backup Project Key",
            subtitle="When active key hits quota limit, NEO auto-rotates to standby keys in 0ms.",
            icon_name="sliders",
            icon_bg="#30D158",
            placeholder="Paste backup Gemini Key from Project 2...",
            action_btn_text="+ Add to Pool",
            action_btn_variant="secondary",
            parent=page,
        )
        self._card_add_key.btn_action.clicked.connect(self._on_add_backup_key)
        lay.addWidget(self._card_add_key)

        # 3. Reasoning Engine Mode & Personality
        lay.addWidget(self._create_section_title("Reasoning Pipeline & Personality", page))
        g_engine = MacOSSettingsGroup("Engine Configuration", page)

        curr_model = cfg.get("chat_model_mode", "models/gemini-2.5-flash-native-audio-latest")
        model_idx = 1 if "3.1" in curr_model else 0
        seg_model = MacOSSegmentedControl(
            ["Gemini 2.5 Live", "Gemini 3.1 Live"],
            selected_index=model_idx,
        )
        def _on_model_changed(idx: int):
            target = "models/gemini-3.1-flash-live-preview" if idx == 1 else "models/gemini-2.5-flash-native-audio-latest"
            _save_settings_config({"chat_model_mode": target})
            self._show_banner(f"✓ Reasoning pipeline set to: {'Gemini 3.1 Live' if idx == 1 else 'Gemini 2.5 Live (Recommended)'}")
        seg_model.selection_changed.connect(_on_model_changed)
        r_model = MacOSSettingsRow(
            "Live Audio/Vision Model",
            "Gemini 2.5 Native Audio offers <260ms latency and high quota",
            icon_name="cpu",
            icon_bg="#BF5AF2",
            control_widget=seg_model,
        )
        g_engine.add_row(r_model)

        personalities = ["Chill", "Tactical", "Co-Pilot", "Focus"]
        full_personas = ["Chill Companion", "Tactical Operator", "Brilliant Co-Pilot", "Hyper-Focus"]
        curr_persona = cfg.get("personality", "Chill Companion")
        p_idx = full_personas.index(curr_persona) if curr_persona in full_personas else 0
        seg_persona = MacOSSegmentedControl(personalities, selected_index=p_idx)
        def _on_persona_changed(idx: int):
            chosen = full_personas[idx]
            _save_settings_config({"personality": chosen})
            self._show_banner(f"✓ Behavioral matrix tuned to: {chosen}")
        seg_persona.selection_changed.connect(_on_persona_changed)
        r_persona = MacOSSettingsRow(
            "Personality Directives",
            "Conversational tone, prompt framing, and proactive guidance",
            icon_name="message-square",
            icon_bg="#0A84FF",
            control_widget=seg_persona,
        )
        g_engine.add_row(r_persona)

        t_swarm = MacOSToggle(checked=cfg.get("swarm_enabled", True))
        t_swarm.toggled.connect(lambda ch: _save_settings_config({"swarm_enabled": ch}))
        r_swarm = MacOSSettingsRow(
            "Autonomous Swarm",
            "Permit background multi-agent task execution and self-healing",
            icon_name="terminal",
            icon_bg="#30D158",
            control_widget=t_swarm,
        )
        g_engine.add_row(r_swarm)
        lay.addWidget(g_engine)

        lay.addStretch(1)
        return page

    def _build_voice_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "Voice & Audio")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        cfg = _load_settings_config()

        lay.addWidget(self._create_section_title("Speech Synthesis & Neural Voice", page))
        g_voice = MacOSSettingsGroup("Speech Synthesis", page)

        voices = ["Aoede", "Puck", "Charon", "Fenrir"]
        curr_voice = cfg.get("voice_name", "Aoede")
        v_idx = voices.index(curr_voice) if curr_voice in voices else 0
        seg_voice = MacOSSegmentedControl(voices, selected_index=v_idx)
        def _on_voice_changed(idx: int):
            chosen = voices[idx]
            _save_settings_config({"voice_name": chosen})
            self._show_banner(f"✓ Neural voice persona set to: {chosen}")
        seg_voice.selection_changed.connect(_on_voice_changed)
        r_voice = MacOSSettingsRow(
            "Live Voice Persona",
            "Gemini Live natural speech synthesis timbre (Aoede: Expressive, Puck: Dynamic)",
            icon_name="message-square",
            icon_bg="#30D158",
            control_widget=seg_voice,
        )
        g_voice.add_row(r_voice)

        t_proactive = MacOSToggle(checked=cfg.get("proactive_audio_enabled", True))
        def _on_proactive_toggle(ch: bool):
            _save_settings_config({"proactive_audio_enabled": ch, "proactive_audio": ch})
            self._show_banner(f"✓ Proactive audio alerts {'enabled' if ch else 'disabled'}")
        t_proactive.toggled.connect(_on_proactive_toggle)
        r_proactive = MacOSSettingsRow(
            "Proactive Audio Speech",
            "NEO speaks autonomously upon detecting urgent notifications or anomalies",
            icon_name="bell",
            icon_bg="#0A84FF",
            control_widget=t_proactive,
        )
        g_voice.add_row(r_proactive)

        t_ptt = MacOSToggle(checked=cfg.get("push_to_talk_enabled", False))
        def _on_ptt_toggle(ch: bool):
            _save_settings_config({"push_to_talk_enabled": ch})
            self._show_banner(f"✓ Push-to-Talk hotkey mode {'enabled (Hold Ctrl)' if ch else 'disabled'}")
        t_ptt.toggled.connect(_on_ptt_toggle)
        r_ptt = MacOSSettingsRow(
            "Push-to-Talk Mode",
            "Hold Ctrl key to stream voice instead of continuous open microphone",
            icon_name="sliders",
            icon_bg="#FF9F0A",
            control_widget=t_ptt,
        )
        g_voice.add_row(r_ptt)

        t_sfx = MacOSToggle(checked=cfg.get("stark_sfx_enabled", False))
        t_sfx.toggled.connect(lambda ch: _save_settings_config({"stark_sfx_enabled": ch}))
        r_sfx = MacOSSettingsRow(
            "Tactical Audio Effects",
            "Play acoustic feedback chimes for task transitions and sentry alerts",
            icon_name="sliders",
            icon_bg="#BF5AF2",
            control_widget=t_sfx,
        )
        g_voice.add_row(r_sfx)
        lay.addWidget(g_voice)

        # Hardware Routing Section
        lay.addWidget(self._create_section_title("Audio Hardware Routing", page))
        g_hw = MacOSSettingsGroup("Audio Devices", page)

        in_dev = cfg.get("input_device", "Default System Microphone")
        lbl_in = QLabel(in_dev)
        lbl_in.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        lbl_in.setStyleSheet(f"color: {theme.colors.labelSecondary};")
        r_in = MacOSSettingsRow("Input Microphone", "Active capture hardware", icon_name="message-square", icon_bg="#30D158", control_widget=lbl_in)
        g_hw.add_row(r_in)

        out_dev = cfg.get("output_device", "Default System Output")
        lbl_out = QLabel(out_dev)
        lbl_out.setFont(theme.font(theme.typography.caption_1, weight_override=QFont.Weight.Bold))
        lbl_out.setStyleSheet(f"color: {theme.colors.labelSecondary};")
        r_out = MacOSSettingsRow("Output Speaker / Headphones", "Active playback hardware", icon_name="bell", icon_bg="#0A84FF", control_widget=lbl_out)
        g_hw.add_row(r_out)

        t_echo = MacOSToggle(checked=True)
        r_echo = MacOSSettingsRow("Echo Cancellation", "Real-time speaker subtraction to prevent self-interruption", icon_name="sliders", icon_bg="#30D158", control_widget=t_echo)
        g_hw.add_row(r_echo)

        t_stream = MacOSToggle(checked=True)
        r_stream = MacOSSettingsRow("Low-Latency WebSocket Audio", "16kHz bi-directional live audio stream with <260ms response", icon_name="message-square", icon_bg="#0A84FF", control_widget=t_stream)
        g_hw.add_row(r_stream)
        lay.addWidget(g_hw)

        lay.addStretch(1)
        return page

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "General & Profile")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        cfg = _load_settings_config()

        lay.addWidget(self._create_section_title("Operator & Assistant Identity", page))
        g_profile = MacOSSettingsGroup("Identity", page)

        # Operator Name
        user_container = QWidget()
        u_lay = QHBoxLayout(user_container)
        u_lay.setContentsMargins(0, 0, 0, 0)
        u_lay.setSpacing(6)
        user_input = MacOSTextField(placeholder="Operator Name")
        user_input.setText(cfg.get("user_name", "Boss"))
        user_input.setFixedWidth(130)
        u_lay.addWidget(user_input)
        btn_save_u = MacOSButton("Save", variant="secondary")
        def _save_user():
            val = user_input.text().strip() or "Boss"
            _save_settings_config({"user_name": val})
            self._show_banner(f"✓ Operator name updated to: {val}")
        btn_save_u.clicked.connect(_save_user)
        u_lay.addWidget(btn_save_u)
        r_user = MacOSSettingsRow("Operator Name", "How NEO addresses you during voice and chat interactions", icon_name="sliders", icon_bg="#0A84FF", control_widget=user_container)
        g_profile.add_row(r_user)

        # Assistant Call-Sign
        asst_container = QWidget()
        a_lay = QHBoxLayout(asst_container)
        a_lay.setContentsMargins(0, 0, 0, 0)
        a_lay.setSpacing(6)
        asst_input = MacOSTextField(placeholder="Assistant Call-Sign")
        asst_input.setText(cfg.get("assistant_name", "NEO"))
        asst_input.setFixedWidth(130)
        a_lay.addWidget(asst_input)
        btn_save_a = MacOSButton("Save", variant="secondary")
        def _save_asst():
            val = asst_input.text().strip() or "NEO"
            _save_settings_config({"assistant_name": val})
            self._show_banner(f"✓ Assistant call-sign updated to: {val}")
        btn_save_a.clicked.connect(_save_asst)
        a_lay.addWidget(btn_save_a)
        r_asst = MacOSSettingsRow("Assistant Call-Sign", "Display name in title bar, HUD, and live telemetry", icon_name="cpu", icon_bg="#BF5AF2", control_widget=asst_container)
        g_profile.add_row(r_asst)
        lay.addWidget(g_profile)

        # Automation
        lay.addWidget(self._create_section_title("System Startup & Automation", page))
        g_auto = MacOSSettingsGroup("Automation", page)

        t_auto = MacOSToggle(checked=_is_autostart_active())
        def _on_auto_toggled(ch: bool):
            _set_autostart_active(ch)
            self._show_banner(f"✓ Autostart at login {'enabled' if ch else 'disabled'}")
        t_auto.toggled.connect(_on_auto_toggled)
        r_auto = MacOSSettingsRow("Launch at Login", "Automatically start NEO assistant background engine on system boot", "sliders", "#0A84FF", t_auto)
        g_auto.add_row(r_auto)

        t_brief = MacOSToggle(checked=cfg.get("morning_brief_enabled", True))
        def _on_brief_toggled(ch: bool):
            _save_settings_config({"morning_brief_enabled": ch})
            self._show_banner(f"✓ Morning intelligence briefing {'enabled' if ch else 'disabled'}")
        t_brief.toggled.connect(_on_brief_toggled)
        r_brief = MacOSSettingsRow("Morning Briefing", "Deliver daily agenda, weather, and priority briefing on first wake", "bell", "#FF9F0A", t_brief)
        g_auto.add_row(r_brief)

        seg_mode = MacOSSegmentedControl(["Balanced", "Max", "Stealth"])
        r_perf = MacOSSettingsRow("Performance Profile", "Dynamically adjust background subagent thread limits", "cpu", "#30D158", seg_mode)
        g_auto.add_row(r_perf)
        lay.addWidget(g_auto)

        # Onboarding Calibration Wizard
        lay.addWidget(self._create_section_title("Neural Calibration & Onboarding", page))
        g_wizard = MacOSSettingsGroup("Calibration Wizard", page)
        btn_wizard = MacOSButton("Re-calibrate...", variant="secondary")
        btn_wizard.clicked.connect(self.recalibrate_requested.emit)
        r_wiz = MacOSSettingsRow(
            "Neural Onboarding Calibration",
            "Re-run the initial 3-step setup to calibrate persona, goal, and system environment",
            icon_name="sliders",
            icon_bg="#BF5AF2",
            control_widget=btn_wizard,
        )
        g_wizard.add_row(r_wiz)
        lay.addWidget(g_wizard)

        lay.addStretch(1)
        return page

    def _build_vision_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "Spatial Vision")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        cfg = _load_settings_config()

        lay.addWidget(self._create_section_title("Optical Sentry & Real-time Vision", page))
        g_vision = MacOSSettingsGroup("Vision Sentry", page)

        t_gesture = MacOSToggle(checked=cfg.get("gesture_control_enabled", False))
        def _on_gesture_toggled(ch: bool):
            _save_settings_config({"gesture_control_enabled": ch})
            self._show_banner(f"✓ MediaPipe gesture recognition {'enabled' if ch else 'disabled'}")
        t_gesture.toggled.connect(_on_gesture_toggled)
        r_gest = MacOSSettingsRow("MediaPipe Hand Gestures", "Pinch, thumbs-up, wave, and optical tracking triggers", "eye", "#FF9F0A", t_gesture)
        g_vision.add_row(r_gest)

        t_presence = MacOSToggle(checked=cfg.get("presence_detection_enabled", False))
        def _on_presence_toggled(ch: bool):
            _save_settings_config({"presence_detection_enabled": ch})
            self._show_banner(f"✓ Operator presence detection {'enabled' if ch else 'disabled'}")
        t_presence.toggled.connect(_on_presence_toggled)
        r_pres = MacOSSettingsRow("Operator Presence Detection", "Continuously scan camera feed for operator arrival", "eye", "#30D158", t_presence)
        g_vision.add_row(r_pres)

        t_lock = MacOSToggle(checked=cfg.get("presence_auto_lock", False))
        def _on_lock_toggled(ch: bool):
            _save_settings_config({"presence_auto_lock": ch})
            self._show_banner(f"✓ Workstation auto-lock {'enabled' if ch else 'disabled'}")
        t_lock.toggled.connect(_on_lock_toggled)
        r_lock = MacOSSettingsRow("Presence Auto-Lock", "Automatically lock workstation or sleep HUD when operator steps away", "shield", "#FF453A", t_lock)
        g_vision.add_row(r_lock)

        t_screen = MacOSToggle(checked=cfg.get("screen_sentinel_enabled", False))
        def _on_screen_toggled(ch: bool):
            _save_settings_config({"screen_sentinel_enabled": ch})
            self._show_banner(f"✓ Continuous screen sentinel {'enabled' if ch else 'disabled'}")
        t_screen.toggled.connect(_on_screen_toggled)
        r_scr = MacOSSettingsRow("Continuous Screen Sentinel", "Periodic visual desktop analysis for proactive assistance", "shield", "#0A84FF", t_screen)
        g_vision.add_row(r_scr)

        lay.addWidget(g_vision)
        lay.addStretch(1)
        return page

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "Appearance & Motion")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        lay.addWidget(self._create_section_title("Interface Theme & Animations", page))
        group = MacOSSettingsGroup("Appearance & Motion", page)

        mode_idx = 0 if theme.is_dark else 1
        seg_theme = MacOSSegmentedControl(["Dark", "Light"], selected_index=mode_idx)
        seg_theme.selection_changed.connect(lambda i: theme.set_dark_mode(i == 0))
        r1 = MacOSSettingsRow("Appearance Mode", "Select interface appearance or sync with system setting", "sun", "#FFD60A", seg_theme)
        group.add_row(r1)

        t_motion = MacOSToggle(checked=motion.is_reduced_motion())
        t_motion.toggled.connect(motion.set_reduced_motion)
        r2 = MacOSSettingsRow("Reduce Motion", "Swap Apple spring physics to simple 100ms fades", "sliders", "#BF5AF2", t_motion)
        group.add_row(r2)
        lay.addWidget(group)

        # Accent Palette
        lay.addWidget(self._create_section_title("System Accent Palette", page))
        acc_group = MacOSSettingsGroup("Accent Color Palette", page)
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
            b = QPushButton(page)
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
            def _choose_accent(k=key, h=hex_v):
                theme.set_accent(k)
                _save_settings_config({"ui_color": h})
            b.clicked.connect(_choose_accent)
            acc_row.addWidget(b)
        acc_row.addStretch()

        acc_container = QWidget()
        acc_container.setLayout(acc_row)
        r_acc = MacOSSettingsRow("Accent Highlight", "Tint buttons, focus halos, waveforms, and selections", "eye", "#0A84FF", acc_container)
        acc_group.add_row(r_acc)
        lay.addWidget(acc_group)

        lay.addStretch(1)
        return page

    def _build_shortcuts_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        meta = next(m for m in self._categories_meta if m["id"] == "Shortcuts & Hotkeys")
        lay.addLayout(self._create_page_header(meta["label"], meta["desc"], page))

        lay.addWidget(self._create_section_title("Global Keyboard Chords", page))
        group = MacOSSettingsGroup("Global Hotkeys", page)

        btn_chord = MacOSButton("Ctrl + Space", variant="secondary")
        r1 = MacOSSettingsRow("Summon Spotlight Command Bar", "Global system-wide hotkey to summon assistant bar", "search", "#0A84FF", btn_chord)
        group.add_row(r1)

        btn_ptt = MacOSButton("Hold Ctrl", variant="secondary")
        r2 = MacOSSettingsRow("Push-to-Talk Hotkey", "Hold key to stream voice without wake-word requirement", "message-square", "#30D158", btn_ptt)
        group.add_row(r2)

        btn_mute = MacOSButton("F4", variant="secondary")
        r3 = MacOSSettingsRow("Instant Voice Mute Toggle", "Instantly silence microphone capture and audio playback", "bell", "#FF453A", btn_mute)
        group.add_row(r3)

        btn_thm = MacOSButton("F7", variant="secondary")
        r4 = MacOSSettingsRow("Toggle Light / Dark Appearance", "Instant theme toggle shortcut", "sun", "#FFD60A", btn_thm)
        group.add_row(r4)

        btn_side = MacOSButton("Ctrl + 1", variant="secondary")
        r5 = MacOSSettingsRow("Toggle Collapsible Sidebar", "Expand or collapse navigation sidebar", "terminal", "#BF5AF2", btn_side)
        group.add_row(r5)

        btn_esc = MacOSButton("Escape", variant="secondary")
        r6 = MacOSSettingsRow("Dismiss Active HUD / Dialog", "Close topmost overlay, Spotlight bar, or drawer", "sliders", "#8E8E93", btn_esc)
        group.add_row(r6)

        lay.addWidget(group)
        lay.addStretch(1)
        return page

    # ── Category Navigation & Pool Actions ───────────────────────────────────

    def _show_category(self, name: str):
        canonical = name
        for meta in self._categories_meta:
            if name == meta["id"] or name == meta["label"] or name in meta["label"] or name in meta["id"]:
                canonical = meta["id"]
                break

        self._active_category = canonical
        self._highlight_active_button()

        if canonical in self._pages:
            self.stack.setCurrentWidget(self._pages[canonical])
            if "Intelligence" in canonical:
                self._refresh_pool_cards()
                if hasattr(self, "_card_primary"):
                    self._card_primary.input_field.setText(key_rotator.get_active_key())

        self.scroll_area.verticalScrollBar().setValue(0)

    def _refresh_pool_cards(self):
        """Re-renders the list of keys in the failover pool."""
        while self._pool_group.lay.count():
            item = self._pool_group.lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._pool_group._rows.clear()

        status = key_rotator.get_status()
        keys_summary = status.get("keys", [])

        if not keys_summary:
            empty_lbl = QLabel("No backup keys in pool. Add an API key from a second Google Cloud project below.")
            empty_lbl.setFont(theme.font(theme.typography.caption_1))
            empty_lbl.setStyleSheet(f"color: {theme.colors.labelSecondary}; padding: 14px;")
            self._pool_group.add_row(empty_lbl)
            return

        can_remove = len(keys_summary) > 1
        for item in keys_summary:
            card = MacOSKeyPoolCard(
                index=item["index"],
                masked=item["masked"],
                is_active=item["is_active"],
                is_cooling=item["is_cooling"],
                cooldown_remaining_sec=item["cooldown_remaining_sec"],
                can_remove=can_remove,
                parent=self._pool_group,
            )
            card.set_active_requested.connect(self._on_set_active_key)
            card.remove_requested.connect(self._on_remove_key)
            self._pool_group.add_row(card)

    def _on_save_primary_key(self):
        key = self._card_primary.input_field.text().strip()
        if not key or len(key) < 15:
            self._show_banner("⚠️ Please enter a valid Gemini API Key (starts with AIzaSy... or AQ...)", is_error=True)
            return

        key_rotator.add_keys([key])
        keys = key_rotator.get_keys()
        if key in keys:
            key_rotator.set_active_index(keys.index(key))

        _save_settings_config({
            "gemini_api_key": key,
            "gemini_api_keys": keys,
        })
        self._refresh_pool_cards()
        self._show_banner("✓ Primary API key saved and activated in engine pool!")

    def _on_add_backup_key(self):
        key = self._card_add_key.input_field.text().strip()
        if not key or len(key) < 15:
            self._show_banner("⚠️ Please enter a valid backup Gemini API Key", is_error=True)
            return

        added, _ = key_rotator.add_keys([key])
        if added > 0:
            self._card_add_key.input_field.clear()
            _save_settings_config({"gemini_api_keys": key_rotator.get_keys()})
            self._refresh_pool_cards()
            self._show_banner(f"✓ Added backup project key! Total in pool: {len(key_rotator.get_keys())}")
        else:
            self._show_banner("⚠️ Key already exists in the failover pool", is_error=True)

    def _on_set_active_key(self, index: int):
        ok = key_rotator.set_active_index(index)
        if ok:
            active_k = key_rotator.get_active_key()
            self._card_primary.input_field.setText(active_k)
            _save_settings_config({"gemini_api_key": active_k})
            self._refresh_pool_cards()
            self._show_banner(f"✓ Active engine key switched to key #{index + 1}")

    def _on_remove_key(self, index: int):
        ok, msg = key_rotator.remove_key(index)
        if ok:
            _save_settings_config({
                "gemini_api_key": key_rotator.get_active_key(),
                "gemini_api_keys": key_rotator.get_keys(),
            })
            self._card_primary.input_field.setText(key_rotator.get_active_key())
            self._refresh_pool_cards()
            self._show_banner(f"✓ Key #{index + 1} removed from pool")
        else:
            self._show_banner(f"⚠️ {msg}", is_error=True)
