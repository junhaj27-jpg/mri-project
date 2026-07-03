import numpy as np
import pytest

from src.volume import (
    calculate_area_mm2,
    calculate_mask_stack_volume_mm3,
    calculate_single_slice_volume_mm3,
    calculate_volume_from_slice_areas,
    summarize_roi,
)


def test_calculate_volume_from_slice_areas_returns_mm3_and_cm3():
    result = calculate_volume_from_slice_areas([100.0, 120.0, 80.0], 5.0)
    assert result["volume_mm3"] == 1500.0
    assert result["volume_cm3"] == 1.5


def test_calculate_volume_from_slice_areas_allows_empty_area_list():
    result = calculate_volume_from_slice_areas([], 5.0)
    assert result["volume_mm3"] == 0.0
    assert result["volume_cm3"] == 0.0


def test_calculate_volume_from_slice_areas_rejects_invalid_values():
    with pytest.raises(ValueError):
        calculate_volume_from_slice_areas([10.0], 0.0)
    with pytest.raises(ValueError):
        calculate_volume_from_slice_areas([-1.0], 5.0)


def test_calculate_area_mm2():
    mask = np.array([[True, False], [True, True]])
    assert calculate_area_mm2(mask, (0.5, 0.5)) == 0.75


def test_calculate_single_slice_volume_mm3():
    mask = np.array([[True, False], [True, True]])
    assert calculate_single_slice_volume_mm3(mask, (2.0, 0.5, 0.5)) == 1.5


def test_calculate_mask_stack_volume_mm3():
    mask_stack = np.ones((2, 3, 4), dtype=bool)
    assert calculate_mask_stack_volume_mm3(mask_stack, (2.0, 0.5, 0.5)) == 12.0


def test_summarize_roi():
    mask = np.array([[True, False], [True, True]])
    summary = summarize_roi(mask, (2.0, 0.5, 0.5))
    assert summary["pixel_count"] == 3
    assert summary["area_mm2"] == 0.75
    assert summary["volume_mm3"] == 1.5
