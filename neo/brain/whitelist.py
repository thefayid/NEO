"""
neo/brain/whitelist.py — Unified Action Whitelist and Schema Enforcement.

Architectural Guarantees:
1. Strict whitelist: LLM can ONLY choose one action from this fixed whitelist.
2. Parameter validation with Pydantic: unknown actions or invalid arguments
   are rejected before execution, returning clear actionable feedback to the LLM.
3. Multi-level action routing: mapped directly to the 5-level preference hierarchy.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger("neo.brain.whitelist")

# Whitelist of all permitted actions across the 5 architectural levels
WHITELISTED_ACTIONS = {
    # Level 1: Direct APIs (Files & Office)
    "file_read",
    "file_write",
    "file_list",
    "file_search",
    "file_delete",
    "office_word_read",
    "office_excel_read",
    "office_excel_write",
    "office_email_draft",
    # Level 2: Browser DOM Control
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_read",
    "browser_snapshot",
    # Level 3: Windows UI Automation
    "click",
    "double_click",
    "right_click",
    "set_text",
    "select",
    "read",
    "scroll",
    "focus",
    "open",
    "wait",
    "screenshot",
    # Level 4: Keyboard Shortcuts & Native Typing
    "type",
    "press_key",
    "hotkey",
    # Level 5: Vision Fallback Coordinates
    "click_coords",
    "type_coords",
    "click_xy",
}


class AgentDecision(BaseModel):
    """
    Structured response required from the LLM at each step.
    Enforces thought rationale and exactly ONE whitelisted action.
    """
    model_config = ConfigDict(extra="forbid")

    thought: str = Field(..., min_length=3, description="Chain-of-thought rationale explaining the step.")
    action: str = Field(..., description="Action name from the whitelisted actions.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters specific to the chosen action.")

    @field_validator("action")
    @classmethod
    def validate_action_whitelist(cls, v: str) -> str:
        act_clean = v.strip().lower()
        if act_clean not in WHITELISTED_ACTIONS:
            raise ValueError(
                f"Action '{v}' is not in the allowed whitelist. Permitted actions: {sorted(list(WHITELISTED_ACTIONS))}"
            )
        return act_clean

    @model_validator(mode="after")
    def validate_parameters_for_action(self) -> AgentDecision:
        act = self.action
        params = self.parameters

        # Level 1 validations
        if act == "file_read" and "path" not in params:
            raise ValueError("file_read requires 'path' parameter.")
        if act == "file_write" and ("path" not in params or "content" not in params):
            raise ValueError("file_write requires 'path' and 'content' parameters.")
        if act == "file_delete" and "path" not in params:
            raise ValueError("file_delete requires 'path' parameter.")

        # Level 2 validations
        if act == "browser_navigate" and "url" not in params:
            raise ValueError("browser_navigate requires 'url' parameter.")
        if act == "browser_click" and "selector" not in params:
            raise ValueError("browser_click requires 'selector' parameter.")
        if act == "browser_type" and ("selector" not in params or "text" not in params):
            raise ValueError("browser_type requires 'selector' and 'text' parameters.")

        # Level 3 validations
        if act in ("click", "double_click", "right_click", "set_text", "select", "read"):
            if "element_id" not in params and "coords" not in params:
                raise ValueError(f"{act} requires either 'element_id' or 'coords'.")
        if act == "focus" and "title_regex" not in params and "target" not in params:
            raise ValueError("focus requires 'title_regex' or 'target' parameter.")
        if act == "open" and "target" not in params:
            raise ValueError("open requires 'target' parameter.")

        # Level 4 validations
        if act == "type" and "text" not in params:
            raise ValueError("type requires 'text' parameter.")
        if act == "press_key" and "key" not in params:
            raise ValueError("press_key requires 'key' parameter.")
        if act == "hotkey" and "keys" not in params:
            raise ValueError("hotkey requires 'keys' list parameter.")

        # Level 5 validations
        if act == "click_coords" and "coords" not in params:
            raise ValueError("click_coords requires 'coords' [x, y] parameter.")
        if act == "type_coords" and ("coords" not in params or "text" not in params):
            raise ValueError("type_coords requires 'coords' and 'text' parameters.")
        if act == "click_xy":
            if "x" not in params or "y" not in params:
                raise ValueError("click_xy requires 'x' and 'y' integer coordinates.")
            if "reason" not in params:
                raise ValueError("click_xy requires 'reason' explaining why UIA/DOM options were exhausted.")
            if "exhaustion_evidence" not in params:
                raise ValueError("click_xy requires 'exhaustion_evidence' dict documenting higher-tier failure.")

        return self
