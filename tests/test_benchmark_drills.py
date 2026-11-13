import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from core.neo_benchmark_drills import NEOBenchmarkRunner, BenchmarkReport, DrillResult
from actions.benchmark_action import manage_benchmark_drills, TOOL
from core.action_loader import discover_actions


class TestNEOBenchmarkDrills(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp_dir.name) / "test_benchmark.json"
        self.runner = NEOBenchmarkRunner(log_path=self.log_path)

    def tearDown(self):
        time.sleep(0.05)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_ghost_drill(self):
        result = self.runner.run_ghost_test()
        self.assertEqual(result.drill_id, 1)
        self.assertTrue(result.passed)
        self.assertIn("OS resolver returned None", result.evidence)

    def test_interrupt_drill(self):
        result = self.runner.run_interrupt_test()
        self.assertEqual(result.drill_id, 2)
        self.assertTrue(result.passed)
        self.assertIn("Halted task plan immediately", result.evidence)

    def test_moved_ui_drill(self):
        result = self.runner.run_moved_ui_test(old_coords=(100, 100), new_coords=(300, 400))
        self.assertEqual(result.drill_id, 3)
        self.assertTrue(result.passed)
        self.assertIn("Cached coordinates", result.evidence)
        self.assertIn("re-located target", result.evidence)

    def test_precision_drill(self):
        result = self.runner.run_precision_test()
        self.assertEqual(result.drill_id, 4)
        self.assertTrue(result.passed)
        self.assertIn("200/200 characters matched exactly", result.evidence)

    def test_vague_command_drill(self):
        result = self.runner.run_vague_command_test("do that thing again")
        self.assertEqual(result.drill_id, 5)
        self.assertTrue(result.passed)
        self.assertIn("classified as AMBIGUOUS", result.evidence)
        self.assertIn("numbered options", result.evidence)

    def test_long_chain_drill(self):
        result = self.runner.run_long_chain_test()
        self.assertEqual(result.drill_id, 6)
        self.assertTrue(result.passed)
        self.assertIn("12 steps executed across 3 applications", result.evidence)
        self.assertIn("Saved 3 checkpoints", result.evidence)

    def test_run_all_drills_and_persistence(self):
        report = self.runner.run_all()
        self.assertEqual(report.total_drills, 6)
        self.assertEqual(report.passed_count, 6)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.score_percentage, 100.0)

        # Check summary text
        summary = report.to_text_summary()
        self.assertIn("OPERATIONAL BENCHMARK DRILL SCORECARD", summary)
        self.assertIn("100.0%", summary)
        self.assertIn("[PASS] ✅", summary)

        # Verify disk persistence
        self.assertTrue(self.log_path.exists())
        data = json.loads(self.log_path.read_text(encoding="utf-8"))
        self.assertEqual(data["passed_count"], 6)

    def test_manage_benchmark_drills_handler(self):
        from core.neo_benchmark_drills import benchmark_runner
        old_log = benchmark_runner.log_path
        try:
            benchmark_runner.log_path = self.log_path

            # Single drill run
            res_single = manage_benchmark_drills({"operation": "run", "drill_id": 1})
            self.assertIn("Drill 1:", res_single)
            self.assertIn("PASS ✅", res_single)

            # Full run
            res_all = manage_benchmark_drills({"operation": "run"})
            self.assertIn("BENCHMARK DRILL SCORECARD", res_all)
            self.assertIn("6/6", res_all)

            # Last results
            res_last = manage_benchmark_drills({"operation": "last_results"})
            self.assertIn("status=done", res_last)
            self.assertIn("passed=6/6", res_last)
        finally:
            benchmark_runner.log_path = old_log

    def test_action_loader_discovers_benchmark_drills(self):
        reg = discover_actions(Path("actions"))
        decls = reg.get_tool_declarations()
        tool_names = [d["name"] for d in decls]
        self.assertIn("benchmark_drills", tool_names)


if __name__ == "__main__":
    unittest.main()

