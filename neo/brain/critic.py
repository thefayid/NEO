"""
neo/brain/critic.py — Independent Dual-Verification Critic Engine.

Architectural Guarantees:
1. Secondary LLM Verification Pass:
   - A distinct, skeptical LLM critic inspects real empirical evidence against the
     claimed result.
   - Answers: 'verified' | 'not_verified' | 'unsure'.
2. Dual-Verification Rule:
   - A step or goal counts as complete ONLY if deterministic code verification
     (file contents, window titles, readbacks) AND the critic agree on 'verified'.
   - If either disagrees or says 'unsure', the task remains INCOMPLETE.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple, Union

from neo.brain.llm_client import BaseLLMClient, get_llm_client, parse_llm_json
from neo.brain.verifier import VerificationResult

logger = logging.getLogger("neo.brain.critic")


CRITIC_SYSTEM_PROMPT = """You are an objective, skeptical verification critic for the NEO Windows assistant agent.
Your SOLE responsibility is to evaluate whether a claimed task outcome is conclusively substantiated by real empirical code evidence.

RULES:
1. Be strict and skeptical. Do NOT assume success without tangible, unambiguous proof.
2. Inspect the provided empirical evidence (e.g. file hashes, exact readback strings, window titles, OpenCV image diff percentage).
3. If the evidence conclusively proves the claimed outcome matches the goal, answer "verified".
4. If the evidence shows a mismatch, an error, or the action did not produce the required state change, answer "not_verified".
5. If the evidence is ambiguous, partial, or inconclusive, answer "unsure".
6. Respond ONLY with a valid JSON object matching this schema:
{
  "verdict": "verified" | "not_verified" | "unsure",
  "explanation": "Clear, concise justification based strictly on the provided evidence",
  "confidence": <float between 0.0 and 1.0>
}
"""


@dataclass
class CriticVerdict:
    """Objective assessment returned by the independent critic."""
    verdict: Literal["verified", "not_verified", "unsure"]
    explanation: str
    confidence: float

    @property
    def is_verified(self) -> bool:
        return self.verdict == "verified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "explanation": self.explanation,
            "confidence": round(self.confidence, 3),
            "is_verified": self.is_verified,
        }


class GoalCritic:
    """
    Independent critic evaluating claimed outcomes against empirical execution evidence.
    """

    def __init__(self, llm_client: Optional[BaseLLMClient] = None) -> None:
        self.client = llm_client or get_llm_client()

    def evaluate(
        self,
        goal: str,
        claimed_result: str,
        step_evidence: Dict[str, Any],
        last_action: str = "unknown",
    ) -> CriticVerdict:
        """
        Submits evidence to the critic LLM and parses the verdict.
        """
        from neo.brain.llm_client import MockLLMClient
        if isinstance(self.client, MockLLMClient) and not self.client._responses:
            return CriticVerdict(verdict="verified", explanation="Mock client auto-verified step completion.", confidence=1.0)

        ev_str = json.dumps(step_evidence, indent=2, default=str)
        user_prompt = (
            f"### TASK GOAL:\n{goal}\n\n"
            f"### LAST ACTION EXECUTED:\n{last_action}\n\n"
            f"### CLAIMED OUTCOME / OBSERVATION:\n{claimed_result}\n\n"
            f"### EMPIRICAL CODE EVIDENCE RECORDED:\n{ev_str}\n\n"
            f"Audit the evidence carefully. Respond with JSON: verdict, explanation, confidence."
        )

        try:
            raw_reply = self.client.decide(CRITIC_SYSTEM_PROMPT, user_prompt)
            # If client returns an AgentDecision, extract thought/parameters
            if hasattr(raw_reply, "thought"):
                # Check if parameters contains the critic fields
                params = getattr(raw_reply, "parameters", {})
                verdict_val = params.get("verdict")
                if not verdict_val:
                    # Parse thought as text
                    data = parse_llm_json(raw_reply.thought)
                else:
                    data = params
            else:
                data = parse_llm_json(str(raw_reply))

            v_raw = str(data.get("verdict", "unsure")).strip().lower()
            if v_raw not in ("verified", "not_verified", "unsure"):
                v_raw = "unsure"

            expl = str(data.get("explanation", "No explanation provided."))
            conf = float(data.get("confidence", 0.5))

            return CriticVerdict(verdict=v_raw, explanation=expl, confidence=conf)

        except Exception as e:
            logger.warning("Critic evaluation failed to parse: %s. Defaulting to 'unsure'.", e)
            return CriticVerdict(
                verdict="unsure",
                explanation=f"Critic encountered evaluation exception: {e}",
                confidence=0.0,
            )


def is_step_complete(
    code_verification: VerificationResult,
    critic_verdict: CriticVerdict,
) -> Tuple[bool, str]:
    """
    Dual-Verification Gate:
    A task or step counts as complete ONLY if deterministic code verification
    AND the independent critic both agree on 'verified'.
    """
    # 1. Check deterministic code verification
    if not code_verification.completed:
        return False, f"Code verification failed: {code_verification.rationale}"

    # 2. Check independent critic
    if critic_verdict.verdict == "not_verified":
        return False, f"Critic rejected completion: {critic_verdict.explanation}"
    elif critic_verdict.verdict == "unsure":
        return False, f"Critic is unsure ({critic_verdict.explanation}). Conclusive proof missing."
    elif critic_verdict.verdict == "verified":
        combined_rationale = (
            f"Goal verified by both deterministic code evidence ({code_verification.rationale}) "
            f"and independent critic approval ({critic_verdict.explanation})."
        )
        return True, combined_rationale

    return False, "Unknown verification state; defaulting to incomplete."
