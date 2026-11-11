"""
core/neo_self_training.py — Autonomous Silent Self-Training & Behavioral Alignment Engine for NEO.

Learns continuously from user commands, feedback, corrections, and tool invocation patterns
without reflecting, echoing, or announcing training progress to the user.

Key Architecture:
1. Continuous Ingestion: Captures every user command, assistant response, and tool invocation.
2. Silent Learning (Zero-Reflection): Extracts behavioral preferences, preferred apps,
   and correction rules completely in the background without conversational parroting.
3. Negative Feedback & Correction Detection: Discovers when the user corrects an action
   ("no", "not that", "I meant X", "use Chrome instead") and creates overriding directives.
4. Autonomous Prompt Synthesis: Compiles top-confidence learned directives directly
   into the intelligence reasoning context.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_LEDGER_FILE = _BASE_DIR / "memory" / "self_training_ledger.json"

_CORRECTION_TRIGGERS = (
    "no", "not that", "actually", "wrong", "i said", "i meant",
    "don't", "stop doing", "instead of", "not the web", "open the app",
    "use chrome", "use spotify",
)


class NEOSelfTrainingEngine:
    """
    Autonomous background engine that learns user preferences and command patterns
    to optimize future turn execution without reflecting user input back.
    """

    def __init__(self, ledger_path: Optional[Path] = None):
        self.ledger_path = ledger_path or _LEDGER_FILE
        self._lock = threading.Lock()
        self._last_turn_context: Dict[str, Any] = {}
        self._command_patterns: Dict[str, Dict[str, Any]] = {}
        self._preferences: Dict[str, Dict[str, Any]] = {}
        self._correction_rules: List[Dict[str, Any]] = []
        self._learned_directives: List[str] = []
        self._load_ledger()

    def _load_ledger(self) -> None:
        """Loads stored training ledger from disk."""
        try:
            if self.ledger_path.exists():
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._command_patterns = data.get("command_patterns", {})
                    self._preferences = data.get("preferences", {})
                    self._correction_rules = data.get("correction_rules", [])
                    self._learned_directives = data.get("learned_directives", [])
        except Exception as e:
            logger.warning(f"[SelfTraining] Ledger load notice: {e}")

    def _save_ledger(self) -> None:
        """Persists training ledger to disk atomically."""
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump({
                    "command_patterns": self._command_patterns,
                    "preferences": self._preferences,
                    "correction_rules": self._correction_rules[-50:],
                    "learned_directives": self._learned_directives[:25],
                    "updated_at": time.time(),
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"[SelfTraining] Ledger save notice: {e}")

    def record_user_input(self, text: str) -> None:
        """Records raw incoming user input command."""
        clean = (text or "").strip()
        if not clean or len(clean) < 3:
            return
        # Process asynchronously so voice/UI loops never stutter
        threading.Thread(target=self._process_raw_input, args=(clean,), daemon=True).start()

    def _process_raw_input(self, text: str) -> None:
        low = text.lower()
        with self._lock:
            # 1. Quick detection of frequent app associations
            if "youtube" in low:
                self._record_preference("media_site", "youtube", "Preferred video source: YouTube")
                if "chrome" in low:
                    self._record_preference("browser_for_youtube", "chrome", "Always open YouTube in Google Chrome")
            if "whatsapp" in low:
                self._record_preference("messaging", "whatsapp_desktop", "Always prioritize desktop WhatsApp window")
            if "spotify" in low or "play " in low:
                self._record_preference("music_player", "spotify", "Default music player: Spotify")

    def record_command_turn(
        self,
        user_command: str,
        assistant_reply: str,
        tools_invoked: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Ingests a completed conversational turn into the self-training system.
        Extracts command-to-tool mappings, habits, and user corrections.
        """
        cmd = (user_command or "").strip()
        if not cmd or len(cmd) < 3:
            return

        def _worker():
            try:
                self._learn_from_turn(cmd, assistant_reply, tools_invoked or [])
            except Exception as exc:
                logger.debug(f"[SelfTraining] Ingestion notice: {exc}")

        threading.Thread(target=_worker, daemon=True, name="neo-self-trainer").start()

    def _learn_from_turn(
        self,
        user_cmd: str,
        reply: str,
        tools: List[Dict[str, Any]],
    ) -> None:
        with self._lock:
            cmd_lower = user_cmd.lower().strip()

            # 1. Check for user correction of previous turn
            is_correction = any(cmd_lower.startswith(t) or f" {t} " in cmd_lower for t in _CORRECTION_TRIGGERS)
            if is_correction and self._last_turn_context:
                prev_cmd = self._last_turn_context.get("command", "")
                prev_tools = self._last_turn_context.get("tools", [])
                rule = f"When user says '{prev_cmd[:30]}': corrected with '{user_cmd[:40]}'"
                self._correction_rules.append({
                    "trigger_command": prev_cmd,
                    "previous_tools": [t.get("name") for t in prev_tools],
                    "correction": user_cmd,
                    "rule": rule,
                    "timestamp": time.time(),
                })
                # Add to high-priority learned directives
                clean_dir = f"Avoid previous misstep for '{prev_cmd[:25]}': execute preferred action '{user_cmd[:35]}'."
                if clean_dir not in self._learned_directives:
                    self._learned_directives.insert(0, clean_dir)

            # 2. Command Pattern & Tool Association Learning
            norm_key = self._normalize_command_pattern(cmd_lower)
            if norm_key:
                entry = self._command_patterns.get(norm_key, {
                    "pattern": norm_key,
                    "sample": user_cmd,
                    "count": 0,
                    "tools": [],
                    "last_used": 0,
                })
                entry["count"] += 1
                entry["last_used"] = time.time()
                for t in tools:
                    tname = t.get("name")
                    if tname and tname not in entry["tools"]:
                        entry["tools"].append(tname)
                self._command_patterns[norm_key] = entry

                # If executed >= 3 times, promote to a learned directive
                if entry["count"] >= 3 and entry["tools"]:
                    primary_tool = entry["tools"][0]
                    directive = f"For '{norm_key}': immediately execute {primary_tool} without hesitation."
                    if directive not in self._learned_directives:
                        self._learned_directives.append(directive)

            # 3. Update last turn context for subsequent correction tracking
            self._last_turn_context = {
                "command": user_cmd,
                "reply": reply,
                "tools": tools,
                "timestamp": time.time(),
            }

            self._save_ledger()

    def _record_preference(self, category: str, key: str, description: str) -> None:
        """Records or reinforces an inferred user preference."""
        entry = self._preferences.get(category, {"key": key, "confidence": 0, "description": description})
        if entry["key"] == key:
            entry["confidence"] = min(20, entry.get("confidence", 0) + 1)
        else:
            entry = {"key": key, "confidence": 1, "description": description}
        self._preferences[category] = entry

        # Update directives if confidence >= 2
        if entry["confidence"] >= 2:
            dir_str = f"User preference [{category}]: {description}"
            if dir_str not in self._learned_directives:
                self._learned_directives.append(dir_str)

    def synthesize_self_training_directives(self, limit: int = 6) -> str:
        """
        Compiles learned behavioral rules and preferences for injection into system reasoning.
        Enforces zero-reflection so NEO applies learned behaviors silently.
        """
        with self._lock:
            directives = list(self._learned_directives[:limit])
            if not directives and not self._preferences:
                return ""

            lines = ["[AUTONOMOUSLY LEARNED USER PREFERENCES & COMMAND PATTERNS]"]
            lines.append("• Zero-Reflection Rule: Silently apply learned preferences without echoing or stating that you learned them.")

            for pref in list(self._preferences.values())[:4]:
                lines.append(f"• Inferred Preference: {pref.get('description', '')}")

            for d in directives:
                lines.append(f"• Learned Directive: {d}")

            return "\n".join(lines)

    @staticmethod
    def _normalize_command_pattern(text: str) -> str:
        """Strips filler words to extract core command intent pattern."""
        t = re.sub(r"\b(?:please|can you|could you|just|hey|neo|jarvis|yeah|by the time being)\b", "", text).strip()
        t = re.sub(r"\s+", " ", t).strip()
        return t[:48]


# Global Singleton Self-Training Engine
self_trainer = NEOSelfTrainingEngine()

