from __future__ import annotations


def build_2d_preview_metadata(filename: str) -> dict:
    return {
        "filename": filename,
        "dimensions": "read at UI layer",
        "modality": "2D public demo image",
        "status": "ready",
    }
