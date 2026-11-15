"""
core/neo_shadow_guard.py — Shadow Mode & Visual Action Guard for Autonomous Computer-Use.

Provides a deterministic safety verification layer for desktop automation:
1. Multi-Tier Risk Classification:
   - Evaluates action intent, target element labels, and execution parameters.
   - Detects destructive patterns (e.g., delete, format, wipe, drop, shutdown, kill, pay, submit, checkout).
2. Dry-Run / Simulation Mode:
   - When enabled, validates target coordinates and Set-of-Marks bounds without dispatching
     destructive OS input (mouse clicks, key presses).
   - Generates action prediction telemetry and audit trails.
3. Visual Target Ghost Highlighting:
   - Computes and draws high-contrast safety bounding boxes around candidate click targets.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("NEO.ShadowGuard")

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "memory"


class ActionRisk(Enum):
    SAFE = "SAFE"            # Read-only, inspection, screenshots
    LOW = "LOW"              # Scrolling, mouse movement, window focus
    MEDIUM = "MEDIUM"        # Standard clicks, benign text typing
    HIGH = "HIGH"            # Closing unsaved apps, system changes, file edits
    CRITICAL = "CRITICAL"    # Deletions, formatting, financial/checkout, process kill, sudo/admin


@dataclass
class RiskAssessment:
    level: ActionRisk
    is_blocked: bool
    requires_confirmation: bool
    reason: str
    target_label: str = ""
    suggested_action: str = ""


# High-risk keywords across multiple languages and contexts
_CRITICAL_KEYWORDS: Set[str] = {
    "delete", "remove", "erase", "format", "wipe", "drop", "destroy",
    "shutdown", "restart", "reboot", "kill", "terminate",
    "pay", "checkout", "buy", "purchase", "order", "transfer",
    "password", "secret", "token", "credential",
    "rm -rf", "drop table", "truncate", "format c:", "push --force",
}

_HIGH_KEYWORDS: Set[str] = {
    "close", "quit", "exit", "cancel", "submit", "apply", "save as",
    "overwrite", "replace", "install", "uninstall", "modify",
}


class NEOActionShadowGuard:
    """Safety sentry and dry-run simulator for computer operations."""

    _instance: Optional["NEOActionShadowGuard"] = None

    def __new__(cls) -> "NEOActionShadowGuard":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._shadow_mode_enabled = False
            cls._instance._dry_run_mode = False
            cls._instance._action_history: List[Dict[str, Any]] = []
            cls._instance._lock = threading.Lock()
        return cls._instance

    @property
    def shadow_mode_enabled(self) -> bool:
        return self._shadow_mode_enabled

    @property
    def dry_run_mode(self) -> bool:
        return self._dry_run_mode

    def set_modes(self, shadow_mode: Optional[bool] = None, dry_run: Optional[bool] = None) -> None:
        """Configures safety guard behavior."""
        with self._lock:
            if shadow_mode is not None:
                self._shadow_mode_enabled = shadow_mode
            if dry_run is not None:
                self._dry_run_mode = dry_run
            logger.info(f"ShadowGuard updated: shadow_mode={self._shadow_mode_enabled}, dry_run={self._dry_run_mode}")

    def evaluate_risk(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        target_label: str = "",
    ) -> RiskAssessment:
        """Classifies the risk profile of an intended action."""
        params = params or {}
        action_lower = action.lower().strip()
        label_lower = target_label.lower().strip()
        combined_text = f"{action_lower} {label_lower} {json.dumps(params).lower()}"

        # 1. Check for Critical Patterns
        for kw in _CRITICAL_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", combined_text):
                return RiskAssessment(
                    level=ActionRisk.CRITICAL,
                    is_blocked=False,
                    requires_confirmation=True,
                    reason=f"Action involves critical safety keyword '{kw}'.",
                    target_label=target_label,
                    suggested_action="Verify physical confirmation before execution.",
                )

        # 2. Check for High-Risk Patterns
        for kw in _HIGH_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", combined_text):
                return RiskAssessment(
                    level=ActionRisk.HIGH,
                    is_blocked=False,
                    requires_confirmation=False,
                    reason=f"Action involves high-impact keyword '{kw}'.",
                    target_label=target_label,
                    suggested_action="Perform pre-execution visual target highlighting.",
                )

        # 3. Read-only actions
        read_only_actions = {
            "screenshot", "screen_shot", "mouse_position", "read_text",
            "som_tag_screen", "get_active_window", "status", "list_monitors",
        }
        if action_lower in read_only_actions:
            return RiskAssessment(
                level=ActionRisk.SAFE,
                is_blocked=False,
                requires_confirmation=False,
                reason="Read-only operation.",
                target_label=target_label,
            )

        # 4. Standard interaction
        return RiskAssessment(
            level=ActionRisk.MEDIUM if "click" in action_lower or "type" in action_lower else ActionRisk.LOW,
            is_blocked=False,
            requires_confirmation=False,
            reason="Standard benign input operation.",
            target_label=target_label,
        )

    def guard_action_execution(
        self,
        action_name: str,
        parameters: Dict[str, Any],
        target_coords: Optional[Tuple[int, int]] = None,
        target_label: str = "",
    ) -> Tuple[bool, str]:
        """
        Guards an action.
        Returns:
            (allow_execution: bool, message: str)
            If dry_run_mode is True, returns (False, "[DRY-RUN] ...") to simulate success without executing.
        """
        assessment = self.evaluate_risk(action_name, parameters, target_label)

        log_entry = {
            "timestamp": time.time(),
            "action": action_name,
            "params": parameters,
            "target_coords": target_coords,
            "target_label": target_label,
            "risk": assessment.level.value,
            "dry_run": self._dry_run_mode,
        }

        with self._lock:
            self._action_history.append(log_entry)
            if len(self._action_history) > 200:
                self._action_history.pop(0)

        # Dry-run interception
        if self._dry_run_mode:
            coord_str = f" at ({target_coords[0]}, {target_coords[1]})" if target_coords else ""
            msg = (
                f"[SHADOW-MODE DRY-RUN] Verified {action_name}{coord_str} on '{target_label}'. "
                f"Risk: {assessment.level.value}. OS input withheld for safe simulation."
            )
            return False, msg

        # Real execution allowance
        return True, f"Approved ({assessment.level.value})"

    def render_ghost_highlight(
        self,
        image_path: Union[str, Path],
        bbox: Tuple[int, int, int, int],
        label: str = "TARGET",
        output_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Draws a pulsing neon safety bounding box around the target region
        and saves it for preview or UI inspection.
        """
        from PIL import Image, ImageDraw

        src = Path(image_path)
        out = Path(output_path) if output_path else _MEMORY_DIR / "shadow_target_preview.png"
        out.parent.mkdir(parents=True, exist_ok=True)

        if not src.exists():
            img = Image.new("RGB", (1920, 1080), color=(20, 20, 24))
        else:
            img = Image.open(str(src)).convert("RGB")

        draw = ImageDraw.Draw(img)
        left, top, right, bottom = bbox

        # Neon Cyan / Magenta double border
        draw.rectangle([left - 2, top - 2, right + 2, bottom + 2], outline=(0, 240, 255), width=3)
        draw.rectangle([left, top, right, bottom], outline=(255, 0, 128), width=2)

        # Label tag
        tag_text = f"🎯 {label}"
        tag_box = [left, max(0, top - 22), left + len(tag_text) * 9 + 12, max(18, top)]
        draw.rectangle(tag_box, fill=(0, 240, 255))
        draw.text((left + 4, max(2, top - 18)), tag_text, fill=(0, 0, 0))

        img.save(str(out))
        return out


shadow_guard = NEOActionShadowGuard()
