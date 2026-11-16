"""
tests/test_agent_and_ui.py — Tests for LLM Decision parsing, NeoAgent loop, coordinate dispatch, and UI confirmation.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from neo.brain.agent import NeoAgent
from neo.brain.llm_client import (
    LLMDecisionParseError,
    MockLLMClient,
    parse_llm_json,
    validate_decision,
)
from neo.brain.planner import ActionDispatcher
from neo.brain.verifier import GoalVerifier
from neo.brain.whitelist import AgentDecision
from neo.config import load_settings
from neo.safety.emergency_stop import emergency_stop
from neo.tasks.task_manager import TaskManager, TaskState
from neo.ui.confirmation_dialog import show_confirmation_popup


def test_parse_llm_json_variations():
    # 1. Clean JSON
    raw1 = '{"thought": "Opening file", "action": "file_read", "parameters": {"path": "test.txt"}}'
    d1 = parse_llm_json(raw1)
    assert d1["action"] == "file_read"

    # 2. Markdown code fenced JSON
    raw2 = """```json
{
  "thought": "Navigating to site",
  "action": "browser_navigate",
  "parameters": {"url": "https://example.com"}
}
```"""
    d2 = parse_llm_json(raw2)
    assert d2["action"] == "browser_navigate"

    # 3. Code fence with chatter before and after
    raw3 = """Here is my decision:
```
{
  "thought": "Listing files",
  "action": "file_list",
  "parameters": {"path": "."}
}
```
Let me know if this helps."""
    d3 = parse_llm_json(raw3)
    assert d3["action"] == "file_list"

    # 4. Invalid JSON
    with pytest.raises(LLMDecisionParseError):
        parse_llm_json("This is not JSON at all.")


def test_validate_decision_enforces_whitelist():
    raw_valid = '{"thought": "Valid click", "action": "click", "parameters": {"coords": [100, 200]}}'
    dec = validate_decision(raw_valid)
    assert dec.action == "click"
    assert dec.parameters["coords"] == [100, 200]

    raw_unwhitelisted = '{"thought": "Invalid action", "action": "run_arbitrary_shell", "parameters": {}}'
    with pytest.raises(LLMDecisionParseError):
        validate_decision(raw_unwhitelisted)


def test_neo_agent_end_to_end_loop_with_mock(tmp_path: Path):
    load_settings(allowed_folders=[str(tmp_path)])
    target_file = tmp_path / "final_report.txt"

    # Sequence of decisions: step 1 writes partial, step 2 writes completed text
    decisions = [
        AgentDecision(
            thought="Step 1: Write draft",
            action="file_write",
            parameters={"path": str(target_file), "content": "Drafting initial findings..."},
        ),
        AgentDecision(
            thought="Step 2: Append final conclusion",
            action="file_write",
            parameters={"path": str(target_file), "content": "Mission Verified Complete.", "mode": "append"},
        ),
    ]

    mock_llm = MockLLMClient(decision_sequence=decisions)
    verifier = GoalVerifier(
        goal_description="Produce verified report",
        expected_file=str(target_file),
        expected_file_contains="Mission Verified Complete",
    )

    agent = NeoAgent(llm_client=mock_llm)
    task_rec = agent.run_task(
        goal="Produce verified report",
        verifier=verifier,
        max_steps=5,
    )

    assert task_rec.state == TaskState.COMPLETED
    assert task_rec.current_step == 2
    assert "Mission Verified Complete" in target_file.read_text(encoding="utf-8")
    assert len(mock_llm.call_history) == 2

    # Check evidence feedback into step 2 prompt
    step2_prompt = mock_llm.call_history[1]["step_prompt"]
    assert "FEEDBACK" in step2_prompt
    assert "file_write" in step2_prompt


def test_action_dispatcher_level_5_coordinates():
    dispatcher = ActionDispatcher()

    # click_coords
    with patch("neo.brain.planner.execute_action") as mock_exec:
        mock_exec.return_value = MagicMock(ok=True, data=None, warning=None, evidence={"method": "mouse"})
        dec_click = AgentDecision(
            thought="Clicking visual coordinate",
            action="click_coords",
            parameters={"coords": [450, 600]},
        )
        res = dispatcher.dispatch(dec_click)
        assert res.ok is True
        mock_exec.assert_called_once()
        args, kwargs = mock_exec.call_args
        assert args[0]["action"] == "click"
        assert args[0]["coords"] == (450, 600)

    # type_coords
    with patch("neo.brain.planner.execute_action") as mock_exec_type:
        mock_exec_type.return_value = MagicMock(ok=True, data=None, warning=None, evidence={})
        dec_type = AgentDecision(
            thought="Focus and type at coordinates",
            action="type_coords",
            parameters={"coords": [300, 400], "text": "Hello World"},
        )
        res_type = dispatcher.dispatch(dec_type)
        assert res_type.ok is True
        assert mock_exec_type.call_count == 2  # 1 click + 1 type
