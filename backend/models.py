from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from .database import Base

class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    patient_code = Column(String(50), index=True, nullable=False, default="P001")
    study_label = Column(String(20), unique=True, index=True, nullable=False)
    event_type = Column(String(80), nullable=False)
    section = Column(String(80), nullable=True)
    hospital_alias = Column(String(50), nullable=True)
    memo = Column(Text, nullable=True)

    volume_cm3 = Column(Float, nullable=True)
    change_cm3 = Column(Float, nullable=True)
    change_rate_percent = Column(Float, nullable=True)

    preview_url = Column(String(255), nullable=True)
    overlay_url = Column(String(255), nullable=True)
    model_3d_url = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
