from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom


def load_dicom_volume(folder_path: str | Path) -> tuple[np.ndarray, dict]:
    """Load a DICOM brain MRI folder as a 3D numpy volume.

    Only .dcm files with PixelData are used. Slices are sorted by InstanceNumber.
    PatientID is intentionally not returned for display.
    """
    folder = Path(folder_path).expanduser()
    if not folder.exists():
        raise FileNotFoundError(f"DICOM folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder}")

    paths = sorted(path for path in folder.rglob("*.dcm") if path.is_file())
    if not paths:
        raise FileNotFoundError(f"No .dcm files found under: {folder}")

    slices = []
    for path in paths:
        ds = pydicom.dcmread(str(path), force=True)
        if hasattr(ds, "PixelData"):
            slices.append(ds)

    if not slices:
        raise ValueError("No DICOM files with PixelData were found.")

    slices.sort(key=lambda ds: int(getattr(ds, "InstanceNumber", 0)))
    volume = np.stack([get_pixels(ds) for ds in slices]).astype(np.float32)
    info = get_public_info(slices[0], volume)
    return volume, info


def get_pixels(ds) -> np.ndarray:
    """Return pixel data with optional DICOM rescale slope/intercept applied."""
    pixels = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1.0))
    intercept = float(getattr(ds, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


def get_public_info(ds, volume: np.ndarray) -> dict:
    """Return minimal non-identifying metadata."""
    return {
        "StudyDate": format_dicom_date(str(getattr(ds, "StudyDate", "Unknown"))),
        "SeriesDescription": str(getattr(ds, "SeriesDescription", "Unknown")),
        "SliceCount": int(volume.shape[0]),
        "Shape": tuple(int(value) for value in volume.shape),
    }


def format_dicom_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "Unknown"

