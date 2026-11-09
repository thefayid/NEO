"""
actions/document_analyzer.py — F.R.I.D.A.Y. Document Intelligence & Contract Redliner.

Provides high-speed document analysis for Tony Stark:
  • redline: Analyzes legal agreements, contracts, and NDAs for high-risk clauses,
             liability traps, missing caps, IP overreaches, and suggests counter-draft redlines.
  • ocr_receipt: Extracts vendor, line items, taxes, dates, and totals from invoices & receipts.
  • summarize: Delivers executive briefings of long PDFs, technical specs, and whitepapers.
  • extract_tables: Extracts structured tabular data into clean markdown tables.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
from typing import Optional

from core import gemini

try:
    import PIL
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import pdfplumber
    _PDFPLUMBER_OK = True
except ImportError:
    _PDFPLUMBER_OK = False

try:
    import PyPDF2
    _PYPDF2_OK = True
except ImportError:
    _PYPDF2_OK = False


def _find_recent_document(extension_filter: tuple[str, ...] | None = None) -> Optional[Path]:
    """Find the most recently modified document in Downloads, Desktop, or Workspace."""
    search_dirs = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.cwd(),
    ]
    extensions = extension_filter or (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg")
    candidates = []

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        try:
            for item in s_dir.iterdir():
                if item.is_file() and item.suffix.lower() in extensions:
                    try:
                        candidates.append((item.stat().st_mtime, item))
                    except Exception:
                        pass
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def _extract_text_from_pdf(pdf_path: Path, max_pages: int = 15) -> str:
    """Extract clean text from PDF using pdfplumber with PyPDF2 fallback."""
    text_parts = []
    if _PDFPLUMBER_OK:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages[:max_pages]):
                    p_txt = page.extract_text()
                    if p_txt:
                        text_parts.append(f"--- Page {i+1} ---\n{p_txt}")
            if text_parts:
                return "\n\n".join(text_parts)
        except Exception as e:
            print(f"[DocumentAnalyzer] pdfplumber error: {e}")

    if _PYPDF2_OK:
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for i, page in enumerate(reader.pages[:max_pages]):
                    p_txt = page.extract_text()
                    if p_txt:
                        text_parts.append(f"--- Page {i+1} ---\n{p_txt}")
            if text_parts:
                return "\n\n".join(text_parts)
        except Exception as e:
            print(f"[DocumentAnalyzer] PyPDF2 error: {e}")

    return ""


def _extract_document_content(file_path: Path) -> tuple[str, Optional[bytes], str]:
    """Extract content from file: returns (text_content, optional_image_bytes, mime_type)."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        txt = _extract_text_from_pdf(file_path)
        return txt, None, "application/pdf"
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            img_bytes = file_path.read_bytes()
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            return "", img_bytes, mime
        except Exception:
            return "", None, ""
    elif ext in (".txt", ".md", ".csv", ".json"):
        try:
            txt = file_path.read_text(encoding="utf-8", errors="replace")
            return txt, None, "text/plain"
        except Exception:
            return "", None, ""
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            txt = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return txt, None, "application/docx"
        except Exception:
            return "", None, ""
    return "", None, ""


def _redline_contract(content: str, img_bytes: Optional[bytes] = None, mime: str = "") -> str:
    """Analyze contract or NDA for risky clauses and suggest redlines."""
    prompt = (
        "You are Tony Stark's senior legal advisor and contract intelligence engine. "
        "Review this contract/agreement with extreme tactical precision.\n\n"
        "Analyze for:\n"
        "1. HIGH RISK CLAUSES: Unlimited liability, one-sided indemnification, broad IP assignment, "
        "onerous non-compete clauses, automatic renewals without notice, and unfair termination fees.\n"
        "2. MEDIUM RISKS: Ambiguous deliverables, tight payment terms, unclear confidentiality terms.\n"
        "3. RECOMMENDED REDLINE AMENDMENTS: Exact proposed counter-draft wording for each problematic clause.\n"
        "4. EXECUTIVE SUMMARY: 2-3 sentence verdict for the Boss on whether to sign, negotiate, or reject.\n\n"
        "Format cleanly with markdown headers, risk badges [CRITICAL / HIGH / MODERATE], and bullet points."
    )
