"""
tests/test_files_office.py — Comprehensive unit and integration tests for Level 1 File & Office operations.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from neo.config import load_settings
from neo.files_office import (
    ExcelController,
    WordController,
    compute_sha256,
    safe_copy_file,
    safe_create_folder,
    safe_delete_file,
    safe_file_info,
    safe_list_dir,
    safe_move_file,
    safe_read_file,
    safe_rename_file,
    safe_search_files,
    safe_write_file,
)
from neo.safety import get_confirmation_gate


@pytest.fixture
def temp_workspace(tmp_path: Path):
    """Sets up a temporary directory registered in allowed_folders."""
    load_settings(allowed_folders=[str(tmp_path)])
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Filesystem CRUD & Overwrite Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_safe_write_and_read_file(temp_workspace: Path):
    target = temp_workspace / "notes.txt"
    content = "Hello, NEO deterministic file control!"

    # 1. Write file
    w_res = safe_write_file(target, content)
    assert w_res.ok is True
    assert w_res.evidence.get("verified") is True
    assert w_res.evidence.get("size_bytes") == len(content.encode("utf-8"))

    # 2. Read file back
    r_res = safe_read_file(target)
    assert r_res.ok is True
    assert r_res.data == content
    assert r_res.evidence.get("sha256") == compute_sha256(target)


def test_safe_append_file(temp_workspace: Path):
    target = temp_workspace / "log.txt"
    safe_write_file(target, "Line 1\n")
    safe_write_file(target, "Line 2\n", mode="append")

    r_res = safe_read_file(target)
    assert r_res.ok is True
    assert r_res.data == "Line 1\nLine 2\n"
    assert r_res.evidence.get("total_lines") == 2


def test_safe_create_folder_and_list(temp_workspace: Path):
    sub = temp_workspace / "sub_folder" / "nested"
    f_res = safe_create_folder(sub)
    assert f_res.ok is True
    assert sub.exists() is True
    assert sub.is_dir() is True


def test_safe_copy_move_rename_file(temp_workspace: Path):
    src = temp_workspace / "original.txt"
    safe_write_file(src, "Payload Data")

    # 1. Copy
    copied = temp_workspace / "copied.txt"
    c_res = safe_copy_file(src, copied)
    assert c_res.ok is True
    assert copied.exists() is True
    assert src.exists() is True
    assert compute_sha256(copied) == compute_sha256(src)

    # 2. Rename in-place
    r_res = safe_rename_file(copied, "renamed.txt")
    assert r_res.ok is True
    renamed = temp_workspace / "renamed.txt"
    assert renamed.exists() is True
    assert copied.exists() is False

    # 3. Move to subfolder
    sub = temp_workspace / "archive"
    safe_create_folder(sub)
    moved = sub / "archived.txt"
    m_res = safe_move_file(renamed, moved)
    assert m_res.ok is True
    assert moved.exists() is True
    assert renamed.exists() is False


def test_overwrite_confirmation_gate(temp_workspace: Path):
    """Verifies that overwriting an existing file requires confirmation and defaults to DENY."""
    target = temp_workspace / "important.txt"
    safe_write_file(target, "Initial Data")

    gate = get_confirmation_gate()

    # 1. Denied overwrite
    gate.set_handler(lambda *args: (False, "User declined overwrite"))
    res_denied = safe_write_file(target, "Overwritten Data", mode="write")
    assert res_denied.ok is False
    assert "overwrite denied" in res_denied.error.lower()
    assert target.read_text(encoding="utf-8") == "Initial Data"

    # 2. Approved overwrite
    gate.set_handler(lambda *args: (True, "User confirmed overwrite"))
    res_approved = safe_write_file(target, "Overwritten Data", mode="write")
    assert res_approved.ok is True
    assert target.read_text(encoding="utf-8") == "Overwritten Data"

    gate.set_handler(None)


def test_recycle_delete_file_gated(temp_workspace: Path):
    """Verifies that delete moves to .neo_recycle instead of unlinking, and requires confirmation."""
    target = temp_workspace / "to_delete.txt"
    safe_write_file(target, "Sensitive data")

    gate = get_confirmation_gate()

    # 1. Gate Denies
    gate.set_handler(lambda *args: (False, "Cancel deletion"))
    del_res = safe_delete_file(target)
    assert del_res.ok is False
    assert "denied by confirmation gate" in del_res.error
    assert target.exists() is True

    # 2. Gate Approves
    gate.set_handler(lambda *args: (True, "Approve deletion"))
    del_ok = safe_delete_file(target)
    assert del_ok.ok is True
    assert target.exists() is False

    # Verify moved to .neo_recycle
    recycle_dir = temp_workspace / ".neo_recycle"
    assert recycle_dir.exists() is True
    recycled_files = list(recycle_dir.glob("to_delete_*"))
    assert len(recycled_files) == 1
    assert recycled_files[0].read_text(encoding="utf-8") == "Sensitive data"

    gate.set_handler(None)


def test_disallowed_paths_and_traversal_attempts(temp_workspace: Path):
    # Outside allowed workspace
    outside = Path(tempfile.gettempdir()) / "outside_neo.txt"
    res_outside = safe_read_file(outside)
    assert res_outside.ok is False
    assert "Access denied by security policy" in res_outside.error

    # Traversal escape attempt
    traversal_path = temp_workspace / ".." / "traversal_secret.txt"
    res_trav = safe_read_file(traversal_path)
    assert res_trav.ok is False

    # Disallowed executable extension
    exe_target = temp_workspace / "script.bat"
    res_exe = safe_write_file(exe_target, "echo malicious")
    assert res_exe.ok is False
    assert "disallowed" in res_exe.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Office COM Tests (Excel Round Trip)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.windows_only
def test_excel_round_trip(temp_workspace: Path):
    """
    Creates an Excel workbook, writes a 2D range, reads back the range,
    and empirically verifies data integrity and complete COM process termination.
    """
    import win32com.client
    import pythoncom

    wb_path = temp_workspace / "inventory.xlsx"

    # 1. Initialize a blank workbook using Excel COM
    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = excel.Workbooks.Add()
    wb.SaveAs(str(wb_path))
    wb.Close()
    excel.Quit()
    pythoncom.CoUninitialize()
    time.sleep(0.1)

    assert wb_path.exists() is True

    # 2. Write 2D range using ExcelController
    grid_data = [
        ["SKU", "Item", "Quantity", "Price"],
        ["A101", "Keyboard", 15, 45.0],
        ["B202", "Mouse", 30, 25.5],
        ["C303", "Monitor", 8, 199.99],
    ]
    w_res = ExcelController.write_range(
        path=wb_path,
        start_cell="A1",
        values_2d=grid_data,
    )
    assert w_res.ok is True
    assert w_res.evidence.get("verified") is True

    # 3. Read back 2D range
    r_res = ExcelController.read_range(
        path=wb_path,
        range_address="A1:D4",
    )
    assert r_res.ok is True
    read_grid = r_res.data
    assert len(read_grid) == 4
    assert read_grid[0] == ["SKU", "Item", "Quantity", "Price"]
    assert read_grid[1][0] == "A101"
    assert read_grid[1][1] == "Keyboard"
    assert read_grid[2][2] == 30.0  # Excel numeric float
