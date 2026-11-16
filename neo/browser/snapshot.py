"""
neo/browser/snapshot.py — Browser DOM Snapshot Engine and Stale-ID Registry.

Architectural Guarantees:
1. Mirrors neo.windows.uia_snapshot: numbered list of visible, interactive elements.
2. Element IDs are scoped strictly to the snapshot that generated them. Actions
   referencing obsolete snapshot IDs are rejected with StaleBrowserSnapshotError.
3. Password fields (input[type="password"]) are strictly redacted as [REDACTED].
4. Traverses active page and visible iframes.
5. Flags sensitive surfaces (login, OTP, CAPTCHA, payment) to trigger Hard Stops.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("neo.browser.snapshot")


class BrowserSnapshotError(Exception):
    """Base exception for browser snapshot errors."""
    pass


class StaleBrowserSnapshotError(BrowserSnapshotError):
    """Raised when an action references a snapshot ID that is no longer active."""
    pass


class BrowserElementNotFoundError(BrowserSnapshotError):
    """Raised when an element ID cannot be resolved within the active snapshot."""
    pass


@dataclass
class BrowserElement:
    """Represents a single interactive DOM element captured in a snapshot."""
    id: int
    snapshot_id: str
    tag_name: str
    role: str
    name: str
    text: str
    value: Optional[str]
    enabled: bool
    in_viewport: bool
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    frame_url: Optional[str] = None
    selector: str = ""
    is_password: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "tag_name": self.tag_name,
            "role": self.role,
            "name": self.name,
            "text": self.text,
            "value": "[REDACTED]" if self.is_password else self.value,
            "enabled": self.enabled,
            "in_viewport": self.in_viewport,
            "bounding_box": self.bounding_box,
            "frame_url": self.frame_url,
            "selector": self.selector,
            "is_password": self.is_password,
        }


@dataclass
class BrowserSnapshot:
    """A point-in-time capture of all interactive elements in the browser."""
    snapshot_id: str
    url: str
    title: str
    elements: List[BrowserElement]
    timestamp: float
    duration_ms: float
    total_elements_scanned: int
    has_cookie_banner: bool = False
    requires_hard_stop: bool = False
    hard_stop_reason: Optional[str] = None

    def get_element_by_id(self, elem_id: int) -> Optional[BrowserElement]:
        for el in self.elements:
            if el.id == elem_id:
                return el
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "url": self.url,
            "title": self.title,
            "element_count": len(self.elements),
            "elements": [el.to_dict() for el in self.elements],
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "has_cookie_banner": self.has_cookie_banner,
            "requires_hard_stop": self.requires_hard_stop,
            "hard_stop_reason": self.hard_stop_reason,
        }


class BrowserSnapshotRegistry:
    """
    Manages active snapshot lifecycle and caches element locators.
    Guarantees that element IDs are valid ONLY for the snapshot that created them.
    """

    def __init__(self) -> None:
        self._active_snapshot: Optional[BrowserSnapshot] = None
        self._locators: Dict[int, Any] = {}

    @property
    def active_snapshot_id(self) -> Optional[str]:
        return self._active_snapshot.snapshot_id if self._active_snapshot else None

    @property
    def active_snapshot(self) -> Optional[BrowserSnapshot]:
        return self._active_snapshot

    def register(self, snapshot: BrowserSnapshot, locators: Dict[int, Any]) -> None:
        """Registers a fresh snapshot and invalidates all prior IDs."""
        self._active_snapshot = snapshot
        self._locators = locators

    def resolve(self, snapshot_id: str, element_id: int) -> Tuple[BrowserElement, Any]:
        """
        Resolves an element ID within the specified snapshot.
        Raises StaleBrowserSnapshotError if the snapshot_id is obsolete.
        Raises BrowserElementNotFoundError if element_id is missing.
        """
        if not self._active_snapshot or self._active_snapshot.snapshot_id != snapshot_id:
            curr_id = self._active_snapshot.snapshot_id if self._active_snapshot else "None"
            raise StaleBrowserSnapshotError(
                f"Snapshot ID '{snapshot_id}' is stale. The active snapshot ID is '{curr_id}'. "
                "You must take a fresh snapshot before dispatching actions."
            )

        elem = self._active_snapshot.get_element_by_id(element_id)
        if not elem:
            raise BrowserElementNotFoundError(
                f"Element ID {element_id} not found in active snapshot '{snapshot_id}'."
            )

        locator = self._locators.get(element_id)
        return elem, locator

    def clear(self) -> None:
        self._active_snapshot = None
        self._locators.clear()


# Global active registry instance
_GLOBAL_BROWSER_REGISTRY = BrowserSnapshotRegistry()


def get_active_browser_registry() -> BrowserSnapshotRegistry:
    return _GLOBAL_BROWSER_REGISTRY


# ─────────────────────────────────────────────────────────────────────────────
# DOM Element Extraction JS Snippet
# ─────────────────────────────────────────────────────────────────────────────
EXTRACT_INTERACTIVE_DOM_JS = """
() => {
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const isInViewport = (rect) => {
        return (
            rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
            rect.bottom > 0 &&
            rect.left < (window.innerWidth || document.documentElement.clientWidth) &&
            rect.right > 0
        );
    };

    const getAccessibleName = (el) => {
        return (
            el.getAttribute('aria-label') ||
            el.getAttribute('aria-labelledby') ||
            el.getAttribute('alt') ||
            el.getAttribute('title') ||
            (el.labels && el.labels[0] ? el.labels[0].innerText : '') ||
            el.placeholder ||
            ''
        ).trim();
    };

    const query = 'button, a[href], input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="combobox"], [role="menuitem"], [role="tab"]';
    const elements = Array.from(document.querySelectorAll(query));

    return elements.map((el, i) => {
        const visible = isVisible(el);
        const rect = el.getBoundingClientRect();
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'button' ? 'button' : tag === 'input' ? (el.type || 'text') : tag);
        const isPwd = (tag === 'input' && (el.type || '').toLowerCase() === 'password');

        // Text & accessible name
        const accName = getAccessibleName(el);
        const innerTxt = (el.innerText || el.textContent || '').trim().slice(0, 150);

        // Value
        let val = null;
        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            val = isPwd ? '[REDACTED]' : (el.value || '');
        }

        // Generate robust selector
        let sel = '';
        if (el.id) {
            sel = '#' + CSS.escape(el.id);
        } else if (el.name) {
            sel = `${tag}[name="${CSS.escape(el.name)}"]`;
        } else if (el.getAttribute('data-testid')) {
            sel = `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
        } else {
            // Path selector with nth-of-type
            let path = [];
            let curr = el;
            while (curr && curr.nodeType === Node.ELEMENT_NODE && curr.tagName.toLowerCase() !== 'body') {
                let tagN = curr.tagName.toLowerCase();
                let parent = curr.parentNode;
                if (parent) {
                    let siblings = Array.from(parent.children).filter(c => c.tagName.toLowerCase() === tagN);
                    if (siblings.length > 1) {
                        let idx = siblings.indexOf(curr) + 1;
                        tagN += `:nth-of-type(${idx})`;
                    }
                }
                path.unshift(tagN);
                curr = parent;
            }
            sel = path.join(' > ');
        }

        return {
            tag_name: tag,
            role: role,
            name: accName,
            text: innerTxt,
            value: val,
            enabled: !el.disabled,
            visible: visible,
            in_viewport: visible && isInViewport(rect),
            bounding_box: [rect.left, rect.top, rect.right, rect.bottom],
            selector: sel,
            is_password: isPwd
        };
    });
}
"""


def capture_browser_snapshot(page: Any, max_elements: int = 150) -> BrowserSnapshot:
    """
    Executes DOM inspection across active page and attached frames.
    Redacts password fields and creates numbered, stable element entities.
    """
    start_time = time.perf_counter()
    snap_id = f"bsnap_{uuid.uuid4().hex[:10]}"

    url = page.url
    title = page.title()

    raw_items: List[Dict[str, Any]] = []
    try:
        raw_items = page.evaluate(EXTRACT_INTERACTIVE_DOM_JS)
    except Exception as e:
        logger.warning("DOM evaluation failed on main page: %s", e)

    elements: List[BrowserElement] = []
    locators: Dict[int, Any] = {}
    elem_id = 1

    # Main page items
    for item in raw_items:
        if not item.get("visible", False):
            continue
        if len(elements) >= max_elements:
            break

        sel = item.get("selector", "")
        loc = page.locator(sel).first if sel else None

        be = BrowserElement(
            id=elem_id,
            snapshot_id=snap_id,
            tag_name=item.get("tag_name", ""),
            role=item.get("role", ""),
            name=item.get("name", ""),
            text=item.get("text", ""),
            value=item.get("value"),
            enabled=item.get("enabled", True),
            in_viewport=item.get("in_viewport", False),
            bounding_box=tuple(item.get("bounding_box", [0, 0, 0, 0])),
            frame_url=None,
            selector=sel,
            is_password=item.get("is_password", False),
        )
        elements.append(be)
        locators[elem_id] = loc
        elem_id += 1

    # Iframe traversal
    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if len(elements) >= max_elements:
                break
            try:
                frame.wait_for_load_state("domcontentloaded", timeout=1000)
            except Exception:
                pass
            try:
                frame_items = frame.evaluate(EXTRACT_INTERACTIVE_DOM_JS)
                for item in frame_items:
                    if not item.get("visible", False):
                        continue
                    if len(elements) >= max_elements:
                        break

                    sel = item.get("selector", "")
                    loc = frame.locator(sel).first if sel else None

                    be = BrowserElement(
                        id=elem_id,
                        snapshot_id=snap_id,
                        tag_name=item.get("tag_name", ""),
                        role=item.get("role", ""),
                        name=item.get("name", ""),
                        text=item.get("text", ""),
                        value=item.get("value"),
                        enabled=item.get("enabled", True),
                        in_viewport=item.get("in_viewport", False),
                        bounding_box=tuple(item.get("bounding_box", [0, 0, 0, 0])),
                        frame_url=frame.url,
                        selector=sel,
                        is_password=item.get("is_password", False),
                    )
                    elements.append(be)
                    locators[elem_id] = loc
                    elem_id += 1
            except Exception as fe:
                logger.debug("Could not inspect iframe '%s': %s", frame.url, fe)
    except Exception as e:
        logger.warning("Iframe traversal exception: %s", e)

    # Detect cookie banner presence
    cookie_terms = {"cookie", "consent", "gdpr", "privacy preference"}
    has_cookie = any(
        any(term in (el.name.lower() + " " + el.text.lower()) for term in cookie_terms)
        for el in elements
    )

    # Detect sensitive hard-stop surfaces: Login, OTP, CAPTCHA, Payment
    requires_hard_stop = False
    hard_stop_reason = None

    url_lower = url.lower()
    title_lower = title.lower()

    if any(k in url_lower or k in title_lower for k in ("login", "signin", "auth", "password", "otp", "2fa", "captcha", "checkout", "payment")):
        requires_hard_stop = True
        hard_stop_reason = f"Sensitive page URL/Title detected: '{title}' ({url})"
    else:
        # Check elements for explicit payment or OTP indicators
        for el in elements:
            combined = (el.name + " " + el.text + " " + el.role).lower()
            if any(k in combined for k in ("pay now", "credit card", "card number", "cvv", "enter otp", "one time password", "solve captcha")):
                requires_hard_stop = True
                hard_stop_reason = f"Sensitive element detected: [{el.id}] {el.role} '{el.name or el.text}'"
                break

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    snapshot = BrowserSnapshot(
        snapshot_id=snap_id,
        url=url,
        title=title,
        elements=elements,
        timestamp=time.time(),
        duration_ms=duration_ms,
        total_elements_scanned=len(elements),
        has_cookie_banner=has_cookie,
        requires_hard_stop=requires_hard_stop,
        hard_stop_reason=hard_stop_reason,
    )

    # Register into active registry
    get_active_browser_registry().register(snapshot, locators)
    return snapshot


def diff_browser_snapshots(snap_a: BrowserSnapshot, snap_b: BrowserSnapshot) -> Dict[str, Any]:
    """Computes difference between two snapshots."""
    a_keys = {(el.role, el.name, el.text): el for el in snap_a.elements}
    b_keys = {(el.role, el.name, el.text): el for el in snap_b.elements}

    appeared = [el.to_dict() for k, el in b_keys.items() if k not in a_keys]
    disappeared = [el.to_dict() for k, el in a_keys.items() if k not in b_keys]

    changed: List[Dict[str, Any]] = []
    for k, b_elem in b_keys.items():
        if k in a_keys:
            a_elem = a_keys[k]
            if a_elem.value != b_elem.value:
                changed.append({
                    "id": b_elem.id,
                    "name": b_elem.name,
                    "old_value": a_elem.value,
                    "new_value": b_elem.value,
                })

    return {
        "url_changed": snap_a.url != snap_b.url,
        "title_changed": snap_a.title != snap_b.title,
        "appeared": appeared,
        "disappeared": disappeared,
        "changed": changed,
        "is_different": bool(appeared or disappeared or changed or snap_a.url != snap_b.url or snap_a.title != snap_b.title),
    }
