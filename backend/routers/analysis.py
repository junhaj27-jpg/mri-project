from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..demo_mode import run_demo_mode
from ..private_mode import run_private_analysis
from ..services.mesh_generator import nifti_mask_to_glb, numpy_mask_to_glb
from ..services.nifti_volume import calculate_nifti_mask_volume
from ..services.structure_masks import extract_region_masks
from ..upload_router import UnsupportedUploadError, classify_upload

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
NOTICE = "Research prototype only. This is not medical diagnosis or treatment guidance."


class UploadRoutePayload(BaseModel):
    filename: str


class KaggleDirectImportPayload(BaseModel):
    dataset: str
    anatomy: str = "brain_mri"
    label: str = "tumor"
    name: str | None = None
    max_files: int | None = 200
    generate_reference_masks: bool = True
    keep_raw: bool = False


class VolumePayload(BaseModel):
    study_label: str
    mask_npy_path: str | None = None
    voxel_count: int | None = None
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0)


class NiftiVolumePayload(BaseModel):
    study_label: str
    mask_nifti_path: str


class MeshPayload(BaseModel):
    study_label: str
    mask_npy_path: str
    patient_code: str = "P001"
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0)
    output_name: str = "lesion_model.glb"


class StructureMeshPayload(BaseModel):
    study_label: str
    seg_nifti_path: str
    patient_code: str = "P001"


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        raise HTTPException(status_code=400, detail="absolute paths are not allowed")

    base = BASE_DIR.resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=400, detail="path escapes project directory")
    return target


def relative_url(path: Path) -> str:
    return "/" + str(path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")


def route_response(filename: str) -> dict:
    try:
        route = classify_upload(filename)
    except UnsupportedUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(route)


@router.post("/upload-route")
def classify_upload_route(payload: UploadRoutePayload):
    return route_response(payload.filename)


@router.post("/demo-result")
def demo_result(payload: UploadRoutePayload):
    try:
        return run_demo_mode(payload.filename)
    except (UnsupportedUploadError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/private-placeholder")
def private_placeholder(payload: UploadRoutePayload):
    try:
        return run_private_analysis(payload.filename)
    except (UnsupportedUploadError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/kaggle-direct-import")
def kaggle_direct_import(payload: KaggleDirectImportPayload):
    if payload.max_files is not None and payload.max_files <= 0:
        raise HTTPException(status_code=400, detail="max_files must be greater than 0")

    try:
        from scripts.import_kaggle_demo import build_source, import_source_objects

        source = build_source(
            {
                "name": payload.name or payload.dataset.split("/")[-1],
                "dataset": payload.dataset,
                "anatomy": payload.anatomy,
                "label": payload.label,
                "max_files": payload.max_files,
                "generate_reference_masks": payload.generate_reference_masks,
            }
        )
        reports = import_source_objects([source], keep_raw=payload.keep_raw)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Kaggle direct import failed: {exc}") from exc

    return {
        "mode": "public_2d_demo",
        "source": "kaggle_api_direct_download",
        "report": reports[0],
        "notice": "Kaggle JPG/PNG files are public demo/fine-tuning data only and are not used for 3D volume measurement.",
    }


@router.post("/upload")
async def classify_uploaded_file(file: UploadFile = File(...)):
    filename = file.filename or "uploaded"
    route = route_response(filename)
    result = run_demo_mode(filename) if route["mode"] == "demo" else run_private_analysis(filename)
    return {
        "route": route,
        "result": result,
        "saved": False,
        "notice": "Upload was classified by extension only. Private files are not saved by this placeholder endpoint.",
    }


@router.post("/volume")
def calculate_volume(payload: VolumePayload):
    if payload.mask_npy_path:
        path = resolve_project_path(payload.mask_npy_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="mask file not found")
        mask = np.load(path)
        voxel_count = int(np.count_nonzero(mask))
    elif payload.voxel_count is not None:
        voxel_count = payload.voxel_count
    else:
        raise HTTPException(status_code=400, detail="mask_npy_path or voxel_count is required")

    voxel_volume_mm3 = float(payload.spacing_mm[0] * payload.spacing_mm[1] * payload.spacing_mm[2])
    volume_cm3 = round((voxel_count * voxel_volume_mm3) / 1000.0, 3)
    return {
        "study_label": payload.study_label,
        "voxel_count": voxel_count,
        "spacing_mm": payload.spacing_mm,
        "volume_cm3": volume_cm3,
        "notice": NOTICE,
    }


@router.post("/volume/nifti")
def calculate_volume_from_nifti(payload: NiftiVolumePayload):
    mask_path = resolve_project_path(payload.mask_nifti_path)
    if not mask_path.exists():
        raise HTTPException(status_code=404, detail="mask NIfTI file not found")

    try:
        volume_info = calculate_nifti_mask_volume(mask_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "study_label": payload.study_label,
        **volume_info,
        "notice": NOTICE,
    }


@router.post("/mesh")
def create_mesh_from_mask(payload: MeshPayload):
    mask_path = resolve_project_path(payload.mask_npy_path)
    if not mask_path.exists():
        raise HTTPException(status_code=404, detail="mask file not found")

    mask = np.load(mask_path).astype(np.uint8)
    if np.count_nonzero(mask) == 0:
        raise HTTPException(status_code=400, detail="mask is empty")

    out_dir = BASE_DIR / "media" / "models" / payload.patient_code / payload.study_label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / payload.output_name

    try:
        mesh_info = numpy_mask_to_glb(mask, out_path, payload.spacing_mm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "study_label": payload.study_label,
        "patient_code": payload.patient_code,
        "model_3d_url": relative_url(out_path),
        "voxel_count": mesh_info["voxel_count"],
        "spacing_mm": mesh_info["spacing_mm"],
        "notice": "3D model generated from a private segmentation mask.",
    }


@router.post("/structure-mesh")
def create_structure_meshes(payload: StructureMeshPayload):
    seg_path = resolve_project_path(payload.seg_nifti_path)
    if not seg_path.exists():
        raise HTTPException(status_code=404, detail="segmentation NIfTI file not found")

    mask_dir = BASE_DIR / "media" / "masks" / payload.patient_code / payload.study_label / "structures"
    model_dir = BASE_DIR / "media" / "models" / payload.patient_code / payload.study_label / "structures"

    try:
        masks = extract_region_masks(seg_path, mask_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    structures = {}
    for region_name, info in masks.items():
        mask_path = Path(info["mask_path"])

        try:
            volume_info = calculate_nifti_mask_volume(mask_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{region_name} volume failed: {exc}") from exc

        model_url = None
        if volume_info["voxel_count"] > 0:
            glb_path = model_dir / f"{region_name}.glb"
            try:
                nifti_mask_to_glb(mask_path, glb_path)
                model_url = relative_url(glb_path)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"{region_name} mesh failed: {exc}") from exc

        structures[region_name] = {
            "labels": info["labels"],
            "mask_path": str(mask_path.resolve().relative_to(BASE_DIR.resolve())),
            "model_3d_url": model_url,
            "voxel_count": volume_info["voxel_count"],
            "spacing_mm": volume_info["spacing_mm"],
            "volume_cm3": volume_info["volume_cm3"],
        }

    return {
        "study_label": payload.study_label,
        "patient_code": payload.patient_code,
        "structures": structures,
        "notice": NOTICE,
    }
