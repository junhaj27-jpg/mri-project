from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Study
from ..schemas import StudyCreate, StudyOut

router = APIRouter()


@router.get("", response_model=list[StudyOut])
def list_studies(db: Session = Depends(get_db)):
    return db.query(Study).order_by(Study.study_label.asc()).all()


@router.get("/{study_label}", response_model=StudyOut)
def get_study(study_label: str, db: Session = Depends(get_db)):
    study = db.query(Study).filter(Study.study_label == study_label).first()
    if not study:
        raise HTTPException(status_code=404, detail="study not found")
    return study


@router.post("", response_model=StudyOut)
def create_study(payload: StudyCreate, db: Session = Depends(get_db)):
    exists = db.query(Study).filter(Study.study_label == payload.study_label).first()
    if exists:
        raise HTTPException(status_code=409, detail="study_label already exists")
    study = Study(**payload.model_dump())
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


@router.post("/seed", response_model=list[StudyOut])
def seed_studies(db: Session = Depends(get_db)):
    seed_rows = [
        {
            "study_label": "T01",
            "event_type": "surgery_follow_up",
            "section": "T01~T04",
            "hospital_alias": "HOSP_A",
            "volume_cm3": 52.8,
            "preview_url": "/media/slices/P001/T01/preview_slice.png",
            "overlay_url": "/media/overlays/P001/T01/overlay.png",
            "memo": "Demo Mode: Kaggle-style 2D preview and mock longitudinal record.",
        },
        {"study_label": "T02", "event_type": "surgery_follow_up", "section": "T01~T04", "hospital_alias": "HOSP_A", "volume_cm3": 50.1},
        {"study_label": "T03", "event_type": "surgery_follow_up", "section": "T01~T04", "hospital_alias": "HOSP_A", "volume_cm3": 48.7},
        {"study_label": "T04", "event_type": "surgery_follow_up", "section": "T01~T04", "hospital_alias": "HOSP_A", "volume_cm3": 45.3},
        {
            "study_label": "T05",
            "event_type": "hospital_transition",
            "section": "T04~T05",
            "hospital_alias": "HOSP_B",
            "volume_cm3": 44.9,
            "memo": "Mock transition interval; do not use as treatment-effect evidence.",
        },
        {"study_label": "T06", "event_type": "chemo_period_estimated", "section": "T05~T07", "hospital_alias": "HOSP_B", "volume_cm3": 42.0},
        {"study_label": "T07", "event_type": "chemo_period_estimated", "section": "T05~T07", "hospital_alias": "HOSP_B", "volume_cm3": 40.8},
        {
            "study_label": "T08",
            "event_type": "post_gamma_knife_follow_up",
            "section": "T08 이후",
            "hospital_alias": "HOSP_B",
            "volume_cm3": 39.4,
            "change_cm3": -2.6,
            "change_rate_percent": -6.19,
            "preview_url": "/media/slices/P001/T08/preview_slice.png",
            "overlay_url": "/media/overlays/P001/T08/overlay.png",
            "memo": "Demo 2D preview only; real 3D volume analysis uses private NIfTI/DICOM input.",
        },
        {"study_label": "T09", "event_type": "stable_follow_up", "section": "T09~T12", "hospital_alias": "HOSP_B", "volume_cm3": 39.1},
        {"study_label": "T10", "event_type": "stable_follow_up", "section": "T09~T12", "hospital_alias": "HOSP_B", "volume_cm3": 38.9},
        {"study_label": "T11", "event_type": "stable_follow_up", "section": "T09~T12", "hospital_alias": "HOSP_B", "volume_cm3": 38.7},
        {"study_label": "T12", "event_type": "stable_follow_up", "section": "T09~T12", "hospital_alias": "HOSP_B", "volume_cm3": 38.5},
    ]
    for row in seed_rows:
        study = db.query(Study).filter(Study.study_label == row["study_label"]).first()
        if study:
            for key, value in row.items():
                setattr(study, key, value)
            study.patient_code = "P001"
            study.is_sample_data = True
            study.model_3d_url = None
            continue
        db.add(Study(patient_code="P001", is_sample_data=True, model_3d_url=None, **row))
    db.commit()
    return db.query(Study).order_by(Study.study_label.asc()).all()
