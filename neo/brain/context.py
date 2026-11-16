"""
neo/brain/context.py — Compact Context Builder with Conditional Screenshot Attachment.

Architectural Guarantees:
1. Builds compact, high-density prompts from:
   - Goal and step budget
   - Last action result and empirical evidence
   - Current UI snapshot (or DOM elements)
   - Recent history capped strictly to the last 5 steps
   - System state log (foreground window, process, PID, DPI)
2. Token-efficient conditional screenshot attachment:
   - Attaches a screenshot ONLY when current UI snapshot is sparse OR when the LLM asks.
   - Normal rich snapshots omit screenshots to maximize latency and context budget.
3. Safe untrusted data wrapping via neo.safety.injection.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from neo.safety.injection import wrap_untrusted_data
from neo.vision.capture import VisionCaptureResult, capture_screen
from neo.windows.uia_snapshot import UIASnapshot

logger = logging.getLogger("neo.brain.context")


@dataclass
class BrainContext:
    """Encapsulates the rendered text prompt and optional screenshot artifact."""
    prompt_text: str
    screenshot_path: Optional[str] = None
    screenshot_attached: bool = False
    element_count: int = 0
    history_step_count: int = 0
    is_sparse: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screenshot_attached": self.screenshot_attached,
            "screenshot_path": self.screenshot_path,
            "element_count": self.element_count,
            "history_step_count": self.history_step_count,
            "is_sparse": self.is_sparse,
        }


def format_compact_snapshot(snapshot: UIASnapshot, max_elements: int = 35) -> str:
    """Renders a compact, numbered list of interactive UI elements."""
    if not snapshot.elements:
        return "  (No interactable elements detected in snapshot)"

    lines = []
    for elem in snapshot.elements[:max_elements]:
        safe_name = wrap_untrusted_data(elem.name, source="UIElement")
        val_str = f" value='{elem.value}'" if elem.value else ""
        auto_id = f" auto_id='{elem.automation_id}'" if elem.automation_id else ""
        lines.append(f"  [{elem.id}] <{elem.control_type}>{auto_id} '{safe_name}'{val_str}")

    if len(snapshot.elements) > max_elements:
        lines.append(f"  ... and {len(snapshot.elements) - max_elements} more elements.")
    return "\n".join(lines)


def build_step_context(
    goal: str,
    step_index: int = 1,
    max_steps: int = 25,
    last_result: Optional[Dict[str, Any]] = None,
    current_snapshot: Optional[UIASnapshot] = None,
    step_history: Optional[List[Dict[str, Any]]] = None,
    state_log: Optional[Dict[str, Any]] = None,
    llm_asked_for_screenshot: bool = False,
) -> BrainContext:
    """
    Constructs the compact step prompt and conditionally captures/attaches a screenshot.
    """
    lines: List[str] = []

    # 1. Goal and Budget Header
    remaining_steps = max(0, max_steps - step_index)
    lines.append(f"### TASK GOAL: {goal}")
    lines.append(f"### STEP BUDGET: Step {step_index} of {max_steps} (Remaining: {remaining_steps})")

    # 2. System State Log
    if state_log:
        title = wrap_untrusted_data(state_log.get("window_title", ""), source="WindowTitle")
        proc = state_log.get("process_name", "Unknown")
        pid = state_log.get("pid", 0)
        dpi = state_log.get("dpi_scale", 1.0)
        lines.append(f"\n### ACTIVE WINDOW STATE:\n- Title: {title}\n- Process: {proc} (PID: {pid}) | DPI Scale: {dpi}")

    # 3. Feedback from Last Action
    if last_result:
        act = last_result.get("action", "unknown")
        ok_str = "OK" if last_result.get("ok") else "ERROR"
        lines.append("\n### LAST ACTION FEEDBACK:")
        lines.append(f"- Action: `{act}` -> [{ok_str}]")

        warning = last_result.get("warning")
        if warning:
            lines.append(f"- WARNING: {warning}")

        evidence = last_result.get("evidence")
        if evidence:
            ev_str = json.dumps(evidence, indent=2, default=str)
            lines.append(f"- Recorded Evidence:\n{ev_str}")

    # 4. Recent History (Strictly Capped to Last 5 Steps)
    hist_count = 0
    if step_history:
        recent_5 = step_history[-5:]
        hist_count = len(recent_5)
        lines.append(f"\n### RECENT STEP HISTORY (Last {hist_count} steps):")
        for st in recent_5:
            s_idx = st.get("step_index", "?")
            s_act = st.get("action", "?")
            s_ok = "OK" if st.get("ok") else "FAILED"
            s_target = f" (target={st.get('target_id')})" if st.get("target_id") is not None else ""
            lines.append(f"  • Step {s_idx}: `{s_act}`{s_target} -> {s_ok}")

    # 5. Active UI Snapshot & Screenshot Attachment Decision
    attach_screenshot = False
    screenshot_path: Optional[str] = None
    is_sparse = False
    elem_count = 0

    if current_snapshot:
        elem_count = len(current_snapshot.elements)
        is_sparse = current_snapshot.is_sparse
        lines.append(f"\n### ACTIVE UI SNAPSHOT (ID: {current_snapshot.snapshot_id}, Elements: {elem_count}):")

        if is_sparse:
            lines.append("> [!NOTE] Sparse UI snapshot detected (few or no named UIA controls).")
            attach_screenshot = True
        elif llm_asked_for_screenshot:
            lines.append("> [!NOTE] Attaching screenshot per model request.")
            attach_screenshot = True

        lines.append(format_compact_snapshot(current_snapshot))
    else:
        if llm_asked_for_screenshot:
            attach_screenshot = True
        lines.append("\n### ACTIVE UI SNAPSHOT: None available.")

    # 6. Execute Screenshot Capture if Triggered
    if attach_screenshot:
        try:
            cap = capture_screen()
            if cap.ok and cap.path:
                screenshot_path = cap.path
                lines.append(f"\n[ATTACHED SCREENSHOT]: Local path '{cap.path}' ({cap.width}x{cap.height})")
            else:
                lines.append(f"\n[ATTACHED SCREENSHOT]: Failed to capture ({cap.error})")
        except Exception as e:
            logger.warning("Could not capture screenshot for context: %s", e)
            lines.append(f"\n[ATTACHED SCREENSHOT]: Capture error: {e}")

    full_prompt = "\n".join(lines)

    return BrainContext(
        prompt_text=full_prompt,
        screenshot_path=screenshot_path,
        screenshot_attached=attach_screenshot and screenshot_path is not None,
        element_count=elem_count,
        history_step_count=hist_count,
        is_sparse=is_sparse,
    )
