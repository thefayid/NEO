"""
neo/windows/uia_snapshot.py — Windows UI Automation Snapshot & Element Registry.

Level 3 of the 5-level architecture:
Inspects real named elements, control types, automation IDs, enabled status,
and values using pywinauto with the UIA backend.

Key Capabilities:
- snapshot(window) -> numbered list of visible, relevant elements.
- Size capping, region bounding box filtering, control type filtering.
- Traversal timeout protection to prevent slow/hanging apps from blocking NEO.
- Per-snapshot element registry caching; stale IDs from obsolete snapshots are rejected.
- Strict password redaction: password fields are never read or output.
- "is_sparse" detection flag to trigger Level 5 Vision fallback when UIA tree is bare.
- diff(snapshot_a, snapshot_b) computing appeared, disappeared, and changed elements.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from neo.safety.emergency_stop import emergency_stop
from neo.windows.core import (
    WindowInfo,
    ensure_desktop_attached,
    focus_window,
    list_windows,
)

logger = logging.getLogger("neo.windows.uia_snapshot")

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class StaleSnapshotError(RuntimeError):
    """Raised when attempting to access or interact with an element from an obsolete snapshot."""
    pass


class ElementNotFoundError(LookupError):
    """Raised when an element ID does not exist within the active snapshot."""
    pass


class SnapshotTimeoutError(TimeoutError):
    """Raised when snapshot extraction exceeds the configured timeout."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class UIAElement:
    """Detailed metadata for a single UI Automation element in a snapshot."""
    id: int
    snapshot_id: str
    control_type: str
    name: str
    automation_id: str
    enabled: bool
    value: Optional[str]
    bounding_rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_password: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "enabled": self.enabled,
            "value": self.value,
            "bounding_rect": self.bounding_rect,
            "is_password": self.is_password,
        }


@dataclass
class UIASnapshot:
    """The structured representation of a window's accessibility state."""
    snapshot_id: str
    hwnd: int
    window_title: str
    elements: List[UIAElement]
    is_sparse: bool
    timestamp: float
    total_elements_scanned: int
    duration_ms: float
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "hwnd": self.hwnd,
            "window_title": self.window_title,
            "elements": [e.to_dict() for e in self.elements],
            "element_count": len(self.elements),
            "is_sparse": self.is_sparse,
            "timestamp": self.timestamp,
            "total_elements_scanned": self.total_elements_scanned,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
            "error": self.error,
        }

    def get_element(self, element_id: int) -> Optional[UIAElement]:
        for e in self.elements:
            if e.id == element_id:
                return e
        return None


@dataclass
class UIAElementChange:
    """Represents a delta in state or value between two snapshots for a matched element."""
    element_id_a: int
    element_id_b: int
    control_type: str
    automation_id: str
    name: str
    change_type: str  # "value_changed", "enabled_changed", "name_changed", "rect_changed"
    old_value: Optional[str]
    new_value: Optional[str]
    old_enabled: bool
    new_enabled: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id_a": self.element_id_a,
            "element_id_b": self.element_id_b,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "name": self.name,
            "change_type": self.change_type,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "old_enabled": self.old_enabled,
            "new_enabled": self.new_enabled,
        }


@dataclass
class UIADiff:
    """The delta between two sequential snapshots."""
    snapshot_id_a: str
    snapshot_id_b: str
    appeared: List[UIAElement]
    disappeared: List[UIAElement]
    changed: List[UIAElementChange]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id_a": self.snapshot_id_a,
            "snapshot_id_b": self.snapshot_id_b,
            "appeared": [e.to_dict() for e in self.appeared],
            "disappeared": [e.to_dict() for e in self.disappeared],
            "changed": [c.to_dict() for c in self.changed],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot Registry & Stale-ID Enforcement
