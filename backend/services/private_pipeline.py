import json
from pathlib import Path

from .deidentify import finding_group_for_region, study_group_for_region
from .dicom_scanner import WARNING, scan_dicom_folder
from .dicom_to_nifti import convert_dicom_to_nifti_placeholder


def region_slug(body_region: str) -> str:
    return "lumbar" if body_region == "LUMBAR_SPINE" else "brain"


def manifest_path(base_dir: Path, patient_code: str, body_region: str) -> Path:
    return base_dir / "outputs" / "private" / patient_code / region_slug(body_region) / "manifest.json"


def run_private_pipeline(
    base_dir: Path,
    patient_code: str,
    body_region: str,
    dicom_root_path: Path,
    study_label_start: str,
    auto_convert_nifti: bool = False,
    auto_generate_mesh: bool = False,
) -> dict:
    scan = scan_dicom_folder(dicom_root_path, body_region, study_label_start)
    mapped_studies = [row["study_label"] for row in scan["series"]]
    conversions = [
        convert_dicom_to_nifti_placeholder(patient_code, body_region, label)
        for label in mapped_studies
    ] if auto_convert_nifti else []

    manifest = {
        "patient_code": patient_code,
        "mode": "private_analysis",
        "body_region": body_region,
        "study_group": study_group_for_region(body_region),
        "finding_group": finding_group_for_region(body_region),
        "diagnosis_alias": "PRIVATE_DIAGNOSIS_REDACTED",
        "total_series": scan["series_count"],
        "mapped_studies": mapped_studies,
        "series": scan["series"],
        "nifti_conversion": conversions,
        "mesh_generation": "planned" if auto_generate_mesh else "skipped",
        "warning": WARNING,
    }
    path = manifest_path(base_dir, patient_code, body_region)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**manifest, "output_manifest": str(path.relative_to(base_dir)).replace("\\", "/")}


def list_manifests(base_dir: Path, patient_code: str) -> dict:
    items = []
    for body_region in ("BRAIN", "LUMBAR_SPINE"):
        path = manifest_path(base_dir, patient_code, body_region)
        items.append({
            "body_region": body_region,
            "manifest_path": str(path.relative_to(base_dir)).replace("\\", "/"),
            "status": "available" if path.exists() else "missing",
        })
    return {
        "patient_code": patient_code,
        "manifests": items,
        "warning": "Raw DICOM metadata is not exposed.",
    }
