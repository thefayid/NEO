"""
neo/safety/gates.py — Confirmation Gates, Hard Stops, and Security Audit Trail.

Enforces:
1. Hard stops: Non-bypassable control gates for sensitive categories
   (payments, OTP, passwords, CAPTCHA, UAC, final submit/confirm buttons).
2. Confirmation gates: Interactive approval prompt (console or GUI callback).
   - Strict rule: TIMEOUTS ALWAYS DEFAULT TO DENY.
3. Audit trail: Every single approval or denial is recorded in a thread-safe
   JSON-lines security audit ledger.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from neo.config import get_settings
from neo.safety.emergency_stop import emergency_stop
from neo.safety.policy import RiskAssessment, detect_risks

logger = logging.getLogger("neo.safety.gates")


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class HardStopRequiredError(PermissionError):
    """Raised when an operation requires an unconditional hard stop yielding control to human."""
    def __init__(self, message: str, risk_assessment: RiskAssessment):
        super().__init__(message)
        self.message = message
        self.risk_assessment = risk_assessment


class ConfirmationDeniedError(PermissionError):
    """Raised when a confirmation gate denies an operation or times out."""
    def __init__(self, message: str, decision: GateDecision):
        super().__init__(message)
        self.message = message
        self.decision = decision


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GateDecision:
    """Detailed record of a confirmation gate outcome."""
    approved: bool
    action_name: str
    reason: str
    approver: str  # e.g. "user_interactive", "custom_handler", "timeout_denied", "policy_auto"
    timestamp: float
    timed_out: bool
    is_hard_stop: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "action_name": self.action_name,
            "reason": self.reason,
            "approver": self.approver,
            "timestamp": self.timestamp,
            "timed_out": self.timed_out,
            "is_hard_stop": self.is_hard_stop,
            "details": self.details,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Security Audit Trail Ledger
# ─────────────────────────────────────────────────────────────────────────────
class SecurityAuditTrail:
    """Thread-safe persistent JSON-lines logger for all safety approvals and denials."""

    def __init__(self, audit_file_path: Optional[Union[str, Path]] = None):
        self._lock = threading.Lock()
        if audit_file_path:
            self._path = Path(audit_file_path)
        else:
            base_log_dir = Path(get_settings().log_path).parent
            self._path = base_log_dir / "safety_audit.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    def log_decision(self, decision: GateDecision) -> None:
        """Appends a GateDecision record to the audit ledger."""
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                line = decision.to_json() + "\n"
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                logger.error("Failed to write security audit record: %s", e)

    def read_records(self) -> List[Dict[str, Any]]:
        """Reads all recorded audit entries."""
        with self._lock:
            if not self._path.exists():
                return []
            records = []
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
            except Exception as e:
                logger.error("Failed to read security audit records: %s", e)
            return records


_global_audit_trail = SecurityAuditTrail()


def get_security_audit_trail() -> SecurityAuditTrail:
    return _global_audit_trail


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation Gate Engine
# ─────────────────────────────────────────────────────────────────────────────
ConfirmationHandler = Callable[[str, RiskAssessment, float], Tuple[bool, str]]


class ConfirmationGate:
    """
    Evaluates risks, invokes confirmation gates, and logs an immutable audit trail.
    Guarantees:
    - Timeouts strictly default to DENY.
    - Hard stops are highlighted and yield full control to human.
    """

    def __init__(
        self,
        audit_trail: Optional[SecurityAuditTrail] = None,
        custom_handler: Optional[ConfirmationHandler] = None,
        use_gui: bool = False,
    ):
        self._audit_trail = audit_trail or _global_audit_trail
        self._custom_handler: Optional[ConfirmationHandler] = custom_handler
        self._use_gui = use_gui
        self._lock = threading.Lock()

    def set_handler(self, handler: Optional[ConfirmationHandler]) -> None:
        """Sets a custom confirmation prompt callback for headless/test environments."""
        with self._lock:
            self._custom_handler = handler

    def enable_gui(self, enabled: bool = True) -> None:
        """Enables or disables GUI modal popup confirmation dialogs."""
        with self._lock:
            self._use_gui = enabled

    def evaluate_and_gate(
        self,
        action_name: str,
        element_name: Optional[str] = None,
        window_title: Optional[str] = None,
        typed_text: Optional[str] = None,
        target: Optional[str] = None,
        timeout_sec: float = 30.0,
    ) -> GateDecision:
        """
        Main entry point:
        1. Analyzes action surfaces for risks and hard stops.
        2. If standard non-risky: approves automatically and returns.
        3. If risky or hard stop: prompts for human confirmation with timeout defaulting to DENY.
        4. Writes decision to audit trail.
        """
        # Always check emergency stop first
        emergency_stop.check_stop()

        assessment = detect_risks(
            element_name=element_name,
            window_title=window_title,
            typed_text=typed_text,
            action_name=action_name,
            target=target,
        )

        # 1. Non-risky operation passes through
        if not assessment.is_risky:
            decision = GateDecision(
                approved=True,
                action_name=action_name,
                reason="Policy evaluated action as non-risky standard operation.",
                approver="policy_auto",
                timestamp=time.time(),
                timed_out=False,
                is_hard_stop=False,
                details={"assessment": assessment.to_dict()},
            )
            self._audit_trail.log_decision(decision)
            return decision

        # 2. Risky action or Hard Stop requires explicit confirmation
        logger.warning(
            "Security Gate Triggered [%s] for action '%s': %s",
            "HARD STOP" if assessment.requires_hard_stop else "RISKY ACTION",
            action_name,
            assessment.summary,
        )

        with self._lock:
            handler = self._custom_handler

        approved = False
        reason = ""
        approver = "unknown"
        timed_out = False
        start_t = time.monotonic()

        if handler is not None:
            try:
                # Custom handler invocation (e.g. test mock or IPC bridge)
                res_approved, res_reason = handler(action_name, assessment, timeout_sec)
                elapsed = time.monotonic() - start_t
                if elapsed >= timeout_sec:
                    approved = False
                    timed_out = True
                    reason = f"Confirmation timed out after {timeout_sec:.1f}s. Defaulted to DENY."
                    approver = "timeout_denied"
                else:
                    approved = bool(res_approved)
                    reason = res_reason
                    approver = "custom_handler"
            except Exception as e:
                approved = False
                reason = f"Confirmation handler raised exception: {e}. Defaulted to DENY."
                approver = "handler_error"
        elif self._use_gui:
            try:
                from neo.ui.confirmation_dialog import show_confirmation_popup
                approved, reason = show_confirmation_popup(action_name, assessment, timeout_sec)
                timed_out = "timed out" in reason.lower()
                approver = "user_gui_popup" if not timed_out else "timeout_denied"
            except Exception as e:
                logger.error("GUI confirmation popup failed: %s. Defaulting to DENY.", e)
                approved = False
                reason = f"GUI popup failed: {e}. Defaulted to DENY."
                approver = "gui_error"
        else:
            # Default interactive console prompt with timeout
            approved, timed_out, reason = self._prompt_console_interactive(
                action_name, assessment, timeout_sec
            )
            approver = "user_console" if not timed_out else "timeout_denied"

        decision = GateDecision(
            approved=approved,
            action_name=action_name,
            reason=reason,
            approver=approver,
            timestamp=time.time(),
            timed_out=timed_out,
            is_hard_stop=assessment.requires_hard_stop,
            details={
                "assessment": assessment.to_dict(),
                "timeout_sec": timeout_sec,
            },
        )

        # Log decision in security audit trail
        self._audit_trail.log_decision(decision)

        if not approved:
            if assessment.requires_hard_stop:
                raise HardStopRequiredError(
                    f"Execution blocked by Hard Stop: {reason}",
                    risk_assessment=assessment,
                )
            raise ConfirmationDeniedError(
                f"Action '{action_name}' was denied: {reason}",
                decision=decision,
            )

        return decision

    def _prompt_console_interactive(
        self,
        action_name: str,
        assessment: RiskAssessment,
        timeout_sec: float,
    ) -> Tuple[bool, bool, str]:
        """
        Console fallback: prints banner and prompts for human approval.
        If timeout expires before input is received, returns (False, True, 'Timed out').
        """
        print("\n" + "=" * 70)
        print(f" [!] NEO SECURITY CONFIRMATION REQUIRED: {action_name.upper()}")
        print(f" Reason: {assessment.summary}")
        if assessment.matched_patterns:
            print(f" Matched: {', '.join(assessment.matched_patterns)}")
        print(f" Surfaces: {assessment.evidence.get('surfaces', {})}")
        print(f" You have {timeout_sec:.0f}s to confirm. Default is DENY.")
        print("=" * 70)

        # Use timed thread for input
        user_input: List[str] = []

        def get_input():
            try:
                ans = input("Approve this action? (y/N): ").strip().lower()
                user_input.append(ans)
            except Exception:
                pass

        t = threading.Thread(target=get_input, daemon=True)
        t.start()
        t.join(timeout=timeout_sec)

        if not user_input:
            print("\n[!] Confirmation timed out. Action DENIED by default.\n")
            return False, True, f"Interactive confirmation timed out after {timeout_sec}s."

        ans = user_input[0]
        if ans in ("y", "yes", "approve"):
            print("\n[+] Action APPROVED by user.\n")
            return True, False, "Approved by user via console."

        print("\n[-] Action DENIED by user.\n")
        return False, False, f"Explicitly denied by user (input: '{ans}')."


# Global default confirmation gate
_global_gate = ConfirmationGate()


def get_confirmation_gate() -> ConfirmationGate:
    return _global_gate
