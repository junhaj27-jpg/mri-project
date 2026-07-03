from __future__ import annotations

import numpy as np


PLANES = ["Axial", "Coronal", "Sagittal"]


def normalize_for_display(image: np.ndarray) -> np.ndarray:
    low, high = np.percentile(image, [1, 99])
    if high <= low:
        return np.zeros_like(image, dtype=np.float32)
    image = np.clip(image, low, high)
    return (image - low) / (high - low)


def get_slice(volume: np.ndarray, plane: str, index: int) -> np.ndarray:
    if plane == "Axial":
        return volume[index, :, :]
    if plane == "Coronal":
        return volume[:, index, :]
    if plane == "Sagittal":
        return volume[:, :, index]
    raise ValueError(f"지원하지 않는 plane입니다: {plane}")


def max_slice_index(volume: np.ndarray, plane: str) -> int:
    if plane == "Axial":
        return volume.shape[0] - 1
    if plane == "Coronal":
        return volume.shape[1] - 1
    if plane == "Sagittal":
        return volume.shape[2] - 1
    raise ValueError(f"지원하지 않는 plane입니다: {plane}")

