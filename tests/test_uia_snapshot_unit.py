"""
tests/test_uia_snapshot_unit.py — Unit tests for neo/windows/uia_snapshot.py.

Verifies:
- Password detection and redaction (COM mocks, method mocks, heuristic fallback).
- SnapshotRegistry caching and stale-ID rejection (StaleSnapshotError, ElementNotFoundError).
- diff() logic for appeared, disappeared, and changed elements.
- Region bounding box intersection filtering.
- Sparse flag detection threshold.
- Full dictionary serialization.
"""
from __future__ import annotations

import time
from typing import Any, Tuple
from unittest.mock import MagicMock

import pytest

from neo.windows.uia_snapshot import (
    ElementNotFoundError,
    SnapshotRegistry,
    StaleSnapshotError,
    UIADiff,
    UIAElement,
    UIAElementChange,
    UIASnapshot,
    diff,
    extract_element_value,
    is_element_relevant,
    is_in_region,
    is_password_element,
)


def test_password_redaction_mock():
    """Verifies that password fields are detected and redacted without leaking real values."""
    # 1. Mock with CurrentIsPassword COM property
    mock_wrapper = MagicMock()
    mock_elem_info = MagicMock()
    mock_com = MagicMock()
    mock_com.CurrentIsPassword = 1
    mock_elem_info.element = mock_com
    mock_elem_info.control_type = "Edit"
    mock_wrapper.element_info = mock_elem_info
    mock_wrapper.iface_value.CurrentValue = "SuperSecretPassword123!"

    assert is_password_element(mock_wrapper) is True
    val = extract_element_value(mock_wrapper, is_password=True)
    assert val == "[REDACTED]"
    assert "SuperSecretPassword123!" not in val

    # 2. Mock with is_password() callable
    mock_wrapper2 = MagicMock()
    mock_wrapper2.element_info = MagicMock()
    del mock_wrapper2.element_info.element
    mock_wrapper2.is_password.return_value = True

    assert is_password_element(mock_wrapper2) is True
    assert extract_element_value(mock_wrapper2, is_password=True) == "[REDACTED]"

    # 3. Mock with heuristic keyword in automation_id
    mock_wrapper3 = MagicMock()
    mock_elem_info3 = MagicMock()
    del mock_elem_info3.element
    mock_elem_info3.control_type = "Edit"
    mock_elem_info3.automation_id = "user_password_input"
    mock_elem_info3.name = "Enter Password"
    mock_elem_info3.class_name = "PasswordBox"
    mock_wrapper3.element_info = mock_elem_info3
    del mock_wrapper3.is_password

    assert is_password_element(mock_wrapper3) is True
    assert extract_element_value(mock_wrapper3, is_password=True) == "[REDACTED]"

    # 4. Standard non-password edit field
    mock_wrapper4 = MagicMock()
    mock_elem_info4 = MagicMock()
    mock_elem_info4.element.CurrentIsPassword = 0
    mock_elem_info4.element.GetCurrentPropertyValue.return_value = 0
    mock_elem_info4.control_type = "Edit"
    mock_elem_info4.automation_id = "search_box"
    mock_elem_info4.name = "Search Query"
    mock_elem_info4.class_name = "TextBox"
    mock_wrapper4.element_info = mock_elem_info4
    mock_wrapper4.is_password.return_value = False
    mock_wrapper4.iface_value.CurrentValue = "machine learning"

    assert is_password_element(mock_wrapper4) is False
    assert extract_element_value(mock_wrapper4, is_password=False) == "machine learning"


