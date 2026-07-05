from __future__ import annotations

import numpy as np


def normalize_intensity(volume: np.ndarray, lower_percentile: float = 1.0, upper_percentile: float = 99.5) -> np.ndarray:
    data = np.nan_to_num(volume.astype(np.float32), copy=False)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return np.zeros_like(data, dtype=np.float32)

    low = float(np.percentile(finite, lower_percentile))
    high = float(np.percentile(finite, upper_percentile))
    if high <= low:
        high = float(np.max(finite))
        low = float(np.min(finite))
    if high <= low:
        return np.zeros_like(data, dtype=np.float32)

    normalized = np.clip(data, low, high)
    normalized = (normalized - low) / (high - low)
    return normalized.astype(np.float32)


def downsample_volume(volume: np.ndarray, factor: int) -> np.ndarray:
    factor = max(1, int(factor))
    return volume[::factor, ::factor, ::factor]


def slice_from_plane(volume: np.ndarray, plane: str, index: int) -> np.ndarray:
    plane = plane.lower()
    if plane == "sagittal":
        return volume[:, :, index]
    if plane == "coronal":
        return volume[:, index, :]
    return volume[index, :, :]


def plane_length(volume: np.ndarray, plane: str) -> int:
    plane = plane.lower()
    if plane == "sagittal":
        return int(volume.shape[2])
    if plane == "coronal":
        return int(volume.shape[1])
    return int(volume.shape[0])
