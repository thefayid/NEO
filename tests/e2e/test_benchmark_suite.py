"""
tests/e2e/test_benchmark_suite.py — Pytest Integration for E2E Benchmark Suite.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from neo.brain.planner import ActionDispatcher
from neo.config import load_settings
from neo.safety import get_confirmation_gate
from neo.tasks import TaskManager
from tests.e2e.scenarios import ALL_SCENARIOS, BenchmarkScenario, ScenarioContext
from tests.e2e.server import BenchmarkServer


@pytest.fixture(scope="module")
def benchmark_server():
    server = BenchmarkServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="module")
def benchmark_context(benchmark_server):
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir)
        load_settings(allowed_folders=[str(ws_path)])

        gate = get_confirmation_gate()
        gate.set_handler(lambda action, assess, timeout: (False if assess.requires_hard_stop else True, "Test handler decision"))

        dispatcher = ActionDispatcher()
        task_manager = TaskManager(dispatcher=dispatcher)

        ctx = ScenarioContext(
            server_url=benchmark_server.base_url,
            workspace_dir=ws_path,
            dispatcher=dispatcher,
            task_manager=task_manager,
        )
        yield ctx
        gate.set_handler(None)


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: f"{s.scenario_id}_{s.name}")
def test_e2e_benchmark_scenario(scenario: BenchmarkScenario, benchmark_context: ScenarioContext):
    """Executes each of the 26 benchmark scenarios and asserts passing outcome."""
    result = scenario.execute(benchmark_context)
    assert result.passed is True, f"Scenario {scenario.scenario_id} failed: {result.error_message}"
