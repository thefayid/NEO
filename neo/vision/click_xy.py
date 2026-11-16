"""
neo/vision/click_xy.py — Level 5 Vision Fallback Click Action with Diff Verification.

Architectural Guarantees:
1. Usable ONLY when higher architectural tiers (Direct APIs, Playwright DOM, Windows UIA, Hotkeys)
   are provably exhausted.
2. Mandatory Justification & Exhaustion Evidence:
   - Raises VisionActionBlockedError if reason or exhaustion_evidence is omitted.
3. Prominent Security Logging:
   - Records high-visibility warning in structured logs documenting why the vision fallback was needed.
4. Diff-Based Empirical Verification:
   - Captures high-speed screenshots before and after click.
   - Uses OpenCV diff to empirically verify visual state change on screen.
   - If no pixels changed, warns the LLM and marks verified="false".
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from neo.safety.emergency_stop import emergency_stop
from neo.vision.capture import capture_screen
from neo.vision.diff import diff_images
from neo.windows.actions import ActionResult
from neo.windows.core import click_coords

logger = logging.getLogger("neo.vision.click_xy")


class VisionActionBlockedError(PermissionError):
    """Raised when Level 5 vision coordinate clicks are attempted without proper exhaustion proof."""
    pass


def validate_exhaustion_evidence(reason: str, exhaustion_evidence: Optional[Dict[str, Any]]) -> None:
    """
    Validates that Level 5 vision fallback is legally permitted by policy.
    Requires an explicit justification string and structured exhaustion evidence.
    """
    if not reason or len(reason.strip()) < 8:
        raise VisionActionBlockedError(
            "Level 5 click_xy rejected: A detailed justification 'reason' is required (minimum 8 characters) "
            "explaining why Level 1 (Direct APIs), Level 2 (Browser DOM), Level 3 (UIA), and Level 4 (Hotkeys) "
            "could not be used."
        )

    if not exhaustion_evidence or not isinstance(exhaustion_evidence, dict) or len(exhaustion_evidence) == 0:
        raise VisionActionBlockedError(
            "Level 5 click_xy rejected: 'exhaustion_evidence' dictionary is mandatory. "
            "Must provide evidence that UIA/DOM options were exhausted (e.g. {'uia_sparse': True, 'dom_inactive': True})."
        )

    # Check that at least one truthy exhaustion flag exists
    if not any(bool(v) for v in exhaustion_evidence.values()):
        raise VisionActionBlockedError(
            f"Level 5 click_xy rejected: 'exhaustion_evidence' contains no positive exhaustion indicators: {exhaustion_evidence}"
        )


def click_xy(
    x: int,
    y: int,
    reason: str,
    exhaustion_evidence: Dict[str, Any],
    button: str = "left",
    double: bool = False,
    settle_timeout: float = 1.0,
    diff_threshold: int = 25,
) -> ActionResult:
    """
    Executes a physical coordinate click at (x, y) with OpenCV diff-based verification.
    Usable ONLY when UIA and DOM options are exhausted.
    """
    emergency_stop.check_stop()

    # Reject negative coordinates
    if x < 0 or y < 0:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"coords": (x, y)},
            warning=f"Invalid click coordinates ({x}, {y}): screen coordinates cannot be negative.",
        )

    # 1. Enforce Tier Exhaustion Gate
    validate_exhaustion_evidence(reason, exhaustion_evidence)

    # 2. Prominent logging of fallback activation
    logger.warning(
        "🚨 [LEVEL 5 VISION FALLBACK] click_xy invoked at (%d, %d). Reason: '%s'. Exhaustion: %s",
        x,
        y,
        reason,
        exhaustion_evidence,
    )

    # 3. Capture screen state before action
    before_cap = capture_screen()
    if not before_cap.ok or before_cap.image is None:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"coords": (x, y), "capture_error": before_cap.error},
            warning=f"Pre-click screen capture failed: {before_cap.error}",
        )

    # 4. Dispatch physical click via SendInput
    click_res = click_coords(x, y, button=button, double=double)
    if not click_res.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"coords": (x, y), "sendinput_error": click_res.error},
            warning=f"SendInput mouse click failed at ({x}, {y}): {click_res.error}",
        )

    # 5. Settle delay
    settle_time = max(0.1, min(3.0, settle_timeout))
    time.sleep(settle_time)
    emergency_stop.check_stop()

    # 6. Capture screen state after action
    after_cap = capture_screen()
    if not after_cap.ok or after_cap.image is None:
        return ActionResult(
            ok=True,
            verified="unknown",
            evidence={"coords": (x, y), "after_capture_error": after_cap.error},
            warning="Click dispatched but post-click screen capture failed for diff verification.",
        )

    # 7. Compute OpenCV Image Difference
    diff = diff_images(before_cap.image, after_cap.image, threshold=diff_threshold)

    evidence: Dict[str, Any] = {
        "action": "click_xy",
        "coords": (x, y),
        "button": button,
        "double": double,
        "reason": reason,
        "exhaustion_evidence": exhaustion_evidence,
        "diff": diff.to_dict(),
        "has_visual_change": diff.has_changed,
        "changed_pixels": diff.changed_pixel_count,
        "changed_percentage": diff.changed_percentage,
        "changed_regions": diff.changed_regions,
    }

    if diff.has_changed:
        return ActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
        )
    else:
        return ActionResult(
            ok=True,
            verified="false",
            evidence=evidence,
            warning=f"Physical click at ({x}, {y}) produced NO observable visual change on screen (0 changed pixels).",
        )