# ─────────────────────────────────────────────────────────────────────────────
class SnapshotRegistry:
    """
    Thread-safe registry caching snapshots and element wrappers.
    Enforces that element IDs are valid ONLY for the active snapshot that created them.
    """

    def __init__(self, max_history: int = 10):
        self._lock = threading.Lock()
        self._max_history = max_history
        self._snapshots: Dict[str, UIASnapshot] = {}
        # snapshot_id -> {element_id: (UIAElement, live_wrapper)}
        self._element_cache: Dict[str, Dict[int, Tuple[UIAElement, Any]]] = {}
        self._active_snapshot_id: Optional[str] = None

    def register(self, snapshot: UIASnapshot, wrappers: Dict[int, Any]) -> None:
        """Stores snapshot and associated live pywinauto wrappers as active."""
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot
            cached: Dict[int, Tuple[UIAElement, Any]] = {}
            for elem in snapshot.elements:
                cached[elem.id] = (elem, wrappers.get(elem.id))
            self._element_cache[snapshot.snapshot_id] = cached
            self._active_snapshot_id = snapshot.snapshot_id

            # Trim history to prevent memory leak
            if len(self._snapshots) > self._max_history:
                oldest_id = next(iter(self._snapshots))
                del self._snapshots[oldest_id]
                self._element_cache.pop(oldest_id, None)

    @property
    def active_snapshot_id(self) -> Optional[str]:
        with self._lock:
            return self._active_snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Optional[UIASnapshot]:
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def resolve(self, snapshot_id: str, element_id: int) -> Tuple[UIAElement, Any]:
        """
        Resolves an element by snapshot_id and element_id.
        Rejects stale IDs from obsolete snapshots by raising StaleSnapshotError.
        """
        with self._lock:
            if not self._active_snapshot_id or snapshot_id != self._active_snapshot_id:
                raise StaleSnapshotError(
                    f"Rejected stale element ID {element_id} from snapshot '{snapshot_id}'. "
                    f"Active snapshot is '{self._active_snapshot_id}'."
                )

            snapshot_elems = self._element_cache.get(snapshot_id, {})
            if element_id not in snapshot_elems:
                raise ElementNotFoundError(
                    f"Element ID {element_id} not found in active snapshot '{snapshot_id}'."
                )

            return snapshot_elems[element_id]

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()
            self._element_cache.clear()
            self._active_snapshot_id = None


# Global active registry instance
_global_registry = SnapshotRegistry()


def get_active_registry() -> SnapshotRegistry:
    return _global_registry


# ─────────────────────────────────────────────────────────────────────────────
# Password Detection & Redaction
# ─────────────────────────────────────────────────────────────────────────────
PASSWORD_KEYWORDS: Set[str] = {
    "password", "passcode", "passwd", "pin", "pinbox", "secret", "cvv", "securitycode"
}


def is_password_element(wrapper: Any) -> bool:
    """
    Checks if a UI element is a password field using multiple layers of evidence:
    1. Direct COM IUIAutomationElement.CurrentIsPassword property.
    2. UIA_IsPasswordPropertyId (30019) via GetCurrentPropertyValue.
    3. Explicit wrapper method/property is_password().
    4. Heuristic analysis on automation_id, class_name, and accessible name.
    """
    # 1. Direct COM checks
    try:
        elem_info = getattr(wrapper, "element_info", None)
        if elem_info and hasattr(elem_info, "element"):
            com_elem = elem_info.element
            if hasattr(com_elem, "CurrentIsPassword") and com_elem.CurrentIsPassword:
                return True
            if hasattr(com_elem, "GetCurrentPropertyValue"):
                if com_elem.GetCurrentPropertyValue(30019):  # UIA_IsPasswordPropertyId
                    return True
    except Exception:
        pass

    # 2. Wrapper method/property
    try:
        if hasattr(wrapper, "is_password"):
            prop = getattr(wrapper, "is_password")
            if callable(prop):
                res = prop()
                if res is True or res == 1:
                    return True
            elif prop is True or prop == 1:
                return True
    except Exception:
        pass

    # 3. Attribute heuristics on Edit/Text/Input controls
    try:
        elem_info = getattr(wrapper, "element_info", None)
        if elem_info:
            ctrl_type = str(getattr(elem_info, "control_type", "")).lower()
            if ctrl_type in ("edit", "text", "document", ""):
                auto_id = str(getattr(elem_info, "automation_id", "") or "").lower()
                name = str(getattr(elem_info, "name", "") or "").lower()
                cls_name = str(getattr(elem_info, "class_name", "") or "").lower()

                for kw in PASSWORD_KEYWORDS:
                    if kw in auto_id or kw in name or kw in cls_name:
                        return True
    except Exception:
        pass

    return False


