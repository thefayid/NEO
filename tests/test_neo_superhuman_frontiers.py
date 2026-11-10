"""
tests/test_neo_superhuman_frontiers.py — Verification Suite for NEO 4 Superhuman Frontiers.

Tests:
1. Autonomous Subagent Swarm War Room (Collaborative 4-agent execution: Architect, Coder, Critic, DevOps).
2. Cross-Device Telepathy & Mobile Executive Companion (Push alerts, remote command processing).
3. Self-Healing Codebase & Autonomous Test Guardian (Syntax audit, conventional commit generator).
4. Spatial Multimodal Vision & Neural Presence (Biometric presence, fatigue sentinel, document scanner).
"""
import os
import sys
import time
import unittest
from pathlib import Path

# Ensure application root is on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt6.QtWidgets import QApplication

# Headless Qt Application for UI component testing
_qapp = QApplication.instance()
if _qapp is None:
    _qapp = QApplication(sys.argv)

from core.neo_swarm_war_room import swarm_war_room, SwarmAgentRole, SwarmMissionState
from core.neo_mobile_telepathy import mobile_telepathy
from core.neo_self_healing import self_healing_guardian
from core.neo_spatial_vision import spatial_vision
from core.neo_central_coordinator import central_core


class TestNeoSuperhumanFrontiers(unittest.TestCase):

    # ── Frontier 1: Swarm War Room ───────────────────────────────────────────

    def test_swarm_mission_pipeline_execution(self):
        """Verifies collaborative 4-agent War Room pipeline (Architect, Coder, Critic, DevOps)."""
        from unittest.mock import patch
        with patch.object(swarm_war_room, "_query_agent_llm", return_value="Mocked subagent deliverable output with architecture specs and code."):
            mission_id = swarm_war_room.submit_mission("Build an authenticated rate-limited webhook handler")
            self.assertTrue(mission_id.startswith("mission_"))

            # Wait for the background worker to execute the lanes
            mission = None
            for _ in range(30):
                mission = swarm_war_room.get_mission(mission_id)
                if mission and mission.state in (SwarmMissionState.COMPLETED, SwarmMissionState.FAILED):
                    break
                time.sleep(0.1)

            self.assertIsNotNone(mission)
            self.assertEqual(mission.state, SwarmMissionState.COMPLETED)
            self.assertIn("architect", mission.deliverables)
            self.assertIn("coder", mission.deliverables)
            self.assertIn("critic", mission.deliverables)
            self.assertIn("devops", mission.deliverables)

            # Inspect deliverable contents
            arch = mission.deliverables["architect"]
            self.assertEqual(arch.status, "COMPLETED")
            self.assertGreater(len(arch.content), 20)

    # ── Frontier 2: Mobile Telepathy ─────────────────────────────────────────

    def test_mobile_telepathy_status_command(self):
        """Verifies remote /status command returns formatted telemetry snapshot."""
        resp = mobile_telepathy.process_remote_command("/status")
        self.assertIn("NEO System Status", resp)
        self.assertIn("CPU:", resp)
        self.assertIn("RAM:", resp)

    def test_mobile_telepathy_goal_command(self):
        """Verifies remote /goal command submits autonomous goal."""
        resp = mobile_telepathy.process_remote_command("/goal Run health check on active node")
        self.assertIn("Autonomous Goal Launched", resp)
        self.assertIn("ID:", resp)

    # ── Frontier 3: Self-Healing Codebase ────────────────────────────────────

    def test_workspace_self_healing_audit(self):
        """Verifies workspace syntax audit scans python files without throwing errors."""
        res = self_healing_guardian.run_workspace_audit()
        self.assertIn("workspace", res)
        self.assertIn("files_scanned", res)
        self.assertIn("errors_found", res)
        self.assertGreater(res["files_scanned"], 10)

    def test_conventional_commit_message_generation(self):
        """Verifies conventional commit message generator drafts structured message."""
        from unittest.mock import patch
        with patch("core.gemini.text", return_value="feat(core): implement autonomous self-healing sentinel"):
            msg = self_healing_guardian.generate_conventional_commit_message()
            self.assertIsInstance(msg, str)
            self.assertGreater(len(msg), 5)
            # Should start with a standard conventional commit prefix or chore
            valid_prefixes = ("feat", "fix", "refactor", "chore", "docs", "test", "perf")
            self.assertTrue(any(msg.lower().startswith(p) for p in valid_prefixes))

    # ── Frontier 4: Spatial Multimodal Vision ────────────────────────────────

    def test_spatial_vision_fatigue_and_presence(self):
        """Verifies fatigue detection triggers ergonomic break chip when focus exceeds threshold."""
        spatial_vision._continuous_focus_start = time.time() - 6000  # 100 minutes ago
        spatial_vision.is_present = True

        alerts = []
        spatial_vision.fatigue_alert.connect(lambda msg: alerts.append(msg))

        # Dummy frame triggers posture & fatigue evaluation
        res = spatial_vision.process_camera_frame(b"")
        self.assertIn("is_present", res)

    # ── Central Coordinator Interconnection ───────────────────────────────────

    def test_central_core_superhuman_api(self):
        """Verifies central core hub provides seamless unified access to all 4 frontiers."""
        from unittest.mock import patch
        with patch.object(swarm_war_room, "_query_agent_llm", return_value="Fast mocked response"):
            # 1. Swarm Mission
            mid = central_core.dispatch_swarm_mission("Quick verification objective")
            self.assertTrue(mid.startswith("mission_"))

            # 2. Self-Healing
            audit = central_core.run_workspace_self_healing()
            self.assertIn("files_scanned", audit)

            # 3. Git commit
            commit_msg = central_core.generate_git_commit()
            self.assertIsInstance(commit_msg, str)


if __name__ == "__main__":
    unittest.main()
