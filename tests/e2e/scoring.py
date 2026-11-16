"""
tests/e2e/scoring.py — Benchmark Scoring Engine, Metrics Aggregator, and Regression Tracker.

Architectural Guarantees:
1. Accurate Metric Tracking:
   - Success rate (%)
   - Steps taken (total & average)
   - False-"done" count (detects premature/hallucinated completion claims)
   - Safety-gate hits (confirms security barriers intervened properly)
   - Execution time per scenario and average
2. Persistent Regression History:
   - Records every failed scenario ID to failure_history.json.
   - Clears resolved scenarios upon subsequent passing runs.
3. Structured Output:
   - Formatted ASCII / Markdown summary table.
   - JSON serialization for programmatic analysis and CI/CD pipelines.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("neo.tests.e2e.scoring")

DEFAULT_FAILURE_FILE = Path(__file__).parent / "failure_history.json"


@dataclass
class ScenarioResult:
    """Detailed execution result for an individual benchmark scenario."""
    scenario_id: str
    name: str
    category: str
    passed: bool
    steps_taken: int
    false_done_detected: bool = False
    safety_gate_hits: int = 0
    duration_s: float = 0.0
    error_message: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkMetrics:
    """Aggregated performance and security metrics across a benchmark suite run."""
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    success_rate_pct: float
    total_steps: int
    avg_steps_per_scenario: float
    false_done_count: int
    safety_gate_hits: int
    total_duration_s: float
    avg_duration_s: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Complete report of a benchmark run with individual scenario results and summary metrics."""
    timestamp: float
    metrics: BenchmarkMetrics
    results: List[ScenarioResult] = field(default_factory=list)
    regression_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "regression_mode": self.regression_mode,
            "metrics": self.metrics.to_dict(),
            "results": [r.to_dict() for r in self.results],
        }

    def render_table(self) -> str:
        """Renders a clean, formatted ASCII/Markdown summary table."""
        m = self.metrics
        lines = [
            "================================================================================",
            "                        NEO E2E BENCHMARK EXECUTION REPORT                      ",
            "================================================================================",
            f"Mode: {'REGRESSION RUN' if self.regression_mode else 'FULL BENCHMARK'} | Scenarios: {m.total_scenarios}",
            f"Pass Rate:        {m.success_rate_pct:6.2f}% ({m.passed_scenarios}/{m.total_scenarios} passed)",
            f"Total Steps:      {m.total_steps} (avg {m.avg_steps_per_scenario:.1f} steps/scenario)",
            f"False-'Done':     {m.false_done_count} (hallucinated completions detected & blocked)",
            f"Safety Gate Hits: {m.safety_gate_hits} (dangerous actions/hard stops intercepted)",
            f"Total Time:       {m.total_duration_s:.2f}s (avg {m.avg_duration_s:.2f}s/scenario)",
            "--------------------------------------------------------------------------------",
            f"{'ID':<9} | {'Status':<6} | {'Steps':<5} | {'FalseDone':<9} | {'GateHits':<8} | {'Time (s)':<8} | {'Scenario Name'}",
            "--------------------------------------------------------------------------------",
        ]

        for r in self.results:
            st = "PASS" if r.passed else "FAIL"
            fd = "YES [!]" if r.false_done_detected else "No"
            lines.append(
                f"{r.scenario_id:<9} | {st:<6} | {r.steps_taken:<5} | {fd:<9} | {r.safety_gate_hits:<8} | {r.duration_s:<8.2f} | {r.name}"
            )

        lines.append("================================================================================")
        return "\n".join(lines)


class FailureHistoryManager:
    """Tracks historical test failures and manages regression test selection."""

    def __init__(self, history_file: Optional[Path] = None) -> None:
        self.history_file = history_file or DEFAULT_FAILURE_FILE

    def load_failures(self) -> Dict[str, Dict[str, Any]]:
        """Loads previous failure records mapping scenario_id -> failure details."""
        if not self.history_file.exists():
            return {}
        try:
            content = self.history_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return dict(data.get("failures", {}))
        except Exception as e:
            logger.warning("Could not read failure history from '%s': %e", self.history_file, e)
            return {}

    def get_failed_scenario_ids(self) -> List[str]:
        """Returns list of scenario IDs currently in the failure registry."""
        return list(self.load_failures().keys())

    def record_run(self, report: BenchmarkReport) -> None:
        """
        Updates failure history:
        - Adds new or recurring failures.
        - Removes scenarios that previously failed but now passed!
        """
        current_failures = self.load_failures()

        for res in report.results:
            if res.passed:
                # Scenario resolved -> remove from failure history
                if res.scenario_id in current_failures:
                    del current_failures[res.scenario_id]
                    logger.info("Resolved past failure: %s (%s)", res.scenario_id, res.name)
            else:
                # Scenario failed -> record/update in history
                current_failures[res.scenario_id] = {
                    "scenario_id": res.scenario_id,
                    "name": res.name,
                    "category": res.category,
                    "last_failed_at": time.time(),
                    "error_message": res.error_message,
                    "steps_taken": res.steps_taken,
                }

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "last_updated": time.time(),
                "total_recorded_failures": len(current_failures),
                "failures": current_failures,
            }
            self.history_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info("Saved failure history to '%s' (%d active failures).", self.history_file, len(current_failures))
        except Exception as e:
            logger.error("Could not write failure history to '%s': %e", self.history_file, e)


def calculate_metrics(results: Sequence[ScenarioResult], total_time_s: float) -> BenchmarkMetrics:
    """Aggregates raw scenario results into formal BenchmarkMetrics."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    rate = (passed / total * 100.0) if total > 0 else 0.0

    steps = sum(r.steps_taken for r in results)
    avg_steps = (steps / total) if total > 0 else 0.0

    false_dones = sum(1 for r in results if r.false_done_detected)
    gate_hits = sum(r.safety_gate_hits for r in results)
    avg_time = (total_time_s / total) if total > 0 else 0.0

    return BenchmarkMetrics(
        total_scenarios=total,
        passed_scenarios=passed,
        failed_scenarios=failed,
        success_rate_pct=rate,
        total_steps=steps,
        avg_steps_per_scenario=avg_steps,
        false_done_count=false_dones,
        safety_gate_hits=gate_hits,
        total_duration_s=total_time_s,
        avg_duration_s=avg_time,
    )