def extract_element_value(wrapper: Any, is_password: bool) -> Optional[str]:
    """
    Extracts the current value of a UI element.
    GUARANTEE: If is_password is True, returns '[REDACTED]' without inspecting the value.
    """
    if is_password:
        return "[REDACTED]"

    val: Optional[str] = None

    # ValuePattern (Edit controls, inputs)
    try:
        if hasattr(wrapper, "iface_value") and wrapper.iface_value:
            v = wrapper.iface_value.CurrentValue
            if v is not None:
                val = str(v)
    except Exception:
        pass

    # RangeValuePattern (Sliders, ProgressBar)
    if val is None:
        try:
            if hasattr(wrapper, "iface_range_value") and wrapper.iface_range_value:
                v = wrapper.iface_range_value.CurrentValue
                if v is not None:
                    val = str(v)
        except Exception:
            pass

    # TogglePattern (CheckBox)
    if val is None:
        try:
            if hasattr(wrapper, "iface_toggle") and wrapper.iface_toggle:
                state = wrapper.iface_toggle.CurrentToggleState
                val = "checked" if state == 1 else ("unchecked" if state == 0 else "indeterminate")
        except Exception:
            pass

    # SelectionItemPattern (RadioButton, Tab, ListItem)
    if val is None:
        try:
            if hasattr(wrapper, "iface_selection_item") and wrapper.iface_selection_item:
                is_sel = wrapper.iface_selection_item.CurrentIsSelected
                val = "selected" if is_sel else "unselected"
        except Exception:
            pass

    return val


# ─────────────────────────────────────────────────────────────────────────────
# Relevance & Region Filtering
# ─────────────────────────────────────────────────────────────────────────────
INTERACTIVE_CONTROL_TYPES: Set[str] = {
    "button", "edit", "menuitem", "checkbox", "radiobutton",
    "combobox", "hyperlink", "tabitem", "listitem", "treeitem",
    "splitbutton", "slider", "scrollbar", "spinner", "document",
}


def is_element_relevant(wrapper: Any) -> bool:
    """
    Determines if an element is relevant to assistive operation.
    Filters out invisible, zero-sized, and off-screen containers.
    """
    try:
        if hasattr(wrapper, "is_visible") and not wrapper.is_visible():
            return False

        rect = wrapper.rectangle()
        if rect.width() <= 0 or rect.height() <= 0:
            return False

        if rect.right <= 0 or rect.bottom <= 0:
            return False

        ctrl_type = str(getattr(wrapper.element_info, "control_type", "")).lower()
        name = (wrapper.window_text() or "").strip()
        auto_id = getattr(wrapper.element_info, "automation_id", "") or ""

        if ctrl_type in INTERACTIVE_CONTROL_TYPES:
            return True

        # Informational controls (Text, TitleBar, etc.)
        if ctrl_type in ("text", "headeritem", "tooltip", "titlebar") and (name or auto_id):
            return True

        # Named containers / groups
        if name or auto_id:
            return True

        return False
    except Exception:
        return False


def is_in_region(rect: Tuple[int, int, int, int], region: Tuple[int, int, int, int]) -> bool:
    """Returns True if the element rectangle intersects the filter region (left, top, right, bottom)."""
    l, t, r, b = rect
    rl, rt, rr, rb = region
    return not (r <= rl or l >= rr or b <= rt or t >= rb)


# ─────────────────────────────────────────────────────────────────────────────
# Core Snapshot Extraction
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_window_wrapper(window: Union[int, WindowInfo, str, Any]) -> Tuple[int, str, Any]:
    """
    Resolves various window input formats into (hwnd, title, pywinauto_window_wrapper).
    """
    from pywinauto import Application

    ensure_desktop_attached()

    hwnd: int = 0
    title: str = ""

    if isinstance(window, int):
        hwnd = window
    elif isinstance(window, WindowInfo):
        hwnd = window.hwnd
        title = window.title
    elif isinstance(window, str):
        # Window title regex
        res_focus = focus_window(window)
        if not res_focus.ok or not res_focus.data:
            raise LookupError(f"Could not find or focus window matching regex '{window}': {res_focus.error}")
        hwnd = res_focus.data.hwnd
        title = res_focus.data.title
    elif hasattr(window, "handle"):
        hwnd = window.handle
        title = getattr(window, "window_text", lambda: "")()
        return hwnd, title, window
    else:
        raise ValueError(f"Unsupported window type: {type(window)}")

    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            raise LookupError(f"Window handle {hex(hwnd)} is not an active desktop window.")
        # Ensure window is restored and visible so Windows populates its accessibility tree
        if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
            user32.BringWindowToTop(hwnd)
            time.sleep(0.15)

    try:
        app = Application(backend="uia").connect(handle=hwnd)
    except Exception:
        time.sleep(0.08)
        app = Application(backend="uia").connect(handle=hwnd)

    win_wrapper = app.window(handle=hwnd)
    if not title:
        try:
            title = win_wrapper.window_text()
        except Exception:
            title = ""

    return hwnd, title, win_wrapper


