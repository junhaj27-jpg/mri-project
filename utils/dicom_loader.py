from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pydicom


DISCOVERY_TAGS = [
    "Modality",
    "StudyDate",
    "SeriesDescription",
    "SeriesInstanceUID",
    "SeriesNumber",
    "Rows",
    "Columns",
    "NumberOfFrames",
    "ImageOrientationPatient",
    "PixelSpacing",
    "SliceThickness",
    "SpacingBetweenSlices",
]

IGNORED_SUFFIXES = {
    ".exe",
    ".dll",
    ".htm",
    ".html",
    ".gif",
    ".ico",
    ".inf",
    ".mdb",
    ".txt",
    ".ini",
    ".xml",
    ".css",
    ".js",
}


def discover_dicom_series(folder_path: str | Path) -> list[dict]:
    folder = normalize_folder(folder_path)
    series: dict[str, dict] = {}

    for path in iter_candidate_files(folder):
        try:
            ds = pydicom.dcmread(
                str(path),
                stop_before_pixels=True,
                force=True,
                specific_tags=DISCOVERY_TAGS,
            )
        except Exception:
            continue
        if not getattr(ds, "Rows", None) or not getattr(ds, "Columns", None):
            continue

        key = str(getattr(ds, "SeriesInstanceUID", "")) or str(path.parent)
        item = series.setdefault(
            key,
            {
                "key": key,
                "paths": [],
                "description": str(getattr(ds, "SeriesDescription", "Unknown")),
                "modality": str(getattr(ds, "Modality", "Unknown")),
                "study_date": format_dicom_date(str(getattr(ds, "StudyDate", "Unknown"))),
                "series_number": str(getattr(ds, "SeriesNumber", "")),
                "shape": dicom_shape_label(ds),
            },
        )
        item["paths"].append(path)

    result = []
    for item in series.values():
        item["paths"] = sorted(item["paths"])
        item["file_count"] = len(item["paths"])
        result.append(item)

    result.sort(key=series_sort_key)
    return result


def series_sort_key(item: dict) -> tuple[int, int, str, str, str]:
    description = str(item.get("description", "")).lower()
    modality = str(item.get("modality", "")).upper()
    file_count = int(item.get("file_count", 0))

    scout_words = ("lateral", "ap", "topogram", "protocol", "unknown", "scout", "localizer")
    mri_words = ("t1", "t2", "flair", "mpr", "sag", "tra", "cor", "hemo", "brain")

    is_scout = file_count <= 2 or any(word in description for word in scout_words)
    is_mri_like = modality == "MR" or any(word in description for word in mri_words)
    priority = 0 if is_mri_like and not is_scout and file_count >= 10 else 1
    return (priority, -file_count, item.get("study_date", ""), item.get("series_number", ""), item["description"])


def load_dicom_volume(paths_or_folder: str | Path, series_key: str | None = None) -> tuple[np.ndarray, dict]:
    folder = normalize_folder(paths_or_folder)
    series = discover_dicom_series(folder)
    if series_key is None:
        paths = series[0]["paths"] if series else []
    else:
        selected = next((item for item in series if str(item.get("key")) == str(series_key)), None)
        paths = selected["paths"] if selected else []
    if not paths:
        raise FileNotFoundError("No readable DICOM files found.")

    slices = []
    skipped = 0
    for path in paths:
        try:
            ds = pydicom.dcmread(str(path), force=True)
            if "PixelData" in ds:
                slices.append((path, ds))
            else:
                skipped += 1
        except Exception:
            skipped += 1

    if not slices:
        raise ValueError("No DICOM files with PixelData were found.")

    slices.sort(key=lambda item: slice_sort_key(item[0], item[1]))
    arrays = [get_pixels(ds) for _, ds in slices]
    volume = stack_arrays(arrays)
    info = get_public_info(slices[0][1], volume, skipped)
    return volume, info


def normalize_folder(folder_path: str | Path) -> Path:
    if not str(folder_path).strip():
        raise ValueError("MRI data folder path is empty.")
    folder = Path(folder_path).expanduser()
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {folder}")

    image_dirs = [path for path in folder.rglob("IMAGE") if path.is_dir()]
    if image_dirs and folder.name.upper() != "IMAGE":
        return image_dirs[0]
    return folder


def iter_candidate_files(folder: Path):
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES:
            continue
        if path.stat().st_size < 132:
            continue
        if path.suffix == "" and not has_dicom_preamble(path):
            continue
        yield path


