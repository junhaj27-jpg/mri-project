from __future__ import annotations

from pathlib import Path

from .mode_schemas import DEMO_FEATURES, PRIVATE_ANALYSIS_FEATURES, UploadRoute

DEMO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PRIVATE_ANALYSIS_EXTENSIONS = {".nii", ".nii.gz", ".dcm", ".dicom", ".ima"}


class UnsupportedUploadError(ValueError):
    """Raised when an upload cannot be routed to a supported mode."""


def normalized_extension(filename: str) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".nii.gz"):
        return ".nii.gz"
    return Path(lower_name).suffix


def classify_upload(filename: str) -> UploadRoute:
    extension = normalized_extension(filename)

    if extension in DEMO_EXTENSIONS:
        return UploadRoute(
            filename=filename,
            extension=extension,
            mode="demo",
            file_kind="kaggle_2d_demo",
            enabled_features=DEMO_FEATURES,
        )

    if extension in PRIVATE_ANALYSIS_EXTENSIONS:
        file_kind = "nifti" if extension.startswith(".nii") else "dicom"
        return UploadRoute(
            filename=filename,
            extension=extension,
            mode="private_analysis",
            file_kind=file_kind,
            enabled_features=PRIVATE_ANALYSIS_FEATURES,
        )

    supported = ", ".join(sorted(DEMO_EXTENSIONS | PRIVATE_ANALYSIS_EXTENSIONS))
    raise UnsupportedUploadError(
        f"Unsupported upload type '{extension or 'unknown'}'. Supported types: {supported}."
    )
