from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

from utils.dicom_loader import discover_dicom_series, load_dicom_volume


@dataclass
class MRIData:
    volume: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]
    info: dict
    source_type: str
    source_label: str


def load_dicom(paths_or_folder) -> MRIData:
    volume, info = load_dicom_volume(paths_or_folder)
    row_spacing, col_spacing = parse_pixel_spacing(info.get("PixelSpacing", [1.0, 1.0]))
    slice_spacing = float(info.get("SliceSpacing") or info.get("SpacingBetweenSlices") or info.get("SliceThickness") or 1.0)
    spacing = (slice_spacing, row_spacing, col_spacing)
    affine = np.diag([col_spacing, row_spacing, slice_spacing, 1.0]).astype(np.float32)
    return MRIData(
        volume=np.asarray(volume, dtype=np.float32),
        affine=affine,
        spacing=spacing,
        info={**info, "Spacing": spacing, "OrientationNote": "DICOM slices sorted by InstanceNumber with orientation metadata preserved."},
        source_type="DICOM",
        source_label=str(info.get("SeriesDescription", "DICOM series")),
    )


def load_nifti(path: str | Path) -> MRIData:
    nifti = nib.load(str(path))
    canonical = nib.as_closest_canonical(nifti)
    data = canonical.get_fdata(dtype=np.float32)
    if data.ndim == 4:
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D NIfTI image, got shape {data.shape}.")

    # NIfTI is loaded as x, y, z. The viewer uses z, y, x for consistent slicing.
    volume = np.transpose(data, (2, 1, 0)).astype(np.float32)
    zooms = canonical.header.get_zooms()[:3]
    spacing = (float(zooms[2]), float(zooms[1]), float(zooms[0]))
    info = {
        "StudyDate": "Unknown",
        "SeriesDescription": Path(path).name,
        "Plane": "axial",
        "PixelSpacing": [spacing[1], spacing[2]],
        "SliceThickness": spacing[0],
        "SpacingBetweenSlices": None,
        "SliceSpacing": spacing[0],
        "Spacing": spacing,
        "Shape": tuple(int(value) for value in volume.shape),
        "Affine": canonical.affine.tolist(),
        "OrientationNote": "NIfTI loaded with nibabel.as_closest_canonical, then transposed to z/y/x viewer order.",
    }
    return MRIData(volume=volume, affine=canonical.affine, spacing=spacing, info=info, source_type="NIfTI", source_label=Path(path).name)


def save_nifti_mask(mask: np.ndarray, affine: np.ndarray, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nifti_mask = np.transpose(mask.astype(np.uint8), (2, 1, 0))
    nib.save(nib.Nifti1Image(nifti_mask, affine), str(output_path))
    return output_path


def save_nifti_volume(volume: np.ndarray, affine: np.ndarray, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nifti_volume = np.transpose(volume.astype(np.float32), (2, 1, 0))
    nib.save(nib.Nifti1Image(nifti_volume, affine), str(output_path))
    return output_path


def load_nifti_mask(path: str | Path) -> np.ndarray:
    nifti = nib.load(str(path))
    data = nifti.get_fdata(dtype=np.float32)
    if data.ndim == 4:
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D mask, got shape {data.shape}.")
    return np.transpose(data > 0.5, (2, 1, 0))


def save_brain_extracted(volume: np.ndarray, mask: np.ndarray, affine: np.ndarray, output_path: str | Path) -> Path:
    return save_nifti_volume(volume * mask.astype(np.float32), affine, output_path)


def parse_pixel_spacing(value) -> tuple[float, float]:
    try:
        return float(value[0]), float(value[1])
    except Exception:
        return 1.0, 1.0
