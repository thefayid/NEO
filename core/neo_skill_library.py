"""
core/neo_skill_library.py — Reusable Skill Library & Failure Lessons Engine for NEO.

Provides persistent storage, fuzzy retrieval, and session-start synthesis for:
1. Reusable Skill Routines:
   - Goal (intent / objective)
   - Preconditions (app, focus, window state, environment setup)
   - Exact verified steps (action list / tools dispatched)
   - Ready-signals (title changes, element visibility, spinner completions)
   - Replay rule: Always replay matching routine, but STILL verify every step (UIs change).
2. Failure Lessons:
   - Situation (what the agent was trying to accomplish)
   - What went wrong (root cause / deviation)
   - Rule to prevent it (preventative constraint)
   - Session Recall: Re-read at the start of every session to prevent past regressions.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_ROUTINES_FILE = _BASE_DIR / "memory" / "skill_routines.json"
_LESSONS_FILE = _BASE_DIR / "memory" / "lessons.json"


@dataclass
class SkillRoutine:
    name: str
    goal: str
    preconditions: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    ready_signals: List[str] = field(default_factory=list)
    success_count: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FailureLesson:
    situation: str
    what_went_wrong: str
    rule_to_prevent: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class NEOSkillLibrary:
    """
    Persistent skill library that records verified routines and failure lessons.
    Re-reads lessons at the start of every session and provides reusable routines.
    """

    def __init__(
        self,
        routines_path: Optional[Path] = None,
        lessons_path: Optional[Path] = None,
    ):
        self.routines_path = Path(routines_path) if routines_path else _ROUTINES_FILE
        self.lessons_path = Path(lessons_path) if lessons_path else _LESSONS_FILE
        self._lock = threading.Lock()
        self._routines: Dict[str, Dict[str, Any]] = {}
        self._lessons: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            # Load routines
            if self.routines_path.exists():
                try:
                    with open(self.routines_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self._routines = data.get("routines", {})
                except Exception as e:
                    logger.warning(f"[SkillLibrary] Routines load error: {e}")
            # Load lessons
            if self.lessons_path.exists():
                try:
                    with open(self.lessons_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self._lessons = data
                        elif isinstance(data, dict):
                            self._lessons = data.get("lessons", [])
                except Exception as e:
                    logger.warning(f"[SkillLibrary] Lessons load error: {e}")

    def _save_routines(self) -> None:
        try:
            self.routines_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.routines_path, "w", encoding="utf-8") as f:
                json.dump({"routines": self._routines, "updated_at": time.time()}, f, indent=2)
        except Exception as e:
            logger.warning(f"[SkillLibrary] Routines save error: {e}")

    def _save_lessons(self) -> None:
        try:
            self.lessons_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.lessons_path, "w", encoding="utf-8") as f:
                json.dump({"lessons": self._lessons, "updated_at": time.time()}, f, indent=2)
        except Exception as e:
            logger.warning(f"[SkillLibrary] Lessons save error: {e}")

    def save_routine(
        self,
        name: str,
        goal: str,
        preconditions: Union[List[str], str],
        steps: Union[List[str], str],
        ready_signals: Union[List[str], str],
    ) -> Dict[str, Any]:
        """Saves or updates a verified named routine."""
        clean_name = re.sub(r"[^\w\s-]", "", str(name or "")).strip().lower().replace(" ", "_")
        if not clean_name:
            clean_name = f"routine_{int(time.time())}"

        def _to_list(val: Union[List[str], str]) -> List[str]:
            if isinstance(val, list):
                return [str(v).strip() for v in val if str(v).strip()]
            if isinstance(val, str):
                lines = [line.strip().lstrip("•*-1234567890. ") for line in val.splitlines() if line.strip()]
                return lines if lines else ([val.strip()] if val.strip() else [])
            return []

        prec_list = _to_list(preconditions)
        steps_list = _to_list(steps)
        signals_list = _to_list(ready_signals)

        with self._lock:
            existing = self._routines.get(clean_name)
            count = (existing.get("success_count", 0) + 1) if existing else 1
            created = existing.get("created_at") if existing else datetime.now().isoformat()

            routine_data = {
                "name": clean_name,
                "goal": str(goal).strip(),
                "preconditions": prec_list,
                "steps": steps_list,
                "ready_signals": signals_list,
                "success_count": count,
                "created_at": created,
                "updated_at": datetime.now().isoformat(),
            }
            self._routines[clean_name] = routine_data
            self._save_routines()

        logger.info(f"[SkillLibrary] Saved routine '{clean_name}' (goal: {goal})")
        return routine_data

    def find_matching_routine(self, query: str) -> Optional[Dict[str, Any]]:
        """Finds the most relevant routine matching the user goal or task description."""
        q_clean = (query or "").lower().strip()
        if not q_clean:
            return None

        q_tokens = set(re.findall(r"\b\w{3,}\b", q_clean))
        if not q_tokens:
            return None

        best_match = None
        best_score = 0.0

        with self._lock:
            for name, r in self._routines.items():
                name_tokens = set(re.findall(r"\b\w{3,}\b", name.lower().replace("_", " ")))
                goal_tokens = set(re.findall(r"\b\w{3,}\b", r.get("goal", "").lower()))
                target_tokens = name_tokens | goal_tokens

                if not target_tokens:
                    continue

                intersection = q_tokens & target_tokens
                # Jaccard / overlap score
                score = len(intersection) / len(q_tokens | target_tokens)
                if score > best_score and score >= 0.15:
                    best_score = score
                    best_match = r

        return best_match

    def list_routines(self) -> List[Dict[str, Any]]:
        """Returns all registered routines."""
        with self._lock:
            return list(self._routines.values())

    def record_lesson(
        self,
        situation: str,
        what_went_wrong: str,
        rule_to_prevent: str,
    ) -> Dict[str, Any]:
        """Records a failure lesson: Situation, what went wrong, and the rule to prevent it."""
        sit = str(situation or "").strip()
        wrong = str(what_went_wrong or "").strip()
        rule = str(rule_to_prevent or "").strip()

        lesson = {
            "situation": sit,
            "what_went_wrong": wrong,
            "rule_to_prevent": rule,
            "timestamp": datetime.now().isoformat(),
        }

        with self._lock:
            self._lessons.append(lesson)
            # Cap lessons to most recent 100 to avoid runaway memory
            if len(self._lessons) > 100:
                self._lessons = self._lessons[-100:]
            self._save_lessons()

        logger.info(f"[SkillLibrary] Recorded failure lesson for situation: {sit}")
        return lesson

    def get_lessons(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the most recent failure lessons."""
        with self._lock:
            return list(self._lessons[-limit:])

    def synthesize_lessons_prompt(self, limit: int = 10) -> str:
        """Synthesizes the failure lessons context block to be re-read at the start of every session."""
        lessons = self.get_lessons(limit=limit)
        if not lessons:
            return ""

        lines = [
            "[FAILURE LESSONS & PREVENTATIVE RULES (Re-read at Session Start)]",
            "Review past failure lessons and adhere strictly to their preventative rules:"
        ]
        for idx, l in enumerate(lessons, 1):
            lines.append(
                f"{idx}. SITUATION: {l.get('situation', '')}\n"
                f"   WHAT WENT WRONG: {l.get('what_went_wrong', '')}\n"
                f"   RULE TO PREVENT IT: {l.get('rule_to_prevent', '')}"
            )
        lines.append("Never repeat any past failure. Always honor these rules.")
        return "\n".join(lines)

    def synthesize_routines_prompt(self, limit: int = 8) -> str:
        """Synthesizes available reusable skill routines for session context."""
        routines = self.list_routines()
        if not routines:
            return ""

        lines = [
            "[REUSABLE SKILL ROUTINE LIBRARY]",
            "Matching routines should be replayed for repeated tasks (verify every step as UIs change):"
        ]
        for r in routines[:limit]:
            prec_str = ", ".join(r.get("preconditions", [])) or "None"
            lines.append(
                f"• Routine '{r.get('name', '')}': Goal: {r.get('goal', '')} | Preconditions: {prec_str} | Steps: {len(r.get('steps', []))} verified steps"
            )
        return "\n".join(lines)


# Singleton instance
skill_library = NEOSkillLibrary()

