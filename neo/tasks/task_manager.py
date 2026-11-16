"""
neo/tasks/task_manager.py — Task Lifecycle State Machine, Stage Engine, and Resilience Coordinator.

Architectural Guarantees:
1. Code-Gated Stage Transitions:
   - Evaluates code-based completion checks at every step; the LLM cannot advance a stage directly.
2. Loop Detection & Step/Task Budget Enforcement:
   - LoopDetector checks for identical action repetitions, cyclic behaviors, and frozen states.
   - Enforces max task steps (default 25) and max stage steps.
3. Automated Pre-Action Checkpoints & Rollback:
   - Automatically snapshots affected targets before risky actions (file modifications, clipboard).
   - Provides deterministic rollback on failure or safety trigger.
4. Tiered Retry Policy:
   - 3 attempts per method tier (Primary -> Alternative -> Vision -> User escalation).
5. Comprehensive Final Reporting:
   - Produces structured reports; invariant: status='Done' ONLY if all checks passed.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:
    from neo.brain.planner import ActionDispatcher, StepExecutionResult
    from neo.brain.verifier import GoalVerifier, VerificationResult
    from neo.brain.whitelist import AgentDecision

from neo.brain.schema import ActionLoopDetectedError, EscalationRequiredError
from neo.logging_setup import StepLogger
from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.tasks.checkpoints import CheckpointManager, CheckpointRecord, RollbackResult
from neo.tasks.reports import TaskReport, TaskReportGenerator
from neo.tasks.retry_policy import (
    BudgetStatus,
    LoopDetectionResult,
    LoopDetector,
    MethodTier,
    RetryDecision,
    RetryPolicy,
    TaskBudgetLimits,
)
from neo.tasks.skills import Routine, SkillLibrary
from neo.tasks.stages import Stage, StageCheckResult, StageStateMachine, StageStatus

logger = logging.getLogger("neo.tasks.manager")


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


@dataclass
class StepRecord:
    """Historical record of an executed step."""
    step_index: int
    timestamp: float
    decision: Dict[str, Any]
    result: Dict[str, Any]
    verification: Dict[str, Any]
    duration_ms: float
    stage_name: Optional[str] = None
    checkpoint_id: Optional[str] = None


@dataclass
class TaskRecord:
    """Persistent state of a high-level task."""
    task_id: str
    goal: str
    state: TaskState
    current_step: int
    max_steps: int
    created_at: float
    completed_at: Optional[float] = None
    steps: List[StepRecord] = field(default_factory=list)
    final_rationale: Optional[str] = None
    stage_machine: Optional[StageStateMachine] = None
    loop_detector: Optional[LoopDetector] = None
    retry_policy: Optional[RetryPolicy] = None
    checkpoints: Optional[CheckpointManager] = None
    final_report: Optional[TaskReport] = None


class TaskManager:
    """
    Coordinates task execution, stages, checkpoints, loop detection,
    retry policies, and report generation.
    """

    def __init__(
        self,
        dispatcher: Optional[ActionDispatcher] = None,
        step_logger: Optional[StepLogger] = None,
        skill_library: Optional[SkillLibrary] = None,
    ) -> None:
        if dispatcher is None:
            from neo.brain.planner import ActionDispatcher
            self.dispatcher = ActionDispatcher()
        else:
            self.dispatcher = dispatcher

        self.step_logger = step_logger or StepLogger()
        self.skill_library = skill_library or SkillLibrary()
        self._tasks: Dict[str, TaskRecord] = {}
        self._verifiers: Dict[str, GoalVerifier] = {}

    def create_task(
        self,
        goal: str,
        verifier: Optional[GoalVerifier] = None,
        stages: Optional[Sequence[Stage]] = None,
        max_steps: int = 25,
        max_stage_steps: int = 8,
        enable_loop_detection: bool = True,
        enable_checkpoints: bool = True,
        enable_retry_policy: bool = True,
    ) -> TaskRecord:
        """Initializes a new task state machine with optional stages, loop detection, and checkpoints."""
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        stage_sm = StageStateMachine(list(stages)) if stages else None
        loop_det = LoopDetector() if enable_loop_detection else None
        retry_pol = RetryPolicy() if enable_retry_policy else None
        chk_mgr = CheckpointManager() if enable_checkpoints else None

        rec = TaskRecord(
            task_id=task_id,
            goal=goal,
            state=TaskState.PENDING,
            current_step=0,
            max_steps=max_steps,
            created_at=time.time(),
            stage_machine=stage_sm,
            loop_detector=loop_det,
            retry_policy=retry_pol,
            checkpoints=chk_mgr,
        )
        self._tasks[task_id] = rec

        if stage_sm is None:
            if verifier is None:
                from neo.brain.verifier import GoalVerifier
                self._verifiers[task_id] = GoalVerifier(goal_description=goal)
            else:
                self._verifiers[task_id] = verifier

        logger.info(
            "Initialized Task '%s': %s (Stages: %d, Budget: %d steps)",
            task_id, goal, len(stages) if stages else 0, max_steps
        )
        return rec

    def create_stage_task(
        self,
        goal: str,
        stages: Sequence[Stage],
        max_steps: int = 25,
        max_stage_steps: int = 8,
    ) -> TaskRecord:
        """Convenience method for creating a multi-stage task."""
        return self.create_task(
            goal=goal,
            stages=stages,
            max_steps=max_steps,
            max_stage_steps=max_stage_steps,
        )

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def execute_step(
        self,
        task_id: str,
        decision: AgentDecision,
        registry: Optional[Any] = None,
        system_state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[TaskRecord, StepExecutionResult, VerificationResult]:
        """
        Executes a single step for the specified task:
        1. Checks emergency stop and budget limits.
        2. Checks for action loops.
        3. Takes pre-action checkpoint if the action is risky.
        4. Dispatches action.
        5. Evaluates loop detector on state and action outcome.
        6. Deterministically verifies stage or goal completion.
        7. Logs structured record to JSON-lines audit trail.
        """
        # 1. Emergency stop check
        try:
            emergency_stop.check_stop()
        except EmergencyStopTriggeredError as e:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.state = TaskState.STOPPED
                task.final_rationale = f"Emergency stop triggered: {e}"
                self._finalize_report(task)
            raise

        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.STOPPED, TaskState.CANCELLED):
            raise RuntimeError(f"Cannot execute step on task '{task_id}' in terminal state '{task.state.value}'.")

        task.state = TaskState.RUNNING
        task.current_step += 1
        step_idx = task.current_step
        start_time = time.perf_counter()

        current_stage_name = task.stage_machine.current_stage.name if task.stage_machine and task.stage_machine.current_stage else "default"

        # 2. Check for action loops before dispatching
        if task.loop_detector:
            upcoming_loop = task.loop_detector.check_upcoming_action(
                action=decision.action,
                parameters=decision.parameters,
            )
            if upcoming_loop.is_loop:
                task.state = TaskState.FAILED
                task.final_rationale = f"Action loop detected: {upcoming_loop.message}"
                self._finalize_report(task)
                raise ActionLoopDetectedError(upcoming_loop.message)

        # 3. Create pre-action checkpoint if risky
        checkpoint_id: Optional[str] = None
        if task.checkpoints:
            chk_rec = task.checkpoints.auto_checkpoint(decision.action, decision.parameters)
            if chk_rec:
                checkpoint_id = chk_rec.checkpoint_id

        # 4. Dispatch action
        exec_res: StepExecutionResult
        with self.step_logger.step_context(
            task_id=task_id,
            stage=current_stage_name,
            action=decision.action,
            parameters=decision.parameters,
            llm_decision=decision.model_dump(),
        ) as ctx:
            exec_res = self.dispatcher.dispatch(decision, registry=registry)
            ctx.result = "ok" if exec_res.ok else "error"
            ctx.evidence = exec_res.evidence

        # Record action outcome in loop detector (single authoritative entry per step)
        if task.loop_detector:
            task.loop_detector.record_action(
                action=decision.action,
                parameters=decision.parameters,
                ok=exec_res.ok,
            )

        # 5. Handle Retry Policy on action failure
        if not exec_res.ok and task.retry_policy:
            retry_dec = task.retry_policy.record_attempt(
                stage_name=current_stage_name,
                action=decision.action,
                ok=False,
                error=exec_res.error,
            )
            if retry_dec.escalate_to_user:
                task.state = TaskState.ESCALATED
                task.final_rationale = f"Retry policy exhausted all method tiers: {retry_dec.message}"
                self._finalize_report(task)
                raise EscalationRequiredError(retry_dec.message)

        # 6. Stage State Machine or GoalVerifier Verification
        from neo.brain.verifier import VerificationResult
        combined_state = dict(system_state or {})
        if registry and hasattr(registry, "snapshot"):
            combined_state["snapshot"] = getattr(registry, "snapshot")

        verif_completed = False
        verif_rationale = ""
        verif_evidence: Dict[str, Any] = {}

        if task.stage_machine:
            # Stage-based evaluation: LLM CANNOT advance stage, code check does!
            advanced, msg = task.stage_machine.evaluate_step(
                system_state=combined_state,
                step_evidence=exec_res.evidence or {},
            )
            verif_completed = task.stage_machine.is_all_completed()
            verif_rationale = msg
            verif_evidence = {"stage_advanced": advanced, "all_stages_completed": verif_completed}
        else:
            # Single-goal verifier evaluation
            verifier = self._verifiers.get(task_id)
            if verifier is None:
                from neo.brain.verifier import GoalVerifier
                verifier = GoalVerifier(goal_description=task.goal)
                self._verifiers[task_id] = verifier
            verif_res = verifier.evaluate(exec_res.evidence)
            verif_completed = verif_res.completed
            verif_rationale = verif_res.rationale
            verif_evidence = verif_res.evidence

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Record step
        step_rec = StepRecord(
            step_index=step_idx,
            timestamp=time.time(),
            decision=decision.model_dump(),
            result={
                "ok": exec_res.ok,
                "action": exec_res.action,
                "warning": exec_res.warning,
                "error": exec_res.error,
                "evidence": exec_res.evidence,
            },
            verification={
                "completed": verif_completed,
                "rationale": verif_rationale,
                "evidence": verif_evidence,
            },
            duration_ms=duration_ms,
            stage_name=current_stage_name,
            checkpoint_id=checkpoint_id,
        )
        task.steps.append(step_rec)

        # Construct VerificationResult object to return
        returned_verif = VerificationResult(
            completed=verif_completed,
            rationale=verif_rationale,
            evidence=verif_evidence,
        )

        # 7. State transition & Budget check
        if verif_completed:
            task.state = TaskState.COMPLETED
            task.completed_at = time.time()
            task.final_rationale = verif_rationale
            self._finalize_report(task)
            logger.info("Task '%s' COMPLETED at step %d: %s", task_id, step_idx, verif_rationale)
        elif step_idx >= task.max_steps:
            task.state = TaskState.FAILED
            task.completed_at = time.time()
            task.final_rationale = (
                f"Exceeded maximum step budget of {task.max_steps} steps without verified goal completion."
            )
            self._finalize_report(task)
            logger.warning("Task '%s' FAILED: step budget exhausted.", task_id)

        return task, exec_res, returned_verif

    def rollback_task(self, task_id: str, checkpoint_id: Optional[str] = None) -> RollbackResult:
        """Rolls back the system to the specified or latest checkpoint for this task."""
        task = self._tasks.get(task_id)
        if not task or not task.checkpoints:
            return RollbackResult(
                ok=False,
                checkpoint_id=checkpoint_id or "none",
                errors=[f"Task '{task_id}' has no active checkpoint manager."],
                message="Rollback failed.",
            )
        return task.checkpoints.rollback(checkpoint_id)

    def _finalize_report(self, task: TaskRecord) -> TaskReport:
        """Generates and binds the final task report."""
        stages = task.stage_machine.stages if task.stage_machine else []
        unverified: List[str] = []
        for step in task.steps:
            res = step.result
            if res.get("warning"):
                unverified.append(f"Step {step.step_index} ({res.get('action')}): {res.get('warning')}")
            if not res.get("ok"):
                unverified.append(f"Step {step.step_index} ({res.get('action')}) failed: {res.get('error')}")

        report = TaskReportGenerator.generate(
            task_id=task.task_id,
            goal=task.goal,
            stages=stages,
            task_state=task.state.value,
            start_time=task.created_at,
            end_time=task.completed_at or time.time(),
            unverified_items=unverified,
        )
        task.final_report = report
        return report

    def save_task_as_skill(
        self,
        task_id: str,
        skill_name: str,
        description: str = "",
        parameter_substitutions: Optional[Dict[str, str]] = None,
        parameters_schema: Optional[Dict[str, str]] = None,
    ) -> Routine:
        """Saves a verified completed task as a reusable parameterized routine in the skill library."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")
        if task.state != TaskState.COMPLETED:
            raise RuntimeError(f"Cannot save skill from task '{task_id}' in non-completed state '{task.state.value}'.")

        return self.skill_library.create_routine_from_task(
            name=skill_name,
            task_record=task,
            description=description,
            parameter_substitutions=parameter_substitutions,
            parameters_schema=parameters_schema,
        )
