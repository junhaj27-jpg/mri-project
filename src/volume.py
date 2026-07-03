from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def calculate_volume_from_slice_areas(
    roi_area_mm2_list: Sequence[float],
    slice_thickness_mm: float,
) -> dict:
    """Calculate ROI volume from per-slice ROI areas.

    Formula: sum(area_mm2 for each ROI slice) * SliceThickness(mm).
    """
    if slice_thickness_mm <= 0:
        raise ValueError("SliceThickness must be greater than zero.")
    if any(area < 0 for area in roi_area_mm2_list):
        raise ValueError("ROI area values must be greater than or equal to zero.")

    volume_mm3 = float(sum(roi_area_mm2_list) * slice_thickness_mm)
    return {
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1000.0,
    }


def calculate_area_mm2(mask: np.ndarray, pixel_spacing_yx_mm: tuple[float, float] | list[float]) -> float:
    row_spacing, col_spacing = pixel_spacing_yx_mm
    return float(mask.sum() * row_spacing * col_spacing)


def calculate_single_slice_volume_mm3(mask: np.ndarray, spacing_zyx_mm: tuple[float, float, float] | list[float]) -> float:
    slice_spacing, row_spacing, col_spacing = spacing_zyx_mm
    area_mm2 = calculate_area_mm2(mask, (row_spacing, col_spacing))
    return float(area_mm2 * slice_spacing)


def calculate_mask_stack_volume_mm3(mask_stack: np.ndarray, spacing_zyx_mm: tuple[float, float, float] | list[float]) -> float:
    slice_spacing, row_spacing, col_spacing = spacing_zyx_mm
    voxel_volume_mm3 = slice_spacing * row_spacing * col_spacing
    return float(mask_stack.sum() * voxel_volume_mm3)


def summarize_roi(mask: np.ndarray, spacing_zyx_mm: tuple[float, float, float] | list[float]) -> dict:
    area_mm2 = calculate_area_mm2(mask, spacing_zyx_mm[1:])
    volume_mm3 = calculate_single_slice_volume_mm3(mask, spacing_zyx_mm)
    return {
        "pixel_count": int(mask.sum()),
        "area_mm2": area_mm2,
        "area_cm2": area_mm2 / 100.0,
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1000.0,
    }

