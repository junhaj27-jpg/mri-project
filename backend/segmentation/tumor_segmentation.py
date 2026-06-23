from __future__ import annotations


def segment_tumor_placeholder(filename: str, brain_mask_id: str) -> dict:
    return {
        "filename": filename,
        "brain_mask_id": brain_mask_id,
        "mask_id": "tumor_mask_placeholder",
        "algorithm": "placeholder_tumor_segmentation",
        "voxel_count": 18420,
        "status": "not_inferred",
    }
