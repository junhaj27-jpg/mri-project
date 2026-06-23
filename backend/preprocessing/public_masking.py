from __future__ import annotations


def build_public_masking_placeholder(filename: str, metadata: dict) -> dict:
    label = metadata["public_label"]
    anatomy = metadata["anatomy"]
    base_name = f"mock_{anatomy}_{label}"

    return {
        "filename": filename,
        "mask_type": "2d_public_demo_mask",
        "mask_label": label,
        "anatomy": anatomy,
        "mask_path": f"sample_data/kaggle_2d_demo/masks/{base_name}_mask.png",
        "overlay_path": f"sample_data/kaggle_2d_demo/masks/{base_name}_overlay.png",
        "status": "placeholder",
        "volume_measurement": "disabled",
        "note": "Public 2D mask for demo/fine-tuning prep only; not a private 3D segmentation mask.",
    }
