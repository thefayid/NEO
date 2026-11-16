"""
neo/brain/agent.py — Main Autonomous Perception-Action-Verification Agent Loop.

Architectural Guarantees:
1. Strict 5-tier preference hierarchy:
   Level 1: Direct APIs / Files / COM
   Level 2: Playwright Browser DOM
   Level 3: Windows UIA Snapshot
   Level 4: Native Keyboard / SendInput
   Level 5: Vision + Coordinates (last resort fallback)
2. Versioned System Prompt:
   - System prompt loaded from versioned text file with whitelist and schema appended.
3. Compact Context Construction:
   - Builds compact state representation; attaches screenshot ONLY when sparse or requested.
4. Strict Schema & Human Escalation:
   - Validates replies with LLMReply schema; retries up to 2 times on error, then escalates to user.
5. Dual-Verification Gate:
   - Completion requires BOTH deterministic code verification AND independent critic agreement.
6. EmergencyStop check before and during every action.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from neo.brain.context import BrainContext, build_step_context
from neo.brain.critic import GoalCritic, is_step_complete
from neo.brain.llm_client import BaseLLMClient, get_llm_client
from neo.brain.planner import ActionDispatcher, StepExecutionResult
from neo.brain.prompts import load_system_prompt
from neo.brain.schema import (
    EscalationRequiredError,
    LLMReply,
    query_with_retries,
)
from neo.brain.verifier import GoalVerifier, VerificationResult
from neo.brain.whitelist import AgentDecision
from neo.browser import PlaywrightBrowser
from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.safety.gates import ConfirmationDeniedError, HardStopRequiredError, get_confirmation_gate
from neo.tasks.task_manager import TaskManager, TaskRecord, TaskState
from neo.vision.capture import get_system_dpi_scale
from neo.windows.core import WindowInfo, foreground
from neo.windows.uia_snapshot import UIASnapshot, snapshot

logger = logging.getLogger("neo.brain.agent")


class NeoAgent:
    """
    High-level autonomous Windows assistant agent coordinating perception,
    context construction, LLM decisioning, deterministic execution, and dual verification.
    """

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        task_manager: Optional[TaskManager] = None,
        browser: Optional[PlaywrightBrowser] = None,
        critic: Optional[GoalCritic] = None,
        use_gui_confirmation: bool = False,
        prompt_version: str = "v1",
    ) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.dispatcher = ActionDispatcher(browser=browser)
        self.task_manager = task_manager or TaskManager(dispatcher=self.dispatcher)
        self.browser = browser
        self.critic = critic or GoalCritic(llm_client=self.llm_client)
        self.prompt_version = prompt_version

        if use_gui_confirmation:
            get_confirmation_gate().enable_gui(True)

    def run_task(
        self,
        goal: str,
        verifier: Optional[GoalVerifier] = None,
        max_steps: int = 25,
    ) -> TaskRecord:
        """
        Executes an end-to-end task loop until goal dual-verification or budget exhaustion.
        """
        emergency_stop.check_stop()

        system_prompt = load_system_prompt(version=self.prompt_version)
        task = self.task_manager.create_task(goal=goal, verifier=verifier, max_steps=max_steps)
        task_id = task.task_id

        logger.info("Starting NeoAgent task '%s': %s (Max steps: %d)", task_id, goal, max_steps)

        last_result: Optional[Dict[str, Any]] = None
        step_history: List[Dict[str, Any]] = []

        while task.state in (TaskState.PENDING, TaskState.RUNNING):
            emergency_stop.check_stop()
            step_num = task.current_step + 1

            # ── 1. Perception Phase ───────────────────────────────────────────
            fg_res = foreground()
            fg_win: Optional[WindowInfo] = fg_res.data if (fg_res.ok and fg_res.data) else None

            active_snapshot: Optional[UIASnapshot] = None
            registry = None

            # Check if active window is browser
            is_browser_fg = False
            if fg_win and fg_win.process_name:
                pname = fg_win.process_name.lower()
                is_browser_fg = "chrome" in pname or "msedge" in pname

            if not is_browser_fg and fg_win and fg_win.hwnd:
                try:
                    snap_res = snapshot(fg_win.hwnd, timeout_sec=2.5)
                    if snap_res.ok and snap_res.snapshot:
                        active_snapshot = snap_res.snapshot
                        registry = snap_res.registry
                except Exception as e:
                    logger.warning("UIA snapshot failed on hwnd %d: %s", fg_win.hwnd, e)

            # ── 2. Compact Context Construction ───────────────────────────────
            state_log = {
                "window_title": fg_win.title if fg_win else "None",
                "process_name": fg_win.process_name if fg_win else "None",
                "pid": fg_win.pid if fg_win else 0,
                "dpi_scale": get_system_dpi_scale(),
            }

            brain_context: BrainContext = build_step_context(
                goal=goal,
                step_index=step_num,
                max_steps=max_steps,
                last_result=last_result,
                current_snapshot=active_snapshot,
                step_history=step_history,
                state_log=state_log,
            )

            # ── 3. Decision Phase with Strict Schema & Retries ────────────────
            def query_fn(prompt_str: str) -> str:
                return self.llm_client.query(system_prompt, prompt_str)

            try:
                reply: LLMReply = query_with_retries(
                    query_fn=query_fn,
                    initial_user_prompt=brain_context.prompt_text,
                    current_snapshot=active_snapshot,
                    recent_actions=step_history,
                    max_retries=2,
                    min_confidence=0.6,
                )
                decision: AgentDecision = reply.to_agent_decision(
                    snapshot_id=active_snapshot.snapshot_id if active_snapshot else None
                )
                logger.info(
                    "Step %d Decision: %s -> %s (Target: %s, Confidence: %.2f)",
                    step_num,
                    reply.observation[:50],
                    decision.action,
                    reply.target_id,
                    reply.confidence,
                )
            except EscalationRequiredError as e:
                logger.critical("Escalation to human required at step %d: %s", step_num, e)
                task.state = TaskState.STOPPED
                task.final_rationale = str(e)
                break
            except Exception as e:
                logger.error("LLM Decision failed at step %d: %s", step_num, e)
                task.state = TaskState.FAILED
                task.final_rationale = f"LLM decision generation failed: {e}"
                break

            # ── 4. Execution & Dual-Verification Phase ────────────────────────
            try:
                task_rec, exec_res, code_verif_res = self.task_manager.execute_step(
                    task_id=task_id,
                    decision=decision,
                    registry=registry,
                )

                last_result = {
                    "action": decision.action,
                    "target_id": reply.target_id,
                    "ok": exec_res.ok,
                    "warning": exec_res.warning,
                    "evidence": exec_res.evidence,
                }
                step_history.append(last_result)

                # ── 5. Dual Verification Check ────────────────────────────────
                # If code verifier marks complete, independent critic must also verify
                if code_verif_res.completed:
                    critic_verdict = self.critic.evaluate(
                        goal=goal,
                        claimed_result=reply.observation,
                        step_evidence=exec_res.evidence,
                        last_action=decision.action,
                    )
                    is_complete, combined_rationale = is_step_complete(code_verif_res, critic_verdict)

                    if is_complete:
                        task_rec.state = TaskState.COMPLETED
                        task_rec.final_rationale = combined_rationale
                        logger.info("Task '%s' Dual-Verified COMPLETED: %s", task_id, combined_rationale)
                        return task_rec
                    else:
                        # Critic disagreed or unsure; task remains running
                        task_rec.state = TaskState.RUNNING
                        last_result["warning"] = f"Code verified but critic disagreed: {critic_verdict.explanation}"
                        logger.warning("Step %d: Dual verification failed. %s", step_num, combined_rationale)

                if task_rec.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.STOPPED):
                    logger.info("Task '%s' reached terminal state '%s'", task_id, task_rec.state.value)
                    return task_rec

            except EmergencyStopTriggeredError as e:
                logger.critical("Emergency stop halted task '%s': %s", task_id, e)
                task.state = TaskState.STOPPED
                task.final_rationale = f"Emergency stop: {e}"
                return task

            except (HardStopRequiredError, ConfirmationDeniedError) as e:
                logger.warning("Safety gate stopped execution: %s", e)
                last_result = {
                    "action": decision.action,
                    "target_id": reply.target_id,
                    "ok": False,
                    "warning": f"Action blocked by safety policy: {e}",
                    "evidence": {"safety_violation": str(e)},
                }
                step_history.append(last_result)

        return task
