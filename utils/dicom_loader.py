from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom


def load_dicom_volume(folder_path: str | Path) -> tuple[np.ndarray, dict]:
    """Load a DICOM brain MRI folder as a 3D numpy volume.

    Only .dcm files with PixelData are used. Slices are sorted by InstanceNumber
    when available, and PatientID is intentionally not returned for display.
    """
    folder = Path(folder_path).expanduser()
    if not str(folder_path).strip():
        raise ValueError("DICOM folder path is empty.")
    if not folder.exists():
        raise FileNotFoundError(f"DICOM folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder}")

    paths = sorted(path for path in folder.rglob("*.dcm") if path.is_file())
    if not paths:
        raise FileNotFoundError(f"No .dcm files found under: {folder}")

    slices = []
    skipped = 0
    for path in paths:
        try:
            ds = pydicom.dcmread(str(path), force=True)
            if hasattr(ds, "PixelData"):
                slices.append((path, ds))
            else:
                skipped += 1
        except Exception:
            skipped += 1

    if not slices:
        raise ValueError("No readable DICOM files with PixelData were found.")

    slices.sort(key=lambda item: slice_sort_key(item[0], item[1]))
    arrays = [get_pixels(ds) for _, ds in slices]
    first_shape = arrays[0].shape
    if any(array.shape != first_shape for array in arrays):
        raise ValueError("DICOM slices have different image sizes and cannot be stacked.")

    volume = np.stack(arrays).astype(np.float32)
    info = get_public_info(slices[0][1], volume, skipped)
    return volume, info


def slice_sort_key(path: Path, ds) -> tuple[float, str]:
    """Sort by InstanceNumber, with ImagePositionPatient and filename fallback."""
    try:
        instance_number = float(getattr(ds, "InstanceNumber"))
        return instance_number, path.name
    except Exception:
        pass

    try:
        return float(ds.ImagePositionPatient[2]), path.name
    except Exception:
        return 0.0, path.name


def get_pixels(ds) -> np.ndarray:
    """Return pixel data with optional DICOM rescale slope/intercept applied."""
    pixels = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1.0))
    intercept = float(getattr(ds, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


def get_public_info(ds, volume: np.ndarray, skipped_files: int) -> dict:
    """Return minimal non-identifying metadata."""
    pixel_spacing = getattr(ds, "PixelSpacing", [1.0, 1.0])
    try:
        pixel_spacing = [float(pixel_spacing[0]), float(pixel_spacing[1])]
    except Exception:
        pixel_spacing = [1.0, 1.0]

    return {
        "StudyDate": format_dicom_date(str(getattr(ds, "StudyDate", "Unknown"))),
        "SeriesDescription": str(getattr(ds, "SeriesDescription", "Unknown")),
        "PixelSpacing": pixel_spacing,
        "SliceThickness": safe_float(getattr(ds, "SliceThickness", 1.0), 1.0),
        "SliceCount": int(volume.shape[0]),
        "Shape": tuple(int(value) for value in volume.shape),
        "SkippedFiles": int(skipped_files),
    }


def format_dicom_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "Unknown"


def safe_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
