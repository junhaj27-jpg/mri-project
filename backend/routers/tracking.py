from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Study

router = APIRouter()

@router.get("")
def get_tracking(db: Session = Depends(get_db)):
    rows = db.query(Study).order_by(Study.study_label.asc()).all()
    result = []
    previous = None
    for row in rows:
        change_cm3 = None
        change_rate_percent = None
        if previous is not None and previous.volume_cm3 and row.volume_cm3:
            change_cm3 = round(row.volume_cm3 - previous.volume_cm3, 2)
            change_rate_percent = round((change_cm3 / previous.volume_cm3) * 100, 2)
        result.append({
            "study_label": row.study_label,
            "event_type": row.event_type,
            "section": row.section,
            "hospital_alias": row.hospital_alias,
            "volume_cm3": row.volume_cm3,
            "change_cm3": row.change_cm3 if row.change_cm3 is not None else change_cm3,
            "change_rate_percent": row.change_rate_percent if row.change_rate_percent is not None else change_rate_percent,
            "notice": "T04~T05 구간은 병원 또는 장비 변경 가능성이 있으므로 직접적인 치료 효과 판단 구간으로 사용하지 않습니다.",
        })
        previous = row
    return result
