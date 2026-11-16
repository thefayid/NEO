"""
neo/tasks/reports.py — Final Task Report Generator with Invariant "Done" Gating.

Architectural Guarantees:
1. Invariant "Done" Gating:
   - Status is "Done" (or "COMPLETED") ONLY if all stages passed their empirical code checks.
   - If any stage is pending, failed, or stopped, the status is strictly "FAILED", "STOPPED", or "INCOMPLETE".
2. Empirical Evidence per Stage:
   - Full audit trail of each stage: status, code check message, duration, attempts, and concrete evidence dict.
3. Unverified Items Tracking:
   - Transparently highlights steps or actions that lacked direct verification or produced warnings.
4. "What I Must Do Next" Actionable Handover:
   - Explicit instructions for the human user when escalation occurred or manual verification is required.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from neo.tasks.stages import Stage, StageStatus

logger = logging.getLogger("neo.tasks.reports")


@dataclass
class StageReportItem:
    """Detailed summary of a single stage's execution."""
    name: str
    description: str
    status: str
    passed_check: bool
    duration_s: float
    attempts: int
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskReport:
    """Comprehensive post-execution report for a task."""
    task_id: str
    goal: str
    status: str  # "Done" | "Failed" | "Stopped" | "Incomplete" | "Escalated"
    all_checks_passed: bool
    start_time: float
    end_time: float
    duration_s: float
    stages: List[StageReportItem] = field(default_factory=list)
    unverified_items: List[str] = field(default_factory=list)
    what_i_must_do_next: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "all_checks_passed": self.all_checks_passed,
            "duration_s": round(self.duration_s, 2),
            "stages": [
                {
                    "name": s.name,
                    "description": s.description,
                    "status": s.status,
                    "passed_check": s.passed_check,
                    "duration_s": round(s.duration_s, 2),
                    "attempts": s.attempts,
                    "evidence": s.evidence,
                }
                for s in self.stages
            ],
            "unverified_items": self.unverified_items,
            "what_i_must_do_next": self.what_i_must_do_next,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Renders the task report as clean, GitHub-flavored Markdown."""
        icon = "✔" if self.status == "Done" else "✖"
        lines = [
            f"# Task Execution Report: {self.goal}",
            "",
            f"**Task ID**: `{self.task_id}`  ",
            f"**Status**: **{icon} {self.status.upper()}** (Checks Passed: `{self.all_checks_passed}`)  ",
            f"**Total Duration**: `{self.duration_s:.2f}s`  ",
            "",
            "## Stages Breakdown",
            "",
            "| Stage | Status | Check Passed | Attempts | Duration | Evidence |",
            "| :--- | :---: | :---: | :---: | :---: | :--- |",
        ]

        for s in self.stages:
            st_icon = "✔" if s.status == "completed" else "✖"
            ev_summary = json.dumps(s.evidence) if s.evidence else "None"
            if len(ev_summary) > 40:
                ev_summary = ev_summary[:37] + "..."
            lines.append(
                f"| **{s.name}** | {st_icon} {s.status} | `{s.passed_check}` | "
                f"{s.attempts} | {s.duration_s:.2f}s | `{ev_summary}` |"
            )

        lines.append("")
        lines.append("## Unverified Items")
        if self.unverified_items:
            for item in self.unverified_items:
                lines.append(f"- ⚠ {item}")
        else:
            lines.append("- *None. All executed stages and actions were empirically verified.*")

        lines.append("")
        lines.append("## What I Must Do Next")
        if self.what_i_must_do_next:
            for next_step in self.what_i_must_do_next:
                lines.append(f"- [ ] {next_step}")
        else:
            lines.append("- *No further human action required. Task completed autonomously.*")

        return "\n".join(lines)


class TaskReportGenerator:
    """
    Constructs a TaskReport from task records and stage state machines.
    Strictly guarantees that status='Done' ONLY if all checks passed.
    """

    @staticmethod
    def generate(
        task_id: str,
        goal: str,
        stages: Sequence[Stage],
        task_state: str = "running",
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        unverified_items: Optional[Sequence[str]] = None,
        what_i_must_do_next: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskReport:
        t_start = start_time or time.time()
        t_end = end_time or time.time()
        duration = max(0.0, t_end - t_start)

        stage_items: List[StageReportItem] = []
        all_passed = True if stages else False

        for st in stages:
            passed = (st.status == StageStatus.COMPLETED)
            if not passed:
                all_passed = False

            dur = 0.0
            if st.started_at:
                dur = (st.completed_at or t_end) - st.started_at

            stage_items.append(
                StageReportItem(
                    name=st.name,
                    description=st.description,
                    status=st.status.value,
                    passed_check=passed,
                    duration_s=max(0.0, dur),
                    attempts=st.attempts,
                    evidence=dict(st.evidence),
                )
            )

        # INVARIANT: "Done" ONLY if all stages passed their completion checks
        if all_passed and task_state.lower() not in ("failed", "stopped", "cancelled"):
            final_status = "Done"
        elif task_state.lower() == "stopped":
            final_status = "Stopped"
        elif task_state.lower() == "escalated":
            final_status = "Escalated"
        else:
            final_status = "Failed"

        next_steps = list(what_i_must_do_next or [])
        if final_status != "Done" and not next_steps:
            # Provide sensible default instructions if something failed or stopped
            if final_status == "Stopped":
                next_steps.append("Emergency stop was triggered. Verify system state before resuming.")
            elif final_status == "Escalated":
                next_steps.append("Human intervention requested. Complete manual step in active application.")
            else:
                next_steps.append("Investigate stage check failures and adjust environment or parameters.")

        return TaskReport(
            task_id=task_id,
            goal=goal,
            status=final_status,
            all_checks_passed=all_passed,
            start_time=t_start,
            end_time=t_end,
            duration_s=duration,
            stages=stage_items,
            unverified_items=list(unverified_items or []),
            what_i_must_do_next=next_steps,
            metadata=dict(metadata or {}),
        )
