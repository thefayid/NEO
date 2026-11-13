"""
core/neo_reinforcement_learning.py — Real-Time Contextual Q-Learning & Policy Reinforcement Engine for NEO.

Implements an adaptive Reinforcement Learning (RL) policy:
1. Environment State (S):
   - User command intent & keywords
   - Active foreground window / application context
   - Time bucket (morning, afternoon, evening, night)
2. Action Space (A):
   - Available tools and invocation parameter signatures
3. Reward Function (R):
   - Tool verified execution (+1.2)
   - Verified done confirmation (+0.8)
   - Fast sub-second execution bonus (+0.3)
   - Tool execution failure / error (-2.0 to -2.5)
   - Explicit user praise ("thanks", "perfect", "great") (+2.0)
   - User rejection / correction / undo ("no", "stop", "wrong", "undo") (-3.0)
4. Policy & Learning Update:
   - Temporal Difference / Q-Learning: Q(S,A) <- Q(S,A) + alpha * [R - Q(S,A)]
   - Upper Confidence Bound (UCB1) exploration vs exploitation score
   - Zero-Reflection: completely autonomous, silent background execution
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_RL_STORE_FILE = _BASE_DIR / "memory" / "rl_q_values.json"

_PRAISE_KEYWORDS = {
    "thanks", "thank you", "perfect", "great", "awesome", "excellent",
    "good job", "nice", "well done", "exactly", "sweet", "superb",
}

_PENALTY_KEYWORDS = {
    "no", "not that", "stop", "wrong", "undo", "cancel", "actually no",
    "don't", "terrible", "bad", "shut up", "that's not what i asked",
}


@dataclass
class QEntry:
    q_value: float = 0.0          # Estimated expected reward
    visits: int = 0               # Times (S, A) was chosen
    successes: int = 0            # Verified successful runs
    failures: int = 0             # Failed or rejected runs
    last_reward: float = 0.0      # Most recent scalar reward
    last_updated: float = 0.0     # Wall-clock timestamp


@dataclass
class RLPolicyRecommendation:
    action_name: str
    q_value: float
    confidence: float
    visits: int
    recommendation_text: str


class NEOReinforcementLearner:
    """
    Real-time Contextual Q-Learning & Policy Reinforcement Engine.
    Learns the optimal tool and trajectory for every desktop and command context.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or _RL_STORE_FILE
        self._lock = threading.Lock()
        self._q_table: Dict[str, Dict[str, QEntry]] = {}  # state_key -> {action_name -> QEntry}
        self._last_state_action: Optional[Tuple[str, str, float]] = None  # (state, action, start_time)
        self._load_q_table()

    def _load_q_table(self) -> None:
        """Loads persistent Q-table from disk."""
        try:
            if self.store_path.exists():
                with open(self.store_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for s_key, actions in raw.get("states", {}).items():
                        self._q_table[s_key] = {}
                        for a_name, entry_data in actions.items():
                            self._q_table[s_key][a_name] = QEntry(**entry_data)
        except Exception as e:
            logger.debug(f"[RL] Table load note: {e}")

        # Seed core high-confidence policies if empty
        if not self._q_table:
            self._q_table["read_whatsapp@any#any"] = {
                "read_messages": QEntry(q_value=1.0, visits=5, successes=5)
            }
            self._q_table["open_youtube@any#any"] = {
                "browser_control": QEntry(q_value=1.0, visits=5, successes=5)
            }
            self._q_table["visual_screen@any#any"] = {
                "visual_screen_grounding": QEntry(q_value=1.0, visits=5, successes=5)
            }

    def _save_q_table(self) -> None:
        """Persists Q-table to disk atomically using temporary file + rename."""
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            export_data: Dict[str, Any] = {"states": {}, "updated_at": time.time()}
            for s_key, actions in self._q_table.items():
                export_data["states"][s_key] = {
                    a_name: asdict(entry) for a_name, entry in actions.items()
                }
            tmp_path = self.store_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            os.replace(tmp_path, self.store_path)
        except Exception as e:
            logger.debug(f"[RL] Table save note: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. State Feature Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def get_state_key(self, user_command: str, active_app: str = "") -> str:
        """
        Extracts a discrete contextual state key S based on command intent root,
        active desktop application, and time bucket.
        """
        cmd_clean = (user_command or "").lower().strip()
        # Extract intent root
        intent = self._extract_intent_root(cmd_clean)

        # Context app
        app = (active_app or "desktop").lower().strip()
        app_tag = "browser" if any(b in app for b in ("chrome", "edge", "firefox", "brave")) else (
            "ide" if any(i in app for i in ("code", "cursor", "pycharm")) else (
                "comm" if any(c in app for c in ("whatsapp", "telegram", "discord")) else app[:12]
            )
        )

        # Time bucket
        hr = datetime.now().hour
        time_tag = "morning" if 6 <= hr < 12 else (
            "afternoon" if 12 <= hr < 18 else ("evening" if 18 <= hr < 23 else "night")
        )

        return f"{intent}@{app_tag}#{time_tag}"

    def _extract_intent_root(self, text: str) -> str:
        """Extracts the primary semantic verb/target tuple from natural prose."""
        t = re.sub(r"\b(?:please|can you|could you|just|hey|neo|jarvis|yeah|by the time being)\b", "", text).strip()
        if not t:
            return "general"

        if "youtube" in t:
            return "open_youtube"
        elif "whatsapp" in t:
            return "read_whatsapp" if any(w in t for w in ("read", "take", "chat", "messages")) else "send_whatsapp"
        elif "telegram" in t:
            return "telegram_chat"
        elif "spotify" in t or "play " in t or "song" in t or "music" in t:
            return "media_playback"
        elif "camera" in t or "webcam" in t:
            return "camera_feed"
        elif "chrome" in t or "browse" in t or "search" in t:
            return "web_navigation"
        elif "screen" in t or "look at" in t:
            return "visual_screen"
        elif "volume" in t:
            return "system_volume"

        tokens = re.findall(r"[a-z0-9_]{3,}", t)
        return "_".join(tokens[:2]) if tokens else "general"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Reinforcement Signal Ingestion & Q-Update
    # ─────────────────────────────────────────────────────────────────────────

    def record_tool_start(self, tool_name: str, user_command: str = "", active_app: str = "") -> None:
        """Records the start of action selection to measure execution latency."""
        state_key = self.get_state_key(user_command, active_app)
        self._last_state_action = (state_key, tool_name, time.time())

    def record_tool_outcome(
        self,
        tool_name: str,
        outcome_result: str,
        user_command: str = "",
        active_app: str = "",
    ) -> float:
        """
        Evaluates tool outcome and applies real-time TD Q-learning update.
        Returns the calculated reward scalar.
        """
        now = time.time()
        state_key = self.get_state_key(user_command, active_app)

        # 1. Calculate Reward Scalar
        reward = 0.0
        out_str = str(outcome_result or "").lower()

        if "status=done" in out_str or "done" in out_str:
            reward += 1.2
            if "verified=true" in out_str or "verified" in out_str:
                reward += 0.8
        elif "status=failed" in out_str or "failed" in out_str or "error" in out_str:
            reward -= 2.0
        elif "status=unverified" in out_str:
            reward += 0.2
        else:
            reward += 0.5  # Standard non-empty output

        # Latency bonus: fast execution (< 1.2s) receives positive reward
        if self._last_state_action and self._last_state_action[1] == tool_name:
            duration = now - self._last_state_action[2]
            if duration < 1.2:
                reward += 0.3
            elif duration > 10.0:
                reward -= 0.2

        # 2. Async Q-Learning Update
        is_success = (reward > 0)
        threading.Thread(
            target=self._update_q_entry,
            args=(state_key, tool_name, reward, is_success),
            daemon=True,
            name="neo-rl-updater"
        ).start()

        return reward

    def record_user_feedback(self, user_text: str) -> Optional[float]:
        """
        Evaluates implicit verbal sentiment / feedback from the user.
        Boosts reward on praise (+2.0) or penalizes on rejection/correction (-3.0).
        """
        low = (user_text or "").lower().strip()
        if not low or not self._last_state_action:
            return None

        state_key, last_action, _ = self._last_state_action

        # Check praise
        is_praise = any(p in low for p in _PRAISE_KEYWORDS)
        # Check rejection / penalty
        is_penalty = any(low.startswith(p) or f" {p} " in low for p in _PENALTY_KEYWORDS)

        if is_praise:
            reward = 2.0
            threading.Thread(
                target=self._update_q_entry,
                args=(state_key, last_action, reward, True),
                daemon=True,
            ).start()
            return reward
        elif is_penalty:
            reward = -3.0
            threading.Thread(
                target=self._update_q_entry,
                args=(state_key, last_action, reward, False),
                daemon=True,
            ).start()
            return reward

        return None

    def _update_q_entry(self, state_key: str, action_name: str, reward: float, is_success: bool) -> None:
        """Applies Temporal Difference / Q-Learning update rule."""
        with self._lock:
            if state_key not in self._q_table:
                self._q_table[state_key] = {}

            entry = self._q_table[state_key].get(action_name)
            if not entry:
                entry = QEntry()
                self._q_table[state_key][action_name] = entry

            entry.visits += 1
            if is_success:
                entry.successes += 1
            else:
                entry.failures += 1

            # Adaptive Robbins-Monro learning rate: alpha decays as visits increase
            alpha = max(0.08, min(0.45, 1.0 / math.sqrt(entry.visits)))

            # TD-Update: Q <- Q + alpha * (R - Q)
            clipped_r = max(-5.0, min(5.0, reward))
            entry.q_value += alpha * (clipped_r - entry.q_value)
            entry.last_reward = clipped_r
            entry.last_updated = time.time()

            self._save_q_table()

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Policy Recommendation & UCB1 Action Selection
    # ─────────────────────────────────────────────────────────────────────────

    def get_policy_recommendation(
        self,
        user_command: str,
        active_app: str = "",
    ) -> Optional[RLPolicyRecommendation]:
        """
        Computes the highest-value action for the current state using Upper Confidence Bound (UCB1).
        """
        state_key = self.get_state_key(user_command, active_app)

        with self._lock:
            actions = self._q_table.get(state_key)
            if not actions:
                # Try generic state lookup
                intent_only = state_key.split("@")[0]
                for sk, acts in self._q_table.items():
                    if sk.startswith(intent_only):
                        actions = acts
                        break

            if not actions:
                return None

            total_visits = sum(e.visits for e in actions.values())
            c = 0.85  # UCB Exploration parameter

            best_action = None
            best_score = -float("inf")

            for a_name, entry in actions.items():
                if entry.visits > 0:
                    bonus = c * math.sqrt(math.log(max(1, total_visits)) / entry.visits)
                    score = entry.q_value + bonus
                else:
                    score = entry.q_value + 1.0  # Encourage trying unvisited action

                if score > best_score:
                    best_score = score
                    best_action = (a_name, entry)

            if not best_action:
                return None

            a_name, entry = best_action
            conf = min(0.99, max(0.1, (entry.successes / max(1, entry.visits)) if entry.visits >= 2 else 0.5))

            return RLPolicyRecommendation(
                action_name=a_name,
                q_value=round(entry.q_value, 2),
                confidence=round(conf, 2),
                visits=entry.visits,
                recommendation_text=(
                    f"Optimal RL Policy: prioritize tool '{a_name}' "
                    f"(Learned Value Q={entry.q_value:+.2f}, Success Rate={conf:.0%}, Visits={entry.visits})."
                )
            )

    def get_top_policies(self, limit: int = 5) -> List[Tuple[str, str, float, float]]:
        """Returns the top reinforced policies across all learned states."""
        with self._lock:
            best_by_intent: Dict[str, Tuple[str, float, float, int]] = {}
            for state_key, actions in self._q_table.items():
                intent = state_key.split("@")[0] if "@" in state_key else state_key
                for a_name, entry in actions.items():
                    if entry.visits < 1:
                        continue
                    conf = min(0.99, max(0.1, (entry.successes / max(1, entry.visits))))
                    if intent not in best_by_intent or entry.q_value > best_by_intent[intent][1]:
                        best_by_intent[intent] = (a_name, entry.q_value, conf, entry.visits)

            sorted_policies = sorted(
                [(intent, data[0], data[1], data[2]) for intent, data in best_by_intent.items()],
                key=lambda x: -x[2] * x[3] if len(x) > 3 and x[3] else -x[2]
            )
            return sorted_policies[:limit]

    def synthesize_rl_prompt(self, current_command: str = "", active_app: str = "") -> str:
        """
        Synthesizes active RL policy guidance directly for LLM system instructions.
        Ensures zero-reflection: tells the agent how to act without echoing user words.
        """
        if current_command:
            rec = self.get_policy_recommendation(current_command, active_app)
            if rec and rec.visits >= 1:
                lines = ["[REINFORCEMENT LEARNING POLICY (Q-OPTIMIZED)]"]
                lines.append(f"• {rec.recommendation_text}")
                lines.append("• Zero-Reflection Policy: Silently execute the optimal policy without mentioning Q-values or training.")
                return "\n".join(lines)

        top_policies = self.get_top_policies(limit=5)
        if not top_policies:
            return ""

        lines = ["[REINFORCEMENT LEARNING POLICIES (Q-OPTIMIZED)]"]
        for intent, a_name, q_val, conf in top_policies:
            lines.append(f"• In context '{intent}': prioritize tool '{a_name}' (learned Q={q_val:+.2f}, success={conf:.0%}).")
        lines.append("• Zero-Reflection Policy: Silently execute without echoing user words or mentioning Q-values.")
        return "\n".join(lines)


# Global Singleton Reinforcement Learner
rl_learner = NEOReinforcementLearner()
