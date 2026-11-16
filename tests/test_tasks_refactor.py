"""
tests/test_tasks_refactor.py — Comprehensive Unit & Integration Tests for neo.tasks.

Covers:
1. Simulated multi-stage task advancement via code checks (LLM cannot advance stages).
2. Loop detection (identical actions, oscillatory action cycles, frozen states, state cycles).
3. Tier-based retry policy (3 attempts per tier -> alternative -> vision -> user escalation).
4. Checkpoints & deterministic rollback (file content restoration, newly created file cleanup, clipboard restoration).
5. Parameterized skill routine creation, saving, and deterministic replay.
6. Replay failure halting with dynamic fallback handler invocation.
7. Final report generator verifying invariant 'Done' gating and Markdown format.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List
import pytest

from neo.brain.planner import ActionDispatcher, StepExecutionResult
from neo.brain.schema import ActionLoopDetectedError, EscalationRequiredError
from neo.brain.verifier import VerificationResult
from neo.brain.whitelist import AgentDecision
from neo.config import load_settings
from neo.safety import get_confirmation_gate
from neo.tasks import (
    ActionFingerprint,
    CheckpointManager,
    CustomCheck,
    ElementExistsCheck,
    FileExistsCheck,
    LoopDetectionResult,
    LoopDetector,
    MethodTier,
    ReplayResult,
    RetryDecision,
    RetryPolicy,
    RollbackResult,
    Routine,
    RoutineReplayer,
    RoutineStep,
    SkillLibrary,
    Stage,
    StageCheckResult,
    StageStateMachine,
    StageStatus,
    TaskBudgetLimits,
    TaskManager,
    TaskReport,
    TaskReportGenerator,
    TaskState,
    URLContainsCheck,
    ValueEqualsCheck,
)


@pytest.fixture(autouse=True)
def auto_approve_gate():
    gate = get_confirmation_gate()
    gate.set_handler(lambda *args: (True, "Auto-approved for test"))
    yield
    gate.set_handler(None)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Simulated Multi-Stage Task with Strict Code-Gated Advancement
# ─────────────────────────────────────────────────────────────────────────────
def test_simulated_multi_stage_task(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    step1_file = tmp_path / "step1.txt"
    step2_file = tmp_path / "step2.json"

    stage1 = Stage(
        name="create_step1_file",
        description="Write step1.txt with at least 5 bytes",
        completion_check=FileExistsCheck(path=step1_file, min_size_bytes=5),
    )
    stage2 = Stage(
        name="verify_step2_content",
        description="Write step2.json containing PROCESSED_OK",
        completion_check=FileExistsCheck(path=step2_file, contains_text="PROCESSED_OK"),
    )
    stage3 = Stage(
        name="verify_browser_url",
        description="Navigate to success confirmation URL",
        completion_check=URLContainsCheck(substring="status=success"),
    )

    tm = TaskManager()
    task = tm.create_stage_task(
        goal="Execute 3-stage automated workflow",
        stages=[stage1, stage2, stage3],
        max_steps=10,
    )

    assert task.state == TaskState.PENDING
    assert task.stage_machine.current_stage.name == "create_step1_file"

    # Step A: Action that does NOT satisfy stage 1 (writes unrelated file)
    dummy_file = tmp_path / "other.txt"
    dec_a = AgentDecision(
        thought="Writing wrong file",
        action="file_write",
        parameters={"path": str(dummy_file), "content": "hello world"},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, dec_a)
    assert t_rec.state == TaskState.RUNNING
    # Stage 1 must NOT have advanced!
    assert task.stage_machine.current_stage_index == 0
    assert task.stage_machine.current_stage.name == "create_step1_file"
    assert verif_res.completed is False

    # Step B: Write step1_file but with too few bytes (only 3 bytes < 5 bytes)
    dec_b = AgentDecision(
        thought="Writing short file",
        action="file_write",
        parameters={"path": str(step1_file), "content": "abc"},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, dec_b)
    # Stage 1 must still NOT advance
    assert task.stage_machine.current_stage_index == 0

    # Step C: Satisfy stage 1 (>5 bytes)
    dec_c = AgentDecision(
        thought="Writing valid step1 file",
        action="file_write",
        parameters={"path": str(step1_file), "content": "123456789"},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, dec_c)
    # Stage 1 is now COMPLETED, advanced to Stage 2!
    assert stage1.status == StageStatus.COMPLETED
    assert task.stage_machine.current_stage_index == 1
    assert task.stage_machine.current_stage.name == "verify_step2_content"

    # Step D: Satisfy stage 2 (create step2_file with PROCESSED_OK)
    dec_d = AgentDecision(
        thought="Writing step2 content",
        action="file_write",
        parameters={"path": str(step2_file), "content": '{"status": "PROCESSED_OK"}'},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, dec_d)
    assert stage2.status == StageStatus.COMPLETED
    assert task.stage_machine.current_stage_index == 2
    assert task.stage_machine.current_stage.name == "verify_browser_url"

    # Step E: Satisfy stage 3 (provide URL in system state)
    dec_e = AgentDecision(
        thought="Navigating to confirmation URL",
        action="file_read",  # Any valid action
        parameters={"path": str(step1_file)},
    )
    t_rec, exec_res, verif_res = tm.execute_step(
        task.task_id,
        dec_e,
        system_state={"browser_url": "https://example.com/checkout?status=success"},
    )

    # All 3 stages complete -> Task state is COMPLETED!
    assert stage3.status == StageStatus.COMPLETED
    assert task.stage_machine.is_all_completed() is True
    assert t_rec.state == TaskState.COMPLETED
    assert verif_res.completed is True
    assert t_rec.final_report is not None
    assert t_rec.final_report.status == "Done"
    assert t_rec.final_report.all_checks_passed is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Loop Detection (Identical Actions, Action Cycles, State Loops)
# ─────────────────────────────────────────────────────────────────────────────
def test_loop_detection_identical_actions_and_cycles():
    detector = LoopDetector(max_identical_actions=3, max_consecutive_failures=2)

    # 1. Consecutive identical successful actions
    res1 = detector.record_action("click", {"target_id": 5}, ok=True)
    assert res1.is_loop is False
    res2 = detector.record_action("click", {"target_id": 5}, ok=True)
    assert res2.is_loop is False
    res3 = detector.record_action("click", {"target_id": 5}, ok=True)
    assert res3.is_loop is True
    assert res3.loop_type == "identical_actions"
    assert "repeated 3 times" in res3.message

    detector.reset()

    # 2. Consecutive identical failing actions (threshold = 2)
    res_f1 = detector.record_action("file_read", {"path": "missing.txt"}, ok=False)
    assert res_f1.is_loop is False
    res_f2 = detector.record_action("file_read", {"path": "missing.txt"}, ok=False)
    assert res_f2.is_loop is True
    assert "failed 2 times consecutively" in res_f2.message

    detector.reset()

    # 3. Oscillatory action cycle: A -> B -> A -> B
    detector.record_action("click", {"target_id": 10}, ok=True)
    detector.record_action("click", {"target_id": 20}, ok=True)
    detector.record_action("click", {"target_id": 10}, ok=True)
    cycle_res = detector.record_action("click", {"target_id": 20}, ok=True)
    assert cycle_res.is_loop is True
    assert cycle_res.loop_type == "action_cycle"
    assert "Oscillatory action cycle detected" in cycle_res.message


def test_loop_detection_state_frozen_and_cycle():
    detector = LoopDetector(max_identical_states=3)

    # 1. Frozen system state
    detector.record_state("state_hash_aaa")
    detector.record_state("state_hash_aaa")
    frozen_res = detector.record_state("state_hash_aaa")
    assert frozen_res.is_loop is True
    assert frozen_res.loop_type == "state_frozen"

    detector.reset()

    # 2. State cycle: S1 -> S2 -> S1 -> S2
    detector.record_state("state_1")
    detector.record_state("state_2")
    detector.record_state("state_1")
    state_cycle_res = detector.record_state("state_2")
    assert state_cycle_res.is_loop is True
    assert state_cycle_res.loop_type == "state_cycle"


def test_task_manager_aborts_on_action_loop(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    tm = TaskManager()
    task = tm.create_task(goal="Loop test task", max_steps=10)

    # Executing identical action 3 times in task manager should trigger ActionLoopDetectedError
    dec = AgentDecision(
        thought="Spamming same action",
        action="file_read",
        parameters={"path": str(tmp_path / "sample.txt")},
    )

    tm.execute_step(task.task_id, dec)
    tm.execute_step(task.task_id, dec)

    with pytest.raises(ActionLoopDetectedError) as exc_info:
        tm.execute_step(task.task_id, dec)

    assert "Loop detected" in str(exc_info.value)
    assert task.state == TaskState.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tier-Based Retry Policy
# ─────────────────────────────────────────────────────────────────────────────
def test_tiered_retry_policy_transitions_and_escalation():
    policy = RetryPolicy(max_attempts_per_tier=3)
    stage_name = "login_stage"

    assert policy.get_current_tier(stage_name) == MethodTier.TIER_1_PRIMARY

    # Tier 1, Attempt 1 fails
    d1 = policy.record_attempt(stage_name, "click", ok=False, error="Element not interactable")
    assert d1.can_retry is True
    assert d1.current_tier == MethodTier.TIER_1_PRIMARY
    assert d1.attempt_in_tier == 1

    # Tier 1, Attempt 2 fails
    d2 = policy.record_attempt(stage_name, "click", ok=False, error="Element timeout")
    assert d2.attempt_in_tier == 2

    # Tier 1, Attempt 3 fails -> Transitions to Tier 2 (Alternative)
    d3 = policy.record_attempt(stage_name, "click", ok=False, error="Stuck element")
    assert d3.current_tier == MethodTier.TIER_2_ALTERNATIVE
    assert policy.get_current_tier(stage_name) == MethodTier.TIER_2_ALTERNATIVE

    # Tier 2: 3 failures -> Transitions to Tier 3 (Vision)
    policy.record_attempt(stage_name, "press_key", ok=False)
    policy.record_attempt(stage_name, "press_key", ok=False)
    d6 = policy.record_attempt(stage_name, "press_key", ok=False)
    assert d6.current_tier == MethodTier.TIER_3_VISION
    assert policy.get_current_tier(stage_name) == MethodTier.TIER_3_VISION

    # Tier 3: 3 failures -> Escalate to user ("ask me")
    policy.record_attempt(stage_name, "click_xy", ok=False)
    policy.record_attempt(stage_name, "click_xy", ok=False)
    d9 = policy.record_attempt(stage_name, "click_xy", ok=False)
    assert d9.can_retry is False
    assert d9.current_tier == MethodTier.ESCALATION
    assert d9.escalate_to_user is True
    assert "Escalating control directly to the user" in d9.message


# ─────────────────────────────────────────────────────────────────────────────
# 4. Checkpoints & Deterministic Rollback
# ─────────────────────────────────────────────────────────────────────────────
def test_checkpoints_and_rollback(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    orig_file = tmp_path / "important_data.txt"
    orig_file.write_text("PRISTINE_DATA_12345", encoding="utf-8")

    new_created_file = tmp_path / "newly_created.tmp"

    chk_mgr = CheckpointManager(storage_dir=tmp_path / "checkpoints")

    # 1. Create checkpoint tracking orig_file and the future new_created_file
    chk = chk_mgr.create_checkpoint(
        action_name="file_write",
        file_paths=[orig_file, new_created_file],
        capture_clipboard=False,
    )
    assert chk.checkpoint_id.startswith("chk_")
    assert orig_file.resolve().as_posix() in [Path(k).resolve().as_posix() for k in chk.file_snapshots.keys()]
    # new_created_file did not exist -> recorded as None
    assert chk.file_snapshots[str(new_created_file.resolve())] is None

    # 2. Modify orig_file and create new_created_file
    orig_file.write_text("CORRUPTED_GARBAGE", encoding="utf-8")
    new_created_file.write_text("EXTRA_DATA", encoding="utf-8")
    assert orig_file.read_text(encoding="utf-8") == "CORRUPTED_GARBAGE"
    assert new_created_file.exists() is True

    # 3. Rollback
    rb_res = chk_mgr.rollback(chk.checkpoint_id)
    assert rb_res.ok is True
    assert len(rb_res.restored_files) == 1
    assert len(rb_res.removed_files) == 1

    # 4. Verify original content is restored and new file was deleted!
    assert orig_file.read_text(encoding="utf-8") == "PRISTINE_DATA_12345"
    assert new_created_file.exists() is False


def test_task_manager_auto_checkpoint_and_rollback(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    target = tmp_path / "state_file.txt"
    target.write_text("INITIAL_STATE", encoding="utf-8")

    tm = TaskManager()
    task = tm.create_task(goal="Testing auto checkpoint rollback", max_steps=5)

    # Executing risky file_write auto-creates a checkpoint
    dec = AgentDecision(
        thought="Overwriting state file",
        action="file_write",
        parameters={"path": str(target), "content": "BAD_OVERWRITE"},
    )
    tm.execute_step(task.task_id, dec)
    assert target.read_text(encoding="utf-8") == "BAD_OVERWRITE"

    # Rollback via task manager
    rb_res = tm.rollback_task(task.task_id)
    assert rb_res.ok is True
    assert target.read_text(encoding="utf-8") == "INITIAL_STATE"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Parameterized Skill Routine Creation, Saving, and Deterministic Replay
# ─────────────────────────────────────────────────────────────────────────────
def test_skill_save_and_deterministic_replay(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    skills_file = tmp_path / "skills.json"
    skill_lib = SkillLibrary(storage_path=skills_file)

    # 1. Define a parameterized routine with {{filename}} and {{content}}
    routine = Routine(
        name="save_report_routine",
        description="Writes a report and reads it back",
        parameters_schema={"filename": "Output filename", "content": "Text content"},
        steps=[
            RoutineStep(
                action="file_write",
                parameters={"path": "{{filename}}", "content": "{{content}}"},
                description="Write report file",
            ),
            RoutineStep(
                action="file_read",
                parameters={"path": "{{filename}}"},
                description="Verify report file",
            ),
        ],
    )
    skill_lib.save_skill(routine)

    # Verify persistence
    loaded_routine = skill_lib.get_skill("save_report_routine")
    assert loaded_routine is not None
    assert len(loaded_routine.steps) == 2

    # 2. Replay deterministically with variables
    target_out = tmp_path / "final_report.txt"
    replayer = RoutineReplayer()
    replay_res = replayer.replay(
        routine=loaded_routine,
        variables={"filename": str(target_out), "content": "AUTONOMOUS_SUCCESS_99"},
    )

    assert replay_res.ok is True
    assert replay_res.completed_steps == 2
    assert replay_res.fallback_needed is False
    assert target_out.exists() is True
    assert target_out.read_text(encoding="utf-8") == "AUTONOMOUS_SUCCESS_99"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Failing Replay Halts and Triggers LLM Fallback
# ─────────────────────────────────────────────────────────────────────────────
def test_failing_replay_triggers_fallback(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    
    # Routine where step 1 succeeds, step 2 attempts to read a nonexistent file
    routine = Routine(
        name="flaky_routine",
        description="Routine designed to fail at step 2",
        steps=[
            RoutineStep(
                action="file_write",
                parameters={"path": str(tmp_path / "valid.txt"), "content": "ok"},
            ),
            RoutineStep(
                action="file_read",
                parameters={"path": str(tmp_path / "nonexistent_ghost_file.txt")},
            ),
            RoutineStep(
                action="file_write",
                parameters={"path": str(tmp_path / "should_not_run.txt"), "content": "never"},
            ),
        ],
    )

    fallback_called = []

    def mock_fallback_handler(res: ReplayResult):
        fallback_called.append(res)

    replayer = RoutineReplayer()
    result = replayer.replay_with_fallback(
        routine=routine,
        fallback_handler=mock_fallback_handler,
    )

    # Verification: Replay stopped at step 2, step 3 never executed!
    assert result.ok is False
    assert result.fallback_needed is True
    assert result.completed_steps == 1
    assert result.failed_step_index == 1  # 0-indexed: step 2
    assert (tmp_path / "should_not_run.txt").exists() is False

    # Fallback handler was invoked with exact failure context
    assert len(fallback_called) == 1
    assert fallback_called[0].routine_name == "flaky_routine"
    assert fallback_called[0].failed_step_index == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. Final Report Generator & Invariant "Done" Gating
# ─────────────────────────────────────────────────────────────────────────────
def test_task_report_generator_invariants_and_markdown(tmp_path: Path):
    st1 = Stage(
        name="stage_one",
        description="First stage",
        completion_check=CustomCheck(lambda s, e: True, "always pass"),
        status=StageStatus.COMPLETED,
    )
    st2_pending = Stage(
        name="stage_two",
        description="Second stage",
        completion_check=CustomCheck(lambda s, e: False, "incomplete"),
        status=StageStatus.RUNNING,
    )

    # If any stage is not COMPLETED, status CANNOT be "Done"
    incomplete_report = TaskReportGenerator.generate(
        task_id="task_fail_1",
        goal="Incomplete workflow",
        stages=[st1, st2_pending],
        task_state="running",
    )
    assert incomplete_report.all_checks_passed is False
    assert incomplete_report.status == "Failed"
    assert "Investigate stage check failures" in incomplete_report.what_i_must_do_next[0]

    # When all stages are COMPLETED, status is "Done"
    st2_pending.status = StageStatus.COMPLETED
    complete_report = TaskReportGenerator.generate(
        task_id="task_success_1",
        goal="Complete workflow",
        stages=[st1, st2_pending],
        task_state="completed",
    )
    assert complete_report.all_checks_passed is True
    assert complete_report.status == "Done"

    # Markdown rendering verification
    md = complete_report.to_markdown()
    assert "# Task Execution Report: Complete workflow" in md
    assert "**Status**: **✔ DONE**" in md
    assert "| **stage_one** | ✔ completed | `True` |" in md
    assert "| **stage_two** | ✔ completed | `True` |" in md
    assert "No further human action required" in md
