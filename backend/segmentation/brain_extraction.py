from __future__ import annotations


def extract_brain_placeholder(filename: str) -> dict:
    return {
        "filename": filename,
        "mask_id": "brain_mask_placeholder",
        "algorithm": "placeholder_brain_extraction",
        "status": "not_inferred",
    }
