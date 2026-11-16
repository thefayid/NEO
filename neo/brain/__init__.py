"""
neo.brain — Unified Reasoning, Schema Validation, Context Building, LLM Clients, and Dual-Verification.
"""
from neo.brain.agent import NeoAgent
from neo.brain.context import BrainContext, build_step_context, format_compact_snapshot
from neo.brain.critic import CriticVerdict, GoalCritic, is_step_complete
from neo.brain.llm_client import (
    BaseLLMClient,
    GoogleGenAIClient,
    LLMDecisionParseError,
    MockLLMClient,
    OpenAIClient,
    get_llm_client,
    parse_llm_json,
    validate_decision,
)
from neo.brain.planner import ActionDispatcher, StepExecutionResult
from neo.brain.prompts import (
    get_action_list_formatted,
    get_reply_schema_formatted,
    load_system_prompt,
)
from neo.brain.schema import (
    ActionLoopDetectedError,
    BrainValidationError,
    EscalationRequiredError,
    InvalidJSONError,
    InvalidTargetIDError,
    LLMReply,
    LowConfidenceError,
    PrematureDoneError,
    UnknownActionError,
    query_with_retries,
    validate_llm_reply,
)
from neo.brain.verifier import GoalVerifier, VerificationResult
from neo.brain.whitelist import (
    WHITELISTED_ACTIONS,
    AgentDecision,
)

__all__ = [
    # Core Agent
    "NeoAgent",
    # Whitelist & Decisions
    "AgentDecision",
    "WHITELISTED_ACTIONS",
    # Prompts & Versioning
    "load_system_prompt",
    "get_action_list_formatted",
    "get_reply_schema_formatted",
    # Schema & Validation
    "LLMReply",
    "validate_llm_reply",
    "query_with_retries",
    "BrainValidationError",
    "InvalidJSONError",
    "UnknownActionError",
    "InvalidTargetIDError",
    "LowConfidenceError",
    "PrematureDoneError",
    "ActionLoopDetectedError",
    "EscalationRequiredError",
    # Context
    "BrainContext",
    "build_step_context",
    "format_compact_snapshot",
    # Critic & Dual Verification
    "CriticVerdict",
    "GoalCritic",
    "is_step_complete",
    # Verifier & Dispatcher
    "GoalVerifier",
    "VerificationResult",
    "ActionDispatcher",
    "StepExecutionResult",
    # Model-Agnostic Clients
    "BaseLLMClient",
    "GoogleGenAIClient",
    "OpenAIClient",
    "MockLLMClient",
    "get_llm_client",
    "parse_llm_json",
    "validate_decision",
    "LLMDecisionParseError",
]
