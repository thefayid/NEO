"""
neo/brain/planner.py — Multi-Level Deterministic Action Router.

Architectural Guarantees:
1. Translates an AgentDecision into the appropriate level-specific engine:
   - Level 1: Direct File & Office COM APIs
   - Level 2: Playwright Browser Controller
   - Level 3-4: Windows UIA & Input Action Dispatcher
   - Level 5: Vision Fallback Coordinate Dispatcher
2. Checks EmergencyStop before dispatch.
3. Packages uniform evidence and warnings back to the Brain loop.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from neo.brain.whitelist import AgentDecision
from neo.browser import PlaywrightBrowser
from neo.files_office import (
    ExcelController,
    OutlookController,
    WordController,
    safe_delete_file,
    safe_list_dir,
    safe_read_file,
    safe_search_files,
    safe_write_file,
)
from neo.safety.emergency_stop import emergency_stop
from neo.vision.grounding import denormalize_coords
from neo.windows.actions import execute_action
from neo.windows.uia_snapshot import SnapshotRegistry, get_active_registry

logger = logging.getLogger("neo.brain.planner")


@dataclass
class StepExecutionResult:
    """Standardized result returned by any level-specific engine."""
    ok: bool
    action: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    warning: Optional[str] = None
    error: Optional[str] = None
    data: Any = None


class ActionDispatcher:
    """Routes whitelisted AgentDecisions to the corresponding deterministic module."""

    def __init__(self, browser: Optional[BrowserController] = None) -> None:
        self.browser = browser

    def dispatch(
        self,
        decision: AgentDecision,
        registry: Optional[SnapshotRegistry] = None,
    ) -> StepExecutionResult:
        """Dispatches an AgentDecision to the deterministic engine."""
        emergency_stop.check_stop()

        act = decision.action
        params = decision.parameters

        try:
            # ── Level 1: Direct File Operations ──────────────────────────────
            if act == "file_read":
                res = safe_read_file(
                    path=params["path"],
                    offset_lines=params.get("offset_lines", 0),
                    max_lines=params.get("max_lines"),
                )
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    error=res.error,
                    evidence=res.evidence,
                )

            elif act == "file_write":
                res = safe_write_file(
                    path=params["path"],
                    content=params["content"],
                    mode=params.get("mode", "write"),
                )
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    error=res.error,
                    evidence=res.evidence,
                )

            elif act == "file_list":
                res = safe_list_dir(
                    path=params.get("path", "."),
                    pattern=params.get("pattern", "*"),
                    recursive=params.get("recursive", False),
                )
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    error=res.error,
                    evidence=res.evidence,
                )

            elif act == "file_search":
                res = safe_search_files(
                    base_path=params.get("path", "."),
                    query=params["query"],
                )
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    error=res.error,
                    evidence=res.evidence,
                )

            elif act == "file_delete":
                res = safe_delete_file(path=params["path"])
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    error=res.error,
                    evidence=res.evidence,
                )

            # ── Level 1: Office COM Operations ───────────────────────────────
            elif act == "office_word_read":
                res_word = WordController.read_document(params["path"])
                return StepExecutionResult(
                    ok=res_word.ok,
                    action=act,
                    data=res_word.data,
                    error=res_word.error,
                    evidence=res_word.evidence,
                )

            elif act == "office_excel_read":
                res_xl = ExcelController.read_sheet(
                    path=params["path"],
                    sheet_name=params.get("sheet_name"),
                )
                return StepExecutionResult(
                    ok=res_xl.ok,
                    action=act,
                    data=res_xl.data,
                    error=res_xl.error,
                    evidence=res_xl.evidence,
                )

            elif act == "office_excel_write":
                res_xl_w = ExcelController.write_cells(
                    path=params["path"],
                    cell_updates=params["cells"],
                    sheet_name=params.get("sheet_name"),
                )
                return StepExecutionResult(
                    ok=res_xl_w.ok,
                    action=act,
                    data=res_xl_w.data,
                    error=res_xl_w.error,
                    evidence=res_xl_w.evidence,
                )

            elif act == "office_email_draft":
                res_mail = OutlookController.create_email_draft(
                    to=params["to"],
                    subject=params["subject"],
                    body=params["body"],
                    send_immediately=params.get("send_immediately", False),
                )
                return StepExecutionResult(
                    ok=res_mail.ok,
                    action=act,
                    data=res_mail.data,
                    error=res_mail.error,
                    evidence=res_mail.evidence,
                )

            # ── Level 2: Browser DOM Operations ──────────────────────────────
            elif act.startswith("browser_"):
                if self.browser is None:
                    self.browser = PlaywrightBrowser(headless=False)
                    self.browser.start()

                browser_action = act.replace("browser_", "")
                if browser_action == "navigate":
                    browser_action = "goto"
                elif browser_action == "snapshot":
                    snap = self.browser.snapshot()
                    return StepExecutionResult(
                        ok=True,
                        action=act,
                        data=snap.to_dict(),
                        evidence={"snapshot_id": snap.snapshot_id, "element_count": len(snap.elements)},
                    )

                payload = {"action": browser_action, **params}
                bres = self.browser.act(payload)
                return StepExecutionResult(
                    ok=bres.ok,
                    action=act,
                    data=bres.data,
                    warning=bres.warning,
                    error=bres.warning if not bres.ok else None,
                    evidence=bres.evidence,
                )

            # ── Level 5: Vision Fallback Coordinates ──────────────────────────
            elif act == "click_xy":
                from neo.vision.click_xy import click_xy as vision_click_xy
                x = int(params["x"])
                y = int(params["y"])
                reason = params["reason"]
                exhaustion_evidence = params["exhaustion_evidence"]
                button = params.get("button", "left")
                double = params.get("double", False)
                res = vision_click_xy(
                    x=x,
                    y=y,
                    reason=reason,
                    exhaustion_evidence=exhaustion_evidence,
                    button=button,
                    double=double,
                )
                return StepExecutionResult(
                    ok=res.ok,
                    action=act,
                    data=res.data,
                    warning=res.warning,
                    error=res.warning if not res.ok else None,
                    evidence=res.evidence,
                )

            elif act == "click_coords":
                coords = params["coords"]
                import ctypes
                user32 = ctypes.windll.user32
                sw = user32.GetSystemMetrics(0) or 1920
                sh = user32.GetSystemMetrics(1) or 1080

                if params.get("normalized", False):
                    sp = denormalize_coords(int(coords[0]), int(coords[1]), sw, sh)
                    final_coords = (sp.x, sp.y)
                else:
                    final_coords = (int(coords[0]), int(coords[1]))

                # Coordinate bounds validation
                if final_coords[0] < 0 or final_coords[1] < 0 or final_coords[0] > sw or final_coords[1] > sh:
                    return StepExecutionResult(
                        ok=False,
                        action=act,
                        error=f"Coordinates {final_coords} out of screen bounds ({sw}x{sh}).",
                        evidence={"coords": final_coords, "screen": (sw, sh)},
                    )

                action_payload: Dict[str, Any] = {
                    "action": "click",
                    "coords": final_coords,
                    "button": params.get("button", "left"),
                    "double": params.get("double", False),
                }
                act_res = execute_action(action_payload, registry=registry)
                return StepExecutionResult(
                    ok=act_res.ok,
                    action=act,
                    data=act_res.data,
                    warning=act_res.warning,
                    error=act_res.warning if not act_res.ok else None,
                    evidence={"coords": final_coords, **act_res.evidence},
                )

            elif act == "type_coords":
                coords = params["coords"]
                import ctypes
                user32 = ctypes.windll.user32
                sw = user32.GetSystemMetrics(0) or 1920
                sh = user32.GetSystemMetrics(1) or 1080

                if params.get("normalized", False):
                    sp = denormalize_coords(int(coords[0]), int(coords[1]), sw, sh)
                    final_coords = (sp.x, sp.y)
                else:
                    final_coords = (int(coords[0]), int(coords[1]))

                # Coordinate bounds validation
                if final_coords[0] < 0 or final_coords[1] < 0 or final_coords[0] > sw or final_coords[1] > sh:
                    return StepExecutionResult(
                        ok=False,
                        action=act,
                        error=f"Coordinates {final_coords} out of screen bounds ({sw}x{sh}).",
                        evidence={"coords": final_coords, "screen": (sw, sh)},
                    )

                click_res = execute_action({"action": "click", "coords": final_coords}, registry=registry)
                if not click_res.ok:
                    return StepExecutionResult(
                        ok=False,
                        action=act,
                        error=f"Failed to focus coordinates {final_coords}: {click_res.warning}",
                        evidence={"click_res": click_res.evidence},
                    )

                type_res = execute_action({"action": "type", "text": params["text"]}, registry=registry)
                return StepExecutionResult(
                    ok=type_res.ok,
                    action=act,
                    data=type_res.data,
                    warning=type_res.warning,
                    error=type_res.warning if not type_res.ok else None,
                    evidence={"coords": final_coords, "click": click_res.evidence, "type": type_res.evidence},
                )

            # ── Levels 3 & 4: Windows UIA & Keyboard Shortcuts ────────────────
            else:
                action_payload: Dict[str, Any] = {"action": act, **params}
                # If element_id is specified but snapshot_id was omitted, check if registry has an active snapshot
                if "element_id" in action_payload and "snapshot_id" not in action_payload:
                    active_reg = registry or get_active_registry()
                    if active_reg and active_reg.active_snapshot_id:
                        action_payload["snapshot_id"] = active_reg.active_snapshot_id

                act_res = execute_action(action_payload, registry=registry)
                return StepExecutionResult(
                    ok=act_res.ok,
                    action=act,
                    data=act_res.data,
                    warning=act_res.warning,
                    error=act_res.warning if not act_res.ok else None,
                    evidence=act_res.evidence,
                )

        except Exception as e:
            logger.error("Error dispatching action '%s': %s", act, e, exc_info=True)
            return StepExecutionResult(
                ok=False,
                action=act,
                error=f"Dispatcher error on '{act}': {e}",
                evidence={"exception_type": type(e).__name__},
            )
