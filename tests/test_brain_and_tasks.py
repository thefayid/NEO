"""
tests/test_brain_and_tasks.py — Unit tests for Action Whitelist, Goal Verifier, and Task Manager.
"""
from pathlib import Path
import pytest
from pydantic import ValidationError

from neo.brain.planner import ActionDispatcher
from neo.brain.verifier import GoalVerifier
from neo.brain.whitelist import AgentDecision
from neo.config import load_settings
from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.tasks.task_manager import TaskManager, TaskState


def test_agent_decision_whitelist_validation():
    # Valid Level 1 action
    d1 = AgentDecision(
        thought="Reading config file",
        action="file_read",
        parameters={"path": "notes.txt"},
    )
    assert d1.action == "file_read"

    # Valid Level 3 action
    d2 = AgentDecision(
        thought="Clicking button",
        action="click",
        parameters={"element_id": 5},
    )
    assert d2.action == "click"

    # Unwhitelisted action -> rejected
    with pytest.raises(ValidationError) as exc_info:
        AgentDecision(
            thought="Inventing shell action",
            action="execute_shell_script",
            parameters={"cmd": "whoami"},
        )
    assert "not in the allowed whitelist" in str(exc_info.value)

    # Missing mandatory parameter -> rejected
    with pytest.raises(ValidationError) as exc_info_params:
        AgentDecision(
            thought="Missing path parameter",
            action="file_read",
            parameters={},
        )
    assert "file_read requires 'path'" in str(exc_info_params.value)


def test_goal_verifier_file_criteria(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    target = tmp_path / "result.txt"
    target.write_text("Mission Accomplished: 42", encoding="utf-8")

    # Match criteria
    verifier = GoalVerifier(
        goal_description="Verify result file",
        expected_file=str(target),
        expected_file_contains="Mission Accomplished",
    )
    res = verifier.evaluate({})
    assert res.completed is True
    assert "Verified file" in res.rationale

    # Mismatch criteria
    verifier_fail = GoalVerifier(
        goal_description="Verify result file",
        expected_file=str(target),
        expected_file_contains="Incorrect Value",
    )
    res_fail = verifier_fail.evaluate({})
    assert res_fail.completed is False


def test_task_manager_lifecycle_and_budget(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    target = tmp_path / "output.txt"

    tm = TaskManager()
    verifier = GoalVerifier(
        goal_description="Write output file",
        expected_file=str(target),
        expected_file_contains="Success",
    )

    task = tm.create_task(goal="Write output file", verifier=verifier, max_steps=3)
    assert task.state == TaskState.PENDING
    assert task.current_step == 0

    # Step 1: Write incomplete text
    d1 = AgentDecision(
        thought="Writing partial draft",
        action="file_write",
        parameters={"path": str(target), "content": "Drafting..."},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, d1)
    assert t_rec.state == TaskState.RUNNING
    assert t_rec.current_step == 1
    assert verif_res.completed is False

    # Step 2: Write required content
    d2 = AgentDecision(
        thought="Writing final text with expected string",
        action="file_write",
        parameters={"path": str(target), "content": "Success", "mode": "append"},
    )
    t_rec, exec_res, verif_res = tm.execute_step(task.task_id, d2)
    assert t_rec.state == TaskState.COMPLETED
    assert verif_res.completed is True
    assert t_rec.completed_at is not None


def test_task_manager_budget_exhaustion(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    tm = TaskManager()
    verifier = GoalVerifier(
        goal_description="Unachievable goal",
        expected_file=str(tmp_path / "never_exists.txt"),
    )

    task = tm.create_task(goal="Impossible task", verifier=verifier, max_steps=2)

    d = AgentDecision(
        thought="Listing files",
        action="file_list",
        parameters={"path": str(tmp_path)},
    )

    # Step 1
    tm.execute_step(task.task_id, d)
    assert task.state == TaskState.RUNNING

    # Step 2 (budget limit reached)
    tm.execute_step(task.task_id, d)
    assert task.state == TaskState.FAILED
    assert "Exceeded maximum step budget" in (task.final_rationale or "")


def test_task_manager_emergency_stop_halts_execution(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    tm = TaskManager()
    task = tm.create_task(goal="Test emergency stop", max_steps=5)

    emergency_stop.trigger("User triggered emergency halt")

    d = AgentDecision(
        thought="Any step",
        action="file_list",
        parameters={"path": str(tmp_path)},
    )

    with pytest.raises(EmergencyStopTriggeredError):
        tm.execute_step(task.task_id, d)

    assert task.state == TaskState.STOPPED
    emergency_stop.reset()
