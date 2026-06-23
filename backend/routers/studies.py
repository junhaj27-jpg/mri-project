from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Study
from ..schemas import StudyCreate, StudyOut

router = APIRouter()

BRAIN_VALUES = [
    52.8, 50.1, 48.7, 45.3, 44.9, 42.0, 39.8, 36.5, 34.1, 31.6, 29.4, 27.9, 26.2, 24.8
]


def brain_seed_row(index: int, previous: float | None) -> dict:
    label = f"T{index:02d}"
    volume = BRAIN_VALUES[index - 1]
    if index <= 4:
        event_type = "initial_reference"
        section = "BRAIN_T01~BRAIN_T04"
        hospital_alias = "HOSP_A"
        quality_flag = "baseline_reference"
        comparison_role = "reference_only"
        note = "mock demo value; cross-hospital comparison caution"
    elif index == 5:
        event_type = "hospital_transition"
        section = "BRAIN_T04~BRAIN_T05"
        hospital_alias = "HOSP_B"
        quality_flag = "transition_caution"
        comparison_role = "transition_point"
        note = "mock demo value; hospital or scanner transition point"
    else:
        event_type = "long_term_follow_up"
        section = "BRAIN_T06~BRAIN_T14"
        hospital_alias = "HOSP_B"
        quality_flag = "longitudinal_tracking"
        comparison_role = "tracking_target"
        note = "mock demo value; longitudinal volume tracking reference"

    change_cm3 = None if previous is None else round(volume - previous, 2)
    change_rate = None if previous is None else round((change_cm3 / previous) * 100, 2)
    return {
        "patient_code": "P001",
        "body_region": "BRAIN",
        "study_group": "BRAIN_TARGET_TRACKING",
        "study_label": label,
        "event_type": event_type,
        "section": section,
        "hospital_alias": hospital_alias,
        "quality_flag": quality_flag,
        "comparison_role": comparison_role,
        "finding_group": "TARGET_REGION_TRACKING",
        "diagnosis_alias": "PRIVATE_DIAGNOSIS_REDACTED",
        "volume_cm3": volume,
        "change_cm3": change_cm3,
        "change_rate_percent": change_rate,
        "preview_url": "/sample_data/kaggle_2d_demo/brain_mri/tumor/mock_brain_tumor.png",
        "overlay_url": "/sample_data/kaggle_2d_demo/masks/mock_brain_mri_tumor_overlay.png",
        "memo": note,
    }


def seed_rows() -> list[dict]:
    rows = []
    previous = None
    for index in range(1, 15):
        row = brain_seed_row(index, previous)
        rows.append(row)
        previous = row["volume_cm3"]

    rows.append({
        "patient_code": "P001",
        "body_region": "LUMBAR_SPINE",
        "study_group": "LUMBAR_SPINE_REVIEW",
        "study_label": "LUMBAR_T01",
        "event_type": "lumbar_reference_review",
        "section": "LUMBAR_REFERENCE",
        "hospital_alias": "HOSP_PRIVATE",
        "quality_flag": "private_reference",
        "comparison_role": "reference_review",
        "finding_group": "SPINE_REGION_REVIEW",
        "diagnosis_alias": "PRIVATE_DIAGNOSIS_REDACTED",
        "volume_cm3": None,
        "preview_url": "/sample_data/kaggle_2d_demo/lumbar_mri/normal/mock_lumbar_normal.png",
        "overlay_url": "/sample_data/kaggle_2d_demo/masks/mock_lumbar_mri_normal_overlay.png",
        "memo": "mock lumbar private review placeholder; not for diagnosis",
    })
    return rows


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
    for row in seed_rows():
        study = db.query(Study).filter(Study.study_label == row["study_label"]).first()
        if study:
            for key, value in row.items():
                setattr(study, key, value)
            study.is_sample_data = True
            study.model_3d_url = None
            continue
        db.add(Study(is_sample_data=True, model_3d_url=None, **row))
    db.commit()
    return db.query(Study).order_by(Study.study_label.asc()).all()
