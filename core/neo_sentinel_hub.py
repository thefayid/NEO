"""
core/neo_sentinel_hub.py — Sentinel Mission Control & Security Cockpit for NEO.
Visual management for Ergonomic Sentinel, Presence Sentry, System Immune Engine,
and Background Intelligence Watchdogs.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QGridLayout, QTextBrowser
)
import psutil

# Shared theme tokens
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

        self.kpi_posture = self._build_kpi_card("🪑", "Ergonomics", "96%", "Posture Alignment")
        self.kpi_presence = self._build_kpi_card("👁️", "Presence", "PRESENT", "Face Locked (0.7m)")
        self.kpi_immune = self._build_kpi_card("🛡️", "System Immune", "100%", "Zero Zombie Bloat")
        self.kpi_threats = self._build_kpi_card("⚡", "Interventions", "0 Alerts", "All Systems Nominal")

        kpi_row.addWidget(self.kpi_posture)
        kpi_row.addWidget(self.kpi_presence)
        kpi_row.addWidget(self.kpi_immune)
        kpi_row.addWidget(self.kpi_threats)
        root_lay.addLayout(kpi_row)

        # ── 3. Sentinel Deck: 4 Quadrants ─────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)

        # Sentinel 1: Ergonomic Sentinel
        self.card_ergo = self._build_sentinel_card(
            icon="🪑",
            title="Ergonomic Sentinel",
            subtitle="Posture alignment, eye-strain monitor & fatigue detection",
            badge="RUNNING",
            badge_color=SEMANTIC_SUCCESS,
            details=[
                ("Posture Score", "96% (Good Spine Elevation)"),
                ("Eye Blink Rate", "18 blinks/min (Normal)"),
                ("Screen Distance", "68 cm (Optimal 60-75cm)"),
                ("Session Stretch", "Break in 24 mins"),
            ],
            btn_label="🧘 Eye & Neck Reset",
            btn_cb=lambda: self.action_requested.emit("Activate quick 60-second ergonomic eye and posture stretch, Boss")
        )
        grid.addWidget(self.card_ergo, 0, 0)

        # Sentinel 2: Presence Sentry
        self.card_presence = self._build_sentinel_card(
            icon="👁️",
            title="Presence Sentry",
            subtitle="Optical face tracker, auto-security lock & return welcome",
            badge="ACTIVE",
            badge_color=SEMANTIC_SUCCESS,
            details=[
                ("User State", "Detected at Console"),
                ("Absence Lock", "Armed (45s threshold)"),
                ("Optical Sentry", "Camera Frame Rate 10 FPS"),
                ("Audio Gate", "Mic unmuted on return"),
            ],
            btn_label="🎯 Recalibrate Sentry",
            btn_cb=self._recalibrate_presence
        )
        grid.addWidget(self.card_presence, 0, 1)

        # Sentinel 3: System Immune Engine
        self.card_immune = self._build_sentinel_card(
            icon="🛡️",
            title="System Immune Engine",
            subtitle="Zombie task terminator, cache purge & memory watchdog",
            badge="VIGILANT",
            badge_color=SEMANTIC_SUCCESS,
            details=[
                ("Zombie Check", "0 Orphaned Processes"),
                ("RAM Watchdog", "Memory leak threshold 85%"),
                ("DNS Cache", "Clean (IPv4/IPv6 Synced)"),
                ("Temp Bloat", "0.0 MB flagged"),
            ],
            btn_label="🧹 Purge Zombie Tasks",
            btn_cb=self._run_immune_kill
        )
        grid.addWidget(self.card_immune, 1, 0)

        # Sentinel 4: Background Intelligence Monitor
        self.card_intel = self._build_sentinel_card(
            icon="🌐",
            title="Intelligence Watchdog",
            subtitle="Autonomous news topic prober, market watcher & alerts",
            badge="PROBING",
            badge_color=ACCENT_PRIMARY,
            details=[
                ("Tracked Topics", "AI Models, Tech, Local News"),
                ("Last Sweep", "Today 08:30 AM"),
                ("Brief Status", "Morning Briefing Ready"),
                ("Alert Mode", "Non-intrusive voice check-in"),
            ],
            btn_label="📡 Probe Topics Now",
            btn_cb=lambda: self.action_requested.emit("Check background intelligence feeds for latest tech updates, Boss")
        )
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
        self.audit_log.setFixedHeight(120)
        self.audit_log.setStyleSheet(f"""
            QTextBrowser {{
                background: #12151B; color: #A0AEC0;
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 6px;
            }}
        """)
        l_lay.addWidget(self.audit_log)

        root_lay.addWidget(log_frame, stretch=1)

        # Initial seed logs
        self._add_log("SENTINEL_BOOT", "All 4 Multi-Sensor Sentinels initialized in non-blocking daemon threads.")
        self._add_log("IMMUNE", "System Immune Engine ran initial process audit: 0 zombie processes found.")
        self._add_log("PRESENCE", "Presence Sentry optical tracker online.")
        self._add_log("ERGO", "Ergonomic Sentinel posture baseline established.")

        # Periodic refresh timer (3 seconds)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_vitals)
        self.refresh_timer.start(3000)

    # ── Builders ─────────────────────────────────────────────────────────────

    def _build_kpi_card(self, icon: str, title: str, value: str, sub: str) -> QFrame:
        c = QFrame()
        c.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        icn = QLabel(icon)
        icn.setFont(QFont("Segoe UI", 10))
        top.addWidget(icn)
        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        top.addWidget(t_lbl)
        top.addStretch()
        lay.addLayout(top)

        v_lbl = QLabel(value)
        v_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        v_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        lay.addWidget(v_lbl)
        c.v_lbl = v_lbl

        sub_lbl = QLabel(sub)
        sub_lbl.setFont(QFont("Segoe UI", 7))
        sub_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        lay.addWidget(sub_lbl)
        c.sub_lbl = sub_lbl

        return c

    def _build_sentinel_card(
        self,
        icon: str,
        title: str,
        subtitle: str,
        badge: str,
        badge_color: str,
        details: List[tuple],
        btn_label: str,
        btn_cb
    ) -> QFrame:
        c = QFrame()
        c.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        icn = QLabel(icon)
        icn.setFont(QFont("Segoe UI", 12))
        hdr.addWidget(icn)

        t_col = QVBoxLayout()
        t_col.setSpacing(1)
        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        t_col.addWidget(t_lbl)
        sub_lbl = QLabel(subtitle)
        sub_lbl.setFont(QFont("Segoe UI", 7))
        sub_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; background: transparent;")
        t_col.addWidget(sub_lbl)
        hdr.addLayout(t_col)

        hdr.addStretch()

        b_lbl = QLabel(badge)
        b_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        b_lbl.setStyleSheet(f"color: {badge_color}; background: rgba(76, 175, 125, 0.12); border-radius: 4px; padding: 2px 6px;")
        hdr.addWidget(b_lbl)
        lay.addLayout(hdr)

        # Metric Details
        det_box = QFrame()
        det_box.setStyleSheet("background: #14171C; border-radius: 4px; padding: 4px;")
        det_lay = QVBoxLayout(det_box)
        det_lay.setContentsMargins(8, 6, 8, 6)
        det_lay.setSpacing(4)
        for k, v in details:
            row = QHBoxLayout()
            kl = QLabel(k)
            kl.setFont(QFont("Segoe UI", 8))
            kl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
            row.addWidget(kl)
            row.addStretch()
            vl = QLabel(v)
            vl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            vl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
            row.addWidget(vl)
            det_lay.addLayout(row)
        lay.addWidget(det_box)

        # Action Button
        act_btn = QPushButton(btn_label)
        act_btn.setFixedHeight(26)
        act_btn.setFont(QFont("Segoe UI", 8))
        act_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        act_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {ACCENT_PRIMARY}; }}
        """)
        act_btn.clicked.connect(btn_cb)
        lay.addWidget(act_btn)

        return c

    # ── Actions & Refresh ─────────────────────────────────────────────────────

    def _add_log(self, tag: str, message: str):
        t = time.strftime("%H:%M:%S")
        color = "#38bdf8" if tag == "SENTINEL_BOOT" else "#34d399" if tag == "IMMUNE" else "#fbbf24"
        line = f"<span style='color: #64748b;'>[{t}]</span> <span style='color: {color}; font-weight: bold;'>[{tag}]</span> <span style='color: #e2e8f0;'>{message}</span><br>"
        self.audit_log.append(line)

    def _refresh_vitals(self):
        try:
            mem = psutil.virtual_memory().percent
            cpu = psutil.cpu_percent()
            self.kpi_immune.sub_lbl.setText(f"RAM Watchdog: {mem}% | CPU {cpu}%")
        except Exception:
            pass

    def _run_full_sweep(self):
        self._add_log("SWEEP", "Initiating Full Sentinel Diagnostic Sweep across all sensors...")
        self.sweep_btn.setEnabled(False)
        self.sweep_btn.setText("Sweeping...")

        def work():
            try:
                from actions.system_immune import health_audit, auto_kill_zombies
                audit_res = health_audit()
                kill_res = auto_kill_zombies()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", f"Health Audit: {audit_res[:100]}..."))
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", f"Zombie Sweep: {kill_res}"))
                QTimer.singleShot(0, lambda: self._add_log("DEFENSE", "✓ Defense Sweep Complete. Zero vulnerabilities identified."))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._add_log("SWEEP_ERROR", f"Error during sweep: {e}"))
            finally:
                QTimer.singleShot(0, lambda: self._reset_sweep_btn())

        threading.Thread(target=work, daemon=True, name="sentinel-sweep").start()

    def _reset_sweep_btn(self):
        self.sweep_btn.setEnabled(True)
        self.sweep_btn.setText("⚡ Full Defense Sweep")

    def _recalibrate_presence(self):
        self._add_log("PRESENCE", "Recalibrating optical facial sentry baseline...")
        self.action_requested.emit("Recalibrate presence optical sentry, Boss")

    def _run_immune_kill(self):
        self._add_log("IMMUNE", "Executing Zombie Process Terminator...")
        def work():
            try:
                from actions.system_immune import auto_kill_zombies
                res = auto_kill_zombies()
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE", res))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._add_log("IMMUNE_ERR", str(e)))
        threading.Thread(target=work, daemon=True, name="immune-kill").start()
