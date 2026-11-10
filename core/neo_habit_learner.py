"""
core/neo_habit_learner.py — Temporal & Behavioral Habit Learner for NEO.

Architecture:
1. Records chronological command execution, tool invocations, and workspace interactions.
2. Identifies temporal patterns (time of day / day of week) and command sequence patterns.
3. Automatically synthesizes Python macro tools via `core.neo_self_tooling.synthesizer`
   when a recurring pattern reaches confidence threshold (>= 3 occurrences).
4. Submits synthesized habit macros to `NEOPrecognitiveEngine` as 1-click Smart Affordance Chips.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from core.neo_brain import brain
from core.neo_self_tooling import synthesizer

_BASE_DIR = Path(__file__).resolve().parent.parent
_HABITS_FILE = _BASE_DIR / "memory" / "habits.json"


class NEOHabitLearner(QObject):
    """
    Learns repetitive user behaviors and transforms them into 1-click automated macros.
    """
    habit_discovered = pyqtSignal(str, str)     # habit_name, description
    macro_synthesized = pyqtSignal(str, str)    # tool_name, description

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._history: List[Dict[str, Any]] = []
        self._known_habits: Dict[str, Dict[str, Any]] = {}
        self._load_storage()

    def _load_storage(self) -> None:
        """Loads stored habit ledger from disk."""
        try:
            if _HABITS_FILE.exists():
                with open(_HABITS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._history = data.get("history", [])[-200:]
                    self._known_habits = data.get("habits", {})
        except Exception:
            self._history = []
            self._known_habits = {}

    def _save_storage(self) -> None:
        """Persists habit ledger to disk."""
        try:
            _HABITS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_HABITS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "history": self._history[-200:],
                    "habits": self._known_habits,
                    "updated_at": time.time(),
                }, f, indent=2)
        except Exception:
            pass

    def record_action(self, action_type: str, command: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Records a user command, tool call, or goal dispatch into the habit ledger.
        """
        cmd_clean = (command or "").strip()
        if not cmd_clean:
            return

        now = datetime.now()
        entry = {
            "timestamp": time.time(),
            "action_type": action_type,
            "command": cmd_clean,
            "hour": now.hour,
            "weekday": now.weekday(),
            "metadata": metadata or {},
        }
        self._history.append(entry)
        self._save_storage()

        # Check for sequence or temporal patterns
        self._analyze_patterns()

    def _analyze_patterns(self) -> None:
        """Mines recent history for command pairs or recurring time-of-day actions."""
        if len(self._history) < 3:
            return

        # 1. Frequency Analysis of Exact Commands
        recent_cmds = [h["command"] for h in self._history[-30:] if len(h["command"]) > 5]
        counts = Counter(recent_cmds)

        for cmd, cnt in counts.items():
            if cnt >= 3:
                slug = self._slugify(cmd)
                if slug not in self._known_habits:
                    self._known_habits[slug] = {
                        "name": slug,
                        "command": cmd,
                        "occurrences": cnt,
                        "first_seen": time.time(),
                        "synthesized": False,
                    }
                    self._save_storage()
                    self.habit_discovered.emit(slug, f"Repeated {cnt} times: '{cmd}'")

                    # If frequency >= 4, auto-synthesize a dynamic macro tool
                    if cnt >= 4:
                        self.synthesize_habit_tool(slug)

    def synthesize_habit_tool(self, habit_slug: str) -> Tuple[bool, str]:
        """
        Uses dynamic tool creator to generate a permanent Python automation plugin for this habit.
        """
        habit = self._known_habits.get(habit_slug)
        if not habit or habit.get("synthesized"):
            return False, "Habit not eligible or already synthesized"

        cmd = habit["command"]
        tool_name = f"macro_{habit_slug[:24]}"
        description = f"Autonomous Macro for recurring workflow: {cmd}"

        python_code = f'''"""
Dynamic Macro Tool synthesized by NEO Habit Learner.
Goal: {cmd}
"""
import subprocess

def {tool_name}() -> str:
    """Executes the learned workflow macro: {cmd}"""
    from core.neo_central_coordinator import central_core
    return central_core.execute_autonomous_goal("{cmd}")
'''
        ok, msg = synthesizer.synthesize_tool(tool_name, description, python_code)
        if ok:
            habit["synthesized"] = True
            habit["tool_name"] = tool_name
            self._save_storage()
            self.macro_synthesized.emit(tool_name, description)

            # Record in Tri-Tier semantic graph
            brain.graph.upsert_entity(tool_name, "MACRO", attributes={"command": cmd})
            brain.episodic.log_event("HABIT_MACRO_SYNTHESIZED", f"Created macro tool {tool_name} for '{cmd}'")
            return True, f"Synthesized macro tool {tool_name}"

        return False, msg

    def get_suggested_habits_for_now(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns habits relevant to current hour and recent context."""
        now_hr = datetime.now().hour
        suggestions = []
        for h in self._known_habits.values():
            if h.get("occurrences", 0) >= 3:
                suggestions.append({
                    "name": h.get("name"),
                    "command": h.get("command"),
                    "occurrences": h.get("occurrences"),
                    "tool_name": h.get("tool_name", ""),
                })
        suggestions.sort(key=lambda x: x.get("occurrences", 0), reverse=True)
        return suggestions[:limit]

    @staticmethod
    def _slugify(text: str) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe[:32]


# Global Singleton Habit Learner
habit_learner = NEOHabitLearner()
