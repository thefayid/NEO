"""
neo/brain/prompt_builder.py — Step Prompt Formatter and Evidence Feedback.

Architectural Guarantees:
1. Strict feedback loop: the empirical evidence gathered by deterministic code
   from step N is directly fed into the LLM prompt for step N+1.
2. The LLM receives structured, numbered element identifiers valid only for the current snapshot.
3. Untrusted screen/window/DOM text is safely wrapped via wrap_untrusted_data().
4. Enforces JSON output matching AgentDecision schema.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from neo.safety.injection import wrap_untrusted_data
from neo.windows.core import WindowInfo
from neo.windows.uia_snapshot import UIASnapshot


def build_system_prompt() -> str:
    """Returns the immutable system prompt for the NEO Agent."""
    return """You are NEO, an expert Windows personal-assistant agent that controls apps, files, browser, keyboard, and mouse accurately and without hallucination.

ARCHITECTURE & STRICT ORDER OF PREFERENCE:
1. Direct APIs / commands / COM (files, Office, launching apps)
2. Browser DOM control (Playwright selectors and properties)
3. Windows UI Automation (real named elements, readable values)
4. Keyboard shortcuts / hotkeys
5. Vision + coordinates (last resort only when UIA is sparse or inaccessible)

RULES:
- Choose exactly ONE action per step from the allowed whitelist.
- Never invent actions or parameters.
- Inspect the empirical evidence from your previous action. If an action produced a warning or failed verification, adapt your approach.
- You NEVER mark anything 'done' yourself. An external deterministic verifier proves goal completion using real system evidence.
- Respond ONLY with a valid JSON object matching this schema:
{
  "thought": "Your concise chain-of-thought rationale analyzing current state and selecting the next action",
  "action": "<action_name_from_whitelist>",
  "parameters": { ... }
}
"""


def build_step_prompt(
    goal: str,
    step_index: int,
    max_steps: int,
    foreground_window: Optional[WindowInfo],
    snapshot: Optional[UIASnapshot],
    last_action: Optional[str] = None,
    last_evidence: Optional[Dict[str, Any]] = None,
    last_warning: Optional[str] = None,
    dom_elements: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Constructs the prompt delivered to the LLM at step N.
    """
    lines: List[str] = []
    lines.append(f"### CURRENT TASK GOAL: {goal}")
    lines.append(f"### STEP BUDGET: Step {step_index} of {max_steps} (Remaining: {max(0, max_steps - step_index)})")

    # Feedback from previous step
    if last_action:
        lines.append("\n### PREVIOUS STEP FEEDBACK:")
        lines.append(f"- Action Executed: {last_action}")
        if last_warning:
            lines.append(f"- WARNING: {last_warning}")
        if last_evidence:
            ev_str = json.dumps(last_evidence, indent=2, default=str)
            lines.append(f"- Empirical Evidence Recorded:\n{ev_str}")

    # Active foreground window
    lines.append("\n### FOREGROUND WINDOW:")
    if foreground_window:
        safe_title = wrap_untrusted_data(foreground_window.title, source="WindowTitle")
        lines.append(f"- Title: {safe_title}")
        lines.append(f"- Process: {foreground_window.process_name} (PID: {foreground_window.pid})")
        lines.append(f"- Rect: {foreground_window.rect}")
    else:
        lines.append("- No foreground window detected.")

    # Browser DOM elements (if browser active)
    if dom_elements:
        lines.append("\n### BROWSER INTERACTIVE DOM ELEMENTS:")
        for el in dom_elements[:40]:
            name = wrap_untrusted_data(el.get("name_or_text", ""), source="DOM")
            lines.append(f"  [{el.get('index')}] <{el.get('tag_name')}> role={el.get('role')} selector='{el.get('selector')}' text='{name}'")

    # UIA Snapshot elements
    elif snapshot and snapshot.elements:
        lines.append(f"\n### ACTIVE UI SNAPSHOT (ID: {snapshot.snapshot_id}):")
        if snapshot.is_sparse:
            lines.append("> [!NOTE] Sparse UI detected. Visual fallback (Level 5) may be required if named elements are absent.")

        for elem in snapshot.elements[:45]:
            safe_name = wrap_untrusted_data(elem.name, source="UIElement")
            val_str = f" value='{elem.value}'" if elem.value else ""
            lines.append(
                f"  [{elem.id}] {elem.control_type} name='{safe_name}' id='{elem.automation_id}'{val_str} bounds={elem.bounding_rect}"
            )
    else:
        lines.append("\n### UI SNAPSHOT: No elements captured for this window.")

    lines.append("\nSelect your NEXT single action. Respond ONLY with valid JSON matching the AgentDecision schema.")
    return "\n".join(lines)
