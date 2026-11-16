"""
neo/tasks/stages.py — Code-Gated Stage-Based State Machine.

Architectural Guarantees:
1. Strict Code-Gated Stage Transitions:
   - The plan consists of explicit stages with deterministic completion checks
     written in code (URL contains, element exists, file exists, value equals).
   - The LLM CANNOT advance a stage directly; transitions occur exclusively when
     the stage's completion check passes empirically.
2. Structured Evidence Collection:
   - Each stage retains its own empirical evidence (file hashes, readbacks, URLs).
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from neo.files_office.files import safe_read_file
from neo.windows.uia_snapshot import UIASnapshot

logger = logging.getLogger("neo.tasks.stages")


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageCheckResult:
    """Result of an objective code verification check for a stage."""
    passed: bool
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)


class StageCheck(ABC):
    """Abstract base class for deterministic stage completion criteria."""

    @abstractmethod
    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        """Evaluates whether the stage criteria have been objectively met."""
        pass


class FileExistsCheck(StageCheck):
    """Verifies that a file exists, has a minimum size, and optionally contains required content."""

    def __init__(
        self,
        path: Union[str, Path],
        min_size_bytes: int = 0,
        contains_text: Optional[str] = None,
    ) -> None:
        self.path = str(path)
        self.min_size_bytes = min_size_bytes
        self.contains_text = contains_text

    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        res = safe_read_file(self.path)
        if not res.ok:
            return StageCheckResult(
                passed=False,
                message=f"File '{self.path}' does not exist or cannot be accessed: {res.error}",
                evidence={"file_result": res.to_dict()},
            )

        ev = res.evidence or {}
        size = ev.get("size_bytes", 0)
        if size < self.min_size_bytes:
            return StageCheckResult(
                passed=False,
                message=f"File '{self.path}' size ({size} bytes) is less than required minimum ({self.min_size_bytes} bytes).",
                evidence=ev,
            )

        if self.contains_text is not None:
            content = str(res.data or "")
            if self.contains_text not in content:
                return StageCheckResult(
                    passed=False,
                    message=f"File '{self.path}' does not contain expected substring: '{self.contains_text}'.",
                    evidence=ev,
                )

        return StageCheckResult(
            passed=True,
            message=f"Verified file '{self.path}' exists (size: {size} bytes) and matches content criteria.",
            evidence=ev,
        )


class ValueEqualsCheck(StageCheck):
    """Verifies that an empirical value matches an expected value."""

    def __init__(
        self,
        expected_value: Any,
        evidence_key: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> None:
        self.expected_value = expected_value
        self.evidence_key = evidence_key
        self.file_path = file_path

    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        # Check from file if specified
        if self.file_path:
            res = safe_read_file(self.file_path)
            if not res.ok:
                return StageCheckResult(passed=False, message=f"Cannot read file '{self.file_path}': {res.error}")
            actual_val = str(res.data or "").strip()
            if actual_val == str(self.expected_value).strip():
                return StageCheckResult(
                    passed=True,
                    message=f"File content in '{self.file_path}' equals expected value.",
                    evidence={"actual": actual_val, "expected": self.expected_value},
                )
            return StageCheckResult(
                passed=False,
                message=f"File content '{actual_val[:40]}' does not equal expected '{self.expected_value}'.",
                evidence={"actual": actual_val, "expected": self.expected_value},
            )

        # Check from evidence dictionary
        if self.evidence_key:
            actual = step_evidence.get(self.evidence_key)
            if actual == self.expected_value:
                return StageCheckResult(
                    passed=True,
                    message=f"Evidence key '{self.evidence_key}' equals expected value '{self.expected_value}'.",
                    evidence={"actual": actual, "expected": self.expected_value},
                )
            return StageCheckResult(
                passed=False,
                message=f"Evidence key '{self.evidence_key}' has value '{actual}', expected '{self.expected_value}'.",
                evidence={"actual": actual, "expected": self.expected_value},
            )

        return StageCheckResult(passed=False, message="ValueEqualsCheck configured without key or file.")


class ElementExistsCheck(StageCheck):
    """Verifies that a named or typed element exists in the active UI snapshot."""

    def __init__(
        self,
        name_regex: Optional[str] = None,
        control_type: Optional[str] = None,
        automation_id: Optional[str] = None,
    ) -> None:
        self.name_regex = re.compile(name_regex, re.IGNORECASE) if name_regex else None
        self.control_type = control_type.lower() if control_type else None
        self.automation_id = automation_id

    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        snapshot: Optional[UIASnapshot] = system_state.get("snapshot")
        if not snapshot or not snapshot.elements:
            return StageCheckResult(
                passed=False,
                message="No active UI snapshot or no elements visible to evaluate element existence.",
            )

        for el in snapshot.elements:
            if self.control_type and el.control_type.lower() != self.control_type:
                continue
            if self.automation_id and el.automation_id != self.automation_id:
                continue
            if self.name_regex and not self.name_regex.search(el.name or ""):
                continue

            return StageCheckResult(
                passed=True,
                message=f"Element matched: [{el.id}] <{el.control_type}> '{el.name}'.",
                evidence={"element_id": el.id, "name": el.name, "type": el.control_type},
            )

        return StageCheckResult(
            passed=False,
            message="No matching UI element found in the active snapshot.",
            evidence={"elements_scanned": len(snapshot.elements)},
        )


class URLContainsCheck(StageCheck):
    """Verifies that the active browser URL contains a specific substring."""

    def __init__(self, substring: str) -> None:
        self.substring = substring.lower()

    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        current_url = str(system_state.get("browser_url") or step_evidence.get("url") or "").lower()
        if not current_url:
            return StageCheckResult(passed=False, message="No active browser URL detected.")

        if self.substring in current_url:
            return StageCheckResult(
                passed=True,
                message=f"Browser URL '{current_url}' contains required substring '{self.substring}'.",
                evidence={"url": current_url, "substring": self.substring},
            )

        return StageCheckResult(
            passed=False,
            message=f"Browser URL '{current_url}' does not contain '{self.substring}'.",
            evidence={"url": current_url, "substring": self.substring},
        )


class CustomCheck(StageCheck):
    """Wraps an arbitrary deterministic predicate function."""

    def __init__(self, predicate: Callable[[Dict[str, Any], Dict[str, Any]], bool], description: str) -> None:
        self.predicate = predicate
        self.description = description

    def evaluate(self, system_state: Dict[str, Any], step_evidence: Dict[str, Any]) -> StageCheckResult:
        try:
            ok = bool(self.predicate(system_state, step_evidence))
            return StageCheckResult(
                passed=ok,
                message=f"Custom check '{self.description}': {'PASSED' if ok else 'FAILED'}",
                evidence={"custom_predicate": ok},
            )
        except Exception as e:
            return StageCheckResult(
                passed=False,
                message=f"Custom check '{self.description}' raised exception: {e}",
                evidence={"exception": str(e)},
            )


@dataclass
class Stage:
    """A distinct milestone in a multi-stage plan with code-verified completion criteria."""
    name: str
    description: str
    completion_check: StageCheck
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "evidence": self.evidence,
            "attempts": self.attempts,
        }


class StageStateMachine:
    """
    Manages the deterministic progression through planned stages.
    Enforces that only code checks can advance stages.
    """

    def __init__(self, stages: Optional[List[Stage]] = None) -> None:
        self.stages: List[Stage] = list(stages or [])
        self.current_stage_index: int = 0
        if self.stages:
            self.stages[0].status = StageStatus.RUNNING
            self.stages[0].started_at = time.time()

    @property
    def current_stage(self) -> Optional[Stage]:
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def is_all_completed(self) -> bool:
        if not self.stages:
            return True
        return all(st.status == StageStatus.COMPLETED for st in self.stages)

    def evaluate_step(
        self,
        system_state: Dict[str, Any],
        step_evidence: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Evaluates the current stage's completion check.
        Advances the stage ONLY if the code check evaluates to passed=True.
        Returns:
            (stage_advanced: bool, summary_message: str)
        """
        curr = self.current_stage
        if not curr:
            return False, "All stages have already completed."

        curr.attempts += 1
        check_res = curr.completion_check.evaluate(system_state, step_evidence)

        if check_res.passed:
            curr.status = StageStatus.COMPLETED
            curr.completed_at = time.time()
            curr.evidence.update(check_res.evidence)
            prev_name = curr.name

            # Advance pointer
            self.current_stage_index += 1
            next_stage = self.current_stage
            if next_stage:
                next_stage.status = StageStatus.RUNNING
                next_stage.started_at = time.time()
                adv_msg = f"Stage '{prev_name}' COMPLETED. Advanced to Stage {self.current_stage_index + 1}: '{next_stage.name}'."
            else:
                adv_msg = f"Final Stage '{prev_name}' COMPLETED. All stages verified complete."

            logger.info("✔ %s (%s)", adv_msg, check_res.message)
            return True, adv_msg

        return False, f"Stage '{curr.name}' check NOT satisfied: {check_res.message}"
