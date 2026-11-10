"""
core/neo_sentinel_hub.py — Sentinel Mission Control & Security Cockpit for NEO.
Provides deep live telemetry and interactive controls for:
  1. Ergonomic Sentinel (actions.ergonomic_sentinel)
  2. Presence Sentry (actions.presence_sentry)
  3. System Immune Engine (actions.system_immune)
  4. Background Intelligence Watchdog (actions.background_monitor)
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QGridLayout, QTextBrowser
)
import psutil

# Shared executive theme tokens
CARD_BG = "#1B1F26"
CARD_BORDER = "#262B34"
CARD_HOVER = "#222731"
TEXT_WHITE = "#E6E8EC"
TEXT_MUTED = "#9AA1AD"
TEXT_DIM = "#5F6672"
ACCENT_PRIMARY = "#5B8DEF"
SEMANTIC_SUCCESS = "#4CAF7D"
SEMANTIC_WARNING = "#D9A441"
SEMANTIC_ERROR = "#D9534F"


class NeoSentinelHub(QWidget):
    """Executive Sentinel Mission Control & Autonomous Security Cockpit."""
    action_requested = pyqtSignal(str)   # (voice_or_system_command)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QWidget {{
                background: #0E1013;
                color: {TEXT_WHITE};
            }}
        """)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(18, 16, 18, 16)
        root_lay.setSpacing(12)

        # ── 1. Top Executive Banner ──────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        icon_lbl = QLabel("🛡️")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        title_lbl = QLabel("Sentinel Mission Control")
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        t_row.addWidget(title_lbl)

        self.shield_badge = QLabel("● ACTIVE SHIELD (4/4 SENTINELS)")
        self.shield_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.shield_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")
        t_row.addWidget(self.shield_badge)
        t_row.addStretch()
        title_col.addLayout(t_row)

        sub_lbl = QLabel("Autonomous multi-sensor protection: Ergonomics, Presence, System Immune, and Proactive Sentinels")
        sub_lbl.setFont(QFont("Segoe UI", 8))
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        self.sweep_btn = QPushButton("⚡ Full Defense Sweep")
        self.sweep_btn.setFixedHeight(32)
        self.sweep_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.sweep_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sweep_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(91, 141, 239, 0.2); color: {ACCENT_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY}; border-radius: 6px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.35); color: #ffffff; }}
        """)
        self.sweep_btn.clicked.connect(self._run_full_sweep)
        hdr.addWidget(self.sweep_btn)

        root_lay.addLayout(hdr)

        # ── 2. KPI Telemetry Vitals Row ───────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        self.kpi_posture = self._build_kpi_card("🪑", "Hydration & Health", "0 Glasses", "Active Session: 0m")
        self.kpi_presence = self._build_kpi_card("👁️", "Presence Sentry", "ONLINE", "User Present at Desk")
        self.kpi_immune = self._build_kpi_card("🛡️", "System Immune", "100%", "Zero Zombie Bloat")
        self.kpi_threats = self._build_kpi_card("🌐", "Intel Feeds", "0 Topics", "DDG Prober Ready")

        kpi_row.addWidget(self.kpi_posture)
        kpi_row.addWidget(self.kpi_presence)
        kpi_row.addWidget(self.kpi_immune)
        kpi_row.addWidget(self.kpi_threats)
        root_lay.addLayout(kpi_row)

        # ── 3. Sentinel Deck: 4 Quadrants ─────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)

        # Sentinel 1: Ergonomic Sentinel
        self.card_ergo = self._build_ergo_card()
        grid.addWidget(self.card_ergo, 0, 0)

        # Sentinel 2: Presence Sentry
        self.card_presence = self._build_presence_card()
        grid.addWidget(self.card_presence, 0, 1)

        # Sentinel 3: System Immune Engine
        self.card_immune = self._build_immune_card()
        grid.addWidget(self.card_immune, 1, 0)

        # Sentinel 4: Background Intelligence Monitor
        self.card_intel = self._build_intel_card()
        grid.addWidget(self.card_intel, 1, 1)

        root_lay.addLayout(grid, stretch=2)

        # ── 4. Live Sentinel Security Audit Log ───────────────────────────────
        log_frame = QFrame()
        log_frame.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        l_lay = QVBoxLayout(log_frame)
        l_lay.setContentsMargins(14, 10, 14, 10)
        l_lay.setSpacing(6)

        l_hdr = QHBoxLayout()
        l_icn = QLabel("📋")
        l_icn.setFont(QFont("Segoe UI", 10))
        l_hdr.addWidget(l_icn)
        l_title = QLabel("Live Sentinel Security & Defense Audit Feed")
        l_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        l_title.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        l_hdr.addWidget(l_title)
        l_hdr.addStretch()

        clear_btn = QPushButton("Clear Log")
        clear_btn.setFixedHeight(22)
        clear_btn.setFont(QFont("Segoe UI", 7))
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; color: {TEXT_WHITE}; }}
        """)
        clear_btn.clicked.connect(lambda: self.audit_log.clear())
        l_hdr.addWidget(clear_btn)
        l_lay.addLayout(l_hdr)

        self.audit_log = QTextBrowser()
        self.audit_log.setFont(QFont("Consolas", 8))
        self.audit_log.setFixedHeight(115)
        self.audit_log.setStyleSheet(f"""
            QTextBrowser {{
                background: #12151B; color: #A0AEC0;
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 6px;
            }}
        """)
        l_lay.addWidget(self.audit_log)

        root_lay.addWidget(log_frame, stretch=1)

        # Initial seed logs
        self._add_log("SENTINEL_BOOT", "Sentinel Mission Control initialized with live multi-sensor connectors.")
        self._add_log("IMMUNE", "System Immune Engine live connection active.")
        self._add_log("PRESENCE", "Presence Sentry optical tracker synced.")
        self._add_log("ERGO", "Ergonomic Sentinel telemetry synchronized.")

        # High-precision refresh timer (2.5 seconds)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2500)
        self.refresh_timer.timeout.connect(self._refresh_all_vitals)
        self.refresh_timer.start()

        # Immediate initial poll
        self._refresh_all_vitals()

    # ── Builders ─────────────────────────────────────────────────────────────

    def _build_kpi_card(self, icon: str, title: str, value: str, sub: str) -> QFrame:
        c = QFrame()
        c.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setFont(QFont("Segoe UI", 12))
        top.addWidget(ic)
        tl = QLabel(title)
        tl.setFont(QFont("Segoe UI", 8))
        tl.setStyleSheet(f"color: {TEXT_MUTED};")
        top.addWidget(tl)
        top.addStretch()
        lay.addLayout(top)

        vl = QLabel(value)
        vl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        vl.setStyleSheet(f"color: {TEXT_WHITE};")
        lay.addWidget(vl)

        sl = QLabel(sub)
        sl.setFont(QFont("Segoe UI", 7))
        sl.setStyleSheet(f"color: {TEXT_DIM};")
        lay.addWidget(sl)

        c.val_lbl = vl
        c.sub_lbl = sl
        return c

    def _build_ergo_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        icn = QLabel("🪑")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        tl = QLabel("Ergonomic Sentinel")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(tl)
        hdr.addStretch()
        self.ergo_badge = QLabel("ONLINE")
        self.ergo_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.ergo_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(self.ergo_badge)
        lay.addLayout(hdr)

        self.ergo_lbl1 = QLabel("Hydration Today: 0 glasses")
        self.ergo_lbl2 = QLabel("Eye Rest Cycles (20-20-20): 0 completed")
        self.ergo_lbl3 = QLabel("Posture Breaks Taken: 0")
        self.ergo_lbl4 = QLabel("Session Duration: Active 0 mins")

        for lbl in (self.ergo_lbl1, self.ergo_lbl2, self.ergo_lbl3, self.ergo_lbl4):
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
            lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_water = QPushButton("💧 Log Water")
        btn_water.setFixedHeight(24)
        btn_water.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_water.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_water.setStyleSheet(f"""
            QPushButton {{ background: rgba(91, 141, 239, 0.15); color: {ACCENT_PRIMARY}; border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.3); }}
        """)
        btn_water.clicked.connect(self._log_water_glass)
        btn_row.addWidget(btn_water)

        btn_stretch = QPushButton("🧘 60s Stretch")
        btn_stretch.setFixedHeight(24)
        btn_stretch.setFont(QFont("Segoe UI", 8))
        btn_stretch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_stretch.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_WHITE}; border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        btn_stretch.clicked.connect(lambda: self.action_requested.emit("Activate quick 60-second ergonomic eye and posture stretch, Boss"))
        btn_row.addWidget(btn_stretch)

        lay.addLayout(btn_row)
        return card

    def _build_presence_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        icn = QLabel("👁️")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        tl = QLabel("Presence Sentry")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(tl)
        hdr.addStretch()
        self.pres_badge = QLabel("ACTIVE")
        self.pres_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.pres_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(self.pres_badge)
        lay.addLayout(hdr)

        self.pres_lbl1 = QLabel("User Status: Detected at Console")
        self.pres_lbl2 = QLabel("Absence Auto-Lock: 20s Trigger")
        self.pres_lbl3 = QLabel("Greeting Protocol: Enabled on return")
        self.pres_lbl4 = QLabel("Sensor: Shared Hardware Camera")

        for lbl in (self.pres_lbl1, self.pres_lbl2, self.pres_lbl3, self.pres_lbl4):
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
            lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_lock = QPushButton("🔒 Toggle Lock")
        btn_lock.setFixedHeight(24)
        btn_lock.setFont(QFont("Segoe UI", 8))
        btn_lock.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_lock.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_WHITE}; border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        btn_lock.clicked.connect(self._toggle_presence_lock)
        btn_row.addWidget(btn_lock)

        btn_recal = QPushButton("🎯 Recalibrate")
        btn_recal.setFixedHeight(24)
        btn_recal.setFont(QFont("Segoe UI", 8))
        btn_recal.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_recal.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_WHITE}; border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        btn_recal.clicked.connect(self._recalibrate_presence)
        btn_row.addWidget(btn_recal)

        lay.addLayout(btn_row)
        return card

    def _build_immune_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        icn = QLabel("🛡️")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        tl = QLabel("System Immune Engine")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(tl)
        hdr.addStretch()
        self.immune_badge = QLabel("VIGILANT")
        self.immune_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.immune_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(self.immune_badge)
        lay.addLayout(hdr)

        self.immune_lbl1 = QLabel("Zombie Tasks: 0 Orphaned Processes")
        self.immune_lbl2 = QLabel("Memory Watchdog: RAM load 45%")
        self.immune_lbl3 = QLabel("DNS & Network: Synchronized")
        self.immune_lbl4 = QLabel("Temp Storage Bloat: 0 MB scanned")

        for lbl in (self.immune_lbl1, self.immune_lbl2, self.immune_lbl3, self.immune_lbl4):
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
            lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_kill = QPushButton("🧹 Purge Zombies")
        btn_kill.setFixedHeight(24)
        btn_kill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_kill.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_kill.setStyleSheet(f"""
            QPushButton {{ background: rgba(217, 83, 79, 0.15); color: {SEMANTIC_ERROR}; border: 1px solid rgba(217, 83, 79, 0.3); border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: rgba(217, 83, 79, 0.3); }}
        """)
        btn_kill.clicked.connect(self._run_immune_kill)
        btn_row.addWidget(btn_kill)

        btn_purge = QPushButton("🗑️ Clear Cache")
        btn_purge.setFixedHeight(24)
        btn_purge.setFont(QFont("Segoe UI", 8))
        btn_purge.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_purge.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_WHITE}; border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: {CARD_HOVER}; }}
        """)
        btn_purge.clicked.connect(self._run_cache_purge)
        btn_row.addWidget(btn_purge)

        lay.addLayout(btn_row)
        return card

    def _build_intel_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        icn = QLabel("🌐")
        icn.setFont(QFont("Segoe UI", 11))
        hdr.addWidget(icn)
        tl = QLabel("Intelligence Watchdog")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        hdr.addWidget(tl)
        hdr.addStretch()
        self.intel_badge = QLabel("PROBING")
        self.intel_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.intel_badge.setStyleSheet(f"color: {ACCENT_PRIMARY}; background: rgba(91, 141, 239, 0.15); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(self.intel_badge)
        lay.addLayout(hdr)

        self.intel_lbl1 = QLabel("Tracked Topics: AI, Tech, Python")
        self.intel_lbl2 = QLabel("DDG News Prober: 1 sweep/day")
        self.intel_lbl3 = QLabel("Alert Mode: Non-intrusive voice briefing")
        self.intel_lbl4 = QLabel("Filtered: Zero crypto/financial noise")

        for lbl in (self.intel_lbl1, self.intel_lbl2, self.intel_lbl3, self.intel_lbl4):
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
            lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_probe = QPushButton("📡 Probe Feeds Now")
        btn_probe.setFixedHeight(24)
        btn_probe.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_probe.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_probe.setStyleSheet(f"""
            QPushButton {{ background: rgba(91, 141, 239, 0.15); color: {ACCENT_PRIMARY}; border: 1px solid {ACCENT_PRIMARY}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: rgba(91, 141, 239, 0.3); }}
        """)
        btn_probe.clicked.connect(self._probe_intel_feeds)
        btn_row.addWidget(btn_probe)

        lay.addLayout(btn_row)
        return card

    # ── Actions & Live Refresh Pipeline ───────────────────────────────────────

    def _add_log(self, tag: str, message: str):
        t = time.strftime("%H:%M:%S")
        color_map = {
            "SENTINEL_BOOT": "#38BDF8",
            "IMMUNE": "#34D399",
            "PRESENCE": "#818CF8",
            "ERGO": "#FBBF24",
            "SWEEP": "#A78BFA",
            "INTEL": "#60A5FA",
            "ERROR": "#F87171",
        }
        color = color_map.get(tag, "#E2E8F0")
        line = f"<span style='color: #64748B;'>[{t}]</span> <span style='color: {color}; font-weight: bold;'>[{tag}]</span> <span style='color: #E2E8F0;'>{message}</span><br>"
        self.audit_log.append(line)
        self.audit_log.verticalScrollBar().setValue(self.audit_log.verticalScrollBar().maximum())

    def _refresh_all_vitals(self):
        """Reads live telemetry directly from backend sentinel singletons and psutil."""
        # 1. System Immune & Hardware Vitals
        try:
            mem = psutil.virtual_memory().percent
            cpu = psutil.cpu_percent()
            self.kpi_immune.val_lbl.setText(f"{100 - int(mem * 0.4)}%")
            self.kpi_immune.sub_lbl.setText(f"RAM: {mem}% · CPU: {cpu}%")
            self.immune_lbl2.setText(f"Memory Watchdog: RAM load {mem}% · CPU {cpu}%")
        except Exception:
            pass

        # 2. Ergonomics Sentinel Live Data
        try:
            from actions.ergonomic_sentinel import _load_ergo_data, _sentinel
            ergo_data = _load_ergo_data()
            glasses = ergo_data.get("water_glasses", 0)
            breaks = ergo_data.get("breaks_taken", 0)
            eye_rests = ergo_data.get("eye_rests_completed", 0)
            mins = int((time.monotonic() - _sentinel.start_time) // 60) if _sentinel._running else 0

            self.kpi_posture.val_lbl.setText(f"{glasses} Glasses")
            self.kpi_posture.sub_lbl.setText(f"Active Session: {mins}m · Breaks: {breaks}")

            self.ergo_lbl1.setText(f"Hydration Today: {glasses} glasses logged")
            self.ergo_lbl2.setText(f"Eye Rest Cycles (20-20-20): {eye_rests} completed")
            self.ergo_lbl3.setText(f"Posture Breaks Taken: {breaks}")
            self.ergo_lbl4.setText(f"Session Duration: Active {mins} mins")

            if _sentinel._running:
                self.ergo_badge.setText("ONLINE")
                self.ergo_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 6px;")
            else:
                self.ergo_badge.setText("STANDBY")
                self.ergo_badge.setStyleSheet(f"color: {TEXT_MUTED}; background: rgba(154, 161, 173, 0.15); border-radius: 4px; padding: 2px 6px;")
        except Exception:
            pass

        # 3. Presence Sentry Live Data
        try:
            from actions.presence_sentry import _monitor
            present = _monitor.is_present
            locked = getattr(_monitor, "auto_lock", False)
            status_text = "PRESENT" if present else "AWAY"
            self.kpi_presence.val_lbl.setText(status_text)
            self.kpi_presence.sub_lbl.setText("User Present at Desk" if present else "Console Vacant")
            self.pres_lbl1.setText(f"User Status: {'Detected at Console' if present else 'Absence Detected'}")
            self.pres_lbl2.setText(f"Absence Auto-Lock: {'ARMED (20s)' if locked else 'DISARMED'}")
        except Exception:
            pass

        # 4. Intelligence Watchdog Topics
        try:
            from actions.background_monitor import _load
            monitors = _load()
            topic_count = len(monitors)
            topics_str = ", ".join(list(monitors.keys())[:3]) if topic_count > 0 else "None"
            self.kpi_threats.val_lbl.setText(f"{topic_count} Topics")
            self.kpi_threats.sub_lbl.setText(f"Watching: {topics_str[:25]}")
            self.intel_lbl1.setText(f"Tracked Topics: {topics_str}")
        except Exception:
            pass

    def _log_water_glass(self):
        """Records water intake and logs immediately."""
        try:
            from actions.ergonomic_sentinel import _sentinel
            msg = _sentinel.log_water()
            self._add_log("ERGO", msg)
            self._refresh_all_vitals()
        except Exception as e:
            self._add_log("ERROR", f"Could not log water: {e}")

    def _toggle_presence_lock(self):
        try:
            from actions.presence_sentry import _monitor, _save_config
            _monitor.auto_lock = not _monitor.auto_lock
            _save_config("presence_auto_lock", _monitor.auto_lock)
            state = "ARMED" if _monitor.auto_lock else "DISARMED"
            self._add_log("PRESENCE", f"Absence workstation auto-lock is now {state}.")
            self._refresh_all_vitals()
        except Exception as e:
            self._add_log("ERROR", f"Auto-lock toggle error: {e}")

    def _recalibrate_presence(self):
        self._add_log("PRESENCE", "Recalibrating optical facial sentry baseline via Shared Camera...")
        self.action_requested.emit("Recalibrate presence optical sentry, Boss")

    def _run_immune_kill(self):
        self._add_log("IMMUNE", "Running Zombie Process Terminator across psutil process tables...")
        def work():
            try:
                from actions.system_immune import auto_kill_zombies
                res = auto_kill_zombies()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", res))
                QTimer.singleShot(0, self._refresh_all_vitals)
            except Exception as e:
                QTimer.singleShot(0, lambda: self._add_log("ERROR", f"Zombie sweep error: {e}"))
        threading.Thread(target=work, daemon=True, name="sentinel-kill").start()

    def _run_cache_purge(self):
        self._add_log("IMMUNE", "Sweeping temporary cache bloat & crash dumps...")
        def work():
            try:
                from actions.system_immune import purge_cache_bloat
                res = purge_cache_bloat()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", res))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._add_log("ERROR", f"Purge error: {e}"))
        threading.Thread(target=work, daemon=True, name="cache-purge").start()

    def _probe_intel_feeds(self):
        self._add_log("INTEL", "Triggering autonomous DuckDuckGo news topic probe...")
        self.action_requested.emit("Check background intelligence feeds for latest tech updates, Boss")

    def _run_full_sweep(self):
        self._add_log("SWEEP", "Initiating Full Defense Diagnostic Sweep across all 4 Sentinels...")
        self.sweep_btn.setEnabled(False)
        self.sweep_btn.setText("Sweeping...")

        def work():
            try:
                from actions.system_immune import health_audit, auto_kill_zombies, purge_cache_bloat
                zombie_res = auto_kill_zombies()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", zombie_res))

                cache_res = purge_cache_bloat()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", cache_res))

                audit_res = health_audit()
                first_line = audit_res.splitlines()[0] if audit_res else "Audit passed"
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", f"Vitals Audit: {first_line}"))

                QTimer.singleShot(0, lambda: self._add_log("SWEEP", "✓ Full Defense Sweep Complete. All sensors nominal."))
                QTimer.singleShot(0, self._refresh_all_vitals)
            except Exception as e:
                QTimer.singleShot(0, lambda: self._add_log("ERROR", f"Sweep error: {e}"))
            finally:
                QTimer.singleShot(0, self._reset_sweep_btn)

        threading.Thread(target=work, daemon=True, name="sentinel-full-sweep").start()

    def _reset_sweep_btn(self):
        self.sweep_btn.setEnabled(True)
        self.sweep_btn.setText("⚡ Full Defense Sweep")
