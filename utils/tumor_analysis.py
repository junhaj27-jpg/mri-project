from __future__ import annotations

import numpy as np
from skimage import measure, morphology


def find_bright_candidate_mask(
    image: np.ndarray,
    percentile: float = 95.0,
    min_area_px: int = 80,
) -> np.ndarray:
    finite = np.nan_to_num(image.astype(np.float32), copy=False)
    active = finite > 0
    if not np.any(active):
        return np.zeros_like(finite, dtype=bool)

    threshold = np.percentile(finite[active], percentile)
    mask = finite >= threshold
    mask &= active
    mask = morphology.remove_small_objects(mask, min_size=max(1, min_area_px))
    mask = morphology.binary_closing(mask, morphology.disk(2))
    return keep_largest_components(mask, max_components=3)


def keep_largest_components(mask: np.ndarray, max_components: int = 3) -> np.ndarray:
    labels = measure.label(mask)
    if labels.max() == 0:
        return mask

    regions = sorted(measure.regionprops(labels), key=lambda region: region.area, reverse=True)
    selected = {region.label for region in regions[:max_components]}
    return np.isin(labels, list(selected))


def calculate_mask_area_mm2(mask: np.ndarray, pixel_spacing: list[float] | tuple[float, float]) -> float:
    try:
        row_spacing, col_spacing = float(pixel_spacing[0]), float(pixel_spacing[1])
    except Exception:
        row_spacing, col_spacing = 1.0, 1.0
    return float(mask.sum() * row_spacing * col_spacing)
