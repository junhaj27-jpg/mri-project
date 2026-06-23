from __future__ import annotations

from pathlib import Path

from .mesh_generation.mesh import generate_mesh_placeholder
from .preprocessing.medical_io import build_slice_viewer_placeholder
from .segmentation.brain_extraction import extract_brain_placeholder
from .segmentation.tumor_segmentation import segment_tumor_placeholder
from .upload_router import classify_upload
from .volume_tracking.longitudinal import load_mock_longitudinal_series
from .volume_tracking.measurement import measure_volume_placeholder

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_private_analysis(filename: str) -> dict:
    route = classify_upload(filename)
    if route.mode != "private_analysis":
        raise ValueError("Private Analysis Mode accepts only NIfTI/DICOM MRI data.")

    slice_viewer = build_slice_viewer_placeholder(filename)
    brain = extract_brain_placeholder(filename)
    tumor = segment_tumor_placeholder(filename, brain_mask_id=brain["mask_id"])
    volume = measure_volume_placeholder(tumor["voxel_count"])
    mesh = generate_mesh_placeholder(filename, tumor_mask_id=tumor["mask_id"])
    tracking = load_mock_longitudinal_series(
        PROJECT_ROOT / "sample_data" / "mock_longitudinal" / "longitudinal_mock.json"
    )

    return {
        "mode": route.mode,
        "enabled_features": route.enabled_features,
        "slice_viewer": slice_viewer,
        "brain_extraction": brain,
        "tumor_segmentation": tumor,
        "mesh_generation": mesh,
        "volume_measurement": volume,
        "longitudinal_tracking": tracking,
    }
