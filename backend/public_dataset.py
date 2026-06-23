from __future__ import annotations


PUBLIC_LABELS = ("tumor", "normal")
PUBLIC_ANATOMIES = ("brain_mri", "lumbar_mri")


def infer_public_demo_metadata(filename: str) -> dict:
    lower_name = filename.lower().replace("\\", "/")

    if any(token in lower_name for token in ("lumbar", "spine", "back", "lowerback", "lowback", "waist", "normal", "\ud5c8\ub9ac")):
        anatomy = "lumbar_mri"
        public_label = "normal"
    else:
        anatomy = "brain_mri"
        public_label = "tumor"

    return {
        "anatomy": anatomy,
        "public_label": public_label,
        "allowed_labels": PUBLIC_LABELS,
        "allowed_anatomies": PUBLIC_ANATOMIES,
        "dataset_folder": f"sample_data/kaggle_2d_demo/{anatomy}/{public_label}",
    }
