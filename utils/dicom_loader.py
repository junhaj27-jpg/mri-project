from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pydicom


@dataclass(frozen=True)
class DicomSeries:
    """Loaded DICOM MRI series.

    The PatientID is intentionally not included in public metadata returned to
    the app because it can be personally identifying information.
    """

    volume: np.ndarray
    metadata: dict


def load_dicom_series(folder_path: str | Path) -> DicomSeries:
    """Load recursive .dcm files into a 3D numpy volume sorted by InstanceNumber."""
    folder = Path(folder_path).expanduser()
    if not folder.exists():
        raise FileNotFoundError(f"DICOM folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder}")

    dicom_paths = find_dicom_files(folder)
    if not dicom_paths:
        raise FileNotFoundError(f"No .dcm files found under: {folder}")

    datasets = []
    for path in dicom_paths:
        # force=True helps read files that are valid DICOM but have weak headers.
        ds = pydicom.dcmread(str(path), force=True)
        if hasattr(ds, "PixelData"):
            datasets.append(ds)

    if not datasets:
        raise ValueError("No DICOM files with PixelData were found.")

    datasets.sort(key=lambda ds: int(getattr(ds, "InstanceNumber", 0)))
    volume = np.stack([pixel_array(ds) for ds in datasets]).astype(np.float32)
    metadata = extract_public_metadata(datasets[0], volume)
    return DicomSeries(volume=volume, metadata=metadata)


def find_dicom_files(folder: Path) -> list[Path]:
    """Find .dcm files recursively."""
    return sorted(path for path in folder.rglob("*.dcm") if path.is_file())


def pixel_array(dataset) -> np.ndarray:
    """Return rescaled pixel data when rescale tags are present."""
    pixels = dataset.pixel_array.astype(np.float32)
    slope = float(getattr(dataset, "RescaleSlope", 1.0))
    intercept = float(getattr(dataset, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


def extract_public_metadata(dataset, volume: np.ndarray) -> dict:
    """Extract non-identifying metadata needed by the MVP."""
    pixel_spacing = getattr(dataset, "PixelSpacing", [1.0, 1.0])
    return {
        "PixelSpacing": [float(pixel_spacing[0]), float(pixel_spacing[1])],
        "SliceThickness": float(getattr(dataset, "SliceThickness", 1.0)),
        "StudyDate": format_dicom_date(str(getattr(dataset, "StudyDate", "Unknown"))),
        "SeriesDescription": str(getattr(dataset, "SeriesDescription", "Unknown")),
        "SliceCount": int(volume.shape[0]),
        "VolumeShape": tuple(int(value) for value in volume.shape),
    }


def format_dicom_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "Unknown"

