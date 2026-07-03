from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom


REQUIRED_METADATA_KEYS = [
    "PixelSpacing",
    "SliceThickness",
    "PatientID",
    "StudyDate",
    "SeriesDescription",
]


def load_dicom_volume(folder_path: str | Path) -> tuple[np.ndarray, dict]:
    """Load .dcm files from a folder as a z, y, x numpy volume.

    PatientID is extracted for internal tracking, but UI code should not display it
    directly because it can be identifying information.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"DICOM folder not found: {folder}")

    dicom_paths = find_dicom_files(folder)
    if not dicom_paths:
        raise FileNotFoundError(f"No .dcm files found in folder: {folder}")

    slices = []
    for path in dicom_paths:
        dataset = pydicom.dcmread(str(path), force=True)
        if hasattr(dataset, "PixelData"):
            slices.append(dataset)

    if not slices:
        raise ValueError("No DICOM files with PixelData were found.")

    slices.sort(key=instance_number)
    volume = np.stack([rescaled_pixels(ds) for ds in slices]).astype(np.float32)
    metadata = extract_metadata(slices[0])
    metadata["SliceCount"] = int(volume.shape[0])
    metadata["VolumeShape"] = tuple(int(value) for value in volume.shape)
    return volume, metadata


def find_dicom_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.dcm") if path.is_file())


def instance_number(dataset) -> int:
    return int(getattr(dataset, "InstanceNumber", 0))


def rescaled_pixels(dataset) -> np.ndarray:
    pixels = dataset.pixel_array.astype(np.float32)
    slope = float(getattr(dataset, "RescaleSlope", 1.0))
    intercept = float(getattr(dataset, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


def extract_metadata(dataset) -> dict:
    pixel_spacing = getattr(dataset, "PixelSpacing", [1.0, 1.0])
    return {
        "PixelSpacing": [float(pixel_spacing[0]), float(pixel_spacing[1])],
        "SliceThickness": float(getattr(dataset, "SliceThickness", 1.0)),
        "PatientID": str(getattr(dataset, "PatientID", "Unknown")),
        "StudyDate": format_dicom_date(str(getattr(dataset, "StudyDate", "Unknown"))),
        "SeriesDescription": str(getattr(dataset, "SeriesDescription", "Unknown")),
    }


def public_metadata(metadata: dict) -> dict:
    """Return metadata that is safe to show in the UI."""
    return {key: value for key, value in metadata.items() if key != "PatientID"}


def format_dicom_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value

