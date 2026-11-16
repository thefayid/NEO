"""
tests/test_vision.py — Comprehensive Unit & Integration Tests for NEO Vision Layer.

Covers:
1. Scaling round-trip coordinate transformations at 100%, 125%, 150%, and 200% DPI.
2. Windows Native OCR on synthetic rendered images with numeric double-reading and ambiguity detection.
3. OpenCV image diff on modified and identical images.
4. Level 5 click_xy exhaustion policy enforcement and diff-based verification.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image, ImageDraw

from neo.vision.capture import (
    ImageCoordinateMapper,
    crop_region,
    scale_to_model_size,
    zoom_region,
)
from neo.vision.click_xy import (
    VisionActionBlockedError,
    click_xy,
    validate_exhaustion_evidence,
)
from neo.vision.diff import diff_images
from neo.vision.ocr import (
    detect_character_ambiguities,
    run_ocr,
)
from neo.windows.actions import ActionResult


# ─────────────────────────────────────────────────────────────────────────────
# 1. Scaling Round-Trip Coordinate Transformations
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dpi_scale", [1.0, 1.25, 1.5, 2.0])
def test_scaling_round_trip_at_various_dpis(dpi_scale: float):
    orig_w, orig_h = 1920, 1080
    max_dim = 1024

    # Create dummy image and scale
    img = Image.new("RGB", (orig_w, orig_h), color=(20, 20, 20))
    scaled_res, mapper = scale_to_model_size(img, max_dim=max_dim, preserve_aspect=True)

    mapper.dpi_scale = dpi_scale

    test_points = [
        (0, 0),
        (100, 100),
        (960, 540),
        (1280, 720),
        (1919, 1079),
    ]

    for px, py in test_points:
        # Physical -> Model -> Physical
        mx, my = mapper.physical_to_model(px, py)
        rt_px, rt_py = mapper.model_to_physical(mx, my)
        assert abs(rt_px - px) <= 2, f"Physical round trip error at ({px}, {py}): got ({rt_px}, {rt_py})"
        assert abs(rt_py - py) <= 2, f"Physical round trip error at ({px}, {py}): got ({rt_px}, {rt_py})"

        # Physical -> Logical -> Physical
        lx, ly = mapper.physical_to_logical(px, py)
        rt_l_px, rt_l_py = mapper.logical_to_physical(lx, ly)
        assert abs(rt_l_px - px) <= 2, f"Logical round trip error at ({px}, {py}) for DPI {dpi_scale}"
        assert abs(rt_l_py - py) <= 2, f"Logical round trip error at ({px}, {py}) for DPI {dpi_scale}"

        # Model -> Logical -> Model
        lx, ly = mapper.model_to_logical(mx, my)
        rt_mx, rt_my = mapper.logical_to_model(lx, ly)
        assert abs(rt_mx - mx) <= 3, f"Model-Logical round trip error at ({mx}, {my})"
        assert abs(rt_my - my) <= 3, f"Model-Logical round trip error at ({mx}, {my})"

    # Bounding box round trip
    test_bbox = (200, 150, 300, 100)  # x, y, w, h
    log_bbox = mapper.physical_bbox_to_logical(test_bbox)
    phys_bbox = mapper.logical_bbox_to_physical(log_bbox)
    assert abs(phys_bbox[0] - test_bbox[0]) <= 2
    assert abs(phys_bbox[1] - test_bbox[1]) <= 2
    assert abs(phys_bbox[2] - test_bbox[2]) <= 2
    assert abs(phys_bbox[3] - test_bbox[3]) <= 2


def test_crop_and_zoom_regions():
    img = Image.new("RGB", (200, 200), color=(100, 100, 100))
    cropped = crop_region(img, (20, 30, 80, 90))
    assert cropped.size == (60, 60)

    zoomed = zoom_region(img, (20, 30, 80, 90), zoom_factor=2.0)
    assert zoomed.size == (120, 120)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Windows Native OCR on Rendered Sample Image
# ─────────────────────────────────────────────────────────────────────────────
def test_ocr_ambiguity_detection_patterns():
    amb_0 = detect_character_ambiguities("Code 0O")
    assert any("0" in a for a in amb_0)
    assert any("O" in a for a in amb_0)

    amb_1 = detect_character_ambiguities("Item 1l")
    assert any("1" in a for a in amb_1)
    assert any("l" in a for a in amb_1)

    amb_5 = detect_character_ambiguities("Pass 5S")
    assert any("5" in a for a in amb_5)
    assert any("S" in a for a in amb_5)


def test_ocr_on_rendered_sample_image(tmp_path: Path):
    # Render synthetic image with numbers and ambiguous text
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Clean rendering
    draw.text((20, 30), "Invoice 49201", fill=(0, 0, 0))
    draw.text((20, 70), "Ref 0O1l5S", fill=(0, 0, 0))

    img_path = tmp_path / "sample_ocr.png"
    img.save(str(img_path))

    ocr_res = run_ocr(img_path, verify_numbers=True)
    assert ocr_res.ok is True
    assert len(ocr_res.words) > 0

    # Locate the recognized number word
    num_words = [w for w in ocr_res.words if w.is_number]
    assert len(num_words) >= 1

    # Check that ambiguity is detected on Ref word with 0O1l5S
    amb_words = [w for w in ocr_res.words if w.is_ambiguous]
    assert len(amb_words) >= 1
    assert any("0" in w.text or "O" in w.text or "1" in w.text for w in amb_words)


# ─────────────────────────────────────────────────────────────────────────────
# 3. OpenCV Image Difference Engine
# ─────────────────────────────────────────────────────────────────────────────
def test_image_diff_on_edited_images():
    base = Image.new("RGB", (300, 200), color=(50, 50, 50))
    edited = base.copy()
    draw = ImageDraw.Draw(edited)
    # Draw white square in the center
    draw.rectangle([100, 80, 160, 120], fill=(255, 255, 255))

    diff_res = diff_images(base, edited)
    assert diff_res.has_changed is True
    assert diff_res.changed_pixel_count > 0
    assert diff_res.changed_percentage > 0.0
    assert len(diff_res.changed_regions) >= 1

    # Check bounding box encompasses the square (expanded slightly by dilation kernel)
    rx, ry, rw, rh = diff_res.changed_regions[0]
    assert 90 <= rx <= 105
    assert 70 <= ry <= 85
    assert 55 <= rw <= 75
    assert 35 <= rh <= 55


def test_image_diff_on_identical_images():
    base = Image.new("RGB", (200, 200), color=(80, 80, 80))
    diff_res = diff_images(base, base)
    assert diff_res.has_changed is False
    assert diff_res.changed_pixel_count == 0
    assert diff_res.changed_percentage == 0.0
    assert len(diff_res.changed_regions) == 0
    assert diff_res.enclosing_bbox is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Level 5 click_xy Action & Exhaustion Gate Enforcement
# ─────────────────────────────────────────────────────────────────────────────
def test_click_xy_enforces_exhaustion_evidence():
    # 1. Missing reason -> rejected
    with pytest.raises(VisionActionBlockedError) as exc_reason:
        validate_exhaustion_evidence(reason="", exhaustion_evidence={"uia_sparse": True})
    assert "detailed justification" in str(exc_reason.value)

    # 2. Missing exhaustion evidence -> rejected
    with pytest.raises(VisionActionBlockedError) as exc_ev:
        validate_exhaustion_evidence(reason="Button is custom canvas", exhaustion_evidence={})
    assert "'exhaustion_evidence' dictionary is mandatory" in str(exc_ev.value)

    # 3. Falsy exhaustion evidence -> rejected
    with pytest.raises(VisionActionBlockedError) as exc_false:
        validate_exhaustion_evidence(reason="Button is custom canvas", exhaustion_evidence={"uia_sparse": False})
    assert "no positive exhaustion indicators" in str(exc_false.value)

    # 4. Valid justification and evidence -> passes
    validate_exhaustion_evidence(
        reason="UIA snapshot returned 0 elements on custom Direct2D canvas",
        exhaustion_evidence={"uia_sparse": True, "dom_inactive": True},
    )


def test_click_xy_execution_with_diff_verification():
    img_before = Image.new("RGB", (200, 200), color=(40, 40, 40))
    img_after = img_before.copy()
    draw = ImageDraw.Draw(img_after)
    draw.rectangle([50, 50, 90, 90], fill=(220, 220, 220))  # Visual state change

    with patch("neo.vision.click_xy.capture_screen") as mock_cap, \
         patch("neo.vision.click_xy.click_coords") as mock_click, \
         patch("neo.vision.click_xy.time.sleep"):

        # Mock pre and post capture
        mock_cap.side_effect = [
            MagicMock(ok=True, image=img_before, error=None),
            MagicMock(ok=True, image=img_after, error=None),
        ]
        mock_click.return_value = MagicMock(ok=True, error=None)

        res = click_xy(
            x=70,
            y=70,
            reason="UIA snapshot was completely sparse and custom canvas button has no accessible handles",
            exhaustion_evidence={"uia_sparse": True, "dom_inactive": True},
            settle_timeout=0.01,
        )

        assert res.ok is True
        assert res.verified == "true"
        assert res.warning is None
        assert res.evidence["has_visual_change"] is True
        assert res.evidence["changed_pixels"] > 0
        mock_click.assert_called_once_with(70, 70, button="left", double=False)


def test_click_xy_warns_when_no_visual_change():
    img_identical = Image.new("RGB", (200, 200), color=(40, 40, 40))

    with patch("neo.vision.click_xy.capture_screen") as mock_cap, \
         patch("neo.vision.click_xy.click_coords") as mock_click, \
         patch("neo.vision.click_xy.time.sleep"):

        # Same image before and after
        mock_cap.side_effect = [
            MagicMock(ok=True, image=img_identical, error=None),
            MagicMock(ok=True, image=img_identical, error=None),
        ]
        mock_click.return_value = MagicMock(ok=True, error=None)

        res = click_xy(
            x=150,
            y=150,
            reason="Canvas element not exposed to UIA or DOM tree",
            exhaustion_evidence={"uia_sparse": True},
            settle_timeout=0.01,
        )

        assert res.ok is True
        assert res.verified == "false"
        assert res.warning is not None
        assert "produced NO observable visual change" in res.warning
