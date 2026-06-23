from sqlalchemy import Boolean, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from .database import Base

class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    patient_code = Column(String(50), index=True, nullable=False, default="P001")
    body_region = Column(String(40), index=True, nullable=False, default="BRAIN")
    study_group = Column(String(80), index=True, nullable=False, default="BRAIN_TARGET_TRACKING")
    study_label = Column(String(20), unique=True, index=True, nullable=False)
    event_type = Column(String(80), nullable=False)
    section = Column(String(80), nullable=True)
    hospital_alias = Column(String(50), nullable=True)
    quality_flag = Column(String(80), nullable=True)
    comparison_role = Column(String(80), nullable=True)
    finding_group = Column(String(80), nullable=True)
    diagnosis_alias = Column(String(80), nullable=True, default="PRIVATE_DIAGNOSIS_REDACTED")
    memo = Column(Text, nullable=True)
    sequence_type = Column(String(50), nullable=True)
    modality = Column(String(20), nullable=True, default="MRI")
    voxel_spacing_x = Column(Float, nullable=True)
    voxel_spacing_y = Column(Float, nullable=True)
    voxel_spacing_z = Column(Float, nullable=True)
    slice_count = Column(Integer, nullable=True)
    nifti_path = Column(String(255), nullable=True)
    mask_path = Column(String(255), nullable=True)
    registered_path = Column(String(255), nullable=True)
    preprocess_status = Column(String(50), nullable=True)
    registration_status = Column(String(50), nullable=True)
    segmentation_status = Column(String(50), nullable=True)
    is_sample_data = Column(Boolean, nullable=False, default=True)

    volume_cm3 = Column(Float, nullable=True)
    change_cm3 = Column(Float, nullable=True)
    change_rate_percent = Column(Float, nullable=True)

    preview_url = Column(String(255), nullable=True)
    overlay_url = Column(String(255), nullable=True)
    model_3d_url = Column(String(255), nullable=True)
    structure_models_json = Column(Text, nullable=True)
    structure_volumes_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
