"""
neo/brain/verifier.py — Deterministic Goal Verifier.

Architectural Guarantees:
1. The LLM NEVER marks anything 'done' itself.
2. An objective, deterministic verifier inspects real empirical evidence
   (file hashes, readbacks, DOM attributes, window titles) to prove completion.
3. If criteria are not verified with tangible evidence, the task continues
   until budget exhaustion or until the goal is proven.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from neo.files_office.files import safe_read_file
from neo.windows.core import list_windows

logger = logging.getLogger("neo.brain.verifier")


@dataclass
class VerificationResult:
    """Objective result of goal completion evaluation."""
    completed: bool
    rationale: str
    evidence: Dict[str, Any] = field(default_factory=dict)


class GoalVerifier:
    """
    Deterministic validator that checks whether a user's objective has been completed.
    """

    def __init__(
        self,
        goal_description: str,
        expected_file: Optional[str] = None,
        expected_file_contains: Optional[str] = None,
        expected_window_title: Optional[str] = None,
        expected_element_value: Optional[str] = None,
        custom_predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> None:
        self.goal_description = goal_description
        self.expected_file = expected_file
        self.expected_file_contains = expected_file_contains
        self.expected_window_title = expected_window_title
        self.expected_element_value = expected_element_value
        self.custom_predicate = custom_predicate

    def evaluate(self, step_evidence: Dict[str, Any]) -> VerificationResult:
        """
        Examines real system state and step evidence against goal completion criteria.
        """
        # 1. Custom predicate evaluation
        if self.custom_predicate is not None:
            try:
                passed = self.custom_predicate(step_evidence)
                if passed:
                    return VerificationResult(
                        completed=True,
                        rationale="Custom verification predicate satisfied by step evidence.",
                        evidence={"custom_predicate": True, **step_evidence},
                    )
            except Exception as e:
                logger.warning("Custom verification predicate raised exception: %s", e)

        # 2. File verification
        if self.expected_file is not None:
            fres = safe_read_file(self.expected_file)
            if not fres.ok:
                return VerificationResult(
                    completed=False,
                    rationale=f"Expected file '{self.expected_file}' does not exist or cannot be read: {fres.error}",
                    evidence={"file_result": fres.to_dict()},
                )

            if self.expected_file_contains is not None:
                content = str(fres.data or "")
                if self.expected_file_contains not in content:
                    return VerificationResult(
                        completed=False,
                        rationale=f"File '{self.expected_file}' exists but does not contain expected string '{self.expected_file_contains}'.",
                        evidence={"file_size": fres.evidence.get("size_bytes"), "sha256": fres.evidence.get("sha256")},
                    )

            # If no other criteria or all file checks passed
            if not self.expected_window_title and not self.expected_element_value:
                return VerificationResult(
                    completed=True,
                    rationale=f"Verified file '{self.expected_file}' created and matches required content.",
                    evidence={"file": fres.evidence},
                )

        # 3. Window title verification
        if self.expected_window_title is not None:
            wins = list_windows(only_visible=True)
            matched = False
            pattern = re.compile(self.expected_window_title, re.IGNORECASE)
            for w in (wins.data or []):
                if pattern.search(w.title):
                    matched = True
                    break

            if not matched:
                return VerificationResult(
                    completed=False,
                    rationale=f"Expected window matching regex '{self.expected_window_title}' is not visible.",
                    evidence={"visible_windows_count": len(wins.data or [])},
                )

            if not self.expected_element_value:
                return VerificationResult(
                    completed=True,
                    rationale=f"Verified active window matching '{self.expected_window_title}' is present.",
                    evidence={"matched_window_title": self.expected_window_title},
                )

        # 4. Element readback verification
        if self.expected_element_value is not None:
            readback = str(step_evidence.get("readback") or "")
            if self.expected_element_value in readback:
                return VerificationResult(
                    completed=True,
                    rationale=f"Verified element readback matches expected value '{self.expected_element_value}'.",
                    evidence={"readback": readback},
                )
            return VerificationResult(
                completed=False,
                rationale=f"Element readback '{readback}' does not contain expected '{self.expected_element_value}'.",
                evidence={"step_evidence": step_evidence},
            )

        # Default: if no criteria specified, check if step explicitly confirmed high-level verified outcome
        if step_evidence.get("verified") is True:
            return VerificationResult(
                completed=True,
                rationale="Action verified with direct evidence.",
                evidence=step_evidence,
            )

        return VerificationResult(
            completed=False,
            rationale="Goal completion criteria not yet satisfied.",
            evidence=step_evidence,
        )
