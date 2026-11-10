"""
core/neo_precognition.py — Pre-Cognitive Intent & Non-Intrusive Delivery Engine for NEO.

Architecture:
1. Translates raw ambient sensory signals into structured Proactive Opportunities.
2. Evaluates urgency vs focus state (Apple HIG Delivery Etiquette).
3. Delivery Channels:
   - Level 1 (Ambient / Tactical): Dynamic Smart Action Chips in Hero Stage & Spotlight.
   - Level 2 (Medium Attention): macOS Toast Notification Banners with [Run] [Dismiss].
   - Level 3 (High Urgency): Live Voice & chime (only when urgency >= 0.85 and user NOT typing).
4. Cooldown and deduplication prevents repeating suggestions.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.neo_ambient_sensor import ambient_sensor, UserFocusState
from core.neo_brain import brain

_BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ProactiveOpportunity:
    """Actionable proactive opportunity identified by the Pre-Cognitive Engine."""
    opportunity_id: str
    category: str        # CODE_ERROR, CALENDAR_BRIEF, CLIPBOARD_ACTION, GIT_HYGIENE, RESOURCE_PRESSURE, HABIT_RECOMMENDATION
    urgency: float       # 0.0 to 1.0 (0.85+ triggers voice if idle)
    confidence: float    # 0.0 to 1.0
    title: str           # Short crisp chip text (e.g. "🛠 Fix 'ModuleNotFoundError'")
    subtitle: str        # Detailed explanation
    action_type: str     # GOAL, TOOL, COMMAND, URL, DISMISS
    action_payload: str  # Prompt string or tool argument to execute
    icon_name: str       # Lucide icon name
    cooldown_key: str    # Unique deduplication key
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NEOPrecognitiveEngine(QObject):
    """
    Cognitive evaluation loop that turns ambient telemetry into actionable, non-intrusive opportunities.
    """
    opportunity_detected = pyqtSignal(object)              # ProactiveOpportunity
    toast_requested = pyqtSignal(str, str, str, str)       # title, message, variant, action_payload
    voice_alert_requested = pyqtSignal(str)                # spoken message text
    chips_updated = pyqtSignal(list)                       # List[dict] for Hero UI

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cooldowns: Dict[str, float] = {}             # key -> expiration timestamp
        self._active_opportunities: Dict[str, ProactiveOpportunity] = {}
        self._default_cooldown_secs = 600                  # 10 minutes default
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connects to the ambient sensory stream."""
        ambient_sensor.telemetry_updated.connect(self.evaluate_snapshot)
        ambient_sensor.error_detected.connect(self._on_direct_error)
        ambient_sensor.clipboard_detected.connect(self._on_direct_clipboard)
        ambient_sensor.meeting_imminent.connect(self._on_direct_meeting)

    def is_on_cooldown(self, key: str) -> bool:
        """Checks if a recommendation is currently in its cooldown period."""
        exp = self._cooldowns.get(key, 0.0)
        return time.time() < exp

    def set_cooldown(self, key: str, duration_secs: Optional[int] = None) -> None:
        """Registers a cooldown for a given opportunity key."""
        dur = duration_secs or self._default_cooldown_secs
        self._cooldowns[key] = time.time() + dur

    def dismiss_opportunity(self, opportunity_id: str) -> None:
        """User dismissed or executed an opportunity; removes it from active list."""
        if opportunity_id in self._active_opportunities:
            opp = self._active_opportunities.pop(opportunity_id)
            self.set_cooldown(opp.cooldown_key, 900)  # 15m cooldown on dismissal
            self._emit_chips()

    def get_active_opportunities(self) -> List[Dict[str, Any]]:
        """Returns currently active opportunities sorted by urgency."""
        opps = sorted(
            self._active_opportunities.values(),
            key=lambda x: (x.urgency, x.confidence),
            reverse=True
        )
        return [o.to_dict() for o in opps[:3]]

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot Evaluation Loop
    # ─────────────────────────────────────────────────────────────────────────

    def evaluate_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Evaluates ambient snapshot against rule engines and context."""
        vitals = snapshot.get("vitals", {})
        git_state = snapshot.get("git", {})
        agenda = snapshot.get("agenda", [])
        focus_state = UserFocusState(snapshot.get("focus_state", "FOCUSED_IDLE"))

        # 1. Evaluate Calendar
        self._evaluate_calendar_agenda(agenda, focus_state)

        # 2. Evaluate Resource Saturation
        self._evaluate_resource_vitals(vitals, focus_state)

        # 3. Evaluate Git Hygiene
        self._evaluate_git_hygiene(git_state, focus_state)

        # Purge stale opportunities (> 15 mins old)
        now = time.time()
        stale_keys = [
            k for k, v in self._active_opportunities.items()
            if now - v.created_at > 900
        ]
        for k in stale_keys:
            self._active_opportunities.pop(k, None)

        self._emit_chips()

    # ─────────────────────────────────────────────────────────────────────────
    # Evaluators
    # ─────────────────────────────────────────────────────────────────────────

    def _evaluate_calendar_agenda(self, agenda: List[Dict[str, Any]], focus_state: UserFocusState) -> None:
        """Anticipates meetings starting within 15 minutes."""
        if not agenda:
            return
        soonest = min(agenda, key=lambda x: x.get("minutes_until", 999))
        mins = soonest.get("minutes_until", 999)
        title = soonest.get("title", "Meeting")

        if mins <= 15:
            ckey = f"meeting:{title}"
            if self.is_on_cooldown(ckey):
                return

            urgency = 0.90 if mins <= 3 else (0.75 if mins <= 10 else 0.55)
            short_title = (title[:20] + "...") if len(title) > 20 else title
            opp = ProactiveOpportunity(
                opportunity_id=f"cal_{int(time.time())}",
                category="CALENDAR_BRIEF",
                urgency=urgency,
                confidence=0.95,
                title=f"📅 Prep '{short_title}' (in {mins}m)",
                subtitle=f"Upcoming agenda event starting in {mins} minutes. Review briefing & notes.",
                action_type="GOAL",
                action_payload=f"Review and brief me on '{title}' and prepare my notes, Boss.",
                icon_name="calendar",
                cooldown_key=ckey,
                created_at=time.time(),
            )
            self._dispatch_opportunity(opp, focus_state)

    def _evaluate_resource_vitals(self, vitals: Dict[str, Any], focus_state: UserFocusState) -> None:
        """Detects critical RAM/CPU saturation or low battery."""
        ram_crit = vitals.get("ram_critical", False)
        batt_low = vitals.get("battery_low", False)

        if ram_crit:
            ckey = "resource:ram_critical"
            if not self.is_on_cooldown(ckey):
                opp = ProactiveOpportunity(
                    opportunity_id=f"res_ram_{int(time.time())}",
                    category="RESOURCE_PRESSURE",
                    urgency=0.88,
                    confidence=0.92,
                    title=f"⚡ RAM Critical ({vitals.get('ram_percent')}%)",
                    subtitle="System memory exceeded 90%. Purge cached objects and inactive processes.",
                    action_type="GOAL",
                    action_payload="Inspect system memory hogs, clean cache, and report telemetry, Boss.",
                    icon_name="activity",
                    cooldown_key=ckey,
                    created_at=time.time(),
                )
                self._dispatch_opportunity(opp, focus_state)

        if batt_low:
            ckey = "resource:battery_low"
            if not self.is_on_cooldown(ckey):
                opp = ProactiveOpportunity(
                    opportunity_id=f"res_batt_{int(time.time())}",
                    category="RESOURCE_PRESSURE",
                    urgency=0.85,
                    confidence=0.95,
                    title=f"🔋 Battery Low ({vitals.get('battery_percent')}%)",
                    subtitle="Laptop battery below 20% on discharge. Connect charger or switch to Eco mode.",
                    action_type="COMMAND",
                    action_payload="Activate Eco Mode and lower screen telemetry power, Boss.",
                    icon_name="zap",
                    cooldown_key=ckey,
                    created_at=time.time(),
                )
                self._dispatch_opportunity(opp, focus_state)

    def _evaluate_git_hygiene(self, git_state: Dict[str, Any], focus_state: UserFocusState) -> None:
        """Prompts commit generation if user has multiple uncommitted files."""
        dirty = git_state.get("dirty", False)
        count = git_state.get("modified_count", 0)
        branch = git_state.get("branch", "main")

        if dirty and count >= 3:
            ckey = f"git:dirty_{count}"
            if not self.is_on_cooldown(ckey):
                opp = ProactiveOpportunity(
                    opportunity_id=f"git_{int(time.time())}",
                    category="GIT_HYGIENE",
                    urgency=0.45,
                    confidence=0.85,
                    title=f"✦ Review & Commit ({count} files)",
                    subtitle=f"{count} uncommitted modifications detected on branch '{branch}'.",
                    action_type="GOAL",
                    action_payload="Review uncommitted git modifications and generate a conventional commit, Boss.",
                    icon_name="git-branch",
                    cooldown_key=ckey,
                    created_at=time.time(),
                )
                self._dispatch_opportunity(opp, focus_state)

    # ─────────────────────────────────────────────────────────────────────────
    # Event-Driven Direct Triggers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_direct_error(self, err_type: str, details: str) -> None:
        """Triggered immediately when ambient sensor spots a traceback or build error."""
        ckey = f"error:{details[:30]}"
        if self.is_on_cooldown(ckey):
            return

        opp = ProactiveOpportunity(
            opportunity_id=f"err_{int(time.time())}",
            category="CODE_ERROR",
            urgency=0.78,
            confidence=0.90,
            title=f"🛠 Fix '{err_type}': {details[:16]}...",
            subtitle=f"Detected error in workspace: {details[:60]}. Click to diagnose and fix.",
            action_type="GOAL",
            action_payload=f"Diagnose and autonomously fix this error: {details}, Boss.",
            icon_name="wrench",
            cooldown_key=ckey,
            created_at=time.time(),
        )
        self._dispatch_opportunity(opp, ambient_sensor.get_focus_state())

    def _on_direct_clipboard(self, content_type: str, text: str) -> None:
        """Triggered immediately when user copies a repo or install command."""
        ckey = f"clip:{content_type}:{text[:25]}"
        if self.is_on_cooldown(ckey):
            return

        if content_type == "github_repo":
            repo_name = text.rstrip("/").split("/")[-1]
            opp = ProactiveOpportunity(
                opportunity_id=f"clip_gh_{int(time.time())}",
                category="CLIPBOARD_ACTION",
                urgency=0.55,
                confidence=0.92,
                title=f"📦 Clone '{repo_name}'",
                subtitle=f"Detected GitHub URL '{text}'. Inspect and clone into workspace?",
                action_type="GOAL",
                action_payload=f"Inspect and clone GitHub repository {text} into workspace, Boss.",
                icon_name="download",
                cooldown_key=ckey,
                created_at=time.time(),
            )
            self._dispatch_opportunity(opp, ambient_sensor.get_focus_state())

        elif content_type == "package_install":
            opp = ProactiveOpportunity(
                opportunity_id=f"clip_pkg_{int(time.time())}",
                category="CLIPBOARD_ACTION",
                urgency=0.50,
                confidence=0.90,
                title=f"⚡ Run '{text[:20]}'",
                subtitle=f"Detected installation command in clipboard. Run in active venv?",
                action_type="GOAL",
                action_payload=f"Execute this package installation in active virtualenv: {text}, Boss.",
                icon_name="terminal",
                cooldown_key=ckey,
                created_at=time.time(),
            )
            self._dispatch_opportunity(opp, ambient_sensor.get_focus_state())

    def _on_direct_meeting(self, title: str, mins_until: int) -> None:
        """Triggered when calendar event enters 15-minute window."""
        pass  # Handled in _evaluate_calendar_agenda with cooldown

    # ─────────────────────────────────────────────────────────────────────────
    # Non-Intrusive Delivery Router (Apple HIG Etiquette)
    # ─────────────────────────────────────────────────────────────────────────

    def _dispatch_opportunity(self, opp: ProactiveOpportunity, focus_state: UserFocusState) -> None:
        """Routes opportunity according to strict etiquette guidelines."""
        self._active_opportunities[opp.opportunity_id] = opp
        self.set_cooldown(opp.cooldown_key)
        self.opportunity_detected.emit(opp)

        # 1. Level 3: Urgent (>= 0.85) AND user is NOT in active rapid typing
        if opp.urgency >= 0.85:
            if focus_state != UserFocusState.ACTIVE_TYPING:
                self.voice_alert_requested.emit(f"Boss, {opp.title.split(':')[-1].strip()}. {opp.subtitle}")
            self.toast_requested.emit(opp.title, opp.subtitle, "warning", opp.action_payload)

        # 2. Level 2: Medium (0.50 <= urgency < 0.85)
        elif opp.urgency >= 0.50:
            if focus_state == UserFocusState.FOCUSED_IDLE:
                self.toast_requested.emit(opp.title, opp.subtitle, "info", opp.action_payload)

        # 3. Level 1: Ambient / Tactical (< 0.50) -> Silent Smart Chips only
        self._emit_chips()

    def _emit_chips(self) -> None:
        """Updates UI subscribers with current top active chips."""
        chips = self.get_active_opportunities()
        self.chips_updated.emit(chips)


# Global Singleton Precognitive Engine
precognitive_engine = NEOPrecognitiveEngine()