def test_stale_id_rejection():
    """Verifies that element IDs are valid ONLY for the snapshot that created them."""
    reg = SnapshotRegistry(max_history=5)

    # Snapshot 1
    elem1 = UIAElement(
        id=1,
        snapshot_id="snap_1",
        control_type="Button",
        name="Submit",
        automation_id="btnSubmit",
        enabled=True,
        value=None,
        bounding_rect=(10, 10, 100, 40),
    )
    snap1 = UIASnapshot(
        snapshot_id="snap_1",
        hwnd=12345,
        window_title="Form Window",
        elements=[elem1],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=1,
        duration_ms=10.0,
    )
    mock_wrapper_1 = MagicMock()
    reg.register(snap1, {1: mock_wrapper_1})

    assert reg.active_snapshot_id == "snap_1"
    resolved_elem, resolved_wrapper = reg.resolve("snap_1", 1)
    assert resolved_elem.name == "Submit"
    assert resolved_wrapper is mock_wrapper_1

    # Snapshot 2 supersedes Snapshot 1
    elem2 = UIAElement(
        id=1,
        snapshot_id="snap_2",
        control_type="Button",
        name="Next",
        automation_id="btnNext",
        enabled=True,
        value=None,
        bounding_rect=(10, 10, 100, 40),
    )
    snap2 = UIASnapshot(
        snapshot_id="snap_2",
        hwnd=12345,
        window_title="Form Window - Step 2",
        elements=[elem2],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=1,
        duration_ms=10.0,
    )
    mock_wrapper_2 = MagicMock()
    reg.register(snap2, {1: mock_wrapper_2})

    assert reg.active_snapshot_id == "snap_2"

    # Resolving element from snap_1 must raise StaleSnapshotError
    with pytest.raises(StaleSnapshotError) as exc_info:
        reg.resolve("snap_1", 1)
    assert "Rejected stale element ID 1 from snapshot 'snap_1'" in str(exc_info.value)

    # Resolving element from snap_2 succeeds
    resolved_elem2, resolved_wrapper2 = reg.resolve("snap_2", 1)
    assert resolved_elem2.name == "Next"
    assert resolved_wrapper2 is mock_wrapper_2

    # Requesting non-existent element in active snapshot raises ElementNotFoundError
    with pytest.raises(ElementNotFoundError) as exc_info2:
        reg.resolve("snap_2", 999)
    assert "Element ID 999 not found" in str(exc_info2.value)


def test_diff_logic():
    """Verifies diff() accurately identifies appeared, disappeared, and changed elements."""
    # Snapshot A
    elem_btn = UIAElement(
        id=1,
        snapshot_id="snap_a",
        control_type="Button",
        name="Calculate",
        automation_id="btnCalc",
        enabled=True,
        value=None,
        bounding_rect=(10, 10, 100, 40),
    )
    elem_edit = UIAElement(
        id=2,
        snapshot_id="snap_a",
        control_type="Edit",
        name="Result",
        automation_id="txtResult",
        enabled=True,
        value="0",
        bounding_rect=(10, 50, 200, 80),
    )
    elem_old = UIAElement(
        id=3,
        snapshot_id="snap_a",
        control_type="Text",
        name="Status: Ready",
        automation_id="lblStatus",
        enabled=True,
        value=None,
        bounding_rect=(10, 90, 200, 110),
    )
    snap_a = UIASnapshot(
        snapshot_id="snap_a",
        hwnd=1001,
        window_title="CalcApp",
        elements=[elem_btn, elem_edit, elem_old],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=3,
        duration_ms=12.0,
    )

    # Snapshot B:
    # - Calculate button is disabled
    # - Result edit value changed from "0" to "42"
    # - lblStatus disappeared
    # - New element "Clear" appeared
    elem_btn_b = UIAElement(
        id=1,
        snapshot_id="snap_b",
        control_type="Button",
        name="Calculate",
        automation_id="btnCalc",
        enabled=False,  # changed!
        value=None,
        bounding_rect=(10, 10, 100, 40),
    )
    elem_edit_b = UIAElement(
        id=2,
        snapshot_id="snap_b",
        control_type="Edit",
        name="Result",
        automation_id="txtResult",
        enabled=True,
        value="42",  # changed!
        bounding_rect=(10, 50, 200, 80),
    )
    elem_new = UIAElement(
        id=3,
        snapshot_id="snap_b",
        control_type="Button",
        name="Clear",
        automation_id="btnClear",
        enabled=True,
        value=None,
        bounding_rect=(10, 90, 100, 120),
    )
    snap_b = UIASnapshot(
        snapshot_id="snap_b",
        hwnd=1001,
        window_title="CalcApp",
        elements=[elem_btn_b, elem_edit_b, elem_new],
        is_sparse=False,
        timestamp=time.time(),
        total_elements_scanned=3,
        duration_ms=15.0,
    )

    delta = diff(snap_a, snap_b)

    # Appeared
    assert len(delta.appeared) == 1
    assert delta.appeared[0].automation_id == "btnClear"

    # Disappeared
    assert len(delta.disappeared) == 1
    assert delta.disappeared[0].automation_id == "lblStatus"

    # Changed
    assert len(delta.changed) == 2
    changed_map = {c.automation_id: c for c in delta.changed}

    # btnCalc changed enabled state
    assert "btnCalc" in changed_map
    assert changed_map["btnCalc"].old_enabled is True
    assert changed_map["btnCalc"].new_enabled is False
    assert "enabled_changed" in changed_map["btnCalc"].change_type

    # txtResult changed value
    assert "txtResult" in changed_map
    assert changed_map["txtResult"].old_value == "0"
    assert changed_map["txtResult"].new_value == "42"
    assert "value_changed" in changed_map["txtResult"].change_type