def has_dicom_preamble(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            header = file.read(132)
    except OSError:
        return False
    return len(header) >= 132 and header[128:132] == b"DICM"


def slice_sort_key(path: Path, ds) -> tuple[int, float, str]:
    """Sort slices by InstanceNumber first, then ImagePositionPatient fallback."""
    try:
        instance_number = int(getattr(ds, "InstanceNumber", 0))
    except Exception:
        instance_number = 0

    position = getattr(ds, "ImagePositionPatient", None)
    if position is not None and len(position) >= 3:
        try:
            return instance_number, float(position[2]), path.name
        except Exception:
            pass
    return instance_number, 0.0, path.name


def get_pixels(ds) -> np.ndarray:
    pixels = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1.0))
    intercept = float(getattr(ds, "RescaleIntercept", 0.0))
    return pixels * slope + intercept


def stack_arrays(arrays: list[np.ndarray]) -> np.ndarray:
    normalized = []
    for array in arrays:
        if array.ndim == 2:
            normalized.append(array[np.newaxis, :, :])
        elif array.ndim == 3:
            normalized.append(array)
        else:
            raise ValueError(f"Unsupported DICOM pixel array shape: {array.shape}")

    shapes = {item.shape[1:] for item in normalized}
    if len(shapes) != 1:
        counts = defaultdict(int)
        for item in normalized:
            counts[item.shape[1:]] += item.shape[0]
        best_shape = max(counts, key=counts.get)
        normalized = [item for item in normalized if item.shape[1:] == best_shape]

    return np.concatenate(normalized, axis=0).astype(np.float32)


def get_public_info(ds, volume: np.ndarray, skipped_files: int) -> dict:
    pixel_spacing = getattr(ds, "PixelSpacing", [1.0, 1.0])
    try:
        pixel_spacing = [float(pixel_spacing[0]), float(pixel_spacing[1])]
    except Exception:
        pixel_spacing = [1.0, 1.0]

    try:
        slice_thickness = float(getattr(ds, "SliceThickness", 1.0))
    except Exception:
        slice_thickness = 1.0

    spacing_between_slices = getattr(ds, "SpacingBetweenSlices", None)
    try:
        spacing_between_slices = float(spacing_between_slices)
    except Exception:
        spacing_between_slices = None

    image_orientation = parse_float_list(getattr(ds, "ImageOrientationPatient", None))
    series_description = str(getattr(ds, "SeriesDescription", "Unknown"))
    plane = infer_plane(image_orientation, series_description)
    slice_spacing = spacing_between_slices if spacing_between_slices is not None else slice_thickness

    return {
        "StudyDate": format_dicom_date(str(getattr(ds, "StudyDate", "Unknown"))),
        "SeriesDescription": series_description,
        "ImageOrientationPatient": image_orientation,
        "Plane": plane,
        "PixelSpacing": pixel_spacing,
        "SliceThickness": slice_thickness,
        "SpacingBetweenSlices": spacing_between_slices,
        "SliceSpacing": slice_spacing,
        "SliceCount": int(volume.shape[0]),
        "Shape": tuple(int(value) for value in volume.shape),
        "SkippedFiles": int(skipped_files),
    }


def parse_float_list(value) -> list[float] | None:
    if value is None:
        return None
    try:
        result = [float(item) for item in value]
    except Exception:
        return None
    return result if len(result) >= 6 else None


def infer_plane(image_orientation: list[float] | None, series_description: str) -> str:
    if image_orientation and len(image_orientation) >= 6:
        row = np.array(image_orientation[:3], dtype=np.float64)
        col = np.array(image_orientation[3:6], dtype=np.float64)
        normal = np.cross(row, col)
        norm = float(np.linalg.norm(normal))
        if norm > 0:
            normal = np.abs(normal / norm)
            axis = int(np.argmax(normal))
            if float(normal[axis]) >= 0.75:
                return ("sagittal", "coronal", "axial")[axis]

    description = str(series_description or "").lower()
    if "sag" in description or "sagittal" in description:
        return "sagittal"
    if "cor" in description or "coronal" in description:
        return "coronal"
    if any(word in description for word in ("ax", "axl", "tra", "trans", "axial")):
        return "axial"
    return "unknown"


def dicom_shape_label(ds) -> str:
    rows = getattr(ds, "Rows", None)
    cols = getattr(ds, "Columns", None)
    frames = getattr(ds, "NumberOfFrames", None)
    if frames:
        return f"{frames} x {rows} x {cols}"
    if rows and cols:
        return f"{rows} x {cols}"
    return "unknown"


def format_dicom_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "Unknown"
