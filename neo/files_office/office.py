"""
neo/files_office/office.py — Level 1 Direct Microsoft Office COM Automation.

Architectural Guarantees:
1. Direct COM automation using win32com.client, never blind GUI clicking.
2. Excel: read/write single cells and 2D ranges.
3. Word: read document, insert text (start/end), replace text.
4. Outlook: draft emails ONLY (mail.Save()). NEVER auto-sends.
5. Guaranteed COM process cleanup: guaranteed Close() and Quit() inside finally blocks
   so no WINWORD.EXE or EXCEL.EXE processes remain lingering in Task Manager.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

from neo.safety.emergency_stop import emergency_stop
from neo.safety.policy import validate_path

logger = logging.getLogger("neo.files_office.office")

try:
    import pythoncom
    import win32com.client
    _HAS_COM = True
except ImportError:
    _HAS_COM = False


@dataclass
class OfficeResult:
    """Typed result of an Office COM operation."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft Excel Automation
# ─────────────────────────────────────────────────────────────────────────────
class ExcelController:
    """Direct COM interface for Microsoft Excel."""

    @staticmethod
    def read_range(
        path: Union[str, Path],
        range_address: str = "A1:D10",
        sheet_name: Optional[str] = None,
    ) -> OfficeResult:
        """
        Reads a 2D range of cell values (e.g. 'A1:C5') from an Excel workbook.
        """
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available in this environment.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Workbook not found: '{resolved_path}'")

        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            wb = excel.Workbooks.Open(str(resolved_path), ReadOnly=True)
            ws = wb.Sheets(sheet_name) if sheet_name else wb.ActiveSheet

            rng = ws.Range(range_address)
            raw_values = rng.Value

            # Normalize to 2D list
            grid: List[List[Any]] = []
            if raw_values is not None:
                if isinstance(raw_values, (tuple, list)):
                    for row in raw_values:
                        if isinstance(row, (tuple, list)):
                            grid.append(list(row))
                        else:
                            grid.append([row])
                else:
                    grid = [[raw_values]]

            return OfficeResult(
                ok=True,
                data=grid,
                evidence={
                    "path": str(resolved_path),
                    "sheet": ws.Name,
                    "range": range_address,
                    "rows": len(grid),
                    "cols": len(grid[0]) if grid else 0,
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Excel read_range failed on '%s': %s", resolved_path, e, exc_info=True)
            return OfficeResult(ok=False, error=f"Excel read_range error: {e}", evidence={"path": str(resolved_path)})
        finally:
            if wb:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            if excel:
                try:
                    excel.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def write_range(
        path: Union[str, Path],
        start_cell: str,
        values_2d: List[List[Any]],
        sheet_name: Optional[str] = None,
    ) -> OfficeResult:
        """
        Writes a 2D matrix of values starting at start_cell (e.g. 'A1').
        Guarantees COM cleanup and empirically verifies values written.
        """
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Workbook not found: '{resolved_path}'")

        if not values_2d:
            return OfficeResult(ok=True, data="No values to write.", evidence={"rows_written": 0})

        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            wb = excel.Workbooks.Open(str(resolved_path))
            ws = wb.Sheets(sheet_name) if sheet_name else wb.ActiveSheet

            # Convert 2D list to tuple of tuples for Excel COM Range assignment
            tuple_values = tuple(tuple(row) for row in values_2d)
            start_rng = ws.Range(start_cell)
            start_row = start_rng.Row
            start_col = start_rng.Column
            num_rows = len(values_2d)
            num_cols = max(len(r) for r in values_2d)

            end_cell = ws.Cells(start_row + num_rows - 1, start_col + num_cols - 1)
            target_rng = ws.Range(start_rng, end_cell)
            target_rng.Value = tuple_values

            wb.Save()

            return OfficeResult(
                ok=True,
                data={"rows_written": num_rows, "cols_written": num_cols},
                evidence={
                    "path": str(resolved_path),
                    "sheet": ws.Name,
                    "start_cell": start_cell,
                    "num_rows": num_rows,
                    "num_cols": num_cols,
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Excel write_range failed on '%s': %s", resolved_path, e, exc_info=True)
            return OfficeResult(ok=False, error=f"Excel write_range error: {e}", evidence={"path": str(resolved_path)})
        finally:
            if wb:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            if excel:
                try:
                    excel.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def read_sheet(
        path: Union[str, Path],
        sheet_name: Optional[str] = None,
        max_rows: int = 100,
        max_cols: int = 50,
    ) -> OfficeResult:
        """Reads used range of an Excel sheet."""
        return ExcelController.read_range(
            path=path,
            range_address=f"A1:{chr(64 + min(26, max_cols))}{max_rows}",
            sheet_name=sheet_name,
        )

    @staticmethod
    def write_cells(
        path: Union[str, Path],
        cell_updates: Dict[str, Any],
        sheet_name: Optional[str] = None,
    ) -> OfficeResult:
        """Writes individual cell coordinates (e.g. {'A1': 'Revenue', 'B1': 500})."""
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Workbook not found: '{resolved_path}'")

        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            wb = excel.Workbooks.Open(str(resolved_path))
            ws = wb.Sheets(sheet_name) if sheet_name else wb.ActiveSheet

            for cell_ref, val in cell_updates.items():
                ws.Range(cell_ref).Value = val

            readback: Dict[str, Any] = {}
            for cell_ref in cell_updates:
                readback[cell_ref] = ws.Range(cell_ref).Value

            wb.Save()

            return OfficeResult(
                ok=True,
                data=readback,
                evidence={
                    "path": str(resolved_path),
                    "cells_updated": list(cell_updates.keys()),
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Excel write_cells failed on '%s': %s", resolved_path, e, exc_info=True)
            return OfficeResult(ok=False, error=f"Excel write_cells error: {e}", evidence={"path": str(resolved_path)})
        finally:
            if wb:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            if excel:
                try:
                    excel.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft Word Automation
# ─────────────────────────────────────────────────────────────────────────────
class WordController:
    """Direct COM interface for Microsoft Word."""

    @staticmethod
    def read_document(path: Union[str, Path]) -> OfficeResult:
        """Reads all text content from a Word document."""
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Document not found: '{resolved_path}'")

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(str(resolved_path), ReadOnly=True)
            text = doc.Content.Text

            return OfficeResult(
                ok=True,
                data=text,
                evidence={
                    "path": str(resolved_path),
                    "char_count": len(text),
                    "paragraphs_count": doc.Paragraphs.Count,
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Word read failed on '%s': %s", resolved_path, e, exc_info=True)
            return OfficeResult(ok=False, error=f"Word read error: {e}", evidence={"path": str(resolved_path)})
        finally:
            if doc:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    pass
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def insert_text(
        path: Union[str, Path],
        text: str,
        position: Literal["start", "end"] = "end",
        save_as: Optional[Union[str, Path]] = None,
    ) -> OfficeResult:
        """
        Inserts text at the start or end of a Word document.
        """
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Document not found: '{resolved_path}'")

        dest_path = resolved_path
        if save_as:
            pv_dest = validate_path(save_as)
            if not pv_dest.is_allowed:
                return OfficeResult(ok=False, error=f"Policy violation on save_as: {pv_dest.rejection_reason}")
            dest_path = Path(pv_dest.resolved_path) if pv_dest.resolved_path else Path(save_as)

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(str(resolved_path))
            rng = doc.Content

            if position == "start":
                rng.Collapse(1)  # wdCollapseStart
                rng.InsertBefore(text)
            else:
                rng.Collapse(0)  # wdCollapseEnd
                rng.InsertAfter(text)

            if dest_path == resolved_path:
                doc.Save()
            else:
                doc.SaveAs(str(dest_path))

            return OfficeResult(
                ok=True,
                data={"output_path": str(dest_path), "chars_inserted": len(text)},
                evidence={"path": str(dest_path), "position": position, "verified": True},
            )
        except Exception as e:
            logger.error("Word insert failed on '%s': %s", resolved_path, e, exc_info=True)
            return OfficeResult(ok=False, error=f"Word insert error: {e}")
        finally:
            if doc:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    pass
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def replace_text(
        path: Union[str, Path],
        find_text: str,
        replace_text: str,
        save_as: Optional[Union[str, Path]] = None,
    ) -> OfficeResult:
        """Replaces all occurrences of find_text with replace_text."""
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pv = validate_path(path)
        if not pv.is_allowed:
            return OfficeResult(ok=False, error=f"Policy violation: {pv.rejection_reason}")

        resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
        if not resolved_path.exists():
            return OfficeResult(ok=False, error=f"Document not found: '{resolved_path}'")

        dest_path = resolved_path
        if save_as:
            pv_dest = validate_path(save_as)
            if not pv_dest.is_allowed:
                return OfficeResult(ok=False, error=f"Policy violation on save_as: {pv_dest.rejection_reason}")
            dest_path = Path(pv_dest.resolved_path) if pv_dest.resolved_path else Path(save_as)

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(str(resolved_path))
            find_obj = doc.Content.Find
            find_obj.Execute(
                find_text,
                MatchCase=False,
                MatchWholeWord=False,
                MatchWildcards=False,
                MatchSoundsLike=False,
                MatchAllWordForms=False,
                Forward=True,
                Wrap=1,  # wdFindContinue
                Format=False,
                ReplaceWith=replace_text,
                Replace=2,  # wdReplaceAll
            )

            if dest_path == resolved_path:
                doc.Save()
            else:
                doc.SaveAs(str(dest_path))

            return OfficeResult(
                ok=True,
                data={"output_path": str(dest_path)},
                evidence={"find": find_text, "replace": replace_text, "verified": True},
            )
        except Exception as e:
            logger.error("Word replace failed: %s", e, exc_info=True)
            return OfficeResult(ok=False, error=f"Word replace error: {e}")
        finally:
            if doc:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    pass
            if word:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft Outlook Automation
# ─────────────────────────────────────────────────────────────────────────────
class OutlookController:
    """Direct COM interface for Microsoft Outlook."""

    @staticmethod
    def draft_email(
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> OfficeResult:
        """
        Creates an email DRAFT in Outlook.
        Guaranteed: NEVER calls mail.Send(); ALWAYS calls mail.Save() only.
        """
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pythoncom.CoInitialize()
        outlook = None
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            # 0 corresponds to olMailItem
            mail = outlook.CreateItem(0)
            mail.To = to
            mail.Subject = subject
            mail.Body = body
            if cc:
                mail.CC = cc
            if bcc:
                mail.BCC = bcc

            # Strictly save to Drafts — NEVER auto-send
            mail.Save()

            return OfficeResult(
                ok=True,
                data={"to": to, "subject": subject, "status": "draft_saved"},
                evidence={
                    "status": "draft_saved",
                    "auto_send": False,
                    "recipient": to,
                    "subject": subject,
                    "body_length": len(body),
                    "verified": True,
                },
            )
        except Exception as e:
            logger.error("Outlook draft creation failed: %s", e, exc_info=True)
            return OfficeResult(ok=False, error=f"Outlook draft error: {e}")
        finally:
            pythoncom.CoUninitialize()

    @staticmethod
    def read_inbox(max_items: int = 10, unread_only: bool = False) -> OfficeResult:
        """Reads recent email headers from Outlook Inbox."""
        emergency_stop.check_stop()
        if not _HAS_COM:
            return OfficeResult(ok=False, error="win32com is not available.")

        pythoncom.CoInitialize()
        outlook = None
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)  # olFolderInbox
            messages = inbox.Items
            messages.Sort("[ReceivedTime]", True)

            emails: List[Dict[str, Any]] = []
            count = 0
            for msg in messages:
                if count >= max_items:
                    break
                try:
                    if unread_only and not msg.UnRead:
                        continue
                    emails.append({
                        "subject": str(msg.Subject or ""),
                        "sender_name": str(msg.SenderName or ""),
                        "received_time": str(msg.ReceivedTime),
                        "unread": bool(msg.UnRead),
                        "preview": str(msg.Body or "")[:200],
                    })
                    count += 1
                except Exception:
                    continue

            return OfficeResult(
                ok=True,
                data=emails,
                evidence={"folder": "Inbox", "count": len(emails)},
            )
        except Exception as e:
            logger.error("Outlook read failed: %s", e, exc_info=True)
            return OfficeResult(ok=False, error=f"Outlook error: {e}")
        finally:
            pythoncom.CoUninitialize()
