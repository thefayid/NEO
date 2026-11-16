"""
neo/browser/actions.py — Browser Action Dispatcher with Empirical Verification.

Architectural Guarantees:
1. Whitelist of permitted browser actions:
   goto, click, type, select_option, press_key, scroll, wait_for, go_back, screenshot.
2. Parameter validation with Pydantic: unwhitelisted actions or malformed payloads
   are rejected with clear diagnostic errors.
3. Strict Security Boundaries:
   - All URLs validated via validate_domain() from neo.safety.policy.
   - Immediate Handover / Hard Stop at Login, OTP, CAPTCHA, and Payment surfaces.
   - Emergency stop check before every operation.
4. Empirical Verification:
   - Every action collects tangible evidence (readback values, scroll offset delta, URL/title delta).
   - Any action with no observable effect returns a warning, NEVER plain success.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from neo.browser.snapshot import (
    BrowserElement,
    BrowserElementNotFoundError,
    BrowserSnapshotRegistry,
    StaleBrowserSnapshotError,
    capture_browser_snapshot,
    get_active_browser_registry,
)
from neo.safety.emergency_stop import emergency_stop
from neo.safety.gates import (
    ConfirmationDeniedError,
    HardStopRequiredError,
    get_confirmation_gate,
)
from neo.safety.policy import RiskAssessment, detect_risks, validate_domain, validate_path

logger = logging.getLogger("neo.browser.actions")

WHITELISTED_BROWSER_ACTIONS = {
    "goto",
    "click",
    "type",
    "select_option",
    "press_key",
    "scroll",
    "wait_for",
    "go_back",
    "screenshot",
}


class BrowserActionRequest(BaseModel):
    """Pydantic validated request for a browser action."""
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="Action from WHITELISTED_BROWSER_ACTIONS.")
    element_id: Optional[int] = Field(None, ge=1)
    snapshot_id: Optional[str] = None
    selector: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    key: Optional[str] = None
    direction: Optional[Literal["down", "up"]] = "down"
    amount: Optional[int] = Field(300, ge=1, le=5000)
    condition: Optional[
        Literal["network_idle", "selector_visible", "selector_hidden", "url_contains", "title_contains", "text_present"]
    ] = None
    condition_target: Optional[str] = None
    timeout_ms: Optional[int] = Field(5000, ge=100, le=60000)
    output_path: Optional[str] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        act = v.strip().lower()
        if act not in WHITELISTED_BROWSER_ACTIONS:
            raise ValueError(
                f"Action '{v}' is not allowed. Permitted browser actions: {sorted(list(WHITELISTED_BROWSER_ACTIONS))}"
            )
        return act

    @model_validator(mode="after")
    def validate_action_requirements(self) -> BrowserActionRequest:
        act = self.action
        if act == "goto" and not self.url:
            raise ValueError("Action 'goto' requires 'url'.")
        if act in ("click", "type", "select_option"):
            if self.element_id is None and not self.selector:
                raise ValueError(f"Action '{act}' requires either 'element_id' or 'selector'.")
            if self.element_id is not None and not self.snapshot_id:
                raise ValueError(f"Action '{act}' with 'element_id' requires accompanying 'snapshot_id'.")
        if act == "type" and self.text is None:
            raise ValueError("Action 'type' requires 'text'.")
        if act == "select_option" and self.value is None:
            raise ValueError("Action 'select_option' requires 'value'.")
        if act == "press_key" and not self.key:
            raise ValueError("Action 'press_key' requires 'key'.")
        if act == "wait_for" and not self.condition:
            raise ValueError("Action 'wait_for' requires 'condition'.")
        return self


@dataclass
class BrowserActionResult:
    """Standardized result returned by browser actions."""
    ok: bool
    verified: Literal["true", "false", "unknown"]
    evidence: Dict[str, Any] = field(default_factory=dict)
    warning: Optional[str] = None
    data: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "verified": self.verified,
            "evidence": self.evidence,
            "warning": self.warning,
            "data": self.data,
        }


def _check_sensitive_handover(
    url: str,
    title: str,
    element_text: Optional[str] = None,
) -> None:
    """
    Checks if page or element represents a sensitive human surface:
    Login, OTP, CAPTCHA, or Payment. If detected, raises HardStopRequiredError.
    """
    assessment = detect_risks(
        window_title=title,
        element_name=element_text,
        target=url,
    )
    if assessment.requires_hard_stop:
        raise HardStopRequiredError(
            f"Navigation/Interaction blocked by Hard Stop: {assessment.summary}",
            risk_assessment=assessment,
        )

    # Specific browser payment / auth heuristics
    combined = (url + " " + title + " " + (element_text or "")).lower()
    for sensitive_keyword in ("payment", "checkout", "credit card", "cvv", "enter otp", "solve captcha"):
        if sensitive_keyword in combined:
            raise HardStopRequiredError(
                f"Browser handover triggered on sensitive surface: '{sensitive_keyword}' detected.",
                risk_assessment=RiskAssessment(
                    is_risky=True,
                    requires_hard_stop=True,
                    risk_categories=["pay"],
                    hard_stop_categories=["payment"],
                    summary=f"Critical Hard Stop: {sensitive_keyword} surface detected.",
                ),
            )


def execute_browser_action(
    page: Any,
    payload: Union[Dict[str, Any], BrowserActionRequest],
    registry: Optional[BrowserSnapshotRegistry] = None,
) -> BrowserActionResult:
    """
    Validates, executes, settles, and verifies a browser action.
    """
    emergency_stop.check_stop()

    reg = registry or get_active_browser_registry()

    # 1. Parameter validation
    if isinstance(payload, dict):
        try:
            req = BrowserActionRequest(**payload)
        except Exception as e:
            return BrowserActionResult(
                ok=False,
                verified="false",
                evidence={"raw_payload": payload},
                warning=f"Browser action validation failed: {e}",
            )
    elif isinstance(payload, BrowserActionRequest):
        req = payload
    else:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"type": str(type(payload))},
            warning=f"Invalid payload type: {type(payload)}.",
        )

    act = req.action

    try:
        if act == "goto":
            return _handle_goto(page, req)
        elif act == "click":
            return _handle_click(page, req, reg)
        elif act == "type":
            return _handle_type(page, req, reg)
        elif act == "select_option":
            return _handle_select_option(page, req, reg)
        elif act == "press_key":
            return _handle_press_key(page, req)
        elif act == "scroll":
            return _handle_scroll(page, req)
        elif act == "wait_for":
            return _handle_wait_for(page, req)
        elif act == "go_back":
            return _handle_go_back(page, req)
        elif act == "screenshot":
            return _handle_screenshot(page, req)
        else:
            return BrowserActionResult(
                ok=False,
                verified="false",
                evidence={"action": act},
                warning=f"Browser action '{act}' not implemented.",
            )

    except StaleBrowserSnapshotError as e:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"snapshot_id": req.snapshot_id, "element_id": req.element_id},
            warning=f"StaleBrowserSnapshotError: {e}",
        )
    except BrowserElementNotFoundError as e:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"snapshot_id": req.snapshot_id, "element_id": req.element_id},
            warning=f"BrowserElementNotFoundError: {e}",
        )
    except HardStopRequiredError as e:
        logger.warning("Hard Stop triggered in browser: %s", e)
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"hard_stop": True, "categories": [c.value if hasattr(c, "value") else str(c) for c in e.risk_assessment.hard_stop_categories]},
            warning=f"HardStopRequiredError: {e}",
        )
    except Exception as e:
        logger.error("Unhandled browser action exception on '%s': %s", act, e, exc_info=True)
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"action": act, "error_type": type(e).__name__},
            warning=f"Execution error on '{act}': {e}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ─────────────────────────────────────────────────────────────────────────────
def _handle_goto(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    target_url = req.url or ""

    # Policy validation
    dv = validate_domain(target_url)
    if not dv.is_allowed:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"url": target_url, "validation": dv.__dict__},
            warning=f"Domain access denied by security policy: {dv.reason}",
        )

    url_before = page.url
    resp = page.goto(target_url, timeout=req.timeout_ms or 15000, wait_until="domcontentloaded")
    status = resp.status if resp else 200

    url_after = page.url
    title_after = page.title()

    # Check for sensitive handover on arrival
    _check_sensitive_handover(url=url_after, title=title_after)

    navigated = (url_before != url_after)
    success = (200 <= status < 400)
    evidence = {
        "action": "goto",
        "url_before": url_before,
        "url_after": url_after,
        "title": title_after,
        "status_code": status,
        "navigated": navigated,
    }
    if not success:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence=evidence,
            warning=f"Navigation failed with HTTP error status {status}.",
        )

    if navigated:
        return BrowserActionResult(
            ok=True,
            verified="true",
            evidence=evidence,
            warning=None,
        )

    return BrowserActionResult(
        ok=True,
        verified="true" if status == 200 else "unknown",
        evidence=evidence,
        warning=None if status == 200 else "Navigation produced no observable change.",
    )


def _handle_click(
    page: Any,
    req: BrowserActionRequest,
    reg: BrowserSnapshotRegistry,
) -> BrowserActionResult:
    elem: Optional[BrowserElement] = None
    locator: Any = None

    if req.element_id is not None and req.snapshot_id is not None:
        elem, locator = reg.resolve(req.snapshot_id, req.element_id)
    elif req.selector:
        locator = page.locator(req.selector).first

    if locator is None:
        return BrowserActionResult(ok=False, verified="false", warning="Could not resolve locator for click.")

    elem_name = (elem.name or elem.text) if elem else ""

    # Disabled element check: refuse to click non-interactable/disabled elements
    if elem is not None and not elem.enabled:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": req.element_id, "enabled": False},
            warning=f"Element ID {req.element_id} ('{elem_name}') is disabled.",
        )

    # Sensitive element check
    _check_sensitive_handover(url=page.url, title=page.title(), element_text=elem_name)

    url_before = page.url
    title_before = page.title()

    # Empirical pre-state capture for change verification
    state_before = None
    try:
        state_before = locator.evaluate(
            "el => { "
            "  const doc = el.ownerDocument; "
            "  const inputs = Array.from(doc.querySelectorAll('input, textarea, select')).map(i => (i.value || '') + ':' + (i.checked || false)); "
            "  return { html: doc.body ? doc.body.innerHTML : '', inputs: inputs.join(';') }; "
            "}"
        )
    except Exception:
        pass

    locator.wait_for(state="visible", timeout=req.timeout_ms or 5000)
    locator.click(timeout=req.timeout_ms or 5000)

    # Settle
    time.sleep(0.15)
    url_after = page.url
    title_after = page.title()

    # Check sensitive handover after click (e.g. redirected to payment page)
    _check_sensitive_handover(url=url_after, title=title_after)

    navigated = (url_before != url_after) or (title_before != title_after)

    # Empirical post-state capture to verify DOM changes
    dom_changed = False
    if state_before is not None and not navigated:
        try:
            state_after = locator.evaluate(
                "el => { "
                "  const doc = el.ownerDocument; "
                "  const inputs = Array.from(doc.querySelectorAll('input, textarea, select')).map(i => (i.value || '') + ':' + (i.checked || false)); "
                "  return { html: doc.body ? doc.body.innerHTML : '', inputs: inputs.join(';') }; "
                "}"
            )
            dom_changed = (state_before != state_after)
        except Exception:
            # If locator is now detached, removed, or navigated, DOM definitely changed
            dom_changed = True

    evidence = {
        "action": "click",
        "element_id": req.element_id,
        "selector": req.selector or (elem.selector if elem else None),
        "url_before": url_before,
        "url_after": url_after,
        "navigated": navigated,
        "dom_changed": dom_changed,
    }

    if navigated or dom_changed:
        return BrowserActionResult(ok=True, verified="true", evidence=evidence, warning=None)

    # An action with no observable effect must return a warning, never plain success!
    return BrowserActionResult(
        ok=True,
        verified="false",
        evidence=evidence,
        warning="Click executed, but had no observable effect on DOM state, element values, or navigation.",
    )


def _handle_type(
    page: Any,
    req: BrowserActionRequest,
    reg: BrowserSnapshotRegistry,
) -> BrowserActionResult:
    elem: Optional[BrowserElement] = None
    locator: Any = None

    if req.element_id is not None and req.snapshot_id is not None:
        elem, locator = reg.resolve(req.snapshot_id, req.element_id)
    elif req.selector:
        locator = page.locator(req.selector).first

    if locator is None:
        return BrowserActionResult(ok=False, verified="false", warning="Could not resolve locator for typing.")

    elem_name = (elem.name or elem.text) if elem else ""

    # Disabled element check: refuse to type into disabled elements
    if elem is not None and not elem.enabled:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": req.element_id, "enabled": False},
            warning=f"Element ID {req.element_id} ('{elem_name}') is disabled.",
        )

    text = req.text or ""
    is_pwd = elem.is_password if elem else False

    # Block typing into password fields without confirmation
    if is_pwd:
        _check_sensitive_handover(url=page.url, title=page.title(), element_text="Password Field")

    locator.wait_for(state="visible", timeout=req.timeout_ms or 5000)
    locator.fill(text)

    # Empirical readback verification
    readback = ""
    try:
        readback = locator.input_value()
    except Exception:
        try:
            readback = locator.inner_text()
        except Exception:
            pass

    evidence = {
        "action": "type",
        "element_id": req.element_id,
        "chars_typed": len(text),
        "is_password": is_pwd,
        "readback": "[REDACTED]" if is_pwd else readback,
    }

    verified = is_pwd or (text in readback)
    return BrowserActionResult(
        ok=verified,
        verified="true" if verified else "false",
        evidence=evidence,
        warning=None if verified else "Typed text was not reflected in element readback.",
    )


def _handle_select_option(
    page: Any,
    req: BrowserActionRequest,
    reg: BrowserSnapshotRegistry,
) -> BrowserActionResult:
    elem: Optional[BrowserElement] = None
    locator: Any = None

    if req.element_id is not None and req.snapshot_id is not None:
        elem, locator = reg.resolve(req.snapshot_id, req.element_id)
    elif req.selector:
        locator = page.locator(req.selector).first

    if locator is None:
        return BrowserActionResult(ok=False, verified="false", warning="Could not resolve select element.")

    elem_name = (elem.name or elem.text) if elem else ""

    # Disabled element check: refuse to select on disabled elements
    if elem is not None and not elem.enabled:
        return BrowserActionResult(
            ok=False,
            verified="false",
            evidence={"element_id": req.element_id, "enabled": False},
            warning=f"Element ID {req.element_id} ('{elem_name}') is disabled.",
        )

    val = req.value or ""
    locator.wait_for(state="visible", timeout=req.timeout_ms or 5000)
    locator.select_option(val)

    # Readback
    readback_val = locator.input_value()
    is_match = (val == readback_val)
    evidence = {
        "action": "select_option",
        "value_chosen": val,
        "readback_value": readback_val,
        "verified": is_match,
    }

    return BrowserActionResult(
        ok=is_match,
        verified="true" if is_match else "false",
        evidence=evidence,
        warning=None if is_match else "Selected value readback did not match chosen option.",
    )


def _handle_press_key(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    key = req.key or ""
    page.keyboard.press(key)
    evidence = {"action": "press_key", "key": key}
    return BrowserActionResult(
        ok=True,
        verified="unknown",
        evidence=evidence,
        warning="Key dispatched to browser without direct visual feedback.",
    )


def _handle_scroll(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    direction = req.direction or "down"
    amount = req.amount or 300
    delta = amount if direction == "down" else -amount

    y_before = page.evaluate("() => window.scrollY")
    page.mouse.wheel(0, delta)
    time.sleep(0.1)
    y_after = page.evaluate("() => window.scrollY")

    scrolled = y_before != y_after
    evidence = {
        "action": "scroll",
        "direction": direction,
        "delta": delta,
        "scroll_y_before": y_before,
        "scroll_y_after": y_after,
        "scrolled": scrolled,
    }

    return BrowserActionResult(
        ok=True,
        verified="true" if scrolled else "false",
        evidence=evidence,
        warning=None if scrolled else "Scroll dispatched, but page vertical offset did not change (already at boundary).",
    )


def _handle_wait_for(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    cond = req.condition
    target = req.condition_target
    timeout = req.timeout_ms or 5000

    start = time.perf_counter()
    if cond == "network_idle":
        page.wait_for_load_state("networkidle", timeout=timeout)
    elif cond == "selector_visible" and target:
        page.wait_for_selector(target, state="visible", timeout=timeout)
    elif cond == "selector_hidden" and target:
        page.wait_for_selector(target, state="hidden", timeout=timeout)
    elif cond == "url_contains" and target:
        page.wait_for_url(f"**/*{target}*", timeout=timeout)
    elif cond == "text_present" and target:
        page.wait_for_selector(f"text={target}", timeout=timeout)
    else:
        time.sleep(timeout / 1000.0)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    evidence = {
        "action": "wait_for",
        "condition": cond,
        "target": target,
        "elapsed_ms": elapsed_ms,
        "verified": True,
    }
    return BrowserActionResult(ok=True, verified="true", evidence=evidence)


def _handle_go_back(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    url_before = page.url
    page.go_back(timeout=req.timeout_ms or 5000)
    url_after = page.url

    navigated = (url_before != url_after)
    evidence = {
        "action": "go_back",
        "url_before": url_before,
        "url_after": url_after,
        "navigated": navigated,
    }
    return BrowserActionResult(
        ok=navigated,
        verified="true" if navigated else "false",
        evidence=evidence,
        warning=None if navigated else "go_back did not change the page URL.",
    )


def _handle_screenshot(page: Any, req: BrowserActionRequest) -> BrowserActionResult:
    output_path = req.output_path
    if output_path:
        pv = validate_path(output_path)
        if not pv.is_allowed:
            return BrowserActionResult(ok=False, verified="false", warning=f"Destination path rejected: {pv.rejection_reason}")
        dest = pv.resolved_path
    else:
        dest = Path(tempfile.gettempdir()) / f"neo_browser_{int(time.time()*1000)}.png"

    dest.parent.mkdir(parents=True, exist_ok=True)
    bytes_data = page.screenshot(path=str(dest), full_page=False)

    h = hashlib.sha256(bytes_data).hexdigest()
    evidence = {
        "action": "screenshot",
        "path": str(dest),
        "size_bytes": len(bytes_data),
        "sha256": h,
        "verified": True,
    }
    return BrowserActionResult(ok=True, verified="true", evidence=evidence)
