from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_ROOT = PROJECT_ROOT / "sample_data" / "kaggle_2d_demo"
MANIFEST_PATH = DEMO_ROOT / "manifest.csv"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_PUBLIC_TARGETS = {("brain_mri", "tumor"), ("lumbar_mri", "normal")}
PRIVATE_EXTENSIONS = {
    ".dcm",
    ".dicom",
    ".ima",
    ".nii",
    ".gz",
    ".nrrd",
    ".mha",
    ".mhd",
    ".mgz",
    ".npy",
    ".npz",
}


@dataclass(frozen=True)
class KaggleSource:
    name: str
    dataset: str
    anatomy: str
    label: str
    target: Path
    generate_reference_masks: bool = True
    max_files: int | None = None


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\uac00-\ud7a3_-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-") or "image"


def normalize_max_files(value: Any) -> int | None:
    if value in (None, ""):
        return None
    max_files = int(value)
    if max_files <= 0:
        raise ValueError("max_files must be greater than 0 when provided.")
    return max_files


def build_source(row: dict[str, Any]) -> KaggleSource:
    dataset = str(row.get("dataset", "")).strip()
    if not dataset or "/" not in dataset:
        raise ValueError("Kaggle dataset slug must use owner/dataset format.")

    anatomy = str(row.get("anatomy", "brain_mri")).strip()
    label = str(row.get("label", "tumor")).strip()
    if (anatomy, label) not in SUPPORTED_PUBLIC_TARGETS:
        raise ValueError(
            f"Unsupported public target {anatomy}/{label}. "
            "Use brain_mri/tumor or lumbar_mri/normal."
        )

    name = str(row.get("name") or dataset.split("/")[-1]).strip()
    return KaggleSource(
        name=slugify(name),
        dataset=dataset,
        anatomy=anatomy,
        label=label,
        target=DEMO_ROOT / anatomy / label,
        generate_reference_masks=bool(row.get("generate_reference_masks", True)),
        max_files=normalize_max_files(row.get("max_files")),
    )


def load_sources(config_path: Path) -> list[KaggleSource]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return [build_source(row) for row in payload.get("sources", [])]


def ensure_kaggle_api():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Kaggle package is not installed. Run: pip install -r requirements.txt\n"
            "Then set KAGGLE_USERNAME/KAGGLE_KEY or place kaggle.json under ~/.kaggle/."
        ) from exc

    api = KaggleApi()
    api.authenticate()
    return api


def download_dataset(api, source: KaggleSource, keep_raw: bool) -> Path:
    raw_dir = DEMO_ROOT / "_downloads" / source.name
    if raw_dir.exists() and not keep_raw:
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(source.dataset, path=str(raw_dir), unzip=True, quiet=False)
    return raw_dir


def is_public_image(path: Path) -> bool:
    lower_name = path.name.lower()
    if lower_name.endswith(".nii.gz"):
        return False
    suffix = path.suffix.lower()
    if suffix in PRIVATE_EXTENSIONS:
        return False
    return suffix in IMAGE_EXTENSIONS


def iter_public_images(raw_dir: Path):
    for path in raw_dir.rglob("*"):
        if path.is_file() and is_public_image(path):
            yield path


def existing_manifest_rows() -> list[dict[str, str]]:
    if not MANIFEST_PATH.exists():
        return []
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_manifest(rows: list[dict[str, str]]) -> None:
    fields = [
        "filename",
        "split",
        "anatomy",
        "label",
        "source",
        "mode",
        "mask_path",
        "overlay_path",
        "use_for_3d_volume",
    ]
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def relative_to_demo(path: Path) -> str:
    return path.resolve().relative_to(DEMO_ROOT.resolve()).as_posix()