def _build_contents(prompt: str, content: str, img_bytes: Optional[bytes], mime: str):
    if img_bytes:
        try:
            from google.genai import types as gtypes
            return [prompt, gtypes.Part.from_bytes(data=img_bytes, mime_type=mime or "image/jpeg")]
        except Exception:
            if _PIL_OK:
                try:
                    img = PIL.Image.open(io.BytesIO(img_bytes))
                    return [prompt, img]
                except Exception:
                    pass
    if content.strip():
        return f"{prompt}\n\n[DOCUMENT CONTENT]:\n{content[:40000]}"
    return None


def _redline_contract(content: str, img_bytes: Optional[bytes] = None, mime: str = "") -> str:
    """Analyze contract or NDA for risky clauses and suggest redlines."""
    prompt = (
        "You are Tony Stark's senior legal advisor and contract intelligence engine. "
        "Review this contract/agreement with extreme tactical precision.\n\n"
        "Analyze for:\n"
        "1. HIGH RISK CLAUSES: Unlimited liability, one-sided indemnification, broad IP assignment, "
        "onerous non-compete clauses, automatic renewals without notice, and unfair termination fees.\n"
        "2. MEDIUM RISKS: Ambiguous deliverables, tight payment terms, unclear confidentiality terms.\n"
        "3. RECOMMENDED REDLINE AMENDMENTS: Exact proposed counter-draft wording for each problematic clause.\n"
        "4. EXECUTIVE SUMMARY: 2-3 sentence verdict for the Boss on whether to sign, negotiate, or reject.\n\n"
        "Format cleanly with markdown headers, risk badges [CRITICAL / HIGH / MODERATE], and bullet points."
    )
    contents = _build_contents(prompt, content, img_bytes, mime)
    if not contents:
        return "Could not extract text or image from contract document."

    resp = gemini.text(contents, tier=gemini.SMART, timeout_ms=60000)
    return resp or "Contract redline analysis timed out or could not be completed."


def _ocr_receipt_financial(content: str, img_bytes: Optional[bytes] = None, mime: str = "") -> str:
    """Extract financial breakdown from invoice or receipt."""
    prompt = (
        "You are F.R.I.D.A.Y.'s financial intelligence module. Extract receipt/invoice data:\n"
        "1. Vendor / Merchant Name\n"
        "2. Transaction Date & Time\n"
        "3. Invoice / Receipt Number\n"
        "4. Line Items Table (Item Description, Quantity, Unit Price, Total Price)\n"
        "5. Financial Summary (Subtotal, Taxes/VAT/GST, Discounts, Grand Total Amount with Currency)\n"
        "6. Payment Method & Auth Code (if present)\n"
        "Format as clean markdown table and concise bullet points."
    )
    contents = _build_contents(prompt, content, img_bytes, mime)
    if not contents:
        return "Could not extract text or image from receipt."

    resp = gemini.text(contents, tier=gemini.SMART, timeout_ms=45000)
    return resp or "Receipt analysis timed out."


def _summarize_document(content: str, img_bytes: Optional[bytes] = None, mime: str = "") -> str:
    """Provide executive summary of document."""
    prompt = (
        "You are F.R.I.D.A.Y. providing an Executive Briefing of this document for Tony Stark.\n"
        "Deliver:\n"
        "- Core Purpose (1 sentence)\n"
        "- Key Takeaways & Crucial Findings (3-5 high-impact bullets)\n"
        "- Deadlines & Action Items (if any)\n"
        "- Bottom Line Verdict."
    )
    contents = _build_contents(prompt, content, img_bytes, mime)
    if not contents:
        return "Could not extract text or image from document."

    resp = gemini.text(contents, tier=gemini.SMART, timeout_ms=45000)
    return resp or "Document summary timed out."


