"""
neo.vision — Level 5 Vision Fallback, Screen Capture, OCR, Image Diff, and Coordinate Grounding.
"""
from neo.vision.capture import (
    ImageCoordinateMapper,
    ScaledImageResult,
    VisionCaptureResult,
    capture_screen,
    crop_region,
    get_system_dpi_scale,
    scale_to_model_size,
    zoom_region,
)
from neo.vision.click_xy import (
    VisionActionBlockedError,
    click_xy,
    validate_exhaustion_evidence,
)
from neo.vision.diff import (
    ImageDiffResult,
    diff_images,
)
from neo.vision.grounding import (
    ScreenPoint,
    denormalize_coords,
    normalize_coords,
)
from neo.vision.ocr import (
    AMBIGUOUS_CHAR_MAP,
    OcrLine,
    OcrResult,
    OcrWord,
    detect_character_ambiguities,
    run_ocr,
)

__all__ = [
    # Capture & Scaling
    "capture_screen",
    "crop_region",
    "zoom_region",
    "scale_to_model_size",
    "ScaledImageResult",
    "ImageCoordinateMapper",
    "VisionCaptureResult",
    "get_system_dpi_scale",
    # Grounding
    "normalize_coords",
    "denormalize_coords",
    "ScreenPoint",
    # OCR
    "run_ocr",
    "OcrResult",
    "OcrWord",
    "OcrLine",
    "detect_character_ambiguities",
    "AMBIGUOUS_CHAR_MAP",
    # Image Diff
    "diff_images",
    "ImageDiffResult",
    # Fallback Click
    "click_xy",
    "VisionActionBlockedError",
    "validate_exhaustion_evidence",
]
