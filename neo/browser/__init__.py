"""
neo.browser — Playwright Chromium Automation Layer.

Exposes the exact same interface as the Windows layer:
- snapshot() -> BrowserSnapshot (numbered list of visible, interactive elements)
- act() -> BrowserActionResult (validated via Pydantic & verified with empirical readbacks)
- verify() -> Verification assessment
"""
from neo.browser.actions import (
    WHITELISTED_BROWSER_ACTIONS,
    BrowserActionRequest,
    BrowserActionResult,
    execute_browser_action,
)
from neo.browser.controller import PlaywrightBrowser

# Backward-compatible alias
BrowserController = PlaywrightBrowser

from neo.browser.popups import PopupDismissConfig, dismiss_popups
from neo.browser.snapshot import (
    BrowserElement,
    BrowserElementNotFoundError,
    BrowserSnapshot,
    BrowserSnapshotError,
    BrowserSnapshotRegistry,
    StaleBrowserSnapshotError,
    capture_browser_snapshot,
    diff_browser_snapshots,
    get_active_browser_registry,
)

__all__ = [
    "PlaywrightBrowser",
    "BrowserController",
    "BrowserSnapshot",
    "BrowserElement",
    "BrowserSnapshotRegistry",
    "get_active_browser_registry",
    "capture_browser_snapshot",
    "diff_browser_snapshots",
    "BrowserActionRequest",
    "BrowserActionResult",
    "execute_browser_action",
    "WHITELISTED_BROWSER_ACTIONS",
    "PopupDismissConfig",
    "dismiss_popups",
    "BrowserSnapshotError",
    "StaleBrowserSnapshotError",
    "BrowserElementNotFoundError",
]
