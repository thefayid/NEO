"""
neo.safety — Safety guardrails, emergency stop, and confirmation gates.
"""
from neo.safety.emergency_stop import (
    EmergencyStop,
    EmergencyStopTriggeredError,
    emergency_stop,
    setup_emergency_hotkey,
)
from neo.safety.gates import (
    ConfirmationDeniedError,
    ConfirmationGate,
    GateDecision,
    HardStopRequiredError,
    SecurityAuditTrail,
    get_confirmation_gate,
    get_security_audit_trail,
)
from neo.safety.injection import (
    InjectionReport,
    analyze_untrusted_text,
    strip_stealth_unicode,
    wrap_untrusted_data,
)
from neo.safety.policy import (
    DEFAULT_ALLOWED_DOMAINS,
    DISALLOWED_EXECUTABLE_EXTENSIONS,
    DomainValidationResult,
    PathValidationResult,
    RiskAssessment,
    detect_risks,
    is_app_allowed,
    validate_domain,
    validate_path,
)

__all__ = [
    "EmergencyStop",
    "EmergencyStopTriggeredError",
    "emergency_stop",
    "is_app_allowed",
    "validate_path",
    "validate_domain",
    "detect_risks",
    "RiskAssessment",
    "PathValidationResult",
    "DomainValidationResult",
    "DISALLOWED_EXECUTABLE_EXTENSIONS",
    "DEFAULT_ALLOWED_DOMAINS",
    "ConfirmationGate",
    "GateDecision",
    "HardStopRequiredError",
    "ConfirmationDeniedError",
    "SecurityAuditTrail",
    "get_confirmation_gate",
    "get_security_audit_trail",
    "InjectionReport",
    "analyze_untrusted_text",
    "strip_stealth_unicode",
    "wrap_untrusted_data",
]
