"""
neo/vision/ocr.py — Native Windows OCR Engine with Numeric Verification.

Architectural Guarantees & OCR Selection Justification:
1. Engine Choice: Windows Native OCR (Windows.Media.Ocr.OcrEngine).
   - Zero External Dependencies: Built directly into all modern Windows 10/11 installations.
     Requires NO external C++ binaries (unlike Tesseract which requires tesseract.exe) and NO
     massive 500MB neural network frameworks (unlike PaddleOCR).
   - Windows Desktop Typography Optimization: Specifically engineered for Windows ClearType
     sub-pixel font rendering, system dialogs, and native DPI scaling.
   - 100% Local & Offline: Runs completely locally with zero cloud network leakage.
2. Numeric Verification Protocol:
   - Every detected sequence containing numeric digits is read twice.
   - Pass 1: Global screen/window OCR pass.
   - Pass 2: High-contrast 2x upscaled crop of the isolated numeric region.
3. Ambiguity Flagging:
   - Identifies and flags visually conflated character pairs:
     '0' vs 'O'/'o', '1' vs 'l'/'I'/'|', '5' vs 'S'/'s', '8' vs 'B', '2' vs 'Z'/'z'.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger("neo.vision.ocr")

# Path to the bundled PowerShell WinRT OCR bridge
_PS_OCR_SCRIPT = Path(__file__).parent / "win_ocr_runner.ps1"

# Ambiguity mapping for character confusion in UI typography
AMBIGUOUS_CHAR_MAP: Dict[str, List[str]] = {
    "0": ["O", "o", "D", "Q"],
    "O": ["0", "o", "Q"],
    "o": ["0", "O"],
    "1": ["l", "I", "|", "i", "!"],
    "l": ["1", "I", "|"],
    "I": ["1", "l", "|"],
    "|": ["1", "l", "I"],
    "5": ["S", "s"],
    "S": ["5", "s"],
    "s": ["5", "S"],
    "8": ["B"],
    "B": ["8"],
    "2": ["Z", "z"],
    "Z": ["2", "z"],
    "z": ["2", "Z"],
    "6": ["b", "G"],
    "b": ["6"],
}


@dataclass
class OcrWord:
    """A single recognized word with bounding box and numeric verification metadata."""
    text: str
    x: int
    y: int
    width: int
    height: int
    is_number: bool = False
    reading_1: Optional[str] = None
    reading_2: Optional[str] = None
    is_verified: bool = False
    is_ambiguous: bool = False
    ambiguities: List[str] = field(default_factory=list)
    ambiguity_warning: Optional[str] = None

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "bbox": {"x": self.x, "y": self.y, "w": self.width, "h": self.height},
            "is_number": self.is_number,
            "reading_1": self.reading_1,
            "reading_2": self.reading_2,
            "is_verified": self.is_verified,
            "is_ambiguous": self.is_ambiguous,
            "ambiguities": self.ambiguities,
            "ambiguity_warning": self.ambiguity_warning,
        }


@dataclass
class OcrLine:
    """A line of recognized words."""
    text: str
    words: List[OcrWord] = field(default_factory=list)

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        if not self.words:
            return 0, 0, 0, 0
        min_x = min(w.x for w in self.words)
        min_y = min(w.y for w in self.words)
        max_r = max(w.x + w.width for w in self.words)
        max_b = max(w.y + w.height for w in self.words)
        return min_x, min_y, max_r - min_x, max_b - min_y

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "bbox": self.bbox,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class OcrResult:
    """Structured result of Windows OCR analysis."""
    ok: bool
    text: str = ""
    lines: List[OcrLine] = field(default_factory=list)
    words: List[OcrWord] = field(default_factory=list)
    engine: str = "Windows.Media.Ocr"
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "lines": [ln.to_dict() for ln in self.lines],
            "words": [w.to_dict() for w in self.words],
            "engine": self.engine,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


def _execute_win_ocr_powershell(image_path: Path) -> Dict[str, Any]:
    """Invokes the WinRT OCR runner script via PowerShell."""
    if not _PS_OCR_SCRIPT.exists():
        raise FileNotFoundError(f"PowerShell OCR script not found at {_PS_OCR_SCRIPT}")

    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_PS_OCR_SCRIPT),
        "-ImagePath",
        str(image_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"Windows OCR PowerShell error (code {proc.returncode}): {proc.stderr}")

    stdout = proc.stdout.strip()
    if not stdout:
        return {"text": "", "lines": [], "words": []}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse OCR JSON response: {e}\nRaw output: {stdout}") from e


def detect_character_ambiguities(text: str) -> List[str]:
    """
    Checks if a string contains characters prone to optical confusion (0/O, 1/l/I, 5/S, etc.).
    """
    found: List[str] = []
    for ch in text:
        if ch in AMBIGUOUS_CHAR_MAP:
            confusions = "/".join(AMBIGUOUS_CHAR_MAP[ch])
            entry = f"'{ch}' (confusable with {confusions})"
            if entry not in found:
                found.append(entry)
    return found


def _verify_number_isolated_crop(
    image: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    temp_dir: Path,
) -> Optional[str]:
    """
    Crops a number bounding box with 6px margin, applies 2x zoom and contrast enhancement,
    and runs a 2nd isolated OCR read.
    """
    try:
        pad = 6
        img_w, img_h = image.size
        l = max(0, x - pad)
        t = max(0, y - pad)
        r = min(img_w, x + w + pad)
        b = min(img_h, y + h + pad)

        crop = image.crop((l, t, r, b))
        # 2x upscale with high-quality resampling
        crop_zoomed = crop.resize((crop.width * 2, crop.height * 2), resample=Image.Resampling.LANCZOS)

        # Contrast enhancement
        gray = crop_zoomed.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(2.0)

        crop_path = temp_dir / f"ocr_num_check_{int(time.time() * 1000)}.png"
        enhanced.save(crop_path, format="PNG")

        raw_data = _execute_win_ocr_powershell(crop_path)
        try:
            crop_path.unlink(missing_ok=True)
        except Exception:
            pass

        recognized = (raw_data.get("text") or "").strip()
        return recognized if recognized else None
    except Exception as e:
        logger.debug("Isolated number verification read failed: %s", e)
        return None


def run_ocr(
    image_input: Union[str, Path, Image.Image],
    verify_numbers: bool = True,
) -> OcrResult:
    """
    Executes Windows Native OCR on the provided image.
    - Reads numbers twice via high-contrast crops.
    - Flags ambiguous characters.
    - Returns structured OcrResult with words and bounding boxes.
    """
    start_t = time.perf_counter()
    temp_dir = Path(tempfile.gettempdir())
    cleanup_temp = False

    temp_img_path: Path
    pil_image: Image.Image

    if isinstance(image_input, (str, Path)):
        temp_img_path = Path(image_input)
        if not temp_img_path.exists():
            return OcrResult(ok=False, error=f"Image file not found: {temp_img_path}")
        pil_image = Image.open(temp_img_path)
    elif isinstance(image_input, Image.Image):
        pil_image = image_input
        temp_img_path = temp_dir / f"neo_ocr_input_{int(time.time() * 1000)}.png"
        pil_image.save(temp_img_path, format="PNG")
        cleanup_temp = True
    else:
        return OcrResult(ok=False, error=f"Unsupported image input type: {type(image_input)}")

    try:
        raw_res = _execute_win_ocr_powershell(temp_img_path)
    except Exception as e:
        logger.error("Windows OCR failed: %s", e, exc_info=True)
        return OcrResult(ok=False, error=str(e), duration_ms=(time.perf_counter() - start_t) * 1000.0)
    finally:
        if cleanup_temp and temp_img_path.exists():
            try:
                temp_img_path.unlink(missing_ok=True)
            except Exception:
                pass

    words: List[OcrWord] = []
    lines: List[OcrLine] = []

    raw_lines = raw_res.get("lines") or []
    for r_ln in raw_lines:
        line_words: List[OcrWord] = []
        for r_w in r_ln.get("words", []):
            txt = r_w.get("text", "").strip()
            wx = int(r_w.get("x", 0))
            wy = int(r_w.get("y", 0))
            ww = int(r_w.get("w", 0))
            wh = int(r_w.get("h", 0))

            is_num = bool(re.search(r"\d", txt))
            ambiguities = detect_character_ambiguities(txt)
            is_ambiguous = len(ambiguities) > 0
            amb_warning: Optional[str] = None

            reading_1: Optional[str] = None
            reading_2: Optional[str] = None
            is_verified = False

            if is_num and verify_numbers:
                reading_1 = txt
                reading_2 = _verify_number_isolated_crop(pil_image, wx, wy, ww, wh, temp_dir)

                if reading_2 is not None:
                    # Compare the 2 readings (ignoring trivial punctuation/whitespace differences)
                    clean_r1 = re.sub(r"\s+", "", reading_1)
                    clean_r2 = re.sub(r"\s+", "", reading_2)
                    if clean_r1 == clean_r2 and not is_ambiguous:
                        is_verified = True
                    else:
                        is_ambiguous = True
                        reasons = []
                        if clean_r1 != clean_r2:
                            reasons.append(f"Discrepancy: Pass 1='{reading_1}' vs Pass 2='{reading_2}'")
                        if ambiguities:
                            reasons.append(f"Ambiguous characters: {', '.join(ambiguities)}")
                        amb_warning = "; ".join(reasons)
                elif is_ambiguous:
                    amb_warning = f"Ambiguous characters present: {', '.join(ambiguities)}"

            word_obj = OcrWord(
                text=txt,
                x=wx,
                y=wy,
                width=ww,
                height=wh,
                is_number=is_num,
                reading_1=reading_1,
                reading_2=reading_2,
                is_verified=is_verified,
                is_ambiguous=is_ambiguous,
                ambiguities=ambiguities,
                ambiguity_warning=amb_warning,
            )
            line_words.append(word_obj)
            words.append(word_obj)

        lines.append(OcrLine(text=r_ln.get("text", ""), words=line_words))

    full_text = raw_res.get("text") or " ".join(w.text for w in words)
    duration = (time.perf_counter() - start_t) * 1000.0

    return OcrResult(
        ok=True,
        text=full_text,
        lines=lines,
        words=words,
        duration_ms=duration,
    )
