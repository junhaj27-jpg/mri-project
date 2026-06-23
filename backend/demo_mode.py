from __future__ import annotations

from .preprocessing.public_masking import build_public_masking_placeholder
from .public_dataset import infer_public_demo_metadata
from .upload_router import classify_upload


def run_demo_mode(filename: str) -> dict:
    route = classify_upload(filename)
    if route.mode != "demo":
        raise ValueError("Demo Mode accepts only public JPG/PNG 2D MRI data.")

    metadata = infer_public_demo_metadata(filename)
    masking = build_public_masking_placeholder(filename, metadata)

    return {
        "mode": route.mode,
        "enabled_features": route.enabled_features,
        "public_category": metadata,
        "preview": {
            "filename": filename,
            "viewer": "2D MRI Preview",
            "source": metadata["dataset_folder"],
        },
        "classification": {
            "predicted_label": metadata["public_label"],
            "confidence": 0.82,
            "model_status": "placeholder",
        },
        "masking": masking,
        "result_card": {
            "title": "Public 2D Demo Result",
            "summary": "Kaggle-style 2D MRI classification and masking demo only.",
            "volume_measurement": "disabled",
            "private_analysis": "disabled",
        },
    }
