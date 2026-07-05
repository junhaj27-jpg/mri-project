from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage import filters, measure, morphology

from preprocessing import normalize_intensity


def largest_connected_component(mask: np.ndarray) -> np.ndarray:
    """
    Keep only the largest connected component from a binary mask.
    """
    labels = measure.label(mask.astype(bool))
    if labels.max() == 0:
        return mask.astype(bool)
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    return labels == int(np.argmax(counts))


def refine_brain_mask(
    raw_mask: np.ndarray,
    hole_area_threshold: int = 5000,
    closing_radius: int = 3,
    min_object_size: int = 20000,
    gaussian_sigma: float = 1.0,
    fill_holes: bool = True,
) -> tuple[np.ndarray, dict]:
    """
    Convert a raw brain mask into a closed mask suitable for 3D mesh generation.
    The flow intentionally avoids strong opening because it can remove brain tissue.
    """
    mask = raw_mask.astype(bool)
    if not np.any(mask):
        return mask.astype(np.uint8), {
            "refinement": "empty mask",
            "fill_holes": bool(fill_holes),
            "closing_radius": int(closing_radius),
            "remove_small_holes_threshold": int(hole_area_threshold),
            "remove_small_objects_threshold": int(min_object_size),
            "mask_smoothing_sigma": float(gaussian_sigma),
            "refined_components": 0,
            "initial_refine_voxels": 0,
        }

    initial_voxels = int(np.count_nonzero(mask))
    mask = largest_connected_component(mask)

    if fill_holes:
        mask = fill_internal_holes_by_slices(mask)
        mask = ndi.binary_fill_holes(mask)

    hole_threshold = max(0, int(hole_area_threshold))
    if hole_threshold > 0:
        mask = morphology.remove_small_holes(mask, area_threshold=hole_threshold)

    radius = max(0, int(closing_radius))
    if radius > 0:
        footprint = morphology.ball(radius)
        mask = morphology.binary_closing(mask, footprint)
        mask = ndi.binary_fill_holes(mask)
        mask = morphology.binary_dilation(mask, morphology.ball(1))
        mask = morphology.binary_erosion(mask, morphology.ball(1))
        mask = morphology.binary_closing(mask, morphology.ball(max(1, radius - 1)))

    min_size = max(0, int(min_object_size))
    if min_size > 0:
        mask = morphology.remove_small_objects(mask, min_size=min_size)

    mask = largest_connected_component(mask)
    if fill_holes:
        mask = fill_internal_holes_by_slices(mask)
        mask = ndi.binary_fill_holes(mask)

    sigma = max(0.0, float(gaussian_sigma))
    if sigma > 0 and np.any(mask):
        smooth = ndi.gaussian_filter(mask.astype(np.float32), sigma=sigma)
        mask = smooth >= 0.45
        mask = largest_connected_component(mask)
        if fill_holes:
            mask = fill_internal_holes_by_slices(mask)
            mask = ndi.binary_fill_holes(mask)
        if radius > 0:
            mask = morphology.binary_closing(mask, morphology.ball(max(1, radius - 1)))

    mask = largest_connected_component(mask)
    if fill_holes:
        mask = ndi.binary_fill_holes(mask)

    metadata = {
        "refinement": "largest_component + fill_holes + remove_small_holes + closing + dilation/erosion + small_object cleanup + smoothing",
        "fill_holes": bool(fill_holes),
        "closing_radius": radius,
        "remove_small_holes_threshold": hole_threshold,
        "remove_small_objects_threshold": min_size,
        "mask_smoothing_sigma": sigma,
        "refined_components": int(measure.label(mask).max()),
        "initial_refine_voxels": initial_voxels,
    }
    return mask.astype(np.uint8), metadata


def fill_internal_holes_by_slices(mask: np.ndarray) -> np.ndarray:
    filled = mask.astype(bool)
    for axis in range(3):
        moved = np.moveaxis(filled, axis, 0)
        out = np.empty_like(moved, dtype=bool)
        for index, slice_mask in enumerate(moved):
            out[index] = ndi.binary_fill_holes(slice_mask) if np.any(slice_mask) else slice_mask
        filled = np.moveaxis(out, 0, axis)
    return filled


