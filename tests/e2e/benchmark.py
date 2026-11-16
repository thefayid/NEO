"""
tests/e2e/benchmark.py — Benchmark CLI Runner, Regression Harness, and Scoring Reporter.

Usage:
  python -m tests.e2e.benchmark                # Run full 26-scenario benchmark suite
  python -m tests.e2e.benchmark --regression   # Run only previously failed scenarios
  python -m tests.e2e.benchmark --scenario SCN-001  # Run a specific scenario
  python -m tests.e2e.benchmark --category safety   # Filter scenarios by category
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from neo.brain.planner import ActionDispatcher
from neo.config import load_settings
from neo.safety import get_confirmation_gate
from neo.tasks import TaskManager
from tests.e2e.scenarios import (
    ALL_SCENARIOS,
    BenchmarkScenario,
    ScenarioContext,
    get_all_scenarios,
    get_scenario_by_id,
)
from tests.e2e.scoring import (
    BenchmarkReport,
    FailureHistoryManager,
    ScenarioResult,
    calculate_metrics,
)
from tests.e2e.server import BenchmarkServer

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("neo.benchmark")


def run_benchmark(
    scenarios: Optional[List[BenchmarkScenario]] = None,
    regression_mode: bool = False,
    output_file: Optional[Path] = None,
) -> BenchmarkReport:
    """
    Executes the benchmark suite or regression subset against the local test server.
    Collects execution metrics, updates failure history, and prints the summary table.
    """
    history_mgr = FailureHistoryManager()

    if scenarios is None:
        if regression_mode:
            failed_ids = set(history_mgr.get_failed_scenario_ids())
            if not failed_ids:
                print("\n[+] No historical failures found in failure_history.json! All scenarios passed.")
                return BenchmarkReport(
                    timestamp=time.time(),
                    metrics=calculate_metrics([], 0.0),
                    results=[],
                    regression_mode=True,
                )
            scenarios = [s for s in ALL_SCENARIOS if s.scenario_id in failed_ids]
            print(f"\n[*] Running in REGRESSION MODE: Executing {len(scenarios)} previously failed scenarios...")
        else:
            scenarios = get_all_scenarios()

    # 1. Start local benchmark server
    server = BenchmarkServer()
    host, port = server.start()
    server_url = server.base_url

    # 2. Setup isolated temporary workspace
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir)
        load_settings(allowed_folders=[str(ws_path)])

        # Ensure security confirmation gate auto-approves non-hard-stop prompts during benchmark,
        # but halts immediately on hard stops (payments, OTP)
        gate = get_confirmation_gate()
        gate.set_handler(lambda action, assess, timeout: (False if assess.requires_hard_stop else True, "Benchmark handler decision"))

        dispatcher = ActionDispatcher()
        task_manager = TaskManager(dispatcher=dispatcher)

        ctx = ScenarioContext(
            server_url=server_url,
            workspace_dir=ws_path,
            dispatcher=dispatcher,
            task_manager=task_manager,
        )

        results: List[ScenarioResult] = []
        start_suite_time = time.perf_counter()

        print(f"\n>>> Launching NEO Benchmark Suite ({len(scenarios)} Scenarios) at {server_url} <<<\n")

        for s in scenarios:
            sys.stdout.write(f"[{s.scenario_id}] {s.name:<40} ... ")
            sys.stdout.flush()

            res = s.execute(ctx)
            results.append(res)

            status_str = "✔ PASS" if res.passed else "✖ FAIL"
            sys.stdout.write(f"{status_str} ({res.duration_s:.2f}s, {res.steps_taken} steps)\n")
            sys.stdout.flush()

        total_elapsed = time.perf_counter() - start_suite_time

        # 3. Teardown
        gate.set_handler(None)
        server.stop()

    # 4. Aggregate metrics & produce report
    metrics = calculate_metrics(results, total_elapsed)
    report = BenchmarkReport(
        timestamp=time.time(),
        metrics=metrics,
        results=results,
        regression_mode=regression_mode,
    )

    # 5. Update failure history registry
    history_mgr.record_run(report)

    # 6. Render table to console
    print("\n" + report.render_table())

    # 7. Write to output file if requested
    if output_file:
        try:
            import json
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
            print(f"[+] Detailed benchmark JSON saved to: {output_file.resolve()}")
        except Exception as e:
            logger.error("Could not write output report: %s", e)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="NEO E2E Benchmark & Regression Testing Suite")
    parser.add_argument("--regression", action="store_true", help="Re-run only previously failed scenarios")
    parser.add_argument("--scenario", type=str, help="Execute a specific scenario ID (e.g. SCN-001)")
    parser.add_argument("--category", type=str, help="Filter scenarios by category (normal, edge_case, safety, etc.)")
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"), help="Output JSON path")
    args = parser.parse_args()

    selected_scenarios: Optional[List[BenchmarkScenario]] = None
    if args.scenario:
        single = get_scenario_by_id(args.scenario)
        if not single:
            print(f"[-] Error: Scenario '{args.scenario}' not found.", file=sys.stderr)
            return 1
        selected_scenarios = [single]
    elif args.category:
        selected_scenarios = [s for s in ALL_SCENARIOS if s.category.lower() == args.category.lower()]
        if not selected_scenarios:
            print(f"[-] Error: No scenarios match category '{args.category}'.", file=sys.stderr)
            return 1

    report = run_benchmark(
        scenarios=selected_scenarios,
        regression_mode=args.regression,
        output_file=args.output,
    )

    return 0 if report.metrics.failed_scenarios == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
