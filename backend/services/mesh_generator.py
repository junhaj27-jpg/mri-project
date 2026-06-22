from pathlib import Path
from typing import Sequence

import numpy as np


def numpy_mask_to_glb(
    mask: np.ndarray,
    output_glb_path: str | Path,
    spacing_mm: Sequence[float] = (1.0, 1.0, 1.0),
) -> dict:
    output_glb_path = Path(output_glb_path)
    output_glb_path.parent.mkdir(parents=True, exist_ok=True)

    binary_mask = (mask > 0).astype(np.uint8)
    if np.count_nonzero(binary_mask) == 0:
        raise ValueError("empty mask")

    from skimage import measure
    import trimesh

    spacing = tuple(float(value) for value in spacing_mm[:3])
    verts, faces, normals, _ = measure.marching_cubes(
        binary_mask,
        level=0.5,
        spacing=spacing,
    )

    mesh = trimesh.Trimesh(
        vertices=verts,
        faces=faces,
        vertex_normals=normals,
        process=True,
    )
    mesh.export(str(output_glb_path))

    return {
        "output_glb_path": str(output_glb_path),
        "voxel_count": int(np.count_nonzero(binary_mask)),
        "spacing_mm": list(spacing),
    }


def nifti_mask_to_glb(mask_nifti_path: str | Path, output_glb_path: str | Path) -> dict:
    import nibabel as nib

    nii = nib.load(str(mask_nifti_path))
    mask = nii.get_fdata()
    spacing = nii.header.get_zooms()[:3]
    return numpy_mask_to_glb(mask, output_glb_path, spacing)
