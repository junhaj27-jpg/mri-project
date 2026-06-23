from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.deidentify import safe_patient_code, study_group_for_region
from ..services.dicom_scanner import scan_dicom_folder
from ..services.model_catalog import filter_model_catalog, load_model_catalog
from ..services.private_pipeline import list_manifests, run_private_pipeline

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALLOWED_REGIONS = {"BRAIN", "LUMBAR_SPINE"}


class PrivateScanPayload(BaseModel):
    patient_code: str = "P001"
    body_region: str = "BRAIN"
    dicom_root_path: str
    study_label_start: str | None = None


class PrivatePipelinePayload(PrivateScanPayload):
    auto_convert_nifti: bool = False
    auto_generate_mesh: bool = False


def normalized_region(value: str) -> str:
    region = value.upper()
    if region not in ALLOWED_REGIONS:
        raise HTTPException(status_code=400, detail="body_region must be BRAIN or LUMBAR_SPINE")
    return region


def resolve_private_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        raise HTTPException(status_code=400, detail="Use a project-relative private path.")
    target = (BASE_DIR / path).resolve()
    base = BASE_DIR.resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Path escapes project directory.")
    return target


def default_label(body_region: str) -> str:
    return "LUMBAR_T01" if body_region == "LUMBAR_SPINE" else "BRAIN_T01"


@router.post("/scan-dicom")
def scan_dicom(payload: PrivateScanPayload):
    patient_code = safe_patient_code(payload.patient_code)
    body_region = normalized_region(payload.body_region)
    root = resolve_private_path(payload.dicom_root_path)
    try:
        result = scan_dicom_folder(root, body_region, payload.study_label_start or default_label(body_region))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "patient_code": patient_code,
        **result,
    }


@router.post("/run-pipeline")
def run_pipeline(payload: PrivatePipelinePayload):
    patient_code = safe_patient_code(payload.patient_code)
    body_region = normalized_region(payload.body_region)
    root = resolve_private_path(payload.dicom_root_path)
    try:
        return run_private_pipeline(
            BASE_DIR,
            patient_code,
            body_region,
            root,
            payload.study_label_start or default_label(body_region),
            payload.auto_convert_nifti,
            payload.auto_generate_mesh,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/manifest/{patient_code}")
def manifest(patient_code: str):
    return list_manifests(BASE_DIR, safe_patient_code(patient_code))


@router.get("/model-catalog")
def model_catalog(body_region: str | None = None, mode: str | None = None):
    region = normalized_region(body_region) if body_region else None
    catalog = load_model_catalog(BASE_DIR)
    return filter_model_catalog(catalog, region, mode)


@router.get("/policy")
def private_policy():
    return {
        "mode": "private_analysis",
        "allowed_body_regions": sorted(ALLOWED_REGIONS),
        "study_groups": {
            region: study_group_for_region(region) for region in sorted(ALLOWED_REGIONS)
        },
        "model_catalog_endpoint": "/api/private/model-catalog",
        "warning": "Use only local ignored DICOM/NIfTI folders. Raw metadata is never returned.",
    }
