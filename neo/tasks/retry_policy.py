"""
neo/tasks/retry_policy.py — Loop Detection, Step/Task Budgets, and Multi-Tier Retry Policy.

Architectural Guarantees:
1. Comprehensive Loop Detection:
   - Detects consecutive identical actions (e.g. repeated failing clicks or inputs).
   - Detects oscillatory action cycles (e.g. [A, B, A, B]).
   - Detects frozen or cycling system states via state hashing.
2. Rigid Step & Task Budgets:
   - Enforces per-stage step limit and overall task step limit (default 25).
3. 3-Attempt Multi-Tier Retry Policy:
   - 3 attempts per tier:
     * Tier 1: Primary deterministic method (UIA invoke/value, Playwright DOM, safe file API).
     * Tier 2: Alternative interaction method (mouse click, keyboard hotkey/text, window refocus).
     * Tier 3: Vision fallback (OCR grounding, click_xy with visual diff verification).
     * Tier 4 / Human Handover: When Tier 3 fails or 3 tiers are exhausted, escalates to the user.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from neo.brain.schema import ActionLoopDetectedError, EscalationRequiredError

logger = logging.getLogger("neo.tasks.retry_policy")


class MethodTier(str, Enum):
    TIER_1_PRIMARY = "tier_1_primary"          # Native UIA invoke / DOM / Direct API
    TIER_2_ALTERNATIVE = "tier_2_alternative"  # Mouse click / Keyboard emulation / Refocus
    TIER_3_VISION = "tier_3_vision"            # Native OCR / Vision click_xy
    ESCALATION = "escalation"                  # Escalate to human user ("ask me")


@dataclass(frozen=True)
class ActionFingerprint:
    """Immutable signature representing an action and its primary target/parameters."""
    action: str
    target: str
    params_hash: str
    ok: bool

    @classmethod
    def create(cls, action: str, parameters: Optional[Dict[str, Any]] = None, ok: bool = True) -> ActionFingerprint:
        params = dict(parameters or {})
        target = str(params.get("target_id") or params.get("element_id") or params.get("path") or params.get("selector") or "")
        
        # Canonical JSON representation for hashing parameters (excluding volatile timestamps)
        clean_params = {k: v for k, v in params.items() if k not in ("timestamp", "now", "time")}
        try:
            param_str = json.dumps(clean_params, sort_keys=True, default=str)
        except Exception:
            param_str = str(sorted(clean_params.items()))
        params_hash = hashlib.sha256(param_str.encode("utf-8")).hexdigest()[:12]
        return cls(action=action.strip().lower(), target=target.strip(), params_hash=params_hash, ok=ok)


@dataclass
class LoopDetectionResult:
    """Outcome of evaluating recent actions and system states for loops."""
    is_loop: bool
    loop_type: Optional[str] = None  # "identical_actions", "action_cycle", "state_frozen", "state_cycle"
    message: str = ""
    repetition_count: int = 0


class LoopDetector:
    """
    Monitors recent actions and system states to detect:
    1. Identical consecutive action repetition (e.g. repeatedly clicking a stuck button).
    2. Oscillatory action cycles (e.g. A -> B -> A -> B).
    3. Frozen system state repetition (state not changing despite actions).
    4. State cycles (e.g. S1 -> S2 -> S1 -> S2).
    """

    def __init__(
        self,
        max_identical_actions: int = 3,
        max_consecutive_failures: int = 2,
        max_identical_states: int = 3,
        history_window: int = 15,
    ) -> None:
        self.max_identical_actions = max_identical_actions
        self.max_consecutive_failures = max_consecutive_failures
        self.max_identical_states = max_identical_states
        self.history_window = history_window

        self.action_history: List[ActionFingerprint] = []
        self.state_history: List[str] = []

    def check_upcoming_action(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> LoopDetectionResult:
        """
        Predictively checks if executing the specified action would trigger an action loop
        without modifying recorded history.
        """
        fp = ActionFingerprint.create(action=action, parameters=parameters, ok=True)
        consecutive_identical = 0
        consecutive_identical_failed = 0
        for item in reversed(self.action_history):
            if item.action == fp.action and item.target == fp.target and item.params_hash == fp.params_hash:
                consecutive_identical += 1
                if not item.ok:
                    consecutive_identical_failed += 1
            else:
                break

        if consecutive_identical_failed >= self.max_consecutive_failures:
            msg = (
                f"Loop detected: action '{fp.action}' on target '{fp.target}' "
                f"failed {consecutive_identical_failed} times consecutively."
            )
            return LoopDetectionResult(
                is_loop=True,
                loop_type="identical_actions",
                message=msg,
                repetition_count=consecutive_identical_failed,
            )

        # If adding this upcoming action would reach max_identical_actions (e.g. 2 in history + 1 = 3)
        if (consecutive_identical + 1) >= self.max_identical_actions:
            msg = (
                f"Loop detected: action '{fp.action}' on target '{fp.target}' "
                f"repeated {consecutive_identical + 1} times consecutively."
            )
            return LoopDetectionResult(
                is_loop=True,
                loop_type="identical_actions",
                message=msg,
                repetition_count=consecutive_identical + 1,
            )

        # 2. Oscillatory action cycle: if history ends with [A, B, A] and upcoming is B
        if len(self.action_history) >= 3:
            a1, b1, a2 = self.action_history[-3:]
            if (
                a1.action == a2.action and a1.target == a2.target and
                fp.action == b1.action and fp.target == b1.target and
                (a1.action != b1.action or a1.target != b1.target)
            ):
                msg = (
                    f"Oscillatory action cycle detected between "
                    f"['{a1.action}'({a1.target})] and ['{b1.action}'({b1.target})]."
                )
                return LoopDetectionResult(
                    is_loop=True,
                    loop_type="action_cycle",
                    message=msg,
                    repetition_count=2,
                )

        return LoopDetectionResult(is_loop=False, message="No loop predicted.")

    def record_action(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        ok: bool = True,
    ) -> LoopDetectionResult:
        """Records an executed action and checks for immediate action loops."""
        fp = ActionFingerprint.create(action=action, parameters=parameters, ok=ok)
        self.action_history.append(fp)
        if len(self.action_history) > self.history_window:
            self.action_history.pop(0)

        return self.detect_action_loop()

    def record_state(self, state_fingerprint: str) -> LoopDetectionResult:
        """Records a hash or canonical representation of system state and checks for state loops."""
        clean_fp = state_fingerprint.strip()
        self.state_history.append(clean_fp)
        if len(self.state_history) > self.history_window:
            self.state_history.pop(0)

        return self.detect_state_loop()

    def detect_action_loop(self) -> LoopDetectionResult:
        """Inspects action history for consecutive identical actions or action cycles."""
        n = len(self.action_history)
        if n < 2:
            return LoopDetectionResult(is_loop=False, message="Action history too short for loop check.")

        # 1. Consecutive identical actions
        latest = self.action_history[-1]
        consecutive_identical = 0
        consecutive_identical_failed = 0
        for item in reversed(self.action_history):
            if item.action == latest.action and item.target == latest.target and item.params_hash == latest.params_hash:
                consecutive_identical += 1
                if not item.ok:
                    consecutive_identical_failed += 1
            else:
                break

        if consecutive_identical_failed >= self.max_consecutive_failures:
            msg = (
                f"Loop detected: action '{latest.action}' on target '{latest.target}' "
                f"failed {consecutive_identical_failed} times consecutively."
            )
            return LoopDetectionResult(
                is_loop=True,
                loop_type="identical_actions",
                message=msg,
                repetition_count=consecutive_identical_failed,
            )

        if consecutive_identical >= self.max_identical_actions:
            msg = (
                f"Loop detected: action '{latest.action}' on target '{latest.target}' "
                f"repeated {consecutive_identical} times consecutively."
            )
            return LoopDetectionResult(
                is_loop=True,
                loop_type="identical_actions",
                message=msg,
                repetition_count=consecutive_identical,
            )

        # 2. Oscillatory 2-action cycle: [A, B, A, B]
        if n >= 4:
            a1, b1, a2, b2 = self.action_history[-4:]
            if (
                a1.action == a2.action and a1.target == a2.target and
                b1.action == b2.action and b1.target == b2.target and
                (a1.action != b1.action or a1.target != b1.target)
            ):
                msg = (
                    f"Oscillatory action cycle detected between "
                    f"['{a1.action}'({a1.target})] and ['{b1.action}'({b1.target})]."
                )
                return LoopDetectionResult(
                    is_loop=True,
                    loop_type="action_cycle",
                    message=msg,
                    repetition_count=2,
                )

        return LoopDetectionResult(is_loop=False, message="No action loop detected.")

    def detect_state_loop(self) -> LoopDetectionResult:
        """Inspects state history for identical frozen states or 2-state cycles."""
        n = len(self.state_history)
        if n < 2:
            return LoopDetectionResult(is_loop=False, message="State history too short for loop check.")

        # 1. Consecutive identical states (frozen system)
        latest_state = self.state_history[-1]
        consecutive_same_state = 0
        for state in reversed(self.state_history):
            if state == latest_state:
                consecutive_same_state += 1
            else:
                break

        if consecutive_same_state >= self.max_identical_states:
            msg = f"System state frozen: same state repeated {consecutive_same_state} times consecutively."
            return LoopDetectionResult(
                is_loop=True,
                loop_type="state_frozen",
                message=msg,
                repetition_count=consecutive_same_state,
            )

        # 2. Oscillatory state cycle: [S1, S2, S1, S2]
        if n >= 4:
            s1, s2, s3, s4 = self.state_history[-4:]
            if s1 == s3 and s2 == s4 and s1 != s2:
                msg = "Oscillatory system state cycle detected: [S1 -> S2 -> S1 -> S2]."
                return LoopDetectionResult(
                    is_loop=True,
                    loop_type="state_cycle",
                    message=msg,
                    repetition_count=2,
                )

        return LoopDetectionResult(is_loop=False, message="No state loop detected.")

    def reset(self) -> None:
        """Clears all recorded action and state history."""
        self.action_history.clear()
        self.state_history.clear()


@dataclass
class RetryDecision:
    """Decision produced by the retry policy after a failed action or step."""
    can_retry: bool
    current_tier: MethodTier
    attempt_in_tier: int
    total_attempts_in_stage: int
    action_suggestion: str
    message: str
    escalate_to_user: bool = False


class RetryPolicy:
    """
    Tier-based retry manager implementing the strict rule:
    - 3 attempts per tier.
    - Tier 1 -> Tier 2 (alternative method) -> Tier 3 (vision) -> Escalate to human.
    """

    def __init__(self, max_attempts_per_tier: int = 3) -> None:
        self.max_attempts_per_tier = max_attempts_per_tier
        # stage_name -> {tier: int, total: int}
        self._stage_attempts: Dict[str, Dict[str, Any]] = {}

    def _get_or_init_stage(self, stage_name: str) -> Dict[str, Any]:
        if stage_name not in self._stage_attempts:
            self._stage_attempts[stage_name] = {
                "tier": MethodTier.TIER_1_PRIMARY,
                "tier_attempts": 0,
                "total_attempts": 0,
            }
        return self._stage_attempts[stage_name]

    def get_current_tier(self, stage_name: str) -> MethodTier:
        st = self._get_or_init_stage(stage_name)
        return st["tier"]

    def record_attempt(
        self,
        stage_name: str,
        action: str,
        ok: bool,
        error: Optional[str] = None,
    ) -> RetryDecision:
        """
        Records the outcome of a step in the given stage.
        If ok is True, resets the tier attempts.
        If ok is False, determines whether to retry within the current tier, switch tiers,
        or escalate to the user.
        """
        st = self._get_or_init_stage(stage_name)
        if ok:
            st["tier_attempts"] = 0
            return RetryDecision(
                can_retry=True,
                current_tier=st["tier"],
                attempt_in_tier=0,
                total_attempts_in_stage=st["total_attempts"],
                action_suggestion="Action succeeded.",
                message="Step succeeded.",
                escalate_to_user=False,
            )

        st["tier_attempts"] += 1
        st["total_attempts"] += 1
        current_tier = st["tier"]
        attempts_in_tier = st["tier_attempts"]

        if attempts_in_tier < self.max_attempts_per_tier:
            msg = (
                f"Attempt {attempts_in_tier}/{self.max_attempts_per_tier} failed in {current_tier.value} "
                f"for stage '{stage_name}': {error or 'Unknown failure'}. Retrying same tier."
            )
            return RetryDecision(
                can_retry=True,
                current_tier=current_tier,
                attempt_in_tier=attempts_in_tier,
                total_attempts_in_stage=st["total_attempts"],
                action_suggestion="Retry action with adjusted parameters or window refocus.",
                message=msg,
                escalate_to_user=False,
            )

        # Tier exhausted -> transition to next tier
        if current_tier == MethodTier.TIER_1_PRIMARY:
            st["tier"] = MethodTier.TIER_2_ALTERNATIVE
            st["tier_attempts"] = 0
            msg = (
                f"Tier 1 (primary) exhausted 3 attempts for stage '{stage_name}'. "
                f"Transitioning to Tier 2 (alternative interaction method: mouse/keyboard)."
            )
            logger.warning(msg)
            return RetryDecision(
                can_retry=True,
                current_tier=MethodTier.TIER_2_ALTERNATIVE,
                attempt_in_tier=0,
                total_attempts_in_stage=st["total_attempts"],
                action_suggestion="Switch to alternative method (keyboard shortcut, mouse click, or window refocus).",
                message=msg,
                escalate_to_user=False,
            )

        if current_tier == MethodTier.TIER_2_ALTERNATIVE:
            st["tier"] = MethodTier.TIER_3_VISION
            st["tier_attempts"] = 0
            msg = (
                f"Tier 2 (alternative) exhausted 3 attempts for stage '{stage_name}'. "
                f"Transitioning to Tier 3 (vision fallback: OCR and click_xy)."
            )
            logger.warning(msg)
            return RetryDecision(
                can_retry=True,
                current_tier=MethodTier.TIER_3_VISION,
                attempt_in_tier=0,
                total_attempts_in_stage=st["total_attempts"],
                action_suggestion="Switch to Tier 3 vision fallback (OCR bounding box or click_xy with visual diff).",
                message=msg,
                escalate_to_user=False,
            )

        # Tier 3 also exhausted -> Escalate to user ("ask me")
        st["tier"] = MethodTier.ESCALATION
        msg = (
            f"All 3 method tiers exhausted (Primary, Alternative, Vision) for stage '{stage_name}'. "
            f"Escalating control directly to the user."
        )
        logger.error(msg)
        return RetryDecision(
            can_retry=False,
            current_tier=MethodTier.ESCALATION,
            attempt_in_tier=attempts_in_tier,
            total_attempts_in_stage=st["total_attempts"],
            action_suggestion="Escalate to user for manual intervention.",
            message=msg,
            escalate_to_user=True,
        )

    def reset_stage(self, stage_name: str) -> None:
        """Resets tier and attempt counts for a specific stage upon success."""
        if stage_name in self._stage_attempts:
            del self._stage_attempts[stage_name]


@dataclass
class BudgetStatus:
    within_budget: bool
    task_step_count: int
    max_task_steps: int
    stage_step_count: int
    max_stage_steps: int
    reason: Optional[str] = None


class TaskBudgetLimits:
    """
    Enforces per-stage and overall task step limits to prevent runaways.
    """

    def __init__(self, max_task_steps: int = 25, max_stage_steps: int = 8) -> None:
        self.max_task_steps = max_task_steps
        self.max_stage_steps = max_stage_steps
        self.task_step_count: int = 0
        self.stage_step_counts: Dict[str, int] = {}

    def increment_step(self, stage_name: str) -> BudgetStatus:
        self.task_step_count += 1
        current_stage_count = self.stage_step_counts.get(stage_name, 0) + 1
        self.stage_step_counts[stage_name] = current_stage_count

        if self.task_step_count > self.max_task_steps:
            reason = (
                f"Task step budget exhausted: {self.task_step_count} steps executed "
                f"(max {self.max_task_steps})."
            )
            return BudgetStatus(
                within_budget=False,
                task_step_count=self.task_step_count,
                max_task_steps=self.max_task_steps,
                stage_step_count=current_stage_count,
                max_stage_steps=self.max_stage_steps,
                reason=reason,
            )

        if current_stage_count > self.max_stage_steps:
            reason = (
                f"Stage step budget exhausted for '{stage_name}': {current_stage_count} steps executed "
                f"(max {self.max_stage_steps})."
            )
            return BudgetStatus(
                within_budget=False,
                task_step_count=self.task_step_count,
                max_task_steps=self.max_task_steps,
                stage_step_count=current_stage_count,
                max_stage_steps=self.max_stage_steps,
                reason=reason,
            )

        return BudgetStatus(
            within_budget=True,
            task_step_count=self.task_step_count,
            max_task_steps=self.max_task_steps,
            stage_step_count=current_stage_count,
            max_stage_steps=self.max_stage_steps,
            reason=None,
        )

    def reset_stage(self, stage_name: str) -> None:
        self.stage_step_counts[stage_name] = 0

    def reset_all(self) -> None:
        self.task_step_count = 0
        self.stage_step_counts.clear()
