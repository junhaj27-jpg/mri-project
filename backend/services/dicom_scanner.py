from pathlib import Path

from .deidentify import sanitized_series, study_group_for_region

DICOM_EXTENSIONS = {".dcm", ".dicom", ".ima", ""}
WARNING = "Private analysis result is not for diagnosis. Raw DICOM metadata is not exposed."


def scan_dicom_folder(root: Path, body_region: str, study_label_start: str | None = None) -> dict:
    if not root.exists():
        raise FileNotFoundError("DICOM root path not found.")
    if not root.is_dir():
        raise NotADirectoryError("DICOM root path must be a directory.")

    files = [
        path for path in root.rglob("*")
        if path.is_file() and (path.suffix.lower() in DICOM_EXTENSIONS)
    ]
    grouped: dict[Path, list[Path]] = {}
    for path in files:
        grouped.setdefault(path.parent, []).append(path)

    series = []
    for index, (_, paths) in enumerate(sorted(grouped.items(), key=lambda item: str(item[0])), start=1):
        study_label = study_label_start if index == 1 and study_label_start else None
        series.append(sanitized_series(index, body_region, len(paths), study_label))

    return {
        "mode": "private_analysis",
        "body_region": body_region,
        "study_group": study_group_for_region(body_region),
        "series_count": len(series),
        "series": series,
        "warning": WARNING,
    }