def _extract_snapshot_worker(
    win_wrapper: Any,
    hwnd: int,
    title: str,
    max_elements: int,
    region: Optional[Tuple[int, int, int, int]],
    control_types: Optional[Sequence[str]],
    timeout_sec: float,
    sparse_threshold: int,
    registry: Optional[SnapshotRegistry],
) -> UIASnapshot:
    """Internal synchronous extraction logic run within a timed executor."""
    start_time = time.monotonic()
    snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    allowed_types_lower = {ct.lower() for ct in control_types} if control_types else None

    elements: List[UIAElement] = []
    wrappers_map: Dict[int, Any] = {}
    truncated = False
    total_scanned = 0

    try:
        descendants = win_wrapper.descendants()
    except Exception as e:
        logger.debug("descendants() failed on hwnd %s: %s", hwnd, e)
        descendants = []

    for item in descendants:
        total_scanned += 1

        # Check emergency stop
        emergency_stop.check_stop()

        # Check traversal timeout
        if (time.monotonic() - start_time) >= timeout_sec:
            truncated = True
            logger.warning("Snapshot extraction exceeded timeout (%.2fs) on hwnd %s; truncating.", timeout_sec, hwnd)
            break

        # Check capacity cap
        if len(elements) >= max_elements:
            truncated = True
            break

        if not is_element_relevant(item):
            continue

        try:
            r = item.rectangle()
            rect = (r.left, r.top, r.right, r.bottom)
        except Exception:
            rect = (0, 0, 0, 0)

        # Region filter
        if region and not is_in_region(rect, region):
            continue

        ctrl_type = str(getattr(item.element_info, "control_type", "") or "Unknown")

        # Control type filter
        if allowed_types_lower and ctrl_type.lower() not in allowed_types_lower:
            continue

        try:
            name = (item.window_text() or "").strip()
        except Exception:
            name = ""

        auto_id = getattr(item.element_info, "automation_id", "") or ""

        try:
            enabled = bool(item.is_enabled())
        except Exception:
            enabled = True

        # Password redaction
        is_pwd = is_password_element(item)
        val = extract_element_value(item, is_pwd)

        elem_id = len(elements) + 1
        elem = UIAElement(
            id=elem_id,
            snapshot_id=snapshot_id,
            control_type=ctrl_type,
            name=name,
            automation_id=auto_id,
            enabled=enabled,
            value=val,
            bounding_rect=rect,
            is_password=is_pwd,
        )

        elements.append(elem)
        wrappers_map[elem_id] = item

    duration_ms = round((time.monotonic() - start_time) * 1000.0, 2)
    is_sparse = len(elements) < sparse_threshold

    snapshot = UIASnapshot(
        snapshot_id=snapshot_id,
        hwnd=hwnd,
        window_title=title,
        elements=elements,
        is_sparse=is_sparse,
        timestamp=time.time(),
        total_elements_scanned=total_scanned,
        duration_ms=duration_ms,
        truncated=truncated,
        error=None,
    )

    reg = registry or _global_registry
    reg.register(snapshot, wrappers_map)

    return snapshot


