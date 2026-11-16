"""
neo/browser/popups.py — Cookie Consent and Modal Popup Dismiss Engine.

Architectural Guarantees:
1. Configurable dismiss routine that defaults to REJECT (preserving privacy and avoiding paid tracking).
2. Fast non-blocking evaluation: checks common cookie banner patterns without hanging pages.
3. Supports custom domain-specific dismiss selectors.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger("neo.browser.popups")

DEFAULT_REJECT_SELECTORS = [
    # Explicit rejection buttons
    'button:has-text("Reject all")',
    'button:has-text("Reject All")',
    'button:has-text("Reject")',
    'button:has-text("Decline all")',
    'button:has-text("Decline")',
    'button:has-text("Only necessary")',
    'button:has-text("Necessary only")',
    'button:has-text("Deny")',
    'button:has-text("Refuse")',
    # Dismiss / close buttons
    'button[aria-label="Close"]',
    'button[aria-label="Dismiss"]',
    'button:has-text("Dismiss")',
    'button:has-text("Close")',
    '.cookie-banner button.reject',
    '#onetrust-reject-all-handler',
    '#cookie-notice .reject',
    '[data-testid="cookie-policy-manage-dialog-reject-button"]',
]

DEFAULT_ACCEPT_SELECTORS = [
    'button:has-text("Accept all")',
    'button:has-text("Accept All")',
    'button:has-text("Accept")',
    'button:has-text("Allow all")',
    'button:has-text("I agree")',
    '#onetrust-accept-btn-handler',
]


@dataclass
class PopupDismissConfig:
    """Configuration for banner and dialog dismissal."""
    mode: Literal["reject", "accept", "ignore"] = "reject"
    timeout_ms: int = 1000
    additional_selectors: List[str] = field(default_factory=list)


def dismiss_popups(page: Any, config: Optional[PopupDismissConfig] = None) -> Dict[str, Any]:
    """
    Attempts to locate and click dismiss/reject buttons for cookie banners or dialogs.
    Returns structured evidence of actions taken.
    """
    cfg = config or PopupDismissConfig()
    if cfg.mode == "ignore":
        return {"dismissed": False, "mode": "ignore"}

    selectors_to_try: List[str] = []
    if cfg.additional_selectors:
        selectors_to_try.extend(cfg.additional_selectors)

    if cfg.mode == "reject":
        selectors_to_try.extend(DEFAULT_REJECT_SELECTORS)
    elif cfg.mode == "accept":
        selectors_to_try.extend(DEFAULT_ACCEPT_SELECTORS)

    start_time = time.perf_counter()
    for sel in selectors_to_try:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=cfg.timeout_ms // 4):
                loc.click(timeout=1000)
                time.sleep(0.1)
                logger.info("Dismissed popup/banner using selector: '%s' (mode: %s)", sel, cfg.mode)
                return {
                    "dismissed": True,
                    "selector_used": sel,
                    "mode": cfg.mode,
                    "duration_ms": (time.perf_counter() - start_time) * 1000.0,
                }
        except Exception:
            continue

    return {
        "dismissed": False,
        "mode": cfg.mode,
        "duration_ms": (time.perf_counter() - start_time) * 1000.0,
    }
