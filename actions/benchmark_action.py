"""
actions/benchmark_action.py — Operational Benchmark Drills Action for NEO.

Auto-discovered by core/action_loader.py. Exposes the 6 operational benchmark drills
to verify system reliability weekly or when commanded "BENCHMARK".
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core.neo_benchmark_drills import benchmark_runner


def manage_benchmark_drills(parameters: dict, **kwargs) -> str:
    """Handler for NEO Operational Benchmark Drills."""
    operation = str(parameters.get("operation", "run")).strip().lower()
    drill_id = parameters.get("drill_id")

    if operation == "run":
        if drill_id:
            did = int(drill_id)
            if did == 1:
                res = benchmark_runner.run_ghost_test()
            elif did == 2:
                res = benchmark_runner.run_interrupt_test()
            elif did == 3:
                res = benchmark_runner.run_moved_ui_test()
            elif did == 4:
                res = benchmark_runner.run_precision_test()
            elif did == 5:
                res = benchmark_runner.run_vague_command_test()
            elif did == 6:
                res = benchmark_runner.run_long_chain_test()
            else:
                return f"status=failed error='Invalid drill_id {did}. Must be 1 to 6.'"

            status_str = "PASS ✅" if res.passed else "FAIL ❌"
            out = [
                f"Drill {res.drill_id}: {res.name} -> {status_str}",
                f"Evidence: {res.evidence}",
            ]
            if not res.passed and res.prompt_fix:
                out.append(f"Proposed Prompt Fix: {res.prompt_fix}")
            return "\n".join(out)

        report = benchmark_runner.run_all()
        return report.to_text_summary()

    elif operation == "last_results":
        if benchmark_runner.log_path.exists():
            try:
                with open(benchmark_runner.log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return (
                        f"status=done timestamp='{data.get('timestamp')}' "
                        f"passed={data.get('passed_count')}/6 score={data.get('score_percentage')}%\n"
                        f"{json.dumps(data.get('results', []), indent=2)}"
                    )
            except Exception as e:
                return f"status=failed error='Failed to read last benchmark: {e}'"
        return "status=done message='No benchmark has been run yet.'"

    else:
        return (
            f"status=failed error='Unknown operation: {operation}'. "
            f"Valid operations: run, last_results."
        )


TOOL = {
    "name": "benchmark_drills",
    "description": (
        "Runs NEO's 6 operational reliability benchmark drills weekly or when commanded 'BENCHMARK'. "
        "Drills: (1) Ghost test, (2) Interrupt test, (3) Moved-UI test, (4) Precision test, "
        "(5) Vague-command test, and (6) Long-chain test across 3 apps. "
        "Scores each pass/fail with concrete evidence and proposes prompt fixes for any failures."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "One of: 'run' (run all drills or single drill) or 'last_results' (inspect latest scorecard).",
            },
            "drill_id": {
                "type": "INTEGER",
                "description": "Optional specific drill ID to run (1 to 6). Omit to run full benchmark suite.",
            },
        },
        "required": ["operation"],
    },
    "handler": manage_benchmark_drills,
}