def create_brain_mask(
    volume: np.ndarray,
    threshold_scale: float = 1.0,
    min_size_ratio: float = 0.001,
    peel_iterations: int = 5,
    method: str = "Fallback Otsu",
    plane: str = "unknown",
) -> tuple[np.ndarray, dict]:
    if method != "Fallback Otsu":
        method = "Fallback Otsu"

    normalized = normalize_intensity(volume)
    active = normalized[normalized > 0]
    if active.size == 0:
        return np.zeros_like(normalized, dtype=bool), {"method": method, "threshold": 0.0, "components": 0}

    base_threshold = float(filters.threshold_otsu(active))
    threshold = float(np.clip(base_threshold * threshold_scale, 0.01, 0.95))
    foreground = normalized >= threshold

    min_size = max(256, int(foreground.size * float(min_size_ratio)))
    foreground = morphology.remove_small_objects(foreground, min_size=min_size)
    foreground = ndi.binary_fill_holes(foreground)
    foreground = morphology.binary_closing(foreground, morphology.ball(2))
    foreground = morphology.binary_opening(foreground, morphology.ball(1))
    foreground = keep_component_near_center(foreground)

    mask = estimate_brain_parenchyma_region(normalized, foreground, threshold, min_size, plane)
    mask = peel_outer_tissue(mask, min_size, peel_iterations)
    mask = solidify_surface_mask(mask)
    mask = keep_component_near_center(mask)

    metadata = {
        "method": method,
        "threshold": threshold,
        "base_threshold": base_threshold,
        "peel_iterations": int(peel_iterations),
        "plane": plane,
        "voxels": int(np.count_nonzero(mask)),
        "components": int(measure.label(mask).max()),
    }
    return mask.astype(bool), metadata


