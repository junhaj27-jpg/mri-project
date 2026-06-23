from __future__ import annotations

from pathlib import Path


def generate_mesh_placeholder(filename: str, tumor_mask_id: str) -> dict:
    stem = Path(filename.replace(".nii.gz", "")).stem
    mesh_path = Path("outputs/private") / f"{stem}_tumor_mesh.glb"

    return {
        "filename": filename,
        "tumor_mask_id": tumor_mask_id,
        "mesh_path": str(mesh_path),
        "format": "glb",
        "status": "placeholder_not_written",
    }
