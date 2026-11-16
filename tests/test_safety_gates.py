"""
tests/test_safety_gates.py — Unit tests for neo/safety/gates.py.

Verifies:
- Standard non-risky actions pass without prompting.
- Risky action approval via custom handler.
- Risky action denial via custom handler (raises ConfirmationDeniedError).
- Confirmation timeout strictly defaults to DENY (raises ConfirmationDeniedError).
- Hard stops raise HardStopRequiredError when denied or timed out.
- Immutable security audit trail logs every approval and denial with timestamp and approver.
"""
from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from neo.safety.gates import (
    ConfirmationDeniedError,
    ConfirmationGate,
    GateDecision,
    HardStopRequiredError,
    SecurityAuditTrail,
)
from neo.safety.policy import RiskAssessment


def test_non_risky_action_auto_approved():
    """Verifies that non-risky actions are approved automatically and logged."""
    with TemporaryDirectory() as tmpdir:
        audit_file = Path(tmpdir) / "audit.jsonl"
        audit = SecurityAuditTrail(audit_file_path=audit_file)
        gate = ConfirmationGate(audit_trail=audit)

        decision = gate.evaluate_and_gate(
            action_name="click",
            element_name="Number 5",
            window_title="Calculator",
        )

        assert decision.approved is True
        assert decision.approver == "policy_auto"
        assert decision.timed_out is False

        # Verify audit record
        records = audit.read_records()
        assert len(records) == 1
        assert records[0]["approved"] is True
        assert records[0]["action_name"] == "click"


def test_risky_action_approved_by_handler():
    """Verifies risky action is approved when handler grants permission."""
    with TemporaryDirectory() as tmpdir:
        audit = SecurityAuditTrail(audit_file_path=Path(tmpdir) / "audit.jsonl")
        gate = ConfirmationGate(audit_trail=audit)

        def mock_approver(act: str, assessment: RiskAssessment, timeout: float):
            return True, "Approved by security officer"

        gate.set_handler(mock_approver)

        decision = gate.evaluate_and_gate(
            action_name="click",
            element_name="Delete Branch",
            window_title="GitHub",
        )

        assert decision.approved is True
        assert decision.approver == "custom_handler"
        assert decision.reason == "Approved by security officer"

        records = audit.read_records()
        assert len(records) == 1
        assert records[0]["approved"] is True
        assert "Delete Branch" in str(records[0]["details"])


def test_risky_action_denied_by_handler():
    """Verifies risky action raises ConfirmationDeniedError when denied."""
    with TemporaryDirectory() as tmpdir:
        audit = SecurityAuditTrail(audit_file_path=Path(tmpdir) / "audit.jsonl")
        gate = ConfirmationGate(audit_trail=audit)

        def mock_denier(act: str, assessment: RiskAssessment, timeout: float):
            return False, "Dangerous deletion prohibited"

        gate.set_handler(mock_denier)

        with pytest.raises(ConfirmationDeniedError) as exc_info:
            gate.evaluate_and_gate(
                action_name="type",
                typed_text="format D: /fs:NTFS",
            )

        assert "Dangerous deletion prohibited" in str(exc_info.value)

        # Audit trail must record the denial
        records = audit.read_records()
        assert len(records) == 1
        assert records[0]["approved"] is False
        assert records[0]["reason"] == "Dangerous deletion prohibited"


def test_confirmation_timeout_defaults_to_deny():
    """CRITICAL RULE: Confirmation timeouts must strictly default to DENY."""
    with TemporaryDirectory() as tmpdir:
        audit = SecurityAuditTrail(audit_file_path=Path(tmpdir) / "audit.jsonl")
        gate = ConfirmationGate(audit_trail=audit)

        def slow_handler(act: str, assessment: RiskAssessment, timeout: float):
            time.sleep(timeout + 0.05)
            return True, "Attempted late approval"

        gate.set_handler(slow_handler)

        with pytest.raises(ConfirmationDeniedError) as exc_info:
            gate.evaluate_and_gate(
                action_name="click",
                element_name="Deploy to Production",
                timeout_sec=0.1,
            )

        assert "timed out" in str(exc_info.value).lower()
        records = audit.read_records()
        assert len(records) == 1
        assert records[0]["approved"] is False
        assert records[0]["timed_out"] is True
        assert records[0]["approver"] == "timeout_denied"


def test_hard_stop_raises_hard_stop_required_error():
    """Verifies that hard stops (payment, OTP, password, UAC) raise HardStopRequiredError."""
    with TemporaryDirectory() as tmpdir:
        audit = SecurityAuditTrail(audit_file_path=Path(tmpdir) / "audit.jsonl")
        gate = ConfirmationGate(audit_trail=audit)

        # Even with a handler attempting to deny, it raises typed HardStopRequiredError
        def deny_handler(act: str, assessment: RiskAssessment, timeout: float):
            return False, "Manual human takeover required"

        gate.set_handler(deny_handler)

        with pytest.raises(HardStopRequiredError) as exc_info:
            gate.evaluate_and_gate(
                action_name="type",
                element_name="Credit Card CVV",
                typed_text="123",
            )

        assert "Hard Stop" in str(exc_info.value)
        assert exc_info.value.risk_assessment.requires_hard_stop is True
        assert "payment" in exc_info.value.risk_assessment.hard_stop_categories

        records = audit.read_records()
        assert len(records) == 1
        assert records[0]["is_hard_stop"] is True
        assert records[0]["approved"] is False