def estimate_brain_parenchyma_region(
    normalized: np.ndarray,
    foreground: np.ndarray,
    threshold: float,
    min_size: int,
    plane: str,
) -> np.ndarray:
    if not np.any(foreground):
        return foreground

    prior = build_brain_location_prior(foreground, plane)
    tissue_low = max(0.08, threshold * 0.42)
    tissue_high = 0.78
    tissue = (normalized >= tissue_low) & (normalized <= tissue_high)
    distance = ndi.distance_transform_edt(foreground)
    tissue &= distance >= 5.0
    candidate = tissue & prior

    candidate = morphology.binary_closing(candidate, morphology.ball(2))
    candidate = morphology.binary_opening(candidate, morphology.ball(1))
    candidate = morphology.remove_small_objects(candidate, min_size=max(256, min_size // 4))
    candidate = keep_component_near_center(candidate)

    if np.count_nonzero(candidate) < min_size:
        candidate = extract_internal_brain_region(normalized, foreground & prior, threshold, min_size)

    candidate = morphology.binary_closing(candidate, morphology.ball(3))
    candidate = morphology.remove_small_holes(candidate, area_threshold=max(2048, candidate.size // 1000))
    candidate = ndi.binary_fill_holes(candidate)
    candidate = morphology.remove_small_objects(candidate, min_size=max(256, min_size // 3))
    return keep_component_near_center(candidate)


def build_brain_location_prior(foreground: np.ndarray, plane: str) -> np.ndarray:
    coords = np.argwhere(foreground)
    if coords.size == 0:
        return np.zeros_like(foreground, dtype=bool)

    lower = coords.min(axis=0).astype(np.float32)
    upper = coords.max(axis=0).astype(np.float32)
    size = np.maximum(upper - lower + 1, 1)
    plane = str(plane or "unknown").lower()

    if plane == "sagittal" or (plane == "unknown" and foreground.shape[0] < foreground.shape[1]):
        # z: left-right slices, y: superior-inferior, x: anterior-posterior in this viewer order.
        # Shift away from the face/anterior side and trim inferior neck tissue.
        center = np.array(
            [
                lower[0] + size[0] * 0.50,
                lower[1] + size[1] * 0.34,
                lower[2] + size[2] * 0.63,
            ],
            dtype=np.float32,
        )
        radii = np.array([size[0] * 0.43, size[1] * 0.35, size[2] * 0.38], dtype=np.float32)
    else:
        center = (lower + upper) * 0.5
        radii = size * 0.40

    grid = np.indices(foreground.shape, dtype=np.float32)
    distance = np.zeros(foreground.shape, dtype=np.float32)
    for axis in range(3):
        distance += ((grid[axis] - center[axis]) / max(float(radii[axis]), 1.0)) ** 2
    prior = distance <= 1.0
    return prior & foreground


def extract_internal_brain_region(normalized: np.ndarray, foreground: np.ndarray, threshold: float, min_size: int) -> np.ndarray:
    if not np.any(foreground):
        return foreground

    distance = ndi.distance_transform_edt(foreground)
    internal_distances = distance[foreground]
    seed_distance = max(2.0, float(np.percentile(internal_distances, 70)))
    seed = distance >= seed_distance
    seed &= normalized >= max(0.06, threshold * 0.45)
    seed = morphology.remove_small_objects(seed, min_size=max(64, min_size // 12))
    seed = keep_component_near_center(seed)

    if not np.any(seed):
        seed = morphology.binary_erosion(foreground, morphology.ball(4))
        seed = keep_component_near_center(seed)
    if not np.any(seed):
        return foreground

    candidate = foreground & (normalized >= max(0.05, threshold * 0.35))
    candidate &= distance >= 1.0
    propagated = ndi.binary_propagation(seed, mask=candidate)
    if np.count_nonzero(propagated) < min_size:
        return foreground
    return propagated.astype(bool)


def peel_outer_tissue(mask: np.ndarray, min_size: int, peel_iterations: int) -> np.ndarray:
    if peel_iterations <= 0 or not np.any(mask):
        return mask.astype(bool)

    eroded = mask.astype(bool)
    for _ in range(int(peel_iterations)):
        eroded = morphology.binary_erosion(eroded, morphology.ball(1))
    eroded = keep_component_near_center(eroded)
    if np.count_nonzero(eroded) < min_size:
        return mask.astype(bool)

    restored = eroded
    restore_iterations = max(1, int(peel_iterations) // 2)
    for _ in range(restore_iterations):
        restored = morphology.binary_dilation(restored, morphology.ball(1))
    return keep_component_near_center(restored)


def apply_center_ellipsoid_prior(mask: np.ndarray, shrink: float = 0.82) -> np.ndarray:
    if not np.any(mask):
        return mask.astype(bool)
    coords = np.argwhere(mask)
    lower = coords.min(axis=0)
    upper = coords.max(axis=0)
    center = coords.mean(axis=0)
    radii = np.maximum((upper - lower + 1).astype(float) * 0.5 * float(shrink), 1.0)
    grid = np.indices(mask.shape, dtype=np.float32)
    distance = np.zeros(mask.shape, dtype=np.float32)
    for axis in range(mask.ndim):
        distance += ((grid[axis] - center[axis]) / radii[axis]) ** 2
    prior = distance <= 1.0
    clipped = mask & prior
    if np.count_nonzero(clipped) < max(256, int(np.count_nonzero(mask) * 0.25)):
        return mask.astype(bool)
    return clipped


def solidify_surface_mask(mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return mask.astype(bool)

    solid = mask.astype(bool)
    solid = morphology.binary_closing(solid, morphology.ball(4))
    solid = morphology.remove_small_holes(solid, area_threshold=max(2048, solid.size // 1000))
    solid = ndi.binary_fill_holes(solid)
    solid = morphology.binary_closing(solid, morphology.ball(3))
    solid = morphology.binary_opening(solid, morphology.ball(1))
    solid = morphology.remove_small_objects(solid, min_size=max(512, solid.size // 1500))
    return solid.astype(bool)


def fill_slice_holes(mask: np.ndarray, axis: int) -> np.ndarray:
    moved = np.moveaxis(mask, axis, 0)
    filled = np.empty_like(moved, dtype=bool)
    for index, slice_mask in enumerate(moved):
        if np.any(slice_mask):
            filled[index] = ndi.binary_fill_holes(slice_mask)
        else:
            filled[index] = slice_mask
    return np.moveaxis(filled, 0, axis)


def keep_component_near_center(mask: np.ndarray) -> np.ndarray:
    labels = measure.label(mask)
    if labels.max() == 0:
        return mask.astype(bool)

    center = np.array(mask.shape, dtype=np.float32) / 2.0
    best_label = 0
    best_score = -float("inf")
    for region in measure.regionprops(labels):
        centroid = np.array(region.centroid, dtype=np.float32)
        distance = float(np.linalg.norm((centroid - center) / np.maximum(center, 1.0)))
        touches_border = any(
            region.bbox[axis] <= 1 or region.bbox[axis + mask.ndim] >= mask.shape[axis] - 1
            for axis in range(mask.ndim)
        )
        border_penalty = 0.35 if touches_border else 0.0
        score = float(region.area) * (1.0 - min(distance + border_penalty, 0.95))
        if score > best_score:
            best_score = score
            best_label = int(region.label)
    return labels == best_label
