from pathlib import Path
import numpy as np
import cv2

def normalize_to_uint8(slice_2d: np.ndarray) -> np.ndarray:
    arr = slice_2d.astype(np.float32)
    arr = arr - np.min(arr)
    max_value = np.max(arr)
    if max_value > 0:
        arr = arr / max_value
    return (arr * 255).astype(np.uint8)

def save_preview_slice(volume: np.ndarray, output_path: str | Path, axis: int = 2) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index = volume.shape[axis] // 2
    if axis == 0:
        slice_2d = volume[index, :, :]
    elif axis == 1:
        slice_2d = volume[:, index, :]
    else:
        slice_2d = volume[:, :, index]
    image = normalize_to_uint8(slice_2d)
    cv2.imwrite(str(output_path), image)
    return output_path

def save_overlay_slice(image_2d: np.ndarray, mask_2d: np.ndarray, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base = cv2.cvtColor(normalize_to_uint8(image_2d), cv2.COLOR_GRAY2BGR)
    overlay = base.copy()
    overlay[mask_2d > 0] = [0, 0, 255]
    blended = cv2.addWeighted(base, 0.65, overlay, 0.35, 0)
    cv2.imwrite(str(output_path), blended)
    return output_path
