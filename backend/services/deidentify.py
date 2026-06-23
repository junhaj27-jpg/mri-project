REDACTED_DESCRIPTION = "MRI_SERIES_REDACTED"
DIAGNOSIS_ALIAS = "PRIVATE_DIAGNOSIS_REDACTED"

SENSITIVE_KEYS = {
    "PatientID",
    "PatientName",
    "PatientBirthDate",
    "PatientSex",
    "InstitutionName",
    "ReferringPhysicianName",
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "AccessionNumber",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "StudyDescription",
    "SeriesDescription",
    "ProtocolName",
}


def study_group_for_region(body_region: str) -> str:
    return "LUMBAR_SPINE_REVIEW" if body_region == "LUMBAR_SPINE" else "BRAIN_TARGET_TRACKING"


def finding_group_for_region(body_region: str) -> str:
    return "SPINE_REGION_REVIEW" if body_region == "LUMBAR_SPINE" else "TARGET_REGION_TRACKING"


def safe_patient_code(value: str | None) -> str:
    return value if value == "P001" else "P001"


def sanitized_series(index: int, body_region: str, slice_count: int, study_label: str | None = None) -> dict:
    prefix = "LUMBAR_T" if body_region == "LUMBAR_SPINE" else "BRAIN_T"
    label = study_label or f"{prefix}{index:02d}"
    return {
        "series_key": f"SERIES_{index:03d}",
        "study_label": label,
        "modality": "MR",
        "slice_count": slice_count,
        "sanitized_description": REDACTED_DESCRIPTION,
        "finding_group": finding_group_for_region(body_region),
        "diagnosis_alias": DIAGNOSIS_ALIAS,
        "status": "ready" if slice_count else "empty",
    }
