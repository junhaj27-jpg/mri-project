from __future__ import annotations

import numpy as np
from skimage import filters, measure, morphology


def brain_only_slice(image: np.ndarray, erode_pixels: int = 4) -> np.ndarray:
    mask = estimate_brain_mask(image, erode_pixels=erode_pixels)
    result = np.zeros_like(image, dtype=np.float32)
    result[mask] = image[mask]
    return result


def estimate_brain_mask(image: np.ndarray, erode_pixels: int = 4) -> np.ndarray:
    finite = np.nan_to_num(image.astype(np.float32), copy=False)
    if np.max(finite) <= np.min(finite):
        return np.ones_like(finite, dtype=bool)

    normalized = (finite - np.min(finite)) / (np.max(finite) - np.min(finite))
    threshold = filters.threshold_otsu(normalized)
    mask = normalized > threshold

    mask = morphology.remove_small_objects(mask, min_size=max(64, mask.size // 500))
    mask = morphology.binary_closing(mask, morphology.disk(5))
    mask = morphology.binary_opening(mask, morphology.disk(2))
    mask = keep_component_near_center(mask)

    if erode_pixels > 0:
        mask = morphology.binary_erosion(mask, morphology.disk(erode_pixels))
    return mask


def keep_component_near_center(mask: np.ndarray) -> np.ndarray:
    labels = measure.label(mask)
    if labels.max() == 0:
        return mask

    center = np.array(mask.shape, dtype=float) / 2.0
    best_label = 0
    best_score = -float("inf")
    for region in measure.regionprops(labels):
        centroid = np.array(region.centroid)
        distance = np.linalg.norm(centroid - center)
        score = region.area - distance * 20.0
        if score > best_score:
            best_score = score
            best_label = region.label
    return labels == best_label
