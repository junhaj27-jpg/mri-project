from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Study

router = APIRouter()


@router.get("")
def get_tracking(db: Session = Depends(get_db)):
    rows = (
        db.query(Study)
        .filter(Study.body_region == "BRAIN")
        .filter(Study.study_group == "BRAIN_TARGET_TRACKING")
        .order_by(Study.study_label.asc())
        .all()
    )
    result = []
    previous = None
    for row in rows:
        change_cm3 = None
        change_rate_percent = None
        if previous is not None and previous.volume_cm3 and row.volume_cm3:
            change_cm3 = round(row.volume_cm3 - previous.volume_cm3, 2)
            change_rate_percent = round((change_cm3 / previous.volume_cm3) * 100, 2)
        result.append({
            "patient_code": row.patient_code,
            "body_region": row.body_region,
            "study_group": row.study_group,
            "study_label": row.study_label,
            "event_type": row.event_type,
            "section": row.section,
            "hospital_alias": row.hospital_alias,
            "quality_flag": row.quality_flag,
            "comparison_role": row.comparison_role,
            "finding_group": row.finding_group,
            "diagnosis_alias": row.diagnosis_alias,
            "volume_cm3": row.volume_cm3,
            "change_cm3": row.change_cm3 if row.change_cm3 is not None else change_cm3,
            "change_rate_percent": row.change_rate_percent if row.change_rate_percent is not None else change_rate_percent,
            "note": row.memo,
            "notice": "Mock data is not for diagnosis. T05 is a transition point and Lumbar studies are excluded from this chart.",
        })
        previous = row
    return result
