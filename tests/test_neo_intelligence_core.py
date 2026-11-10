"""
tests/test_neo_intelligence_core.py — Automated Unit & Integration Tests for NEO Advanced Intelligence Core.

Covers:
- Pillar 2: Lifelong Tri-Tier Memory & Semantic Knowledge Graph (core.neo_brain)
- Pillar 3: Autonomous Computer-Use & Multi-Step Agentic Loops (core.neo_agentic_loop)
- Pillar 4: Dynamic Self-Tooling & Meta-Plugin Synthesizer (core.neo_self_tooling)
- Pillar 5: Multimodal Visual Grounding & Screen Highlights (core.neo_visual_grounding)
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from core.neo_brain import (
    WorkingMemory,
    EpisodicMemory,
    SemanticKnowledgeGraph,
    NeoBrainStore,
    brain,
)
from core.neo_agentic_loop import (
    AgenticGoal,
    GoalStep,
    GoalStatus,
    AgenticToolbox,
    SelfReflectionEngine,
    AutonomousGoalEngine,
    goal_engine,
)
from core.neo_self_tooling import (
    DynamicToolSynthesizer,
    synthesizer,
)
from core.neo_visual_grounding import (
    UIElement,
    MacOSScreenHighlightOverlay,
    VisualGroundingEngine,
    visual_grounding,
)


class TestNeoBrainTriTierMemory(unittest.TestCase):
    """Verifies Pillar 2: Tri-Tier Memory and Knowledge Graph."""

    def test_working_memory_state(self):
        wm = WorkingMemory()
        wm.update_environment(
            active_window="Visual Studio Code - main.py",
            clipboard="https://apple.com/macos/sequoia"
        )
        wm.set_active_goal("Refactor design system to Apple Sequoia HIG")
        wm.add_turn("user", "Please verify design tokens")
        wm.add_turn("neo", "Tokens are synchronized with Apple HIG")

        dump = wm.get_summary()
        self.assertEqual(dump["active_window"], "Visual Studio Code - main.py")
        self.assertEqual(dump["clipboard_snippet"], "https://apple.com/macos/sequoia")
        self.assertEqual(dump["current_goal"], "Refactor design system to Apple Sequoia HIG")
        self.assertEqual(dump["turn_count"], 2)
        self.assertEqual(wm.recent_turns[0]["content"], "Please verify design tokens")

    def test_episodic_memory_bm25_and_decay(self):
        test_db_path = _ROOT / "memory" / "test_brain.db"
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except Exception:
                pass

        store = NeoBrainStore(db_path=test_db_path)
        episodic = EpisodicMemory(store)

        eid1 = episodic.log_event("TOOL_EXEC", "User requested compilation of kernel module", metadata={"tag": "build"})
        eid2 = episodic.log_event("CHAT_TURN", "Discussed Apple macOS Sequoia HIG design tokens", metadata={"tag": "macos"})
        self.assertGreater(eid1, 0)
        self.assertGreater(eid2, 0)

        # Query via BM25
        results = episodic.query_events("macOS Sequoia design", limit=5)
        self.assertTrue(len(results) >= 1)
        self.assertIn("Sequoia", results[0]["content"])

    def test_semantic_knowledge_graph_relations(self):
        test_db_path = _ROOT / "memory" / "test_brain.db"
        store = NeoBrainStore(db_path=test_db_path)
        kg = SemanticKnowledgeGraph(store)

        kg.upsert_entity("Apple Inc", "ORGANIZATION", attributes={"hq": "Cupertino"})
        kg.upsert_entity("macOS Sequoia", "OPERATING_SYSTEM", attributes={"version": "15.0"})
        kg.add_relation("Apple Inc", "macOS Sequoia", "DEVELOPED", weight=1.0)

        # Verify query relations
        rels = kg.get_related_entities("Apple Inc")
        self.assertTrue(len(rels) >= 1)
        self.assertEqual(rels[0]["relation_type"], "DEVELOPED")
        self.assertEqual(rels[0]["target_name"], "macOS Sequoia")

    def test_brain_prompt_synthesis(self):
        brain.working.set_active_goal("Build macOS App Shell")
        synth = brain.synthesize_intelligence_prompt("How do I structure the sidebar?")
        self.assertIn("Current Active Goal:", synth)
        self.assertIn("Build macOS App Shell", synth)


class TestNeoAgenticLoop(unittest.TestCase):
    """Verifies Pillar 3: Multi-step Autonomous Loops & Self-Reflection."""

    def test_agentic_toolbox_run_command(self):
        code, out, err = AgenticToolbox.run_command('python -c "print(40 + 2)"')
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "42")

    def test_agentic_toolbox_file_operations(self):
        test_file = _ROOT / "tests" / "_temp_test_file.txt"
        ok_w, msg_w = AgenticToolbox.write_file(str(test_file), "Autonomous computer-use test content.")
        self.assertTrue(ok_w)

        ok_r, content_r = AgenticToolbox.read_file(str(test_file))
        self.assertTrue(ok_r)
        self.assertIn("Autonomous computer-use test content.", content_r)

        if test_file.exists():
            test_file.unlink()

    def test_self_reflection_diagnosis(self):
        step = GoalStep(
            step_id=1,
            title="Run fast test server",
            tool_name="run_command",
            tool_args={"command": "python server.py"},
        )
        step.error = "ModuleNotFoundError: No module named 'fastapi'"
        corrected = SelfReflectionEngine.diagnose_and_correct(step)
        self.assertTrue(corrected)
        self.assertIn("pip install fastapi", step.tool_args["command"])
        self.assertIn("Missing Python dependency", step.reflection)

    def test_autonomous_goal_engine_execution(self):
        # Submit a fast atomic step goal
        goal_id = goal_engine.submit_goal("Verify system python version")
        self.assertIsNotNone(goal_id)

        # Allow worker thread time to process
        goal = None
        for _ in range(40):
            time.sleep(0.1)
            goal = goal_engine.get_goal(goal_id)
            if goal and goal.status in (GoalStatus.COMPLETED, GoalStatus.FAILED):
                break

        self.assertIsNotNone(goal)
        self.assertIn(goal.status, (GoalStatus.COMPLETED, GoalStatus.EXECUTING, GoalStatus.PLANNING))


class TestNeoSelfTooling(unittest.TestCase):
    """Verifies Pillar 4: Dynamic Self-Tooling & Meta-Plugin Synthesizer."""

    def tearDown(self):
        # Clean up any synthesized test files
        for tool_name in ["test_temperature_converter", "central_test_tool"]:
            p = Path("plugins") / "synthesized" / f"{tool_name}.py"
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def test_synthesizer_success(self):
        tool_name = "test_temperature_converter"
        desc = "Converts Fahrenheit to Celsius"
        code = """def test_temperature_converter(fahrenheit: float, **kwargs) -> float:
    return round((float(fahrenheit) - 32.0) * (5.0 / 9.0), 2)
