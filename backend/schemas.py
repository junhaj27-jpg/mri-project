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
    volume_cm3: Optional[float] = None
    change_cm3: Optional[float] = None
    change_rate_percent: Optional[float] = None
    preview_url: Optional[str] = None
    overlay_url: Optional[str] = None
    model_3d_url: Optional[str] = None

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
