from pydantic import BaseModel
from typing import Optional

NOTICE = "본 결과는 의료진 진단을 대체하지 않는 연구용 분석 보조 결과입니다."

class StudyBase(BaseModel):
    patient_code: str = "P001"
    study_label: str
    event_type: str
    section: Optional[str] = None
    hospital_alias: Optional[str] = None
    memo: Optional[str] = None
    sequence_type: Optional[str] = None
    modality: Optional[str] = "MRI"
    voxel_spacing_x: Optional[float] = None
    voxel_spacing_y: Optional[float] = None
    voxel_spacing_z: Optional[float] = None
    slice_count: Optional[int] = None
    nifti_path: Optional[str] = None
    mask_path: Optional[str] = None
    registered_path: Optional[str] = None
    preprocess_status: Optional[str] = None
    registration_status: Optional[str] = None
    segmentation_status: Optional[str] = None
    is_sample_data: bool = True
    volume_cm3: Optional[float] = None
    change_cm3: Optional[float] = None
    change_rate_percent: Optional[float] = None
    preview_url: Optional[str] = None
    overlay_url: Optional[str] = None
    model_3d_url: Optional[str] = None
    structure_models_json: Optional[str] = None
    structure_volumes_json: Optional[str] = None

class StudyCreate(StudyBase):
    pass

class StudyOut(StudyBase):
    id: int
    notice: str = NOTICE

    class Config:
        from_attributes = True

class VolumeResult(BaseModel):
    study_label: str
    voxel_count: int
    spacing_mm: tuple[float, float, float]
    volume_cm3: float
    notice: str = NOTICE
