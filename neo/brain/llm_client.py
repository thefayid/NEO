"""
neo/brain/llm_client.py — Strongly-Typed LLM Decision Engine.

Architectural Guarantees:
1. Strict schema compliance: enforces AgentDecision whitelist and required parameters.
2. Robust JSON parsing: handles clean JSON, markdown-fenced codeblocks, and raw output.
3. Multi-vendor support: Google GenAI (Gemini) and OpenAI, with zero hard-coded secrets.
4. Deterministic Mock client for hermetic offline test suites.
5. Explicit typed errors: never swallows or hides LLM failures.
"""
from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from pydantic import ValidationError

from neo.brain.whitelist import AgentDecision
from neo.config import get_settings

logger = logging.getLogger("neo.brain.llm_client")


class LLMDecisionParseError(ValueError):
    """Raised when LLM output cannot be parsed or fails AgentDecision validation."""
    def __init__(self, raw_output: str, reason: str):
        super().__init__(f"Failed to parse LLM decision: {reason}\nRaw response:\n{raw_output}")
        self.raw_output = raw_output
        self.reason = reason


def parse_llm_json(raw_text: str) -> Dict[str, Any]:
    """
    Extracts and parses JSON object from LLM response text.
    Handles Markdown code fences (```json ... ```) and leading/trailing chatter.
    """
    cleaned = raw_text.strip()

    # 1. Strip markdown code fences if present
    fence_pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    match = re.search(fence_pattern, cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()

    # 2. Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 3. Fallback: find balanced curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as err:
            raise LLMDecisionParseError(raw_text, f"Extracted candidate JSON was invalid: {err}") from err

    raise LLMDecisionParseError(raw_text, "No valid JSON object could be located in the response.")


def validate_decision(raw_text: str) -> AgentDecision:
    """
    Parses LLM text and validates it against the strict AgentDecision schema.
    """
    data = parse_llm_json(raw_text)
    try:
        return AgentDecision.model_validate(data)
    except ValidationError as e:
        raise LLMDecisionParseError(raw_text, f"AgentDecision schema validation failed: {e}") from e


class BaseLLMClient(ABC):
    """Abstract interface for model-agnostic LLM providers."""

    @abstractmethod
    def query(self, system_prompt: str, user_prompt: str) -> str:
        """Submits prompts to the model and returns the raw string response."""
        pass

    def decide(self, system_prompt: str, step_prompt: str) -> AgentDecision:
        """Submits prompts to the model and returns a validated AgentDecision."""
        raw_text = self.query(system_prompt, step_prompt)
        return validate_decision(raw_text)


class GoogleGenAIClient(BaseLLMClient):
    """
    Official Google GenAI SDK (google.genai) client for Gemini models.
    Reads API key strictly from GEMINI_API_KEY or GOOGLE_API_KEY environment variable.
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "Gemini API key not found. Please set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
            )

        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=key)
        self._types = types
        settings = get_settings()
        self.model_name = model_name or settings.model_name

    def query(self, system_prompt: str, user_prompt: str) -> str:
        try:
            config = self._types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.1,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            logger.error("GoogleGenAIClient query failed: %s", e)
            raise RuntimeError(f"Google GenAI API call failed: {e}") from e


class OpenAIClient(BaseLLMClient):
    """
    OpenAI API client using official openai library.
    Reads API key strictly from OPENAI_API_KEY environment variable.
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OpenAI API key not found. Please set OPENAI_API_KEY environment variable."
            )

        from openai import OpenAI
        self._client = OpenAI(api_key=key)
        self.model_name = model_name or "gpt-4o"

    def query(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("OpenAIClient query failed: %s", e)
            raise RuntimeError(f"OpenAI API call failed: {e}") from e


class MockLLMClient(BaseLLMClient):
    """
    Deterministic Mock LLM Client for hermetic testing.
    Can be configured with an explicit sequence of raw strings, AgentDecisions, or a callable.
    """

    def __init__(
        self,
        decision_sequence: Optional[Sequence[Union[AgentDecision, str]]] = None,
        decision_fn: Optional[Callable[[str, str], Union[AgentDecision, str]]] = None,
    ) -> None:
        self._responses: List[Union[AgentDecision, str]] = list(decision_sequence or [])
        self._decision_fn = decision_fn
        self._call_count: int = 0
        self.call_history: List[Dict[str, str]] = []

    def query(self, system_prompt: str, user_prompt: str) -> str:
        self.call_history.append({"system_prompt": system_prompt, "step_prompt": user_prompt})
        self._call_count += 1

        if self._decision_fn is not None:
            res = self._decision_fn(system_prompt, user_prompt)
            if isinstance(res, AgentDecision):
                return json.dumps(res.model_dump())
            return str(res)

        if self._responses:
            item = self._responses.pop(0)
            if isinstance(item, AgentDecision):
                return json.dumps(item.model_dump())
            return str(item)

        raise RuntimeError(f"MockLLMClient exhausted response sequence at call #{self._call_count}")

    def decide(self, system_prompt: str, step_prompt: str) -> AgentDecision:
        # If the next response is already an AgentDecision, we can return it directly,
        # or parse the query output.
        if self._responses and isinstance(self._responses[0], AgentDecision) and self._decision_fn is None:
            self.call_history.append({"system_prompt": system_prompt, "step_prompt": step_prompt})
            self._call_count += 1
            return self._responses.pop(0)  # type: ignore

        raw_text = self.query(system_prompt, step_prompt)
        return validate_decision(raw_text)


def get_llm_client(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseLLMClient:
    """
    Factory function returning the configured LLM client based on environment or settings.
    """
    settings = get_settings()
    prov = (provider or os.environ.get("NEO_PROVIDER", "gemini")).lower().strip()

    if prov in ("gemini", "google"):
        return GoogleGenAIClient(model_name=model_name or settings.model_name)
    elif prov in ("openai", "gpt"):
        return OpenAIClient(model_name=model_name or "gpt-4o")
    elif prov == "mock":
        return MockLLMClient()
    else:
        raise ValueError(f"Unsupported LLM provider '{prov}'. Supported: 'gemini', 'openai', 'mock'")
