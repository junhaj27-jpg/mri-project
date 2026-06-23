from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["demo", "private_analysis"]

DEMO_FEATURES = (
    "2D MRI Preview",
    "Classification Demo",
    "Public 2D Reference Mask Demo",
    "Example Result Card",
)

PRIVATE_ANALYSIS_FEATURES = (
    "Slice Viewer",
    "Brain Extraction",
    "Tumor Segmentation",
    "3D Mesh Generation",
    "Volume Measurement",
    "Longitudinal Tracking",
)


@dataclass(frozen=True)
class UploadRoute:
    filename: str
    extension: str
    mode: Mode
    file_kind: str
    enabled_features: tuple[str, ...]
