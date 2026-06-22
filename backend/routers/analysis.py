from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import numpy as np

from ..services.mesh_generator import nifti_mask_to_glb, numpy_mask_to_glb
from ..services.nifti_volume import calculate_nifti_mask_volume
from ..services.structure_masks import extract_region_masks

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
NOTICE = "본 결과는 의료진 진단을 대체하지 않는 연구용 분석 보조 결과입니다."

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
        raise HTTPException(status_code=400, detail="mask_npy_path 또는 voxel_count가 필요합니다")

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
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "study_label": payload.study_label,
        **volume_info,
        "notice": NOTICE,
    }

@router.post("/mesh")
def create_mesh_from_mask(payload: MeshPayload):
    """
    실제 mask 파일이 준비되면 marching cubes로 GLB를 생성합니다.
    sample 단계에서는 함수 구조만 제공합니다.
    """
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
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "study_label": payload.study_label,
        "patient_code": payload.patient_code,
        "model_3d_url": relative_url(out_path),
        "voxel_count": mesh_info["voxel_count"],
        "spacing_mm": mesh_info["spacing_mm"],
        "notice": "본 3D 모델은 segmentation mask 기반 연구용 시각화 결과입니다.",
    }

@router.post("/structure-mesh")
def create_structure_meshes(payload: StructureMeshPayload):
    """
    SynthSeg/FastSurfer 등으로 만든 segmentation label map에서
    대뇌/소뇌/뇌간/해마 mask와 GLB를 생성합니다.
    """
    seg_path = resolve_project_path(payload.seg_nifti_path)
    if not seg_path.exists():
        raise HTTPException(status_code=404, detail="segmentation NIfTI file not found")

    mask_dir = BASE_DIR / "media" / "masks" / payload.patient_code / payload.study_label / "structures"
    model_dir = BASE_DIR / "media" / "models" / payload.patient_code / payload.study_label / "structures"

    try:
        masks = extract_region_masks(seg_path, mask_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    structures = {}
    for region_name, info in masks.items():
        mask_path = Path(info["mask_path"])

        try:
            volume_info = calculate_nifti_mask_volume(mask_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{region_name} volume failed: {exc}")

        model_url = None
        if volume_info["voxel_count"] > 0:
            glb_path = model_dir / f"{region_name}.glb"
            try:
                nifti_mask_to_glb(mask_path, glb_path)
                model_url = relative_url(glb_path)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"{region_name} mesh failed: {exc}")

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
        "notice": "본 구조 분할 결과는 연구용 시각화 결과이며 의료진 진단을 대체하지 않습니다.",
    }