def _extract_tables_from_doc(content: str, img_bytes: Optional[bytes] = None, mime: str = "") -> str:
    """Extract tables into structured markdown format."""
    prompt = (
        "Extract all tabular and numerical data from this document. "
        "Output each table as clean GitHub-flavored markdown table with headers. "
        "Preserve currency signs, column headers, and row alignment precisely."
    )
    contents = _build_contents(prompt, content, img_bytes, mime)
    if not contents:
        return "Could not extract text or image to find tables."

    resp = gemini.text(contents, tier=gemini.SMART, timeout_ms=45000)
    return resp or "Table extraction timed out."


def document_analyzer(parameters: dict | None = None, **kwargs) -> str:
    """Analyze documents, redline contracts, or parse receipts."""
    params = parameters or {}
    action = str(params.get("action", "summarize")).strip().lower()
    path_str = str(params.get("file_path", "")).strip()

    target_path: Optional[Path] = None
    if path_str:
        p = Path(path_str).expanduser().resolve()
        if p.exists() and p.is_file():
            target_path = p
        else:
            # Check relative to workspace or downloads
            for base in (Path.cwd(), Path.home() / "Downloads", Path.home() / "Desktop"):
                cand = base / path_str
                if cand.exists() and cand.is_file():
                    target_path = cand
                    break

    if target_path is None:
        target_path = _find_recent_document()

    if target_path is None or not target_path.exists():
        return (
            "No document found to analyze. Please specify a file path or ensure "
            "a PDF/image is present in your Downloads or Desktop folder, Boss."
        )

    print(f"[DocumentAnalyzer] [DOC] Analyzing '{target_path.name}' with action '{action}'...")
    text_content, img_bytes, mime = _extract_document_content(target_path)

    if not text_content and not img_bytes:
        return f"Could not extract readable text or image data from '{target_path.name}'."

    prefix = f"[ANALYSIS REPORT: {target_path.name}]\n\n"

    if action in ("redline", "contract", "nda", "review"):
        report = _redline_contract(text_content, img_bytes, mime)
    elif action in ("ocr_receipt", "receipt", "invoice", "financial"):
        report = _ocr_receipt_financial(text_content, img_bytes, mime)
    elif action in ("tables", "table", "extract_tables"):
        report = _extract_tables_from_doc(text_content, img_bytes, mime)
    else:
        report = _summarize_document(text_content, img_bytes, mime)

    # Save complete report to disk if substantial
    out_file = target_path.parent / f"{target_path.stem}_{action}_report.md"
    try:
        out_file.write_text(prefix + report, encoding="utf-8")
        save_note = f"\n\n[FILE] Full analysis saved to: {out_file.name}"
    except Exception:
        save_note = ""

    return prefix + report + save_note


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "document_analyzer",
    "description": (
        "Analyzes PDFs, agreements, invoices, receipts, and documents using Tony Stark's document intelligence engine. "
        "Actions: "
        "'redline' (Contract & NDA review: flags liability traps, IP overreach, termination clauses, and provides counter-drafts) | "
        "'ocr_receipt' (Financial extraction: vendor, line items, taxes, and totals from receipts or invoices) | "
        "'summarize' (Executive briefing and core takeaways of long documents) | "
        "'extract_tables' (Extracts structured tabular data into clean markdown tables). "
        "Provide 'file_path' or leave blank to automatically inspect the most recent document in Downloads or Desktop."
    ),
    "brief": (
        "Document intelligence: redline contracts & NDAs, OCR invoices & receipts, "
        "summarize PDFs, and extract tables."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'redline' | 'ocr_receipt' | 'summarize' | 'extract_tables'",
                "enum": ["redline", "ocr_receipt", "summarize", "extract_tables"]
            },
            "file_path": {
                "type": "STRING",
                "description": "Optional file path to document (PDF, DOCX, image, receipt, TXT). If omitted, finds most recent document."
            }
        },
        "required": ["action"]
    },
    "handler": document_analyzer,
}
