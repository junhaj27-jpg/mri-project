from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import numpy as np

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class VolumePayload(BaseModel):
    study_label: str
    mask_npy_path: str | None = None
    voxel_count: int | None = None
    spacing_mm: tuple[float, float, float] = (1.0, 1.0, 1.0)

class MeshPayload(BaseModel):
    study_label: str
    mask_npy_path: str
    output_name: str = "lesion_model.glb"

@router.post("/volume")
def calculate_volume(payload: VolumePayload):
    if payload.mask_npy_path:
        path = BASE_DIR / payload.mask_npy_path
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
        "notice": "본 결과는 의료진 진단을 대체하지 않는 연구용 분석 보조 결과입니다.",
    }

@router.post("/mesh")
def create_mesh_from_mask(payload: MeshPayload):
    """
    실제 mask 파일이 준비되면 marching cubes로 GLB를 생성합니다.
    sample 단계에서는 함수 구조만 제공합니다.
    """
    try:
        from skimage import measure
        import trimesh
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"mesh dependencies missing: {exc}")

    mask_path = BASE_DIR / payload.mask_npy_path
    if not mask_path.exists():
        raise HTTPException(status_code=404, detail="mask file not found")

    mask = np.load(mask_path).astype(np.uint8)
    if np.count_nonzero(mask) == 0:
        raise HTTPException(status_code=400, detail="mask is empty")

    verts, faces, normals, values = measure.marching_cubes(mask, level=0.5)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)

    out_dir = BASE_DIR / "media" / "models" / "P001" / payload.study_label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / payload.output_name
    mesh.export(out_path)

    return {
        "study_label": payload.study_label,
        "model_3d_url": f"/media/models/P001/{payload.study_label}/{payload.output_name}",
        "notice": "본 3D 모델은 segmentation mask 기반 연구용 시각화 결과입니다.",
    }