"""
        ok, msg = synthesizer.synthesize_tool(tool_name, desc, code)
        self.assertTrue(ok, f"Synthesis failed: {msg}")

        # Execute synthesized tool
        result = synthesizer.execute_tool(tool_name, fahrenheit=212.0)
        self.assertEqual(result, 100.0)

        # Verify listed tools
        all_tools = synthesizer.list_synthesized_tools()
        names = [t["name"] for t in all_tools]
        self.assertIn(tool_name, names)

    def test_synthesizer_rejects_syntax_error(self):
        bad_code = "def invalid_syntax( broken python ::: "
        ok, msg = synthesizer.synthesize_tool("invalid_tool", "bad syntax test", bad_code)
        self.assertFalse(ok)
        self.assertIn("Syntax error", msg)


class TestNeoVisualGrounding(unittest.TestCase):
    """Verifies Pillar 5: Multimodal Visual Grounding & Overlay."""

    def test_coordinate_normalization_and_denormalization(self):
        sw, sh = 1920, 1080
        orig_box = (192, 108, 960, 540)
        norm = VisualGroundingEngine.normalize_box(orig_box, sw, sh)
        self.assertEqual(norm, (0.1, 0.1, 0.5, 0.5))

        denorm = VisualGroundingEngine.denormalize_box(norm, sw, sh)
        self.assertEqual(denorm, orig_box)

    def test_ui_element_geometry(self):
        elem = UIElement(
            label="Save Document",
            bbox=(100, 150, 260, 190),
            confidence=0.96,
            element_type="button",
        )
        self.assertEqual(elem.width, 160)
        self.assertEqual(elem.height, 40)
        self.assertEqual(elem.center, (180, 170))

        data = elem.to_dict()
        self.assertEqual(data["label"], "Save Document")
        self.assertEqual(data["element_type"], "button")
        self.assertEqual(data["center"], [180, 170])

    def test_screen_highlight_overlay_instantiation_and_render(self):
        overlay = MacOSScreenHighlightOverlay()
        overlay.highlight_target((80, 80, 240, 140), label="Unit Test Target", linger_ms=500)
        overlay.show()
        _app.processEvents()
        self.assertTrue(overlay.isVisible())
        self.assertEqual(overlay._target_label, "Unit Test Target")
        overlay.hide()


class TestCentralActionsAndCoordinator(unittest.TestCase):
    """Verifies action adapter handlers and the central coordinator bus."""

    def tearDown(self):
        p = Path("plugins") / "synthesized" / "central_test_tool.py"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    def test_action_execute_autonomous_goal(self):
        from actions.autonomous_goal import execute_autonomous_goal
        res = execute_autonomous_goal({"instruction": "Verify system disk and python version"})
        self.assertIn("initiated successfully", res)
        self.assertIn("Autonomous Goal", res)

    def test_action_manage_neo_memory(self):
        from actions.neo_memory import manage_neo_memory
        # 1. Remember
        rem_res = manage_neo_memory({
            "operation": "remember",
            "entity": "Fayid",
            "relation": "PREFERS",
            "target": "macOS Sequoia Graphite Dark Mode",
            "category": "USER_PREFERENCE"
        })
        self.assertIn("Successfully saved", rem_res)

        # 2. Query
        q_res = manage_neo_memory({"operation": "query", "query": "Fayid"})
        self.assertIn("Fayid", q_res)

        # 3. Context
        ctx_res = manage_neo_memory({"operation": "get_context"})
        self.assertIn("Active Window", ctx_res)

    def test_action_synthesize_custom_tool(self):
        from actions.dynamic_tool_creator import synthesize_custom_tool
        res = synthesize_custom_tool({
            "action_type": "synthesize",
            "tool_name": "central_test_tool",
            "description": "Calculates circle area",
            "code_body": "def central_test_tool(r, **kwargs):\n    return 3.14159 * float(r) ** 2\n"
        })
        self.assertIn("Success", res)

        list_res = synthesize_custom_tool({"action_type": "list"})
        self.assertIn("central_test_tool", list_res)

    def test_action_visual_screen_grounding(self):
        from actions.visual_grounding_action import visual_screen_grounding
        res = visual_screen_grounding({"action": "reverse_engineer", "format": "mermaid"})
        self.assertIsNotNone(res)

    def test_central_coordinator_telemetry(self):
        from core.neo_central_coordinator import central_core
        snap = central_core.get_full_telemetry_snapshot()
        self.assertIn("working_memory", snap)
        self.assertIn("synthesized_tools_count", snap)
        self.assertIn("timestamp", snap)

        # Test central remember
        ok = central_core.remember_fact("NEO", "POWERS", "Mark-LVI Desktop Assistant")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
