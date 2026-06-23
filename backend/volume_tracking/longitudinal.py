from __future__ import annotations

import json
from pathlib import Path


def load_mock_longitudinal_series(path: Path) -> dict:
    if not path.exists():
        return {"series": [], "status": "mock_data_missing"}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return {
        "patient_id": payload["patient_id"],
        "series": payload["visits"],
        "status": "mock_data",
    }
