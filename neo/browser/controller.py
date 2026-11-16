"""
neo/browser/controller.py — Playwright Chromium Controller.

Architectural Guarantees:
1. Exposes the exact same tripartite interface as the Windows layer:
   - snapshot() -> BrowserSnapshot (numbered list of visible, interactive elements)
   - act(payload) -> BrowserActionResult (validated and empirically verified)
   - verify(result) -> Verification status
2. Headed mode by default (headless=False) so user can observe execution; configurable to headless=True.
3. Persistent browser profile support via user_data_dir.
4. Auto-dismissal of cookie banners and popups (reject by default).
5. Tab and window management: tracks multiple pages, detects popups, allows tab switching.
6. Safe download handling: intercepts downloads and places them into settings.allowed_folders.
7. Immediate Handover / Hard Stop at Login, OTP, CAPTCHA, and Payment surfaces.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Union

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Download,
    Page,
    Playwright,
    sync_playwright,
)

from neo.browser.actions import BrowserActionResult, execute_browser_action
from neo.browser.popups import PopupDismissConfig, dismiss_popups
from neo.browser.snapshot import (
    BrowserSnapshot,
    BrowserSnapshotRegistry,
    capture_browser_snapshot,
    get_active_browser_registry,
)
from neo.config import get_settings
from neo.safety.emergency_stop import emergency_stop
from neo.safety.policy import validate_domain, validate_path

logger = logging.getLogger("neo.browser.controller")


class PlaywrightBrowser:
    """
    Main Playwright Chromium controller exposing snapshot(), act(), and verify()
    matching the Windows core & UIA execution architecture.
    """

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: Optional[Union[str, Path]] = None,
        cdp_url: Optional[str] = None,
        popup_config: Optional[PopupDismissConfig] = None,
    ) -> None:
        self.headless = headless
        self.user_data_dir = Path(user_data_dir) if user_data_dir else None
        self.cdp_url = cdp_url
        self.popup_config = popup_config or PopupDismissConfig(mode="reject")

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._active_page: Optional[Page] = None
        self._downloads: List[Dict[str, Any]] = []
        self._registry: BrowserSnapshotRegistry = get_active_browser_registry()

    def start(self) -> PlaywrightBrowser:
        """Launches Chromium context with tab and download listeners."""
        emergency_stop.check_stop()
        if self._pw is not None:
            return self

        self._pw = sync_playwright().start()

        if self.cdp_url:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
            ctxs = self._browser.contexts
            self._context = ctxs[0] if ctxs else self._browser.new_context()
        elif self.user_data_dir:
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"],
                accept_downloads=True,
            )
        else:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
            )

        # Listen for new pages / popups
        self._context.on("page", self._on_new_page)

        pages = self._context.pages
        self._active_page = pages[0] if pages else self._context.new_page()
        self._setup_page_listeners(self._active_page)

        return self

    def _on_new_page(self, new_page: Page) -> None:
        logger.info("New browser page/tab opened: %s", new_page.url)
        self._setup_page_listeners(new_page)
        self._active_page = new_page

    def _setup_page_listeners(self, page: Page) -> None:
        """Hooks download handling."""
        page.on("download", self._handle_download)

    def _handle_download(self, download: Download) -> None:
        """Safely saves downloaded files into allowed_folders."""
        settings = get_settings()
        dest_dir = Path(settings.allowed_folders[0]) if settings.allowed_folders else Path(os.getcwd())
        dest_dir.mkdir(parents=True, exist_ok=True)

        filename = download.suggested_filename
        dest_path = dest_dir / filename

        pv = validate_path(dest_path)
        if not pv.is_allowed:
            logger.warning("Download target '%s' blocked by safety policy: %s", dest_path, pv.rejection_reason)
            download.cancel()
            return

        try:
            download.save_as(str(dest_path))
            self._downloads.append({
                "filename": filename,
                "saved_to": str(dest_path),
                "url": download.url,
            })
            logger.info("Saved browser download to '%s'", dest_path)
        except Exception as e:
            logger.error("Failed saving download '%s': %s", filename, e)

    @property
    def page(self) -> Page:
        """Returns the currently active page, starting browser if necessary."""
        if self._active_page is None or self._active_page.is_closed():
            self.start()
        return self._active_page

    @property
    def pages(self) -> List[Page]:
        """Returns all open pages in the context."""
        return self._context.pages if self._context else []

    def switch_to_tab(self, index: int) -> bool:
        """Switches focus to tab at specified index."""
        pages = self.pages
        if 0 <= index < len(pages):
            self._active_page = pages[index]
            self._active_page.bring_to_front()
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Core Tripartite Interface: snapshot, act, verify
    # ─────────────────────────────────────────────────────────────────────────
    def snapshot(self, auto_dismiss_popups: bool = True) -> BrowserSnapshot:
        """
        Captures numbered list of visible, interactive elements on active page.
        Automatically dismisses cookie banners if auto_dismiss_popups is True.
        """
        emergency_stop.check_stop()
        active = self.page

        if auto_dismiss_popups:
            dismiss_popups(active, self.popup_config)

        return capture_browser_snapshot(active)

    def act(self, payload: Union[Dict[str, Any], Any]) -> BrowserActionResult:
        """
        Executes a whitelisted browser action and verifies the outcome.
        """
        emergency_stop.check_stop()
        active = self.page
        return execute_browser_action(page=active, payload=payload, registry=self._registry)

    def verify(self, result: BrowserActionResult) -> bool:
        """Evaluates whether an action produced verified evidence."""
        return result.ok and (result.verified == "true")

    def close(self) -> None:
        """Clean shutdown of browser and context."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception as e:
            logger.warning("Error during Playwright close: %s", e)
        finally:
            self._active_page = None
            self._context = None
            self._browser = None
            self._pw = None
            self._registry.clear()
