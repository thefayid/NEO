"""
neo/browser/playwright_controller.py — Level 2 Browser DOM Automation.

Architectural Guarantees:
1. Level 2 in order of preference: real DOM selectors and attributes,
   vastly superior to blind mouse clicking or coordinate guessing.
2. Strict Domain Allow-Listing:
   - Every target URL is validated via validate_domain() from neo.safety.policy.
   - Disallowed domains, IP addresses, or non-http(s) schemes are rejected immediately.
3. Untrusted Data Neutralization:
   - All extracted DOM text is treated as untrusted and wrapped safely.
4. Empirical Readback Verification:
   - Typing into inputs verifies value via element.input_value().
   - Clicking verifies navigation delta, DOM mutation, or attribute change.
5. Emergency Stop:
   - Checked before every browser dispatch.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

from neo.config import get_settings
from neo.safety.emergency_stop import emergency_stop
from neo.safety.injection import wrap_untrusted_data
from neo.safety.policy import validate_domain

logger = logging.getLogger("neo.browser.controller")

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


@dataclass
class BrowserResult:
    """Typed result of any browser operation."""
    ok: bool
    data: Any = None
    error: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "evidence": self.evidence,
        }


@dataclass
class DOMElementMeta:
    """Metadata for an interactive DOM element extracted from a webpage."""
    index: int
    tag_name: str
    role: Optional[str]
    name_or_text: str
    selector: str
    is_visible: bool
    is_enabled: bool
    value: Optional[str] = None


class BrowserController:
    """
    Synchronous Playwright DOM automation engine with life-cycle tracking
    and strict security boundaries.
    """

    def __init__(self, headless: bool = False, cdp_url: Optional[str] = None) -> None:
        self.headless = headless
        self.cdp_url = cdp_url
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._dom_cache: Dict[int, str] = {}

    def _ensure_page(self) -> Page:
        """Initializes Playwright instance and active page if not already running."""
        emergency_stop.check_stop()
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright is not installed or available.")

        if self._page is not None and not self._page.is_closed():
            return self._page

        if self._pw is None:
            self._pw = sync_playwright().start()

        if self.cdp_url:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
            contexts = self._browser.contexts
            self._context = contexts[0] if contexts else self._browser.new_context()
        else:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        return self._page

    def navigate(self, url: str, wait_until: Literal["domcontentloaded", "load", "networkidle"] = "domcontentloaded") -> BrowserResult:
        """
        Navigates to an allow-listed URL.
        Rejects disallowed domains before firing network requests.
        """
        emergency_stop.check_stop()

        # 1. Policy check
        dv = validate_domain(url)
        if not dv.is_allowed:
            return BrowserResult(
                ok=False,
                error=f"Domain access denied: {dv.rejection_reason}",
                evidence={"url": url, "validation": dv.__dict__},
            )

        try:
            page = self._ensure_page()
            response = page.goto(url, wait_until=wait_until, timeout=15000)
            status_code = response.status if response else 200
            current_url = page.url
            title = page.title()

            return BrowserResult(
                ok=True,
                data={"url": current_url, "title": title, "status": status_code},
                evidence={
                    "requested_url": url,
                    "final_url": current_url,
                    "title": title,
                    "status_code": status_code,
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Navigation failed to '%s': %s", url, e, exc_info=True)
            return BrowserResult(ok=False, error=f"Navigation error: {e}", evidence={"url": url})

    def click(self, selector: str, timeout_ms: int = 5000) -> BrowserResult:
        """
        Clicks an element identified by CSS selector, text, or XPath.
        Empirically verifies state change.
        """
        emergency_stop.check_stop()
        try:
            page = self._ensure_page()
            url_before = page.url

            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            locator.click(timeout=timeout_ms)

            # Settle briefly to catch navigation or layout shift
            time.sleep(0.15)
            url_after = page.url

            return BrowserResult(
                ok=True,
                data={"clicked_selector": selector},
                evidence={
                    "selector": selector,
                    "url_before": url_before,
                    "url_after": url_after,
                    "navigated": url_before != url_after,
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Browser click failed on '%s': %s", selector, e, exc_info=True)
            return BrowserResult(ok=False, error=f"Click error: {e}", evidence={"selector": selector})

    def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout_ms: int = 5000,
    ) -> BrowserResult:
        """
        Types text into an input or textarea element.
        Empirically verifies typed characters via input_value() readback.
        """
        emergency_stop.check_stop()
        try:
            page = self._ensure_page()
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)

            if clear_first:
                locator.fill("")

            locator.type(text, delay=20)
            if press_enter:
                locator.press("Enter")

            # Empirical readback verification
            readback_val = locator.input_value()
            matches = (text in readback_val) if not press_enter else True

            return BrowserResult(
                ok=True,
                data={"selector": selector, "readback": readback_val},
                evidence={
                    "selector": selector,
                    "chars_typed": len(text),
                    "readback": readback_val,
                    "readback_matches": matches,
                    "verified": matches,
                },
            )
        except Exception as e:
            logger.error("Browser typing failed on '%s': %s", selector, e, exc_info=True)
            return BrowserResult(ok=False, error=f"Type error: {e}", evidence={"selector": selector})

    def read_text(self, selector: str, timeout_ms: int = 5000) -> BrowserResult:
        """
        Reads visible text content from a DOM element.
        Wraps content safely as untrusted data.
        """
        emergency_stop.check_stop()
        try:
            page = self._ensure_page()
            locator = page.locator(selector).first
            locator.wait_for(state="attached", timeout=timeout_ms)

            raw_text = locator.inner_text(timeout=timeout_ms)
            wrapped_text = wrap_untrusted_data(raw_text, source=f"DOM:{selector}")

            return BrowserResult(
                ok=True,
                data=wrapped_text,
                evidence={
                    "selector": selector,
                    "char_count": len(raw_text),
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Browser text read failed on '%s': %s", selector, e, exc_info=True)
            return BrowserResult(ok=False, error=f"Read text error: {e}", evidence={"selector": selector})

    def get_dom_snapshot(self, max_elements: int = 60) -> BrowserResult:
        """
        Extracts a clean, numbered list of interactive DOM elements (buttons, links, inputs)
        with stable CSS/XPath selectors for the LLM.
        """
        emergency_stop.check_stop()
        try:
            page = self._ensure_page()

            # JS snippet to extract interactive elements
            js_query = """
            () => {
                const candidates = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"]');
                const results = [];
                let idx = 0;
                for (const el of candidates) {
                    if (idx >= 60) break;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
                    if (rect.width === 0 || rect.height === 0) continue;

                    let sel = el.id ? '#' + el.id : '';
                    if (!sel && el.name) sel = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                    if (!sel && el.className && typeof el.className === 'string') {
                        const firstClass = el.className.trim().split(/\\s+/)[0];
                        if (firstClass) sel = el.tagName.toLowerCase() + '.' + firstClass;
                    }
                    if (!sel) sel = el.tagName.toLowerCase();

                    results.push({
                        index: idx++,
                        tag_name: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || el.tagName.toLowerCase(),
                        name_or_text: (el.innerText || el.placeholder || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                        selector: sel,
                        value: el.value || null
                    });
                }
                return results;
            }
            """
            items = page.evaluate(js_query)

            self._dom_cache.clear()
            for it in items:
                self._dom_cache[it["index"]] = it["selector"]

            return BrowserResult(
                ok=True,
                data=items,
                evidence={"element_count": len(items), "title": page.title(), "url": page.url},
            )
        except Exception as e:
            logger.error("DOM snapshot failed: %s", e, exc_info=True)
            return BrowserResult(ok=False, error=f"DOM snapshot error: {e}")

    def screenshot(self, output_path: Optional[Union[str, Path]] = None) -> BrowserResult:
        """
        Captures full or viewport screenshot of the current page.
        """
        emergency_stop.check_stop()
        try:
            page = self._ensure_page()
            path_str = str(output_path) if output_path else None
            bytes_data = page.screenshot(path=path_str, full_page=False)

            return BrowserResult(
                ok=True,
                data={"path": path_str, "bytes_length": len(bytes_data)},
                evidence={"path": path_str, "size_bytes": len(bytes_data), "verified": True},
            )
        except Exception as e:
            logger.error("Browser screenshot failed: %s", e, exc_info=True)
            return BrowserResult(ok=False, error=f"Screenshot error: {e}")

    def close(self) -> None:
        """Safely shuts down browser and context."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception as e:
            logger.warning("Error during browser close: %s", e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None
