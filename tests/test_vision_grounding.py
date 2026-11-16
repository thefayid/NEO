"""
tests/test_vision_grounding.py — Unit tests for Vision Coordinate Grounding.
"""
from neo.vision.grounding import denormalize_coords, normalize_coords


def test_coordinate_normalization():
    # Corner (0, 0)
    assert normalize_coords(0, 0, 1920, 1080) == (0, 0)

    # Center
    assert normalize_coords(960, 540, 1920, 1080) == (500, 500)

    # Max corner
    assert normalize_coords(1920, 1080, 1920, 1080) == (1000, 1000)


def test_coordinate_denormalization():
    # Center roundtrip
    pt = denormalize_coords(500, 500, 1920, 1080)
    assert pt.x == 960
    assert pt.y == 540
    assert pt.is_within_bounds is True

    # Corner roundtrip
    pt_corner = denormalize_coords(1000, 1000, 2560, 1440)
    assert pt_corner.x == 2560
    assert pt_corner.y == 1440
    assert pt_corner.is_within_bounds is True


def test_out_of_bounds_detection():
    pt_oob = denormalize_coords(1200, 1200, 1920, 1080)
    assert pt_oob.is_within_bounds is False
