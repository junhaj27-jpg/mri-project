from __future__ import annotations

from ..upload_router import normalized_extension


def build_slice_viewer_placeholder(filename: str) -> dict:
    extension = normalized_extension(filename)
    estimated_slices = 96 if extension.startswith(".nii") else 1

    return {
        "filename": filename,
        "input_type": "NIfTI" if extension.startswith(".nii") else "DICOM",
        "estimated_slices": estimated_slices,
        "viewer_status": "placeholder",
    }
