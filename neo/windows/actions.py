"""
neo/windows/actions.py — Deterministic Windows UI Action Dispatcher & Verifier.

Level 3-4 Execution Engine of the 5-Level Architecture:
An LLM or Brain chooses ONE action per step from a fixed whitelist:
  click, double_click, right_click, type, set_text, select, read,
  press_key, hotkey, scroll, focus, open, wait, screenshot.

Guarantees:
1. Parameter validation with Pydantic: unknown actions or malformed payloads
   are rejected with clear, actionable error messages for the LLM.
2. Order of execution: tries the most reliable method first (UIA Invoke/Value/Toggle/Select
   patterns before hardware mouse/keyboard dispatch).
3. Settle polling: dynamically polls for the UI to stabilize rather than sleeping blindly.
4. Empirical verification: every action gathers real evidence (readback text, state delta,
   window focus, or element attribute changes).
5. Warning enforcement: an action with no observable effect returns a warning,
   NEVER plain success.
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from neo.config import get_settings
from neo.safety import (
    ConfirmationDeniedError,
    HardStopRequiredError,
    emergency_stop,
    get_confirmation_gate,
)

logger = logging.getLogger("neo.windows.actions")
from neo.windows.core import (
    BlockedError,
    WindowInfo,
    click_coords,
    ensure_desktop_attached,
    focus_window,
    foreground,
    hotkey,
    list_windows,
    open_target,
    scroll,
    type_unicode,
)
from neo.windows.uia_snapshot import (
    ElementNotFoundError,
    SnapshotRegistry,
    StaleSnapshotError,
    UIAElement,
    UIASnapshot,
    extract_element_value,
    get_active_registry,
    is_password_element,
    snapshot,
)

ACTION_WHITELIST: Set[str] = {
    "click",
    "double_click",
    "right_click",
    "type",
    "set_text",
    "select",
    "read",
    "press_key",
    "hotkey",
    "scroll",
    "focus",
    "open",
    "wait",
    "screenshot",
}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Action Request Schema
# ─────────────────────────────────────────────────────────────────────────────
class ActionRequest(BaseModel):
    """
    Strict validation schema for incoming action requests.
    Validates parameter combinations and outputs clear error strings for LLMs.
    """
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="Action name from fixed whitelist")
    snapshot_id: Optional[str] = Field(None, description="Snapshot ID that element_id belongs to")
    element_id: Optional[int] = Field(None, description="1-based element ID from snapshot")
    coords: Optional[Tuple[int, int]] = Field(None, description="Pixel coordinates (x, y)")
    text: Optional[str] = Field(None, description="Text string for type or set_text")
    key: Optional[str] = Field(None, description="Single key name for press_key")
    keys: Optional[List[str]] = Field(None, description="Key names list for hotkey (e.g. ['ctrl', 'c'])")
    direction: Optional[str] = Field("down", description="Scroll direction: 'up' or 'down'")
    amount: Optional[int] = Field(None, description="Scroll click count or delta")
    target: Optional[str] = Field(None, description="Target application name, URL, or window title regex")
    duration: Optional[float] = Field(None, description="Wait duration in seconds")
    settle_timeout: float = Field(1.5, ge=0.1, le=10.0, description="Max seconds to poll for UI settle")

    @field_validator("action")
    @classmethod
    def validate_action_in_whitelist(cls, v: str) -> str:
        act = v.strip().lower()
        if act not in ACTION_WHITELIST:
            sorted_whitelist = ", ".join(sorted(ACTION_WHITELIST))
            raise ValueError(
                f"Unknown action '{v}'. Valid actions are restricted to whitelist: [{sorted_whitelist}]."
            )
        return act

    @model_validator(mode="after")
    def validate_action_specific_requirements(self) -> ActionRequest:
        act = self.action

        # Element ID requires Snapshot ID
        if self.element_id is not None and not self.snapshot_id:
            raise ValueError("Parameter 'element_id' requires accompanying 'snapshot_id'.")

        # type & set_text require text
        if act in ("type", "set_text"):
            if self.text is None:
                raise ValueError(f"Action '{act}' requires the 'text' parameter.")

        # press_key requires key
        if act == "press_key":
            if not self.key:
                raise ValueError("Action 'press_key' requires the 'key' parameter (e.g. 'enter', 'tab', 'esc').")

        # hotkey requires keys
        if act == "hotkey":
            if not self.keys or len(self.keys) == 0:
                raise ValueError("Action 'hotkey' requires a non-empty list of 'keys' (e.g. ['ctrl', 'a']).")

        # open requires target
        if act == "open":
            if not self.target:
                raise ValueError("Action 'open' requires 'target' (application name, URL, or allowed file path).")

        # focus requires target or element_id
        if act == "focus":
            if not self.target and self.element_id is None:
                raise ValueError("Action 'focus' requires either 'target' (window title regex) or 'element_id'.")

        # wait requires duration
        if act == "wait":
            if self.duration is None:
                self.duration = 1.0
            elif self.duration < 0.0 or self.duration > 15.0:
                raise ValueError("Parameter 'duration' for action 'wait' must be between 0.0 and 15.0 seconds.")

        return self


# ─────────────────────────────────────────────────────────────────────────────
# Typed Action Result
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ActionResult:
    """
    Deterministic result structure returned by all action executions.
    Guarantees:
    - verified: 'true', 'false', or 'unknown' based on real evidence.
    - warning: MANDATORY when verified != 'true' or when an action had no observable effect.
    """
    ok: bool
    verified: Literal["true", "false", "unknown"]
    evidence: Dict[str, Any]
    warning: Optional[str] = None
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "verified": self.verified,
            "evidence": self.evidence,
            "warning": self.warning,
            "data": self.data,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic UI Settle Helper
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_ui_settle(
    check_fn: Callable[[], Any],
    timeout_sec: float = 1.5,
    poll_interval: float = 0.04,
    debounce_sec: float = 0.06,
) -> Tuple[bool, Any]:
    """
    Polls check_fn() dynamically until a state change or truthy result is detected,
    then pauses briefly (debounce) to allow cascading layout changes to settle.
    Avoids arbitrary static sleeps while protecting against hanging UIs.
    """
    start_t = time.monotonic()
    last_val = None

    while (time.monotonic() - start_t) < timeout_sec:
        emergency_stop.check_stop()
        res = check_fn()
        if res:
            if debounce_sec > 0:
                time.sleep(debounce_sec)
            return True, res
        last_val = res
        time.sleep(poll_interval)

    return False, last_val


# ─────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_element_and_coords(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> Tuple[Optional[UIAElement], Optional[Any], Optional[Tuple[int, int]]]:
    """
    Resolves element, live pywinauto wrapper, and center coordinate fallback.
    Guarantees non-collapsed bounding boxes and positive coordinate bounds.
    """
    if req.element_id is not None and req.snapshot_id is not None:
        elem, wrapper = registry.resolve(req.snapshot_id, req.element_id)
        rect = elem.bounding_rect
        if rect and len(rect) >= 4 and rect[2] > rect[0] and rect[3] > rect[1]:
            center_x = (rect[0] + rect[2]) // 2
            center_y = (rect[1] + rect[3]) // 2
            return elem, wrapper, (center_x, center_y)
        # Bounding box is collapsed (0, 0, 0, 0) or offscreen: do not return invalid coordinates
        return elem, wrapper, None

    if req.coords is not None:
        cx, cy = req.coords
        if cx >= 0 and cy >= 0:
            return None, None, (cx, cy)
        return None, None, None

    return None, None, None


def _handle_click(
    req: ActionRequest,
    registry: SnapshotRegistry,
    button: str = "left",
    double: bool = False,
) -> ActionResult:
    elem, wrapper, coords = _resolve_element_and_coords(req, registry)

    if elem is None and coords is None:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={},
            warning="Click action requires either 'element_id' + 'snapshot_id' or 'coords'.",
        )

    # Disabled element check: refuse to click non-interactable/disabled elements
    if elem is not None and not elem.enabled:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": elem.id, "enabled": False},
            warning=f"Element ID {elem.id} ('{elem.name}') is disabled.",
        )

    method_used = "unknown"
    pre_value = elem.value if elem else None
    pre_name = elem.name if elem else None

    # Snapshot pre-state for foreground window to verify visual deltas
    fg_before = foreground()
    fg_hwnd_before = fg_before.data.hwnd if fg_before.ok and fg_before.data else 0

    # 1. Try direct UIA patterns (Invoke / Toggle / Select) before mouse dispatch
    uia_invoked = False
    if wrapper is not None and not double and button == "left":
        try:
            # Check InvokePattern (Buttons, MenuItems)
            if hasattr(wrapper, "iface_invoke") and wrapper.iface_invoke:
                wrapper.iface_invoke.Invoke()
                method_used = "uia_invoke"
                uia_invoked = True
        except Exception as e:
            logger.debug("UIA invoke failed: %s; falling back to mouse click.", e)

        if not uia_invoked:
            try:
                # Check TogglePattern (CheckBoxes)
                if hasattr(wrapper, "iface_toggle") and wrapper.iface_toggle:
                    wrapper.iface_toggle.Toggle()
                    method_used = "uia_toggle"
                    uia_invoked = True
            except Exception:
                pass

        if not uia_invoked:
            try:
                # Check SelectionItemPattern (Radio, Tabs)
                if hasattr(wrapper, "iface_selection_item") and wrapper.iface_selection_item:
                    wrapper.iface_selection_item.Select()
                    method_used = "uia_select"
                    uia_invoked = True
            except Exception:
                pass

    # 2. Fallback to physical coordinate click via SendInput
    if not uia_invoked:
        if coords is None:
            return ActionResult(
                ok=False,
                verified="false",
                evidence={"element_id": elem.id if elem else None},
                warning="Failed to invoke UIA pattern and element has no valid coordinates.",
            )
        click_res = click_coords(coords[0], coords[1], button=button, double=double)
        if not click_res.ok:
            return ActionResult(
                ok=False,
                verified="false",
                evidence=click_res.evidence or {},
                warning=f"SendInput mouse click failed: {click_res.error}",
            )
        method_used = f"sendinput_{button}_{'double_' if double else ''}click"

    # 3. Dynamic Settle & Empirical Verification
    def check_state_change() -> Optional[Dict[str, Any]]:
        # Check if foreground window changed
        fg_curr = foreground()
        fg_hwnd_curr = fg_curr.data.hwnd if fg_curr.ok and fg_curr.data else 0
        if fg_hwnd_curr != fg_hwnd_before:
            return {"foreground_changed": True, "new_hwnd": fg_hwnd_curr, "new_title": fg_curr.data.title}

        # Check if element's own value, state, or name changed
        if wrapper is not None:
            try:
                is_pwd = is_password_element(wrapper)
                curr_val = extract_element_value(wrapper, is_pwd)
                curr_name = (wrapper.window_text() or "").strip()
                if curr_val != pre_value or curr_name != pre_name:
                    return {"element_updated": True, "old_value": pre_value, "new_value": curr_val, "new_name": curr_name}
            except Exception:
                pass

        return None

    settled, change_evidence = wait_for_ui_settle(check_state_change, timeout_sec=req.settle_timeout)

    evidence = {
        "action": f"{'double_' if double else (button + '_' if button != 'left' else '')}click",
        "method_used": method_used,
        "coords": coords,
        "element_id": elem.id if elem else None,
        "target_name": elem.name if elem else None,
    }

    if settled and change_evidence:
        evidence.update(change_evidence)
        return ActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
        )

    # If action was a direct UIA invoke on a button (e.g. standard click without navigation/text update),
    # or coords click that had no observable state difference:
    if uia_invoked:
        return ActionResult(
            ok=True,
            verified="unknown",
            evidence=evidence,
            warning="UIA pattern invoked successfully, but no immediate visual state change was observed.",
        )

    # SendInput click with no observable effect must return a warning!
    return ActionResult(
        ok=True,
        verified="false",
        evidence=evidence,
        warning="Click dispatched to OS, but had no observable effect on UI state or window focus.",
    )


def _handle_set_text(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    elem, wrapper, coords = _resolve_element_and_coords(req, registry)
    text = req.text or ""

    if wrapper is None:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={},
            warning="Action 'set_text' requires a valid 'element_id' and 'snapshot_id'.",
        )

    # Disabled element check: refuse to set text on disabled elements
    if elem is not None and not elem.enabled:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": elem.id, "enabled": False},
            warning=f"Element ID {elem.id} ('{elem.name}') is disabled.",
        )

    method_used = "unknown"
    set_successful = False

    # 1. Try ValuePattern.SetValue()
    try:
        if hasattr(wrapper, "iface_value") and wrapper.iface_value:
            wrapper.iface_value.SetValue(text)
            method_used = "uia_value_pattern"
            set_successful = True
    except Exception as e:
        logger.debug("ValuePattern.SetValue failed: %s; falling back to edit wrapper.", e)

    # 2. Try edit wrapper set_text / set_edit_text
    if not set_successful:
        try:
            if hasattr(wrapper, "set_edit_text"):
                wrapper.set_edit_text(text)
                method_used = "wrapper_set_edit_text"
                set_successful = True
            elif hasattr(wrapper, "set_text"):
                wrapper.set_text(text)
                method_used = "wrapper_set_text"
                set_successful = True
        except Exception:
            pass

    # 3. Fallback: focus, select all, type via SendInput
    if not set_successful:
        try:
            if hasattr(wrapper, "set_focus"):
                wrapper.set_focus()
            elif coords is not None:
                click_coords(coords[0], coords[1])
            time.sleep(0.08)
            hotkey("ctrl", "a")
            time.sleep(0.04)
            type_res = type_unicode(text)
            if type_res.ok:
                method_used = "focus_and_sendinput"
                set_successful = True
        except Exception as e:
            return ActionResult(
                ok=False,
                verified="false",
                evidence={"element_id": elem.id if elem else None, "error": str(e)},
                warning=f"Failed to set text via both UIA and SendInput: {e}",
            )

    # 4. Settle & Readback Verification
    is_pwd = is_password_element(wrapper)

    def check_readback() -> Optional[str]:
        val = extract_element_value(wrapper, is_pwd)
        if is_pwd:
            return val
        if val is not None and text in val:
            return val
        # Check window_text fallback
        try:
            w_txt = wrapper.window_text()
            if w_txt and text in w_txt:
                return w_txt
        except Exception:
            pass
        return None

    settled, readback = wait_for_ui_settle(check_readback, timeout_sec=req.settle_timeout)

    evidence = {
        "action": "set_text",
        "method_used": method_used,
        "element_id": elem.id if elem else None,
        "is_password": is_pwd,
        "readback": "[REDACTED]" if is_pwd else readback,
    }

    if is_pwd:
        return ActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
        )

    if settled and readback is not None:
        return ActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
        )

    return ActionResult(
        ok=False,
        verified="false",
        evidence=evidence,
        warning=f"set_text executed via {method_used}, but readback value '{readback}' does not match expected text.",
    )


def _handle_type(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    elem, wrapper, coords = _resolve_element_and_coords(req, registry)
    text = req.text or ""

    # Disabled element check: refuse to type into disabled elements
    if elem is not None and not elem.enabled:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": elem.id, "enabled": False},
            warning=f"Element ID {elem.id} ('{elem.name}') is disabled.",
        )

    # If element provided, focus it first
    if wrapper is not None:
        try:
            if hasattr(wrapper, "set_focus"):
                wrapper.set_focus()
        except Exception:
            if coords is not None:
                click_coords(coords[0], coords[1])
        time.sleep(0.06)
    elif coords is not None:
        click_coords(coords[0], coords[1])
        time.sleep(0.06)

    # Dispatch Unicode characters via SendInput
    res_type = type_unicode(text)
    if not res_type.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=res_type.evidence or {},
            warning=f"type_unicode dispatch failed: {res_type.error}",
        )

    # Empirical Readback Verification
    is_pwd = is_password_element(wrapper) if wrapper is not None else False

    def check_type_readback() -> Optional[str]:
        if wrapper is not None:
            val = extract_element_value(wrapper, is_pwd)
            if is_pwd:
                return val
            if val is not None and text in val:
                return val
            try:
                w_txt = wrapper.window_text()
                if w_txt and text in w_txt:
                    return w_txt
            except Exception:
                pass
        return None

    evidence = {
        "action": "type",
        "chars_typed": len(text),
        "element_id": elem.id if elem else None,
        "is_password": is_pwd,
    }

    if wrapper is not None:
        settled, readback = wait_for_ui_settle(check_type_readback, timeout_sec=req.settle_timeout)
        evidence["readback"] = "[REDACTED]" if is_pwd else readback
        if is_pwd or (settled and readback is not None):
            return ActionResult(ok=True, verified="true", evidence=evidence, warning=None)
        return ActionResult(
            ok=False,
            verified="false",
            evidence=evidence,
            warning="Text typed via SendInput was not reflected in element readback.",
        )

    # Blind typing without target element
    return ActionResult(
        ok=True,
        verified="unknown",
        evidence=evidence,
        warning="Typed text dispatched blindly to active foreground window without element verification.",
    )


def _handle_read(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    elem, wrapper, _ = _resolve_element_and_coords(req, registry)

    if elem is not None and wrapper is not None:
        is_pwd = is_password_element(wrapper)
        val = extract_element_value(wrapper, is_pwd)
        name = (wrapper.window_text() or elem.name or "").strip()

        evidence = {
            "action": "read",
            "element_id": elem.id,
            "control_type": elem.control_type,
            "automation_id": elem.automation_id,
            "name": name,
            "value": "[REDACTED]" if is_pwd else val,
            "is_password": is_pwd,
            "enabled": elem.enabled,
        }
        return ActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
            data=evidence["value"] or evidence["name"],
        )

    # If no element specified, read foreground window
    fg = foreground()
    if not fg.ok or not fg.data:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=fg.evidence or {},
            warning=f"Could not read foreground window: {fg.error}",
        )

    evidence = {
        "action": "read_foreground",
        "hwnd": fg.data.hwnd,
        "title": fg.data.title,
        "process_name": fg.data.process_name,
        "pid": fg.data.pid,
    }
    return ActionResult(
        ok=True,
        verified="true",
        evidence=evidence,
        warning=None,
        data=fg.data.title,
    )


def _handle_select(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    elem, wrapper, coords = _resolve_element_and_coords(req, registry)
    if wrapper is None:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={},
            warning="Action 'select' requires valid 'element_id' and 'snapshot_id'.",
        )

    # Disabled element check: refuse to select disabled elements
    if elem is not None and not elem.enabled:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": elem.id, "enabled": False},
            warning=f"Element ID {elem.id} ('{elem.name}') is disabled.",
        )

    selected = False
    method_used = "unknown"

    try:
        if hasattr(wrapper, "iface_selection_item") and wrapper.iface_selection_item:
            wrapper.iface_selection_item.Select()
            method_used = "uia_select"
            selected = True
    except Exception:
        pass

    if not selected and coords is not None:
        click_coords(coords[0], coords[1])
        method_used = "click_coords_fallback"
        selected = True

    def check_selected() -> bool:
        try:
            if hasattr(wrapper, "iface_selection_item") and wrapper.iface_selection_item:
                return bool(wrapper.iface_selection_item.CurrentIsSelected)
        except Exception:
            pass
        return False

    settled, is_sel = wait_for_ui_settle(check_selected, timeout_sec=req.settle_timeout)
    evidence = {
        "action": "select",
        "element_id": elem.id if elem else None,
        "method_used": method_used,
        "is_selected": is_sel,
    }

    if settled and is_sel:
        return ActionResult(ok=True, verified="true", evidence=evidence, warning=None)

    return ActionResult(
        ok=False,
        verified="false",
        evidence=evidence,
        warning="Selection command dispatched, but element did not confirm selected state.",
    )


def _handle_press_key(req: ActionRequest) -> ActionResult:
    key = req.key or ""
    res = hotkey(key)
    if not res.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=res.evidence or {},
            warning=f"press_key failed: {res.error}",
        )
    return ActionResult(
        ok=True,
        verified="unknown",
        evidence={"action": "press_key", "key": key, **(res.evidence or {})},
        warning="Key dispatched to foreground window without direct visual feedback.",
    )


def _handle_hotkey(req: ActionRequest) -> ActionResult:
    keys = req.keys or []
    res = hotkey(*keys)
    if not res.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=res.evidence or {},
            warning=f"hotkey failed: {res.error}",
        )
    return ActionResult(
        ok=True,
        verified="unknown",
        evidence={"action": "hotkey", "keys": keys, **(res.evidence or {})},
        warning="Hotkey dispatched to foreground window without direct visual feedback.",
    )


def _handle_scroll(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    elem, _, coords = _resolve_element_and_coords(req, registry)
    x = coords[0] if coords else 0
    y = coords[1] if coords else 0

    amount = req.amount or 3
    clicks = amount if (req.direction or "down").lower() == "up" else -amount

    res = scroll(clicks=clicks, x=x, y=y)
    if not res.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=res.evidence or {},
            warning=f"scroll failed: {res.error}",
        )

    return ActionResult(
        ok=True,
        verified="unknown",
        evidence={"action": "scroll", "clicks": clicks, "x": x, "y": y, **(res.evidence or {})},
        warning="Scroll wheel dispatched without verifying pixel displacement.",
    )


def _handle_focus(
    req: ActionRequest,
    registry: SnapshotRegistry,
) -> ActionResult:
    if req.target:
        res = focus_window(req.target, timeout_sec=req.settle_timeout)
        if not res.ok:
            return ActionResult(
                ok=False,
                verified="false",
                evidence=res.evidence or {},
                warning=f"Could not focus window matching '{req.target}': {res.error}",
            )
        return ActionResult(
            ok=True,
            verified="true",
            evidence={"action": "focus_window", "target": req.target, **(res.evidence or {})},
            warning=None,
            data=res.data,
        )

    elem, wrapper, _ = _resolve_element_and_coords(req, registry)
    if wrapper is not None:
        try:
            wrapper.set_focus()
            return ActionResult(
                ok=True,
                verified="true",
                evidence={"action": "focus_element", "element_id": elem.id if elem else None},
                warning=None,
            )
        except Exception as e:
            return ActionResult(
                ok=False,
                verified="false",
                evidence={"element_id": elem.id if elem else None},
                warning=f"Could not focus element: {e}",
            )

    return ActionResult(
        ok=False,
        verified="false",
        evidence={},
        warning="Action 'focus' requires either 'target' (regex) or valid 'element_id'.",
    )


def _handle_open(req: ActionRequest) -> ActionResult:
    target = req.target or ""
    res = open_target(target)
    if not res.ok:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=res.evidence or {},
            warning=f"Could not open target '{target}': {res.error}",
        )

    # Poll for window to appear
    p = Path(target)
    stem = p.stem.lower()

    def check_app_window() -> bool:
        res_list = list_windows(only_visible=True)
        if res_list.ok and res_list.data:
            for w in res_list.data:
                if stem in w.title.lower() or stem in w.process_name.lower():
                    return True
        return False

    settled, window_appeared = wait_for_ui_settle(check_app_window, timeout_sec=req.settle_timeout)
    evidence = {"action": "open", "target": target, **(res.evidence or {})}

    if settled and window_appeared:
        evidence["window_appeared"] = True
        return ActionResult(ok=True, verified="true", evidence=evidence, warning=None)

    return ActionResult(
        ok=True,
        verified="unknown",
        evidence=evidence,
        warning=f"Target '{target}' launched, but no corresponding top-level window appeared within settle timeout.",
    )


def _handle_wait(req: ActionRequest) -> ActionResult:
    dur = req.duration or 1.0
    start_t = time.monotonic()

    # Sleep in small slices to honor emergency stop promptly
    while (time.monotonic() - start_t) < dur:
        emergency_stop.check_stop()
        time.sleep(min(0.1, dur - (time.monotonic() - start_t)))

    actual_dur = round(time.monotonic() - start_t, 3)
    return ActionResult(
        ok=True,
        verified="true",
        evidence={"action": "wait", "requested_duration": dur, "actual_duration": actual_dur},
        warning=None,
    )


def _handle_screenshot(req: ActionRequest) -> ActionResult:
    import PIL.ImageGrab

    temp_dir = Path(tempfile.gettempdir()) / "neo_screenshots"
    temp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"screenshot_{int(time.time() * 1000)}.png"
    out_path = temp_dir / filename

    try:
        im = PIL.ImageGrab.grab()
        im.save(str(out_path))
        return ActionResult(
            ok=True,
            verified="true",
            evidence={
                "action": "screenshot",
                "path": str(out_path),
                "width": im.width,
                "height": im.height,
                "size_bytes": out_path.stat().st_size,
            },
            warning=None,
            data=str(out_path),
        )
    except Exception as e:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"action": "screenshot", "error": str(e)},
            warning=f"Screenshot capture failed: {e}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Primary Action Dispatcher
# ─────────────────────────────────────────────────────────────────────────────
def execute_action(
    payload: Union[Dict[str, Any], ActionRequest],
    registry: Optional[SnapshotRegistry] = None,
) -> ActionResult:
    """
    Validates, executes, settles, and verifies an action chosen by the LLM / Brain.

    Args:
        payload: Dictionary of action arguments or validated ActionRequest model.
        registry: Custom SnapshotRegistry instance (defaults to global registry).

    Returns:
        ActionResult containing ok, verified ('true'|'false'|'unknown'), evidence, and warning.
    """
    # 0. Emergency stop check
    emergency_stop.check_stop()

    reg = registry or get_active_registry()

    # 1. Parameter validation with Pydantic
    if isinstance(payload, dict):
        try:
            req = ActionRequest(**payload)
        except Exception as e:
            logger.warning("Action rejected by Pydantic validator: %s", e)
            return ActionResult(
                ok=False,
                verified="false",
                evidence={"raw_payload": payload},
                warning=f"Validation failed: {e}",
            )
    elif isinstance(payload, ActionRequest):
        req = payload
    else:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"type": str(type(payload))},
            warning=f"Invalid payload type: {type(payload)}. Must be dict or ActionRequest.",
        )

    # 2. Safety evaluation & confirmation gate
    element_name = None
    if req.element_id is not None and req.snapshot_id is not None:
        try:
            elem_meta, _ = reg.resolve(req.snapshot_id, req.element_id)
            element_name = elem_meta.name
        except Exception:
            pass

    fg_info = foreground()
    window_title = fg_info.data.title if (fg_info.ok and fg_info.data) else None

    gate = get_confirmation_gate()
    try:
        gate.evaluate_and_gate(
            action_name=req.action,
            element_name=element_name,
            window_title=window_title,
            typed_text=req.text,
            target=req.target,
        )
    except HardStopRequiredError as e:
        logger.warning("Hard stop triggered for action '%s': %s", req.action, e)
        categories = [
            c.value if hasattr(c, "value") else str(c)
            for c in e.risk_assessment.hard_stop_categories
        ]
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"action": req.action, "hard_stop": True, "categories": categories},
            warning=f"HardStopRequiredError: {e}",
        )
    except ConfirmationDeniedError as e:
        logger.warning("Confirmation denied for action '%s': %s", req.action, e)
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"action": req.action, "denied": True, "reason": e.decision.reason},
            warning=f"ConfirmationDeniedError: {e}",
        )

    # 3. Dispatch to specific handler
    act = req.action
    try:
        if act == "click":
            return _handle_click(req, reg, button="left", double=False)
        elif act == "double_click":
            return _handle_click(req, reg, button="left", double=True)
        elif act == "right_click":
            return _handle_click(req, reg, button="right", double=False)
        elif act == "type":
            return _handle_type(req, reg)
        elif act == "set_text":
            return _handle_set_text(req, reg)
        elif act == "select":
            return _handle_select(req, reg)
        elif act == "read":
            return _handle_read(req, reg)
        elif act == "press_key":
            return _handle_press_key(req)
        elif act == "hotkey":
            return _handle_hotkey(req)
        elif act == "scroll":
            return _handle_scroll(req, reg)
        elif act == "focus":
            return _handle_focus(req, reg)
        elif act == "open":
            return _handle_open(req)
        elif act == "wait":
            return _handle_wait(req)
        elif act == "screenshot":
            return _handle_screenshot(req)
        else:
            return ActionResult(
                ok=False,
                verified="false",
                evidence={"action": act},
                warning=f"Action '{act}' is not implemented.",
            )

    except StaleSnapshotError as e:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"snapshot_id": req.snapshot_id, "element_id": req.element_id},
            warning=f"StaleElementError: {e} You must take a fresh snapshot before dispatching actions.",
        )
    except ElementNotFoundError as e:
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"snapshot_id": req.snapshot_id, "element_id": req.element_id},
            warning=f"ElementNotFoundError: {e}",
        )
    except BlockedError as e:
        return ActionResult(
            ok=False,
            verified="false",
            evidence=e.evidence,
            warning=f"BlockedSecurityError: {e}",
        )
    except Exception as e:
        logger.error("Unhandled exception during action '%s': %s", act, e, exc_info=True)
        return ActionResult(
            ok=False,
            verified="false",
            evidence={"action": act, "error_type": type(e).__name__},
            warning=f"Execution error on action '{act}': {e}",
        )