def snapshot(
    window: Union[int, WindowInfo, str, Any],
    max_elements: int = 200,
    region: Optional[Tuple[int, int, int, int]] = None,
    control_types: Optional[Sequence[str]] = None,
    timeout_sec: float = 3.0,
    sparse_threshold: int = 5,
    registry: Optional[SnapshotRegistry] = None,
) -> UIASnapshot:
    """
    Captures a numbered, filtered, password-redacted UIA snapshot of the target window.

    Args:
        window: HWND (int), WindowInfo, title regex (str), or pywinauto window wrapper.
        max_elements: Maximum number of elements to include in the snapshot.
        region: Optional (left, top, right, bottom) bounding box filter.
        control_types: Optional list of control types to include (e.g. ['Button', 'Edit']).
        timeout_sec: Hard timeout in seconds to prevent slow apps from hanging NEO.
        sparse_threshold: Minimum elements threshold below which is_sparse=True.
        registry: Custom SnapshotRegistry instance (defaults to global registry).

    Returns:
        UIASnapshot containing numbered UIAElement list and metadata.
    """
    emergency_stop.check_stop()

    hwnd, title, win_wrapper = _resolve_window_wrapper(window)

    # Execute extraction in a bounded thread pool to guarantee timeout safety
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _extract_snapshot_worker,
            win_wrapper,
            hwnd,
            title,
            max_elements,
            region,
            control_types,
            timeout_sec,
            sparse_threshold,
            registry,
        )
        try:
            return future.result(timeout=timeout_sec + 1.0)
        except concurrent.futures.TimeoutError:
            logger.error("Snapshot worker deadlocked/timed out after %.2fs on hwnd %s", timeout_sec, hwnd)
            err_snap = UIASnapshot(
                snapshot_id=f"snap_timeout_{uuid.uuid4().hex[:8]}",
                hwnd=hwnd,
                window_title=title,
                elements=[],
                is_sparse=True,
                timestamp=time.time(),
                total_elements_scanned=0,
                duration_ms=round(timeout_sec * 1000, 2),
                truncated=True,
                error=f"TimeoutError: UIA tree extraction timed out after {timeout_sec}s.",
            )
            reg = registry or _global_registry
            reg.register(err_snap, {})
            return err_snap


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot Diffing
# ─────────────────────────────────────────────────────────────────────────────
def _element_signature(elem: UIAElement) -> str:
    """Stable signature for matching elements across snapshots."""
    if elem.automation_id:
        return f"{elem.control_type}:{elem.automation_id}"
    if elem.name:
        return f"{elem.control_type}:name={elem.name}"
    return f"{elem.control_type}:rect={elem.bounding_rect}"


def diff(snapshot_a: UIASnapshot, snapshot_b: UIASnapshot) -> UIADiff:
    """
    Computes semantic differences between two sequential snapshots.
    Returns:
        appeared: Elements in B not found in A.
        disappeared: Elements in A not found in B.
        changed: Elements in both whose value, enabled status, or name changed.
    """
    map_a: Dict[str, UIAElement] = {}
    for ea in snapshot_a.elements:
        map_a[_element_signature(ea)] = ea

    map_b: Dict[str, UIAElement] = {}
    for eb in snapshot_b.elements:
        map_b[_element_signature(eb)] = eb

    appeared: List[UIAElement] = []
    disappeared: List[UIAElement] = []
    changed: List[UIAElementChange] = []

    # Check for appeared and changed
    for sig_b, eb in map_b.items():
        if sig_b not in map_a:
            appeared.append(eb)
        else:
            ea = map_a[sig_b]
            changes: List[str] = []
            if ea.value != eb.value:
                changes.append("value_changed")
            if ea.enabled != eb.enabled:
                changes.append("enabled_changed")
            if ea.name != eb.name:
                changes.append("name_changed")

            if changes:
                changed.append(
                    UIAElementChange(
                        element_id_a=ea.id,
                        element_id_b=eb.id,
                        control_type=eb.control_type,
                        automation_id=eb.automation_id,
                        name=eb.name,
                        change_type=",".join(changes),
                        old_value=ea.value,
                        new_value=eb.value,
                        old_enabled=ea.enabled,
                        new_enabled=eb.enabled,
                    )
                )

    # Check for disappeared
    for sig_a, ea in map_a.items():
        if sig_a not in map_b:
            disappeared.append(ea)

    return UIADiff(
        snapshot_id_a=snapshot_a.snapshot_id,
        snapshot_id_b=snapshot_b.snapshot_id,
        appeared=appeared,
        disappeared=disappeared,
        changed=changed,
    )
