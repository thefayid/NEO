"""
tests/test_logging.py — Tests for structured JSON-lines step logging.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from neo.logging_setup import StepLogger, StepRecord


def test_log_step_writes_valid_json_line(tmp_path: Path):
    log_file = tmp_path / "test_steps.jsonl"
    logger = StepLogger(log_file)

    record = logger.log_step(
        task_id="task-001",
        stage="execute",
        action="launch_app",
        parameters={"app_name": "notepad.exe"},
        result={"status": "done", "pid": 1234},
        evidence={"window_hwnd": 5678, "process_running": True},
        duration=0.245,
        llm_decision="Call Level 1 Direct launch_app",
    )

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["task_id"] == "task-001"
    assert parsed["stage"] == "execute"
    assert parsed["action"] == "launch_app"
    assert parsed["parameters"] == {"app_name": "notepad.exe"}
    assert parsed["result"] == {"status": "done", "pid": 1234}
    assert parsed["evidence"] == {"window_hwnd": 5678, "process_running": True}
    assert parsed["duration"] == 0.245
    assert parsed["llm_decision"] == "Call Level 1 Direct launch_app"
    assert "T" in parsed["timestamp"]


def test_step_context_measures_duration(tmp_path: Path):
    log_file = tmp_path / "context_steps.jsonl"
    logger = StepLogger(log_file)

    with logger.step_context(
        task_id="task-002",
        stage="verify",
        action="inspect_window",
        parameters={"title": "Untitled - Notepad"},
        llm_decision="Verify window title via UIA",
    ) as ctx:
        # Simulate work
        ctx.result = "Window found and focused"
        ctx.evidence = {"hwnd": 9999, "title": "Untitled - Notepad"}

    records = logger.read_records(task_id="task-002")
    assert len(records) == 1
    rec = records[0]
    assert rec.task_id == "task-002"
    assert rec.stage == "verify"
    assert rec.action == "inspect_window"
    assert rec.result == "Window found and focused"
    assert rec.evidence == {"hwnd": 9999, "title": "Untitled - Notepad"}
    assert rec.duration >= 0.0


def test_read_records_filtering(tmp_path: Path):
    log_file = tmp_path / "multi_task.jsonl"
    logger = StepLogger(log_file)

    logger.log_step(task_id="task-A", stage="plan", action="plan_step", parameters={})
    logger.log_step(task_id="task-B", stage="plan", action="plan_step", parameters={})
    logger.log_step(task_id="task-A", stage="execute", action="click", parameters={})

    records_a = logger.read_records(task_id="task-A")
    assert len(records_a) == 2
    assert all(r.task_id == "task-A" for r in records_a)

    records_b = logger.read_records(task_id="task-B")
    assert len(records_b) == 1
    assert records_b[0].task_id == "task-B"

    all_records = logger.read_records()
    assert len(all_records) == 3


def test_concurrent_logging(tmp_path: Path):
    log_file = tmp_path / "concurrent_steps.jsonl"
    logger = StepLogger(log_file)

    threads = []
    num_threads = 5
    records_per_thread = 20

    def worker(tid: int):
        for i in range(records_per_thread):
            logger.log_step(
                task_id=f"thread-{tid}",
                stage="execute",
                action=f"action-{i}",
                parameters={"index": i},
                duration=0.01,
            )

    for tid in range(num_threads):
        t = threading.Thread(target=worker, args=(tid,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    all_records = logger.read_records()
    assert len(all_records) == num_threads * records_per_thread