def relative_to_project(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def copy_images(source: KaggleSource, raw_dir: Path) -> list[tuple[Path, Path]]:
    source.target.mkdir(parents=True, exist_ok=True)
    copied: list[tuple[Path, Path]] = []
    for index, image_path in enumerate(iter_public_images(raw_dir), start=1):
        if source.max_files is not None and len(copied) >= source.max_files:
            break

        name = slugify(image_path.stem)
        ext = image_path.suffix.lower()
        output_name = f"{source.name}_{index:05d}_{name}{ext}"
        output_path = source.target / output_name
        counter = 1
        while output_path.exists():
            output_path = source.target / f"{source.name}_{index:05d}_{name}_{counter}{ext}"
            counter += 1
        shutil.copy2(image_path, output_path)
        copied.append((image_path, output_path))
    return copied


def write_reference_mask(image_path: Path, source: KaggleSource) -> tuple[str, str]:
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError:
        return "", ""

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return "", ""

    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    center = (width // 2, height // 2)
    axes = (max(width // 7, 8), max(height // 6, 8))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)

    overlay = image.copy()
    color = np.zeros_like(image)
    color[:, :, 2] = 255
    overlay = np.where(mask[:, :, None] > 0, (0.65 * overlay + 0.35 * color).astype(np.uint8), overlay)

    mask_dir = DEMO_ROOT / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    base = f"{image_path.stem}_reference"
    mask_path = mask_dir / f"{base}_mask.png"
    overlay_path = mask_dir / f"{base}_overlay.png"
    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(overlay_path), overlay)
    return relative_to_demo(mask_path), relative_to_demo(overlay_path)


def append_manifest_for_copies(source: KaggleSource, copies: list[tuple[Path, Path]]) -> None:
    rows = existing_manifest_rows()
    existing_filenames = {row["filename"] for row in rows if row.get("filename")}

    for _raw_path, output_path in copies:
        filename = relative_to_demo(output_path)
        if filename in existing_filenames:
            continue

        mask_path = ""
        overlay_path = ""
        if source.generate_reference_masks:
            mask_path, overlay_path = write_reference_mask(output_path, source)

        rows.append(
            {
                "filename": filename,
                "split": "train",
                "anatomy": source.anatomy,
                "label": source.label,
                "source": f"kaggle:{source.dataset}",
                "mode": "public_2d_demo",
                "mask_path": mask_path,
                "overlay_path": overlay_path,
                "use_for_3d_volume": "false",
            }
        )
        existing_filenames.add(filename)

    write_manifest(rows)


def import_source_objects(sources: list[KaggleSource], keep_raw: bool = False) -> list[dict[str, Any]]:
    if not sources:
        raise SystemExit("No Kaggle sources were provided.")

    api = ensure_kaggle_api()
    reports: list[dict[str, Any]] = []
    for source in sources:
        print(f"Downloading Kaggle dataset: {source.dataset} -> {source.anatomy}/{source.label}")
        raw_dir = download_dataset(api, source, keep_raw=keep_raw)
        copies = copy_images(source, raw_dir)
        append_manifest_for_copies(source, copies)
        report = {
            "name": source.name,
            "dataset": source.dataset,
            "anatomy": source.anatomy,
            "label": source.label,
            "target_dir": relative_to_project(source.target),
            "download_dir": relative_to_project(raw_dir),
            "manifest_path": relative_to_project(MANIFEST_PATH),
            "imported_count": len(copies),
            "sample_files": [relative_to_demo(output_path) for _raw, output_path in copies[:5]],
            "max_files": source.max_files,
            "reference_masks": source.generate_reference_masks,
        }
        reports.append(report)
        print(f"Imported {len(copies)} public JPG/PNG files for {source.name}")
    return reports


def import_sources(config_path: Path, keep_raw: bool) -> list[dict[str, Any]]:
    return import_source_objects(load_sources(config_path), keep_raw=keep_raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Directly download public Kaggle JPG/PNG MRI data into sample_data.")
    parser.add_argument("--dataset", help="Kaggle dataset slug, for example owner/dataset-name.")
    parser.add_argument("--name", help="Local source name. Defaults to the dataset slug name.")
    parser.add_argument("--anatomy", default="brain_mri", choices=["brain_mri", "lumbar_mri"])
    parser.add_argument("--label", default="tumor", choices=["tumor", "normal"])
    parser.add_argument("--max-files", type=int, help="Maximum public JPG/PNG files to import from this dataset.")
    parser.add_argument(
        "--config",
        default=str(DEMO_ROOT / "kaggle_sources.json"),
        help="Path to Kaggle source config JSON when --dataset is not provided.",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep existing _downloads content instead of cleaning each source cache before download.",
    )
    args = parser.parse_args()

    if args.dataset:
        sources = [
            build_source(
                {
                    "name": args.name,
                    "dataset": args.dataset,
                    "anatomy": args.anatomy,
                    "label": args.label,
                    "max_files": args.max_files,
                    "generate_reference_masks": True,
                }
            )
        ]
        reports = import_source_objects(sources, keep_raw=args.keep_raw)
    else:
        config_path = Path(args.config)
        if not config_path.exists():
            raise SystemExit(
                f"Config not found: {config_path}\n"
                "Copy sample_data/kaggle_2d_demo/kaggle_sources.example.json "
                "to kaggle_sources.json and fill in Kaggle dataset slugs, or pass --dataset owner/dataset."
            )
        reports = import_sources(config_path, keep_raw=args.keep_raw)

    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
