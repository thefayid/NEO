"""
core/neo_swarm_studio.py — Subagent Swarm Orchestrator & Autonomous Command Deck for NEO.
Provides multi-agent mission planning, parallel subagent dispatching,
live execution tracking via Stark Subagent Swarm (_TASK_REGISTRY),
deep deliverable inspection, and persistent Task Engine integration.
"""
from __future__ import annotations

import os
import sys
import time
import json
import threading
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextBrowser, QFrame, QScrollArea, QGridLayout,
    QCheckBox, QProgressBar
)

from core.tasks_db import add_task

# Shared executive styling tokens (Apple macOS Dark Vibrancy)
CARD_BG = "#232327"
CARD_BORDER = "#2F2F34"
CARD_HOVER = "#2A2A2F"
TEXT_WHITE = "#F5F5F7"
TEXT_MUTED = "#98989D"
TEXT_DIM = "#636366"
ACCENT_PRIMARY = "#0A84FF"
SEMANTIC_SUCCESS = "#30D158"
SEMANTIC_WARNING = "#FFD60A"
SEMANTIC_ERROR = "#FF453A"


class NeoSwarmStudio(QWidget):
    """Executive Subagent Swarm Orchestration Deck (macOS Standard)."""
    mission_dispatched = pyqtSignal(str, list)  # (objective, roles)
    task_sync_requested = pyqtSignal(str)       # (task_notification_text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_agents: List[dict] = []
        self._monitored_task_ids: List[str] = []
        self._selected_task_id: Optional[str] = None
        self._last_objective: str = ""

        self.setStyleSheet(f"""
            QWidget {{
                background: #161618;
                color: {TEXT_WHITE};
                font-family: -apple-system, "SF Pro Text", "Helvetica Neue", "Segoe UI", sans-serif;
            }}
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(18, 16, 18, 16)
        main_lay.setSpacing(12)

        # ── 1. Top Bar ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_lbl = QLabel("🐝")
        icon_lbl.setFont(QFont("Segoe UI", 16))
        hdr.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        title_lbl = QLabel("Subagent Swarm Orchestrator")
        title_lbl.setFont(QFont("-apple-system", 13, QFont.Weight.Bold))
        t_row.addWidget(title_lbl)

        self.swarm_badge = QLabel("● IDLE (0 SWARMS)")
        self.swarm_badge.setFont(QFont("-apple-system", 8, QFont.Weight.Bold))
        self.swarm_badge.setStyleSheet(f"color: {TEXT_MUTED}; background: rgba(152, 152, 157, 0.15); border-radius: 10px; padding: 2px 8px;")
        t_row.addWidget(self.swarm_badge)
        t_row.addStretch()
        title_col.addLayout(t_row)

        sub_lbl = QLabel("Parallel multi-agent execution: Code audits, web scouting, testing, and research synthesis")
        sub_lbl.setFont(QFont("-apple-system", 8))
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col)

        hdr.addStretch()

        refresh_btn = QPushButton("↻ Refresh Swarm")
        refresh_btn.setFixedHeight(28)
        refresh_btn.setFont(QFont("-apple-system", 8))
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CARD_BG}; color: {TEXT_MUTED};
                border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; color: {TEXT_WHITE}; }}
        """)
        refresh_btn.clicked.connect(self._refresh_swarm_state)
        hdr.addWidget(refresh_btn)

        main_lay.addLayout(hdr)

        # ── 2. Mission Dispatcher Card ───────────────────────────────────────
        dispatch_box = QFrame()
        dispatch_box.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
            }}
        """)
        d_lay = QVBoxLayout(dispatch_box)
        d_lay.setContentsMargins(14, 12, 14, 12)
        d_lay.setSpacing(8)

        d_title = QLabel("Launch Autonomous Swarm Mission")
        d_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        d_title.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        d_lay.addWidget(d_title)

        # Objective Input
        self.goal_input = QLineEdit()
        self.goal_input.setFixedHeight(30)
        self.goal_input.setFont(QFont("Segoe UI", 9))
        self.goal_input.setPlaceholderText("Enter mission objective (e.g., Audit security vulnerabilities and generate regression tests)...")
        self.goal_input.setStyleSheet(f"""
            QLineEdit {{
                background: #14171C; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_PRIMARY}; }}
        """)
        d_lay.addWidget(self.goal_input)

        # Specialized Agent Role Selectors mapped directly to actions.subagent_swarm
        roles_row = QHBoxLayout()
        roles_row.setSpacing(12)
        r_lbl = QLabel("Agent Squad:")
        r_lbl.setFont(QFont("Segoe UI", 8))
        r_lbl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        roles_row.addWidget(r_lbl)

        self.role_checks = {}
        squad_roles = [
            ("code_reviewer", "🕵️ Code Reviewer & Security Auditor", True),
            ("web_researcher", "🌐 Web Intelligence Scout", True),
            ("data_analyst", "📊 Data & Threat Analyst", True),
            ("doc_writer", "📝 Executive Doc Synthesizer", True),
        ]

        for key, label, checked in squad_roles:
            cb = QCheckBox(label)
            cb.setFont(QFont("Segoe UI", 8))
            cb.setChecked(checked)
            cb.setStyleSheet(f"""
                QCheckBox {{ color: {TEXT_WHITE}; background: transparent; spacing: 4px; }}
                QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {CARD_BORDER}; border-radius: 3px; background: #14171C; }}
                QCheckBox::indicator:checked {{ background: {ACCENT_PRIMARY}; border-color: {ACCENT_PRIMARY}; }}
            """)
            self.role_checks[key] = cb
            roles_row.addWidget(cb)
        roles_row.addStretch()

        self.launch_btn = QPushButton("🚀 Launch Swarm")
        self.launch_btn.setFixedHeight(28)
        self.launch_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.launch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_PRIMARY}; color: #ffffff;
                border: none; border-radius: 4px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: #4a7fdc; }}
        """)
        self.launch_btn.clicked.connect(self._launch_swarm_mission)
        roles_row.addWidget(self.launch_btn)

        d_lay.addLayout(roles_row)
        main_lay.addWidget(dispatch_box)

        # ── 3. Live Swarm Execution Deck ─────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.agents_container = QWidget()
        self.agents_container.setStyleSheet("background: transparent;")
        self.agents_lay = QVBoxLayout(self.agents_container)
        self.agents_lay.setContentsMargins(0, 0, 0, 0)
        self.agents_lay.setSpacing(8)

        # Initial Empty State
        self.empty_card = QFrame()
        self.empty_card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG}; border: 1px dashed {CARD_BORDER}; border-radius: 8px;
            }}
        """)
        empty_l = QVBoxLayout(self.empty_card)
        empty_l.setContentsMargins(20, 24, 20, 24)
        empty_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_icn = QLabel("🐝")
        e_icn.setFont(QFont("Segoe UI", 24))
        e_icn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(e_icn)
        e_lbl = QLabel("No Swarm Missions Currently Active")
        e_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        e_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        e_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(e_lbl)
        e_sub = QLabel("Select squad roles above and launch an objective to dispatch autonomous parallel agents.")
        e_sub.setFont(QFont("Segoe UI", 8))
        e_sub.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        e_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(e_sub)

        self.agents_lay.addWidget(self.empty_card)
        self.agents_lay.addStretch()
        self.scroll.setWidget(self.agents_container)
        main_lay.addWidget(self.scroll, stretch=1)

        # ── 4. Swarm Synthesis Dossier Output ────────────────────────────────
        self.dossier_box = QFrame()
        self.dossier_box.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;
            }}
        """)
        dos_lay = QVBoxLayout(self.dossier_box)
        dos_lay.setContentsMargins(14, 10, 14, 10)
        dos_lay.setSpacing(6)

        dos_hdr = QHBoxLayout()
        d_icn = QLabel("📋")
        d_icn.setFont(QFont("Segoe UI", 10))
        dos_hdr.addWidget(d_icn)
        self.dossier_title_lbl = QLabel("Synthesized Swarm Intelligence Dossier")
        self.dossier_title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.dossier_title_lbl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        dos_hdr.addWidget(self.dossier_title_lbl)
        dos_hdr.addStretch()

        self.sync_task_btn = QPushButton("☑ Sync Action Items as Tasks")
        self.sync_task_btn.setFixedHeight(22)
        self.sync_task_btn.setFont(QFont("Segoe UI", 7))
        self.sync_task_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_task_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: {SEMANTIC_SUCCESS}; }}
        """)
        self.sync_task_btn.clicked.connect(self._sync_swarm_tasks)
        dos_hdr.addWidget(self.sync_task_btn)
        dos_lay.addLayout(dos_hdr)

        self.dossier_browser = QTextBrowser()
        self.dossier_browser.setFont(QFont("Consolas", 8))
        self.dossier_browser.setFixedHeight(130)
        self.dossier_browser.setPlaceholderText("Swarm artifacts, real Gemini deliverables, and synthesized recommendations will stream here live as agents conclude.")
        self.dossier_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: #14171C; color: {TEXT_WHITE};
                border: 1px solid {CARD_BORDER}; border-radius: 4px; padding: 6px;
            }}
        """)
        dos_lay.addWidget(self.dossier_browser)

        main_lay.addWidget(self.dossier_box)

        # Polling timer for real subagent background execution
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(600)
        self.poll_timer.timeout.connect(self._poll_swarm_registry)

    # ── Swarm Dispatch & Deep Live Polling ────────────────────────────────────

    def _launch_swarm_mission(self):
        goal = self.goal_input.text().strip()
        if not goal:
            goal = "Autonomous workspace code audit, security review, and documentation synthesis"
        self._last_objective = goal

        chosen_roles = [k for k, cb in self.role_checks.items() if cb.isChecked()]
        if not chosen_roles:
            chosen_roles = ["code_reviewer", "web_researcher"]

        self.launch_btn.setEnabled(False)
        self.launch_btn.setText("Dispatching...")
        self.swarm_badge.setText(f"● RUNNING ({len(chosen_roles)} AGENTS)")
        self.swarm_badge.setStyleSheet(f"color: {SEMANTIC_WARNING}; background: rgba(217, 164, 65, 0.15); border-radius: 10px; padding: 2px 8px;")

        self.empty_card.setVisible(False)

        # Clear previous cards
        for a in self.active_agents:
            if "widget" in a:
                a["widget"].deleteLater()
        self.active_agents.clear()
        self._monitored_task_ids.clear()

        role_meta = {
            "code_reviewer": ("Code Reviewer & Security Architect", "Deep AST parsing, concurrency flaws, and vulnerability scan"),
            "web_researcher": ("Web Intelligence Scout", "Online documentation, ecosystem best practices, and architecture research"),
            "data_analyst": ("Quantitative & Threat Analyst", "Performance metrics, memory leak analysis, and statistical summary"),
            "doc_writer": ("Executive Doc Synthesizer", "Polished documentation, API specs, and executive briefings"),
        }

        # Dispatch real background workers via actions.subagent_swarm
        from actions.subagent_swarm import spawn_subagent, _TASK_REGISTRY, _LOCK

        for idx, role_key in enumerate(chosen_roles):
            name, desc = role_meta.get(role_key, (role_key.capitalize(), "Autonomous subagent"))
            instruction = f"Objective: {goal}. Focus specifically on role requirements as {name}."

            # Spawn real task
            before_keys = set()
            with _LOCK:
                before_keys = set(_TASK_REGISTRY.keys())

            spawn_subagent(role=role_key, instruction=instruction, player=self)

            # Discover newly generated task ID
            new_task_id = None
            with _LOCK:
                diff = set(_TASK_REGISTRY.keys()) - before_keys
                if diff:
                    new_task_id = list(diff)[0]
                else:
                    new_task_id = f"task_{idx}_{int(time.time()*1000)}"

            self._monitored_task_ids.append(new_task_id)

            # Build reactive UI card
            card = self._build_agent_card(idx + 1, new_task_id, name, desc)
            self.agents_lay.insertWidget(self.agents_lay.count() - 1, card)
            self.active_agents.append({
                "id": idx + 1,
                "task_id": new_task_id,
                "role": role_key,
                "name": name,
                "widget": card,
                "completed": False,
            })

        self.dossier_browser.setHtml(
            f"<div style='color: #38BDF8; font-weight: bold;'>⚡ Mission Dispatched: {goal}</div>"
            f"<div style='color: #9AA1AD; font-size: 8pt; margin-top: 4px;'>"
            f"Active subagents: {', '.join(chosen_roles)}.<br>"
            f"Workers running concurrently in background thread pool. Click any agent card to preview real deliverable.</div>"
        )

        # Start live registry polling
        self.poll_timer.start()

    def _build_agent_card(self, agent_num: int, task_id: str, title: str, desc: str) -> QFrame:
        card = QFrame()
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.setStyleSheet(f"""
            QFrame {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 6px;
            }}
            QFrame:hover {{
                border-color: {ACCENT_PRIMARY};
                background: {CARD_HOVER};
            }}
        """)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        icn = QLabel("⚡")
        icn.setFont(QFont("Segoe UI", 12))
        lay.addWidget(icn)

        col = QVBoxLayout()
        col.setSpacing(2)
        tl = QLabel(f"Subagent #{agent_num}: {title} [{task_id}]")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {TEXT_WHITE}; border: none; background: transparent;")
        col.addWidget(tl)

        dl = QLabel(desc)
        dl.setFont(QFont("Segoe UI", 7))
        dl.setStyleSheet(f"color: {TEXT_MUTED}; border: none; background: transparent;")
        col.addWidget(dl)
        lay.addLayout(col, stretch=1)

        status_lbl = QLabel("QUEUED...")
        status_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        status_lbl.setStyleSheet(f"color: {SEMANTIC_WARNING}; background: rgba(217, 164, 65, 0.15); border-radius: 4px; padding: 2px 8px;")
        lay.addWidget(status_lbl)
        card.status_lbl = status_lbl

        # Clicking card displays deliverable
        card.mousePressEvent = lambda ev, tid=task_id: self._inspect_agent_deliverable(tid)
        return card

    def _poll_swarm_registry(self):
        """Polls Stark Subagent Swarm global registry for live Gemini updates."""
        try:
            from actions.subagent_swarm import _TASK_REGISTRY, _LOCK
        except Exception:
            return

        with _LOCK:
            registry_copy = dict(_TASK_REGISTRY)

        all_done = True
        completed_outputs = []

        for agent in self.active_agents:
            tid = agent["task_id"]
            card = agent.get("widget")
            if tid in registry_copy:
                tdata = registry_copy[tid]
                status = tdata.get("status", "QUEUED")
                output = tdata.get("output")

                if card and hasattr(card, "status_lbl"):
                    if status == "RUNNING":
                        card.status_lbl.setText("● EXECUTING...")
                        card.status_lbl.setStyleSheet(f"color: #38BDF8; background: rgba(56, 189, 248, 0.15); border-radius: 4px; padding: 2px 8px;")
                        all_done = False
                    elif status == "COMPLETED":
                        card.status_lbl.setText("✓ COMPLETED")
                        card.status_lbl.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 8px;")
                        agent["completed"] = True
                        if output:
                            completed_outputs.append((agent["name"], output))
                    elif status == "FAILED":
                        card.status_lbl.setText("✕ FAILED")
                        card.status_lbl.setStyleSheet(f"color: {SEMANTIC_ERROR}; background: rgba(217, 83, 79, 0.15); border-radius: 4px; padding: 2px 8px;")
                        agent["completed"] = True
                    else:
                        all_done = False
            else:
                all_done = False

        if all_done and self.active_agents:
            self.poll_timer.stop()
            self._on_all_subagents_finished(completed_outputs)

    def _inspect_agent_deliverable(self, task_id: str):
        """Inspect deliverable of a specific subagent."""
        self._selected_task_id = task_id
        try:
            from actions.subagent_swarm import _TASK_REGISTRY, _LOCK
            with _LOCK:
                tdata = _TASK_REGISTRY.get(task_id, {})
        except Exception:
            tdata = {}

        if not tdata:
            self.dossier_browser.setHtml(f"<i>Task {task_id} details not yet available.</i>")
            return

        role = tdata.get("role", "subagent").upper()
        status = tdata.get("status", "UNKNOWN")
        output = tdata.get("output", "Awaiting deliverable...")
        instr = tdata.get("instruction", "")

        color = "#34D399" if status == "COMPLETED" else "#FBBF24"
        clean_out = (output or "").replace("\n", "<br>")

        self.dossier_title_lbl.setText(f"Deliverable: {task_id} ({role})")
        self.dossier_browser.setHtml(
            f"<div style='color: {color}; font-weight: bold;'>[{status}] Deliverable: {task_id} ({role})</div>"
            f"<div style='color: #64748B; font-size: 7.5pt; margin-bottom: 6px;'><b>Prompt:</b> {instr}</div>"
            f"<div style='color: #E6E8EC; font-size: 8pt; line-height: 1.4;'>{clean_out}</div>"
        )

    def _on_all_subagents_finished(self, deliverables: List[tuple[str, str]]):
        self.launch_btn.setEnabled(True)
        self.launch_btn.setText("🚀 Launch Swarm")
        self.swarm_badge.setText("● MISSION ACCOMPLISHED")
        self.swarm_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")

        goal = self._last_objective or "Workspace Audit"
        synth_html = [
            f"<div style='color: #34D399; font-weight: bold;'>✓ Mission Completed: {goal}</div>",
            "<div style='color: #9AA1AD; font-size: 8pt; margin: 4px 0;'>All parallel worker subagents returned deliverables:</div>"
        ]

        for name, out in deliverables:
            snippet = (out or "No output").strip()
            if len(snippet) > 280:
                snippet = snippet[:280] + "..."
            clean_snip = snippet.replace("\n", "<br>• ")
            synth_html.append(
                f"<div style='margin-top: 6px; padding: 4px; background: rgba(255,255,255,0.03); border-left: 2px solid {ACCENT_PRIMARY};'>"
                f"<span style='color: {ACCENT_PRIMARY}; font-weight: bold;'>{name}:</span><br>"
                f"<span style='color: #E6E8EC; font-size: 7.5pt;'>• {clean_snip}</span>"
                f"</div>"
            )

        synth_html.append("<br><div style='color: #64748B; font-size: 7.5pt;'>Click any card above to view its full deliverable. Click 'Sync Action Items' to save to Task Engine.</div>")
        self.dossier_title_lbl.setText("Synthesized Swarm Intelligence Dossier")
        self.dossier_browser.setHtml("".join(synth_html))

    def _refresh_swarm_state(self):
        """Reads all active tasks from _TASK_REGISTRY and renders them."""
        try:
            from actions.subagent_swarm import _TASK_REGISTRY, _LOCK
            with _LOCK:
                tasks = list(_TASK_REGISTRY.values())
        except Exception:
            tasks = []

        if not tasks:
            self.empty_card.setVisible(True)
            self.swarm_badge.setText("● IDLE (0 SWARMS)")
            self.swarm_badge.setStyleSheet(f"color: {TEXT_MUTED}; background: rgba(154, 161, 173, 0.15); border-radius: 10px; padding: 2px 8px;")
            return

        self.empty_card.setVisible(False)
        for a in self.active_agents:
            if "widget" in a:
                a["widget"].deleteLater()
        self.active_agents.clear()
        self._monitored_task_ids.clear()

        running_cnt = 0
        for idx, t in enumerate(tasks[-6:]):  # Most recent 6
            tid = t.get("id", f"swarm-{idx}")
            role = t.get("role", "worker")
            status = t.get("status", "QUEUED")
            instr = t.get("instruction", "")
            if status == "RUNNING":
                running_cnt += 1

            card = self._build_agent_card(idx + 1, tid, role.upper(), instr)
            if status == "COMPLETED":
                card.status_lbl.setText("✓ COMPLETED")
                card.status_lbl.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 4px; padding: 2px 8px;")
            elif status == "RUNNING":
                card.status_lbl.setText("● EXECUTING...")
                card.status_lbl.setStyleSheet(f"color: #38BDF8; background: rgba(56, 189, 248, 0.15); border-radius: 4px; padding: 2px 8px;")

            self.agents_lay.insertWidget(self.agents_lay.count() - 1, card)
            self.active_agents.append({"id": idx + 1, "task_id": tid, "role": role, "name": role, "widget": card, "completed": status == "COMPLETED"})
            self._monitored_task_ids.append(tid)

        if running_cnt > 0:
            self.swarm_badge.setText(f"● RUNNING ({running_cnt} ACTIVE)")
            self.swarm_badge.setStyleSheet(f"color: {SEMANTIC_WARNING}; background: rgba(217, 164, 65, 0.15); border-radius: 10px; padding: 2px 8px;")
            self.poll_timer.start()
        else:
            self.swarm_badge.setText(f"● READY ({len(tasks)} TOTAL TASKS)")
            self.swarm_badge.setStyleSheet(f"color: {SEMANTIC_SUCCESS}; background: rgba(76, 175, 125, 0.15); border-radius: 10px; padding: 2px 8px;")

    def _sync_swarm_tasks(self):
        """Atomically saves swarm recommendations to memory/tasks.json."""
        goal = self._last_objective or self.goal_input.text().strip() or "Swarm Mission Follow-up"

        task = add_task(
            title=f"Execute Swarm Recommendations: {goal[:50]}",
            category="Engineering",
            priority="High",
            due_date="Today",
            notes=f"Action items collated by NEO Swarm Orchestrator for objective: '{goal}' across {len(self.active_agents)} subagents.",
        )

        self.dossier_browser.append(
            f"<br><span style='color: {SEMANTIC_SUCCESS}; font-weight: bold;'>"
            f"✓ Synced '{task['title']}' directly to memory/tasks.json!</span>"
        )
        self.task_sync_requested.emit(f"Swarm action item synced to Task Engine: {task['title']}")
