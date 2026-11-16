"""
neo/brain/prompts.py — Versioned System Prompt Loader with Schema & Action Integration.

Architectural Guarantees:
1. Versioned prompt storage: Loads base system instructions from versioned text files.
2. Automatic action list injection: Permitted actions are derived directly from the
   single source of truth (WHITELISTED_ACTIONS).
3. Automatic schema specification: Strict JSON reply format matching LLMReply schema
   is appended dynamically.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Union

from neo.brain.whitelist import WHITELISTED_ACTIONS

logger = logging.getLogger("neo.brain.prompts")

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def get_action_list_formatted() -> str:
    """Returns a clean categorized markdown list of all permitted whitelisted actions."""
    # Group actions by architectural level
    l1_actions = [a for a in sorted(WHITELISTED_ACTIONS) if a.startswith("file_") or a.startswith("office_")]
    l2_actions = [a for a in sorted(WHITELISTED_ACTIONS) if a.startswith("browser_")]
    l3_actions = [a for a in ("click", "double_click", "right_click", "set_text", "select", "read", "scroll", "focus", "open", "wait", "screenshot") if a in WHITELISTED_ACTIONS]
    l4_actions = [a for a in ("type", "press_key", "hotkey") if a in WHITELISTED_ACTIONS]
    l5_actions = [a for a in ("click_coords", "type_coords", "click_xy") if a in WHITELISTED_ACTIONS]

    lines = [
        "### PERMITTED ACTION WHITELIST (Choose exactly ONE):",
        "- Level 1 (Direct APIs): " + ", ".join(f"`{a}`" for a in l1_actions),
        "- Level 2 (Browser DOM): " + ", ".join(f"`{a}`" for a in l2_actions),
        "- Level 3 (Windows UIA): " + ", ".join(f"`{a}`" for a in l3_actions),
        "- Level 4 (Keyboard): " + ", ".join(f"`{a}`" for a in l4_actions),
        "- Level 5 (Vision Fallback): " + ", ".join(f"`{a}`" for a in l5_actions),
    ]
    return "\n".join(lines)


def get_reply_schema_formatted() -> str:
    """Returns the strict JSON format required from the LLM."""
    return """### REQUIRED JSON REPLY SCHEMA:
You MUST respond with a single valid JSON object matching this schema:
```json
{
  "stage": "perceive" | "plan" | "act" | "verify" | "done",
  "observation": "Detailed description of what you observe in the foreground window, DOM, or files",
  "last_action_result": "Objective assessment of the result of the previous action based on real evidence",
  "plan": [
    "Step 1: Current or next sub-goal",
    "Step 2: Subsequent step"
  ],
  "action": "<action_name_from_whitelist>",
  "target_id": <integer_element_id_from_active_snapshot_or_null>,
  "text": "<text_to_type_or_target_path_or_url_or_null>",
  "confidence": <float_between_0.0_and_1.0>,
  "parameters": {
    "key": "optional_action_specific_parameters"
  }
}
```
RULES:
1. Do NOT wrap output in conversational preamble or closing commentary.
2. `target_id` must match a valid, numbered element ID from the CURRENT active snapshot.
3. If acting, `confidence` must be at least 0.6. Low-confidence actions are rejected.
4. You cannot mark stage "done" without conclusive verification evidence."""


def load_system_prompt(
    version: str = "v1",
    custom_path: Optional[Union[str, Path]] = None,
) -> str:
    """
    Loads base prompt from a versioned text file and appends the action list and schema.
    """
    if custom_path is not None:
        path = Path(custom_path)
    else:
        path = _PROMPTS_DIR / f"system_{version}.txt"

    if not path.exists():
        logger.warning("Versioned prompt file '%s' not found. Falling back to built-in v1 template.", path)
        base_prompt = (
            "You are NEO, an expert Windows personal-assistant agent that controls apps, files, "
            "browser, keyboard, and mouse accurately and without hallucination."
        )
    else:
        base_prompt = path.read_text(encoding="utf-8").strip()

    actions_text = get_action_list_formatted()
    schema_text = get_reply_schema_formatted()

    full_prompt = f"{base_prompt}\n\n{actions_text}\n\n{schema_text}"
    return full_prompt
