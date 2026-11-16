"""
tests/test_brain_refactor.py — Tests for Versioned Prompts, Strict Schema, Retries, Context, and Critic.

Covers:
1. Versioned system prompt loading with dynamic action list and schema injection.
2. Strict LLM reply parsing and validation.
3. Every error path with replayed fake LLM responses:
   - Malformed / Bad JSON
   - Hallucinated / Unknown Action
   - Stale or Nonexistent Target Element ID
   - Low-Confidence Acting Step
   - Premature 'done' Claiming
   - Infinite Action Loop Detection
4. Corrective retry loop (max 2 retries) and human escalation (EscalationRequiredError).
5. Compact context construction with conditional screenshot attachment.
6. Dual-verification critic evaluation (code verification + independent critic).
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from neo.brain.context import BrainContext, build_step_context
from neo.brain.critic import CriticVerdict, GoalCritic, is_step_complete
from neo.brain.llm_client import MockLLMClient
from neo.brain.prompts import load_system_prompt
from neo.brain.schema import (
    ActionLoopDetectedError,
    BrainValidationError,
    EscalationRequiredError,
    InvalidJSONError,
    InvalidTargetIDError,
    LLMReply,
    LowConfidenceError,
    PrematureDoneError,
    UnknownActionError,
    query_with_retries,
    validate_llm_reply,
)
from neo.brain.verifier import VerificationResult
from neo.windows.uia_snapshot import UIASnapshot, UIAElement


# ─────────────────────────────────────────────────────────────────────────────
# 1. Versioned System Prompt Loading
# ─────────────────────────────────────────────────────────────────────────────
def test_versioned_prompt_loading():
    prompt_text = load_system_prompt(version="v1")
    assert "You are NEO" in prompt_text
    assert "### PERMITTED ACTION WHITELIST" in prompt_text
    assert "Level 1 (Direct APIs)" in prompt_text
    assert "Level 2 (Browser DOM)" in prompt_text
    assert "Level 3 (Windows UIA)" in prompt_text
    assert "### REQUIRED JSON REPLY SCHEMA" in prompt_text
    assert '"stage"' in prompt_text
    assert '"confidence"' in prompt_text


# ─────────────────────────────────────────────────────────────────────────────
# 2. Strict Reply Parsing & Valid Case
# ─────────────────────────────────────────────────────────────────────────────
def test_validate_llm_reply_valid():
    valid_json = json.dumps({
        "stage": "act",
        "observation": "Notepad editor window is open and focused.",
        "last_action_result": "App launched successfully.",
        "plan": ["Type report content", "Save document"],
        "action": "type",
        "target_id": None,
        "text": "Meeting Notes",
        "confidence": 0.95,
        "parameters": {},
    })

    reply = validate_llm_reply(valid_json)
    assert reply.action == "type"
    assert reply.confidence == 0.95
    assert reply.text == "Meeting Notes"

    decision = reply.to_agent_decision()
    assert decision.action == "type"
    assert decision.parameters["text"] == "Meeting Notes"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Error Paths & Replayed Fake LLM Responses
# ─────────────────────────────────────────────────────────────────────────────
def test_error_path_bad_json_triggers_retries_and_escalation():
    # Replay sequence: attempt 1 bad JSON, attempt 2 bad JSON, attempt 3 bad JSON
    bad_responses = [
        "This is totally invalid text without any JSON at all.",
        "{stage: act, observation: missing quotes and invalid syntax",
        '{"stage": "act", "observation": "truncated...',
    ]

    mock_client = MockLLMClient(decision_sequence=bad_responses)

    with pytest.raises(EscalationRequiredError) as exc_info:
        query_with_retries(
            query_fn=lambda p: mock_client.query("sys", p),
            initial_user_prompt="Do step",
            max_retries=2,
        )

    assert "Failed to obtain valid decision after 2 retries" in str(exc_info.value)
    assert mock_client._call_count == 3  # Initial + 2 retries


def test_error_path_hallucinated_action_triggers_retries_and_escalation():
    hallucinated_responses = [
        json.dumps({
            "stage": "act",
            "observation": "Looking at terminal",
            "last_action_result": "None",
            "plan": "Hack",
            "action": "run_arbitrary_powershell_script",
            "confidence": 0.9,
        }),
        json.dumps({
            "stage": "act",
            "observation": "Still trying",
            "last_action_result": "None",
            "plan": "Hack",
            "action": "bash_exec",
            "confidence": 0.9,
        }),
        json.dumps({
            "stage": "act",
            "observation": "Giving up",
            "last_action_result": "None",
            "plan": "Hack",
            "action": "sudo_rm",
            "confidence": 0.9,
        }),
    ]

    mock_client = MockLLMClient(decision_sequence=hallucinated_responses)

    with pytest.raises(EscalationRequiredError) as exc_info:
        query_with_retries(
            query_fn=lambda p: mock_client.query("sys", p),
            initial_user_prompt="Do step",
            max_retries=2,
        )

    assert "escalated to user" in str(exc_info.value).lower()
    assert "not in the allowed whitelist" in str(exc_info.value)
    assert mock_client._call_count == 3


def make_mock_snapshot(snapshot_id: str, elements: list, is_sparse: bool = False) -> UIASnapshot:
    return UIASnapshot(
        snapshot_id=snapshot_id,
        hwnd=1234,
        window_title="Test Window",
        elements=elements,
        is_sparse=is_sparse,
        timestamp=1000.0,
        total_elements_scanned=len(elements),
        duration_ms=10.0,
    )


def test_error_path_stale_or_nonexistent_target_id():
    elements = [
        UIAElement(id=1, snapshot_id="snap_101", control_type="Button", name="Save", automation_id="BtnSave", enabled=True, value="", bounding_rect=(0,0,10,10)),
        UIAElement(id=2, snapshot_id="snap_101", control_type="Button", name="Cancel", automation_id="BtnCancel", enabled=True, value="", bounding_rect=(0,0,10,10)),
    ]
    mock_snap = make_mock_snapshot(snapshot_id="snap_101", elements=elements)

    # Hallucinated ID 99
    bad_id_response = json.dumps({
        "stage": "act",
        "observation": "Trying to click nonexistent element",
        "last_action_result": "None",
        "plan": ["Click"],
        "action": "click",
        "target_id": 99,
        "confidence": 0.85,
    })

    with pytest.raises(InvalidTargetIDError) as exc_info:
        validate_llm_reply(bad_id_response, current_snapshot=mock_snap)

    assert "target_id=99 is stale or nonexistent" in str(exc_info.value)
    assert "Valid element IDs currently visible: [1, 2]" in str(exc_info.value)


def test_error_path_low_confidence_acting_step():
    low_conf_response = json.dumps({
        "stage": "act",
        "observation": "Not sure what to type",
        "last_action_result": "None",
        "plan": ["Guessing"],
        "action": "type",
        "target_id": None,
        "text": "uncertain input",
        "confidence": 0.35,  # Below 0.6 threshold
    })

    with pytest.raises(LowConfidenceError) as exc_info:
        validate_llm_reply(low_conf_response, min_confidence=0.6)

    assert "confidence (0.35) is below the minimum required threshold of 0.60" in str(exc_info.value)


def test_error_path_premature_done_claim():
    done_response = json.dumps({
        "stage": "done",
        "observation": "I believe everything is finished",
        "last_action_result": "All set",
        "plan": [],
        "action": "done",
        "confidence": 1.0,
    })

    with pytest.raises(PrematureDoneError) as exc_info:
        validate_llm_reply(done_response)

    assert "The LLM cannot mark a task 'done' directly" in str(exc_info.value)


def test_error_path_action_loop_detection():
    # History with 2 identical consecutive failures
    history = [
        {"action": "type", "target_id": None, "ok": False},
        {"action": "type", "target_id": None, "ok": False},
    ]

    looping_reply = json.dumps({
        "stage": "act",
        "observation": "Retrying exact same action again",
        "last_action_result": "Failed previously",
        "plan": ["Type again"],
        "action": "type",
        "target_id": None,
        "text": "repeat text",
        "confidence": 0.9,
    })

    with pytest.raises(ActionLoopDetectedError) as exc_info:
        validate_llm_reply(looping_reply, recent_actions=history)

    assert "Loop detected: Action 'type' on target 'None' failed in the previous two consecutive steps" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Successful Recovery on 1st Retry
# ─────────────────────────────────────────────────────────────────────────────
def test_successful_recovery_on_first_retry():
    # Attempt 1 has hallucinated action; Attempt 2 corrects to valid action
    responses = [
        '{"stage": "act", "observation": "wrong action", "last_action_result": "none", "plan": "p", "action": "fake_act", "confidence": 0.8}',
        '{"stage": "act", "observation": "corrected", "last_action_result": "none", "plan": "p", "action": "type", "text": "hello", "confidence": 0.9}',
    ]

    mock_client = MockLLMClient(decision_sequence=responses)

    reply = query_with_retries(
        query_fn=lambda p: mock_client.query("sys", p),
        initial_user_prompt="Type text",
        max_retries=2,
    )

    assert reply.action == "type"
    assert reply.text == "hello"
    assert mock_client._call_count == 2  # 1 initial + 1 retry recovery


# ─────────────────────────────────────────────────────────────────────────────
# 5. Compact Context Construction & Conditional Screenshots
# ─────────────────────────────────────────────────────────────────────────────
def test_compact_context_normal_snapshot_omits_screenshot():
    elements = [
        UIAElement(id=i, snapshot_id="snap_rich", control_type="Button", name=f"Btn{i}", automation_id=f"id{i}", enabled=True, value="", bounding_rect=(0,0,10,10))
        for i in range(1, 10)
    ]
    snapshot = make_mock_snapshot(snapshot_id="snap_rich", elements=elements, is_sparse=False)

    ctx = build_step_context(
        goal="Test context",
        step_index=1,
        max_steps=10,
        current_snapshot=snapshot,
        llm_asked_for_screenshot=False,
    )

    assert ctx.screenshot_attached is False
    assert ctx.screenshot_path is None
    assert "### TASK GOAL: Test context" in ctx.prompt_text
    assert "Btn1" in ctx.prompt_text
    assert "[1] <Button>" in ctx.prompt_text


def test_compact_context_sparse_snapshot_attaches_screenshot():
    # Sparse snapshot with only 1 element
    elements = [
        UIAElement(id=1, snapshot_id="snap_sparse", control_type="Pane", name="", automation_id="", enabled=True, value="", bounding_rect=(0,0,10,10))
    ]
    snapshot = make_mock_snapshot(snapshot_id="snap_sparse", elements=elements, is_sparse=True)

    with patch("neo.brain.context.capture_screen") as mock_cap:
        mock_cap.return_value = MagicMock(ok=True, path="C:\\test_screen.png", width=1920, height=1080)

        ctx = build_step_context(
            goal="Test sparse context",
            step_index=2,
            max_steps=10,
            current_snapshot=snapshot,
        )

        assert ctx.screenshot_attached is True
        assert ctx.screenshot_path == "C:\\test_screen.png"
        assert "Sparse UI snapshot detected" in ctx.prompt_text
        mock_cap.assert_called_once()


def test_compact_context_caps_history_to_last_5_steps():
    long_history = [{"step_index": i, "action": f"act_{i}", "ok": True} for i in range(1, 15)]

    ctx = build_step_context(
        goal="Test history cap",
        step_index=15,
        max_steps=20,
        step_history=long_history,
    )

    assert ctx.history_step_count == 5
    assert "Last 5 steps" in ctx.prompt_text
    assert "Step 14: `act_14`" in ctx.prompt_text
    assert "Step 1:" not in ctx.prompt_text  # Older steps pruned


# ─────────────────────────────────────────────────────────────────────────────
# 6. Critic Dual-Verification
# ─────────────────────────────────────────────────────────────────────────────
def test_critic_dual_verification_agreement_and_disagreement():
    code_pass = VerificationResult(completed=True, rationale="File sha256 matches expected content.")
    code_fail = VerificationResult(completed=False, rationale="File not found.")

    critic_verified = CriticVerdict(verdict="verified", explanation="Sha256 hash verified.", confidence=0.95)
    critic_not_verified = CriticVerdict(verdict="not_verified", explanation="File size is 0 bytes.", confidence=0.9)
    critic_unsure = CriticVerdict(verdict="unsure", explanation="Evidence is ambiguous.", confidence=0.4)

    # 1. Both agree -> Complete
    ok1, reason1 = is_step_complete(code_pass, critic_verified)
    assert ok1 is True
    assert "Dual-Verified" in reason1 or "verified by both" in reason1

    # 2. Code passed, but Critic rejected -> NOT Complete
    ok2, reason2 = is_step_complete(code_pass, critic_not_verified)
    assert ok2 is False
    assert "Critic rejected completion" in reason2

    # 3. Code passed, but Critic unsure -> NOT Complete
    ok3, reason3 = is_step_complete(code_pass, critic_unsure)
    assert ok3 is False
    assert "Critic is unsure" in reason3

    # 4. Code failed, even if Critic said verified -> NOT Complete
    ok4, reason4 = is_step_complete(code_fail, critic_verified)
    assert ok4 is False
    assert "Code verification failed" in reason4
