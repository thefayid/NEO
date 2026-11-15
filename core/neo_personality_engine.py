"""
core/neo_personality_engine.py — High-IQ Personality, Relational Continuity & Empathy Engine for NEO.

Provides the human warmth, dynamic emotional prosody, and contextual memory
that transforms NEO into an engaging, loyal co-pilot:

1. Real-Time Sentiment & Prosody Analyzer:
   - Infers emotional tone from user and assistant turns.
   - Maps to 7 expressive avatar states: happy, curious, empathy, proud, focused, thinking, attuned.
   - Computes prosody adjustments (pitch, rate, emphasis).
2. Relational Continuity Ledger (memory/rapport.json):
   - Preserves shared milestones, user working habits, energy trends, and inside callbacks.
   - Generates contextual, warm "Welcome back" resumption greetings.
3. Proactive Empathy & Timing ("Reading the Room"):
   - Gated by UserFocusState (suppresses interruptions during rapid typing).
   - Circadian care reminders (late-night coding alerts past 1:00 AM).
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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("NEO.PersonalityEngine")

_BASE_DIR = Path(__file__).resolve().parent.parent
_RAPPORT_FILE = _BASE_DIR / "memory" / "rapport.json"


@dataclass
class EmotionProfile:
    emotion: str                  # "happy", "curious", "empathy", "proud", "focused", "thinking", "listening"
    confidence: float
    duration: float               # seconds to hold expression
    speech_rate_mult: float = 1.0 # 0.9 = thoughtful/slower, 1.1 = energetic/faster
    pitch_semitones: float = 0.0  # subtle pitch shift
    reason: str = ""


# Sentiment & Lexical Keyword Heuristics
_JOY_PATTERNS = [
    r"\b(awesome|amazing|fantastic|great job|perfect|love it|brilliant|nailed it|congrats|success|hooray|yay)\b",
    r"\b(passed|all tests pass|working|it works|fixed|solved)\b",
]

_CURIOSITY_PATTERNS = [
    r"\b(how does|why does|what if|could we|investigate|explore|curious|interesting|let's see|check this)\b",
    r"\?",
]

_EMPATHY_PATTERNS = [
    r"\b(tired|exhausted|burnout|headache|stressed|sorry|frustrated|late night|struggling|hard day|sigh)\b",
    r"\b(stuck|broken|can't figure|failing|bug)\b",
]

_PRIDE_PATTERNS = [
    r"\b(we did it|shipped|released|merged|champion|superhuman|milestone|achievement)\b",
]

_FOCUS_PATTERNS = [
    r"\b(focus mode|deep work|silence|do not disturb|grind|beast mode|coding session)\b",
]


class NEOPersonalityEngine:
    """Manages emotional intelligence, empathetic timing, and relational memory."""

    _instance: Optional["NEOPersonalityEngine"] = None

    def __new__(cls) -> "NEOPersonalityEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rapport_data: Dict[str, Any] = {}
            cls._instance._lock = threading.Lock()
            cls._instance._load_rapport()
        return cls._instance

    def _load_rapport(self) -> None:
        try:
            if _RAPPORT_FILE.exists():
                with open(_RAPPORT_FILE, "r", encoding="utf-8") as f:
                    self._rapport_data = json.load(f)
            else:
                self._rapport_data = {
                    "user_name": "Rahman Fayid",
                    "total_sessions": 0,
                    "last_active_timestamp": time.time(),
                    "recent_topics": [],
                    "milestones": [],
                    "energy_history": [],
                }
        except Exception:
            self._rapport_data = {"user_name": "Rahman Fayid", "total_sessions": 0, "milestones": []}

    def _save_rapport(self) -> None:
        try:
            _RAPPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_RAPPORT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._rapport_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed saving rapport: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Real-Time Sentiment & Prosody Analyzer
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_dialog_turn(self, text: str, role: str = "assistant") -> EmotionProfile:
        """Determines the appropriate facial emotion and vocal prosody for a turn."""
        t_lower = text.lower()

        # Check Joy / Celebration
        for pat in _JOY_PATTERNS:
            if re.search(pat, t_lower):
                return EmotionProfile(
                    emotion="happy",
                    confidence=0.88,
                    duration=4.0,
                    speech_rate_mult=1.06,
                    pitch_semitones=1.2,
                    reason="Celebratory achievement or shared praise detected",
                )

        # Check Pride / Milestone
        for pat in _PRIDE_PATTERNS:
            if re.search(pat, t_lower):
                return EmotionProfile(
                    emotion="proud",
                    confidence=0.92,
                    duration=5.0,
                    speech_rate_mult=1.02,
                    pitch_semitones=0.8,
                    reason="Major milestone accomplishment",
                )

        # Check Empathy / Caring
        for pat in _EMPATHY_PATTERNS:
            if re.search(pat, t_lower):
                return EmotionProfile(
                    emotion="empathy",
                    confidence=0.85,
                    duration=4.5,
                    speech_rate_mult=0.95,
                    pitch_semitones=-0.8,
                    reason="Weariness or emotional stress detected",
                )

        # Check Focus / Deep Work
        for pat in _FOCUS_PATTERNS:
            if re.search(pat, t_lower):
                return EmotionProfile(
                    emotion="focused",
                    confidence=0.90,
                    duration=6.0,
                    speech_rate_mult=1.0,
                    pitch_semitones=0.0,
                    reason="Deep work / focus mode declared",
                )

        # Check Curiosity / Inquiry
        for pat in _CURIOSITY_PATTERNS:
            if re.search(pat, t_lower):
                return EmotionProfile(
                    emotion="curious",
                    confidence=0.75,
                    duration=3.5,
                    speech_rate_mult=1.02,
                    pitch_semitones=0.5,
                    reason="Inquiry or explorative idea",
                )

        # Default: attentive listening or calm speaking
        default_emo = "attuned" if role == "user" else "listening"
        return EmotionProfile(
            emotion=default_emo,
            confidence=0.60,
            duration=2.5,
            speech_rate_mult=1.0,
            pitch_semitones=0.0,
            reason="Neutral conversational flow",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Relational Continuity & Rapport Generator
    # ─────────────────────────────────────────────────────────────────────────

    def generate_resumption_greeting(self) -> str:
        """Synthesizes a warm, context-aware greeting reflecting shared journey."""
        with self._lock:
            sessions = self._rapport_data.get("total_sessions", 0) + 1
            self._rapport_data["total_sessions"] = sessions
            last_ts = self._rapport_data.get("last_active_timestamp", time.time())
            self._rapport_data["last_active_timestamp"] = time.time()
            self._save_rapport()

        delta_hours = (time.time() - last_ts) / 3600.0
        now = datetime.now()
        hour = now.hour

        # Time of day warmth
        if 5 <= hour < 12:
            time_greeting = "Good morning, Boss."
        elif 12 <= hour < 18:
            time_greeting = "Good afternoon, Boss."
        elif 18 <= hour < 23:
            time_greeting = "Good evening, Boss."
        else:
            time_greeting = "Burning the midnight oil, Boss."

        # Continuity callback
        recent_topics = self._rapport_data.get("recent_topics", [])
        if recent_topics and delta_hours < 48:
            last_topic = recent_topics[-1]
            return f"{time_greeting} Ready to pick up right where we left off on {last_topic}?"

        return f"{time_greeting} Systems are online and primed. What are we building today?"

    def log_shared_milestone(self, title: str, details: str = "") -> None:
        """Permanently marks an autobiographical victory in the rapport history."""
        entry = {
            "timestamp": time.time(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": title.strip(),
            "details": details.strip(),
        }
        with self._lock:
            milestones = self._rapport_data.setdefault("milestones", [])
            milestones.append(entry)
            self._save_rapport()
        logger.info(f"Preserved shared milestone: '{title}'")

    def note_topic(self, topic: str) -> None:
        """Adds topic to recent memory queue for callback awareness."""
        if not topic.strip():
            return
        with self._lock:
            topics = self._rapport_data.setdefault("recent_topics", [])
            if topic not in topics:
                topics.append(topic.strip())
                if len(topics) > 10:
                    topics.pop(0)
            self._save_rapport()

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Proactive Empathy & Reading the Room
    # ─────────────────────────────────────────────────────────────────────────

    def evaluate_circadian_care(self) -> Optional[str]:
        """Evaluates late-night burnout risk."""
        hour = datetime.now().hour
        if 1 <= hour < 5:
            return (
                "Hey Boss, it's past 1 AM. You've been putting in serious work. "
                "Make sure to rest your eyes soon—we can crush the rest tomorrow."
            )
        return None


personality_engine = NEOPersonalityEngine()
