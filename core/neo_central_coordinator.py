"""
core/neo_central_coordinator.py — Central Intelligence Coordinator & Interconnection Bus for NEO.

Architecture:
1. Interconnects all features into a unified central nervous system:
   - Voice & Live Reasoning Engine (main.py)
   - Tri-Tier Brain & Semantic Knowledge Graph (core.neo_brain)
   - Autonomous Computer-Use & Agentic Loops (core.neo_agentic_loop)
   - Dynamic Self-Tooling Engine (core.neo_self_tooling)
   - Multimodal Visual Grounding & OS Control (core.neo_visual_grounding)
   - Stark Air Hand Gestures (actions.gesture_control)
   - Subagent Swarm Studio (actions.subagent_swarm)
   - Terminal & Workspace File View (core.neo_terminal_studio, core.neo_files_view)
   - macOS Spotlight & Tray Quick Panels (core.macos_spotlight, core.macos_tray_panel)
2. Thread-safe PyQT signal event bus for real-time telemetry and state distribution.
3. Unified high-level API for the Assistant to access and operate any subsystem.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import QObject, pyqtSignal

from core.neo_brain import brain
from core.neo_agentic_loop import goal_engine, AgenticToolbox, GoalStatus
from core.neo_self_tooling import synthesizer
from core.neo_visual_grounding import visual_grounding, UIElement
from core.neo_ambient_sensor import ambient_sensor, UserFocusState
from core.neo_precognition import precognitive_engine, ProactiveOpportunity
from core.neo_habit_learner import habit_learner
from core.neo_swarm_war_room import swarm_war_room
from core.neo_mobile_telepathy import mobile_telepathy
from core.neo_self_healing import self_healing_guardian
from core.neo_spatial_vision import spatial_vision

_BASE_DIR = Path(__file__).resolve().parent.parent


class NEOCentralCore(QObject):
    """
    Central Core Hub that coordinates and interconnects all of NEO's intelligence systems.
    """
    # Event Signals
    goal_event = pyqtSignal(str, str, str)            # goal_id, status, message
    memory_event = pyqtSignal(str, str, str)          # entity, relation, target
    gesture_event = pyqtSignal(str, float)            # gesture_name, timestamp
    tool_synthesized = pyqtSignal(str, str)           # tool_name, description
    visual_grounded = pyqtSignal(str, int, int)       # target_label, x, y
    system_telemetry = pyqtSignal(dict)               # snapshot dictionary
    proactive_opportunity_event = pyqtSignal(dict)    # ProactiveOpportunity dict
    proactive_toast_event = pyqtSignal(str, str, str, str)  # title, message, variant, payload
    proactive_voice_event = pyqtSignal(str)           # voice speech text
    habit_event = pyqtSignal(str, str)                # habit_name, description
    swarm_event = pyqtSignal(str, str, str)           # mission_id, role_or_status, message
    mobile_event = pyqtSignal(str, str)               # channel, message
    self_healing_event = pyqtSignal(str, str)         # event_type, details
    spatial_vision_event = pyqtSignal(str, str)       # event_type, details
    deep_reasoning_started = pyqtSignal(str)          # query
    deep_reasoning_completed = pyqtSignal(str, str, str)  # query, solution, summary

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._assistant_ref = None
        self._ui_ref = None
        self._wire_subsystem_signals()

    def set_references(self, assistant: Optional[Any] = None, ui: Optional[Any] = None) -> None:
        """Stores references to the main Live assistant and primary UI window."""
        with self._lock:
            if assistant:
                self._assistant_ref = assistant
            if ui:
                self._ui_ref = ui

    def _wire_subsystem_signals(self) -> None:
        """Wires reactive events across all intelligence engines."""
        # 1. Goal Engine -> Central Bus
        goal_engine.goal_started.connect(
            lambda gid, prompt: self.goal_event.emit(gid, "started", prompt)
        )
        goal_engine.step_completed.connect(
            lambda gid, sidx, out: self.goal_event.emit(gid, "step_completed", f"Step {sidx+1}: {out[:100]}")
        )
        goal_engine.goal_completed.connect(
            lambda gid, summary: self._on_goal_finished(gid, summary)
        )

        # 2. Dynamic Synthesizer -> Central Bus
        synthesizer.tool_synthesized.connect(
            lambda name, desc: self.tool_synthesized.emit(name, desc)
        )

        # 3. Visual Grounding -> Central Bus
        visual_grounding.target_grounded.connect(
            lambda label, x, y: self.visual_grounded.emit(label, x, y)
        )

        # 4. Proactive Intelligence -> Central Bus
        precognitive_engine.opportunity_detected.connect(
            lambda opp: self.proactive_opportunity_event.emit(opp.to_dict())
        )
        precognitive_engine.toast_requested.connect(
            lambda t, m, v, p: self.proactive_toast_event.emit(t, m, v, p)
        )
        precognitive_engine.voice_alert_requested.connect(
            lambda txt: self._on_proactive_voice(txt)
        )
        habit_learner.habit_discovered.connect(
            lambda h, desc: self.habit_event.emit(h, desc)
        )
        ambient_sensor.telemetry_updated.connect(
            lambda snap: self.system_telemetry.emit(snap)
        )

        # 5. Frontier 1: Swarm War Room
        swarm_war_room.agent_lane_updated.connect(
            lambda mid, role, st, snip: self.swarm_event.emit(mid, f"{role}:{st}", snip)
        )
        swarm_war_room.mission_completed.connect(
            lambda mid, summ, dels: self.swarm_event.emit(mid, "COMPLETED", summ[:100])
        )

        # 6. Frontier 2: Mobile Telepathy
        mobile_telepathy.mobile_alert_dispatched.connect(
            lambda ch, msg: self.mobile_event.emit(ch, msg)
        )

        # 7. Frontier 3: Self-Healing Guardian
        self_healing_guardian.audit_completed.connect(
            lambda res: self.self_healing_event.emit("AUDIT_COMPLETED", f"Found {res.get('errors_found', 0)} errors")
        )
        self_healing_guardian.commit_generated.connect(
            lambda br, msg: self.self_healing_event.emit("COMMIT_GENERATED", msg)
        )

        # 8. Frontier 4: Spatial Multimodal Vision
        spatial_vision.user_returned.connect(
            lambda grt: self.spatial_vision_event.emit("USER_RETURNED", grt)
        )
        spatial_vision.fatigue_alert.connect(
            lambda fmsg: self.spatial_vision_event.emit("FATIGUE_ALERT", fmsg)
        )

    def _on_proactive_voice(self, text: str) -> None:
        """Emits voice speech if assistant reference is available."""
        self.proactive_voice_event.emit(text)
        if self._assistant_ref and hasattr(self._assistant_ref, "speak_text"):
            try:
                self._assistant_ref.speak_text(text)
            except Exception:
                pass

    def _on_goal_finished(self, goal_id: str, summary: str) -> None:
        """Logs finished goals into Tri-Tier memory and informs UI."""
        brain.episodic.log_event("GOAL_COMPLETED", f"Goal {goal_id} completed: {summary}")
        brain.graph.upsert_entity(f"Goal_{goal_id[:8]}", "GOAL", attributes={"summary": summary})
        self.goal_event.emit(goal_id, "completed", summary)

        if self._ui_ref and hasattr(self._ui_ref, "write_log"):
            try:
                self._ui_ref.write_log(f"GOAL [{goal_id[:8]}]: {summary}")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # High-Level Assistant API
    # ─────────────────────────────────────────────────────────────────────────

    def execute_autonomous_goal(self, prompt: str) -> str:
        """Launches a multi-step agentic goal and updates working memory."""
        ambient_sensor.record_user_input()
        habit_learner.record_action("GOAL", prompt)
        brain.working.set_active_goal(prompt)
        gid = goal_engine.submit_goal(prompt)
        return gid

    def get_proactive_opportunities(self) -> List[Dict[str, Any]]:
        """Returns currently active proactive opportunities from the precognitive engine."""
        return precognitive_engine.get_active_opportunities()

    def dismiss_proactive_opportunity(self, opportunity_id: str) -> None:
        """Dismisses an active opportunity and applies cooldown."""
        precognitive_engine.dismiss_opportunity(opportunity_id)

    def execute_proactive_opportunity(self, opportunity_id: str) -> bool:
        """Executes the action associated with an opportunity."""
        ambient_sensor.record_user_input()
        opp = precognitive_engine._active_opportunities.get(opportunity_id)
        if not opp:
            return False

        payload = opp.action_payload
        precognitive_engine.dismiss_opportunity(opportunity_id)

        if opp.action_type in ("GOAL", "COMMAND"):
            self.execute_autonomous_goal(payload)
            return True
        elif opp.action_type == "TOOL":
            # Direct tool execution
            self.execute_autonomous_goal(payload)
            return True
        return False

    def start_proactive_subsystems(self) -> None:
        """Starts ambient sensory sampling and precognitive monitors."""
        ambient_sensor.start()

    def stop_proactive_subsystems(self) -> None:
        """Stops ambient sensory sampling."""
        ambient_sensor.stop()

    # ── Superhuman Frontiers API ─────────────────────────────────────────────

    def dispatch_swarm_mission(self, objective: str) -> str:
        """Dispatches a collaborative 4-agent swarm mission in the War Room."""
        habit_learner.record_action("SWARM_MISSION", objective)
        mid = swarm_war_room.submit_mission(objective)
        return mid

    def get_swarm_missions(self) -> List[Dict[str, Any]]:
        """Returns all War Room missions."""
        return swarm_war_room.list_missions()

    def send_mobile_push(self, title: str, message: str, urgency: float = 0.5, photo_path: Optional[str] = None) -> bool:
        """Dispatches an encrypted push alert to the paired mobile companion."""
        return mobile_telepathy.dispatch_mobile_push(title, message, urgency=urgency, photo_path=photo_path)

    def capture_and_send_mobile_screen(self, caption: str = "🖥️ Live Desktop Screen Snapshot") -> bool:
        """Captures active desktop and transmits image to phone."""
        return mobile_telepathy.capture_and_send_screen(caption)

    def run_workspace_self_healing(self) -> Dict[str, Any]:
        """Runs syntax audit and automated diagnosis across active workspace."""
        return self_healing_guardian.run_workspace_audit()

    def generate_git_commit(self) -> str:
        """Generates conventional git commit message from active diff."""
        return self_healing_guardian.generate_conventional_commit_message()

    def auto_commit_workspace(self, message: Optional[str] = None) -> Tuple[bool, str]:
        """Stages all changes and creates conventional commit."""
        return self_healing_guardian.auto_commit_workspace(message)

    def scan_physical_document(self) -> Tuple[bool, str, str]:
        """Captures physical document via webcam and converts to markdown notes."""
        return spatial_vision.scan_physical_document()

    def query_knowledge(self, query: str) -> Dict[str, Any]:
        """Queries working context, episodic memories, and knowledge graph."""
        graph_entities = brain.graph.search_entities(query, limit=5)
        relations = []
        for ent in graph_entities:
            rels = brain.graph.get_related_entities(ent["name"])
            relations.extend(rels)

        episodic = brain.episodic.query_events(query, limit=5)
        working = brain.working.get_summary()

        return {
            "query": query,
            "working_memory": working,
            "episodic_recalls": episodic,
            "knowledge_graph": relations,
        }

    def remember_fact(self, entity: str, relation: str, target: str, category: str = "FACT") -> bool:
        """Records a permanent fact into the semantic knowledge graph."""
        try:
            brain.graph.upsert_entity(entity, entity_type=category)
            brain.graph.upsert_entity(target, entity_type="ATTRIBUTE")
            brain.graph.add_relation(entity, target, relation.upper())
            brain.episodic.log_event("FACT_RECORDED", f"{entity} {relation} {target}")
            self.memory_event.emit(entity, relation, target)
            return True
        except Exception as e:
            print(f"[CentralCore] Error recording fact: {e}")
            return False

    def locate_and_click(self, query: str, double_click: bool = False, right_click: bool = False) -> bool:
        """Visually locates a target element on screen, highlights it, and clicks."""
        elem = visual_grounding.ground_target_on_screen(query, highlight=True)
        if not elem:
            return False
        return visual_grounding.click_element(elem, double_click=double_click, right_click=right_click)

    def synthesize_capability(self, name: str, description: str, python_code: str) -> Tuple[bool, str]:
        """Synthesizes, tests, and hot-registers a new runtime Python tool."""
        return synthesizer.synthesize_tool(name, description, python_code)

    def trigger_gesture(self, gesture_name: str) -> None:
        """Handles gesture telemetry and routes actions."""
        now = time.time()
        self.gesture_event.emit(gesture_name, now)
        brain.episodic.log_event("GESTURE_TRIGGERED", f"Detected gesture: {gesture_name}")

        if "palm" in gesture_name.lower():
            # Interrupt active speech or pause
            if self._assistant_ref and hasattr(self._assistant_ref, "interrupt"):
                try:
                    self._assistant_ref.interrupt()
                except Exception:
                    pass

    def dispatch_deep_reasoning(self, query: str, context: str = "") -> Dict[str, str]:
        """Dispatches complex cognitive problems to Cortex Beta deep thinking ladder."""
        from core import gemini
        from core import memory_optimizer

        self.deep_reasoning_started.emit(query)
        prompt = f"Problem / Architectural Challenge:\n{query}"
        if context:
            prompt += f"\n\nContext / Code / Telemetry:\n{context}"

        solution = gemini.deep_reason(prompt, thinking_budget=2048, timeout_ms=45000)
        if not solution:
            solution = "Cortex Beta was unable to formulate a solution within the allocated thinking budget."

        # Fast executive summary for Cortex Alpha voice reflex
        summ_prompt = (
            f"You are Cortex Alpha summarizing a deep reasoning result for the user in 1 or 2 crisp sentences.\n"
            f"Original query: {query}\n"
            f"Full Solution: {solution[:1200]}\n"
            f"Provide only the executive takeaway to speak to the user. No markdown, no filler."
        )
        summary = gemini.text(summ_prompt, tier=gemini.FAST, timeout_ms=10000)
        if not summary:
            summary = "I have reasoned through the problem and projected the step-by-step breakdown onto your display."

        self.deep_reasoning_completed.emit(query, solution, summary)

        # Free working set memory after heavy reasoning
        try:
            memory_optimizer.trim_memory()
        except Exception:
            pass

        return {"query": query, "solution": solution, "summary": summary}

    def get_full_telemetry_snapshot(self) -> Dict[str, Any]:
        """Returns unified telemetry across all 4 pillars and host system."""
        active_goals = [
            {"goal_id": g.goal_id, "status": g.status.value, "prompt": g.prompt}
            for g in goal_engine._goals.values()
            if g.status in (GoalStatus.PLANNING, GoalStatus.EXECUTING)
        ]

        synthesized = synthesizer.list_synthesized_tools()
        working = brain.working.get_summary()

        return {
            "timestamp": time.time(),
            "working_memory": working,
            "active_goals_count": len(active_goals),
            "active_goals": active_goals,
            "synthesized_tools_count": len(synthesized),
            "synthesized_tools": synthesized,
        }


# Global Singleton Coordinator
central_core = NEOCentralCore()
