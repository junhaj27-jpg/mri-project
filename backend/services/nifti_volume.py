from pathlib import Path

import numpy as np


def calculate_nifti_mask_volume(mask_nifti_path: str | Path) -> dict:
    import nibabel as nib

    nii = nib.load(str(mask_nifti_path))
    mask = nii.get_fdata()

    voxel_count = int(np.count_nonzero(mask))
    spacing_x, spacing_y, spacing_z = nii.header.get_zooms()[:3]
    voxel_volume_mm3 = float(spacing_x * spacing_y * spacing_z)
    volume_cm3 = voxel_count * voxel_volume_mm3 / 1000.0

    return {
        "voxel_count": voxel_count,
        "spacing_mm": [float(spacing_x), float(spacing_y), float(spacing_z)],
        "volume_cm3": round(float(volume_cm3), 3),
    }