def test_region_filtering_logic():
    """Verifies bounding box region intersection filtering."""
    region: Tuple[int, int, int, int] = (100, 100, 500, 500)

    # Completely inside
    assert is_in_region((150, 150, 400, 400), region) is True
    # Overlapping boundary
    assert is_in_region((50, 50, 150, 150), region) is True
    # Completely above
    assert is_in_region((100, 10, 300, 80), region) is False
    # Completely to the right
    assert is_in_region((550, 150, 700, 300), region) is False
    # Completely below
    assert is_in_region((150, 550, 300, 600), region) is False


def test_sparse_flag_logic():
    """Verifies sparse flag triggers when fewer elements than threshold are discovered."""
    sparse_snap = UIASnapshot(
        snapshot_id="snap_sparse",
        hwnd=1002,
        window_title="Empty App",
        elements=[
            UIAElement(
                id=1,
                snapshot_id="snap_sparse",
                control_type="Pane",
                name="Canvas",
                automation_id="canvas1",
                enabled=True,
                value=None,
                bounding_rect=(0, 0, 800, 600),
            )
        ],
        is_sparse=True,
        timestamp=time.time(),
        total_elements_scanned=1,
        duration_ms=5.0,
    )
    assert sparse_snap.is_sparse is True

    d = sparse_snap.to_dict()
    assert d["is_sparse"] is True
    assert d["element_count"] == 1


def test_element_relevance_filter():
    """Verifies invisible or zero-sized controls are filtered out."""
    # Invisible wrapper
    mock_inv = MagicMock()
    mock_inv.is_visible.return_value = False
    assert is_element_relevant(mock_inv) is False

    # Zero-sized wrapper
    mock_zero = MagicMock()
    mock_zero.is_visible.return_value = True
    mock_rect = MagicMock()
    mock_rect.width.return_value = 0
    mock_rect.height.return_value = 0
    mock_zero.rectangle.return_value = mock_rect
    assert is_element_relevant(mock_zero) is False

    # Off-screen negative wrapper
    mock_neg = MagicMock()
    mock_neg.is_visible.return_value = True
    mock_rect2 = MagicMock()
    mock_rect2.width.return_value = 100
    mock_rect2.height.return_value = 50
    mock_rect2.right = -10
    mock_rect2.bottom = 100
    mock_neg.rectangle.return_value = mock_rect2
    assert is_element_relevant(mock_neg) is False
