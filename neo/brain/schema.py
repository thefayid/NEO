"""
neo/brain/schema.py — Strict Pydantic LLM Reply Schema, Validation, and Retry/Escalation Engine.

Architectural Guarantees:
1. Strict Pydantic parsing of model responses:
   - stage, observation, last_action_result, plan, action, target_id, text, confidence.
2. Explicit failure classes:
   - InvalidJSONError, UnknownActionError, InvalidTargetIDError, LowConfidenceError,
     PrematureDoneError, ActionLoopDetectedError.
3. Automated Error Feedback & Retry Protocol:
   - On error, returns a precise error explanation back to the LLM for correction.
   - Maximum 2 retries.
4. Human Escalation Gate:
   - If 2 retries are exhausted, raises EscalationRequiredError yielding full control to the user.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from neo.brain.llm_client import parse_llm_json
from neo.brain.whitelist import WHITELISTED_ACTIONS, AgentDecision
from neo.windows.uia_snapshot import UIASnapshot

logger = logging.getLogger("neo.brain.schema")


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class BrainValidationError(ValueError):
    """Base exception for brain decision validation errors."""
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.is_retryable = is_retryable


class InvalidJSONError(BrainValidationError):
    """Raised when the LLM outputs malformed JSON or unparseable text."""
    pass


class UnknownActionError(BrainValidationError):
    """Raised when the LLM hallucinates an action outside the strict whitelist."""
    pass


class InvalidTargetIDError(BrainValidationError):
    """Raised when the target_id is nonexistent or stale from an old snapshot."""
    pass


class LowConfidenceError(BrainValidationError):
    """Raised when an acting step has confidence below the minimum threshold."""
    pass


class PrematureDoneError(BrainValidationError):
    """Raised when the LLM marks the task complete before objective verification."""
    pass


class ActionLoopDetectedError(BrainValidationError):
    """Raised when the LLM repeats identical failing actions in a loop."""
    pass


class EscalationRequiredError(RuntimeError):
    """Raised when retry budget is exhausted, requiring control to yield to the human user."""
    def __init__(self, reason: str, last_error: Optional[Exception] = None):
        super().__init__(f"Agent escalated to user: {reason}")
        self.reason = reason
        self.last_error = last_error


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic LLM Reply Model
# ─────────────────────────────────────────────────────────────────────────────
class LLMReply(BaseModel):
    """
    Strict validation model for the LLM's structured reply at each step.
    """
    model_config = ConfigDict(extra="ignore")

    stage: str = Field(..., description="Current cognitive stage: 'perceive', 'plan', 'act', 'verify', or 'done'")
    observation: str = Field(..., min_length=3, description="Detailed observation of current visual and system state")
    last_action_result: str = Field(..., description="Evaluation of the outcome of the previous step")
    plan: Union[List[str], str] = Field(..., description="List of planned steps or description of remaining work")
    action: str = Field(..., description="Action name selected from the whitelist")
    target_id: Optional[int] = Field(None, description="1-based element ID from active snapshot")
    text: Optional[str] = Field(None, description="Text string, path, URL, or key parameter")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    snapshot_id: Optional[str] = Field(None, description="Snapshot ID element_id belongs to")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Additional action-specific parameters")

    @field_validator("action")
    @classmethod
    def validate_action_whitelist(cls, v: str) -> str:
        act_clean = v.strip().lower()
        if act_clean not in WHITELISTED_ACTIONS and act_clean != "done":
            sorted_actions = ", ".join(sorted(list(WHITELISTED_ACTIONS)))
            raise UnknownActionError(
                f"Action '{v}' is not in the allowed whitelist. Permitted actions: [{sorted_actions}]"
            )
        return act_clean

    def to_agent_decision(self, snapshot_id: Optional[str] = None) -> AgentDecision:
        """
        Converts this LLMReply to an AgentDecision for the deterministic ActionDispatcher.
        Merges target_id, snapshot_id, and text into parameters dictionary.
        """
        merged_params = dict(self.parameters)
        if self.target_id is not None and "element_id" not in merged_params:
            merged_params["element_id"] = self.target_id
        if self.text is not None and "text" not in merged_params:
            merged_params["text"] = self.text

        # Automatically propagate verified snapshot_id to avoid stale/missing snapshot IDs
        resolved_snap = snapshot_id or self.snapshot_id or merged_params.get("snapshot_id")
        if resolved_snap and "snapshot_id" not in merged_params:
            merged_params["snapshot_id"] = resolved_snap

        # Set thought to observation and plan summary
        plan_str = ", ".join(self.plan) if isinstance(self.plan, list) else str(self.plan)
        thought_summary = f"{self.observation} | Plan: {plan_str}"

        return AgentDecision(
            thought=thought_summary,
            action=self.action,
            parameters=merged_params,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reply Validator
# ─────────────────────────────────────────────────────────────────────────────
def validate_llm_reply(
    raw_text: str,
    current_snapshot: Optional[UIASnapshot] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    min_confidence: float = 0.6,
) -> LLMReply:
    """
    Parses and rigorously validates an LLM response.
    Checks for:
    - Valid JSON
    - Pydantic schema compliance
    - Whitelisted action
    - Valid, non-stale element IDs in the current snapshot
    - Confidence threshold for acting steps
    - Action loops
    """
    # 1. Parse JSON
    try:
        data = parse_llm_json(raw_text)
    except Exception as e:
        raise InvalidJSONError(f"Failed to parse valid JSON: {e}") from e

    # Backward compatibility with simple AgentDecision payloads
    if isinstance(data, dict):
        if "thought" in data and "observation" not in data:
            data["observation"] = data["thought"]
        if "stage" not in data:
            data["stage"] = "act"
        if "last_action_result" not in data:
            data["last_action_result"] = "Initial step or previous action executed."
        if "plan" not in data:
            data["plan"] = ["Execute task"]
        if "confidence" not in data:
            data["confidence"] = 1.0

    # 2. Schema compliance
    try:
        reply = LLMReply.model_validate(data)
    except Exception as e:
        if isinstance(e, UnknownActionError):
            raise
        raise BrainValidationError(f"Reply failed schema validation: {e}") from e

    # 3. Premature 'done' check
    if reply.action == "done" or reply.stage.lower() == "done":
        raise PrematureDoneError(
            "The LLM cannot mark a task 'done' directly. Only the deterministic verifier "
            "and critic can declare goal completion based on empirical evidence."
        )

    # 4. Target ID validity check against active snapshot
    if reply.target_id is not None:
        if current_snapshot is None:
            raise InvalidTargetIDError(
                f"target_id={reply.target_id} was specified, but no active UI snapshot exists."
            )
        el = current_snapshot.get_element(reply.target_id)
        if el is None:
            valid_ids = [e.id for e in current_snapshot.elements[:15]]
            valid_str = ", ".join(map(str, valid_ids)) if valid_ids else "None"
            raise InvalidTargetIDError(
                f"target_id={reply.target_id} is stale or nonexistent for active snapshot '{current_snapshot.snapshot_id}'. "
                f"Valid element IDs currently visible: [{valid_str}]"
            )

        # Reject acting steps targeting disabled elements
        if not el.enabled and reply.action in ("click", "double_click", "right_click", "type", "set_text", "select"):
            raise BrainValidationError(
                f"Target element ID {reply.target_id} ('{el.name}') is disabled. Cannot perform action '{reply.action}'."
            )

        # Propagate verified snapshot_id to prevent stale snapshot errors downstream
        reply.snapshot_id = current_snapshot.snapshot_id

    # 5. Low confidence check on acting steps
    acting_actions = {
        "click", "double_click", "right_click", "set_text", "type", "press_key",
        "hotkey", "open", "file_write", "file_delete", "click_xy", "click_coords",
        "browser_click", "browser_type",
    }
    if reply.action in acting_actions and reply.confidence < min_confidence:
        raise LowConfidenceError(
            f"Action '{reply.action}' confidence ({reply.confidence:.2f}) is below the minimum required "
            f"threshold of {min_confidence:.2f}. If uncertain, read or inspect elements first."
        )

    # 6. Action loop detection
    if recent_actions and len(recent_actions) >= 2:
        last1 = recent_actions[-1]
        last2 = recent_actions[-2]
        # If the last two steps attempted the identical action and target without success
        if (
            last1.get("action") == reply.action
            and last2.get("action") == reply.action
            and last1.get("target_id") == reply.target_id
            and last1.get("ok") is False
            and last2.get("ok") is False
        ):
            raise ActionLoopDetectedError(
                f"Loop detected: Action '{reply.action}' on target '{reply.target_id}' failed in the previous "
                f"two consecutive steps. You must change your plan or choose an alternative action."
            )

    return reply


# ─────────────────────────────────────────────────────────────────────────────
# Retry & Escalation Controller
# ─────────────────────────────────────────────────────────────────────────────
def query_with_retries(
    query_fn: Callable[[str], str],
    initial_user_prompt: str,
    current_snapshot: Optional[UIASnapshot] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    max_retries: int = 2,
    min_confidence: float = 0.6,
) -> LLMReply:
    """
    Submits a prompt to the LLM and handles validation errors with corrective feedback.
    Retries up to max_retries (default 2).
    If validation still fails after retries, raises EscalationRequiredError to yield to the user.
    """
    current_prompt = initial_user_prompt
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        raw_response = query_fn(current_prompt)
        try:
            reply = validate_llm_reply(
                raw_text=raw_response,
                current_snapshot=current_snapshot,
                recent_actions=recent_actions,
                min_confidence=min_confidence,
            )
            return reply
        except (BrainValidationError, Exception) as err:
            last_err = err
            err_msg = str(err)
            logger.warning("Reply validation failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, err_msg)

            if attempt < max_retries:
                # Construct corrective feedback
                current_prompt = (
                    f"{initial_user_prompt}\n\n"
                    f"### [VALIDATION ERROR ON PREVIOUS ATTEMPT]:\n"
                    f"{err_msg}\n\n"
                    f"Please correct your response. Ensure you output ONLY a valid JSON object matching the "
                    f"required schema with a whitelisted action, valid active element IDs, and confidence >= {min_confidence:.1f}."
                )
            else:
                break

    # Exceeded max_retries -> Escalate to human user
    escalation_reason = f"Failed to obtain valid decision after {max_retries} retries. Final error: {last_err}"
    logger.critical("🚨 %s", escalation_reason)
    raise EscalationRequiredError(escalation_reason, last_error=last_err)
