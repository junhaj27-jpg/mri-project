from __future__ import annotations

from pathlib import Path

import pydicom

IDENTIFIER_TAGS = [
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientSex",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "OtherPatientIDs",
    "OtherPatientNames",
    "InstitutionName",
    "ReferringPhysicianName",
]


def anonymize_dicom_file(input_path: str | Path, output_path: str | Path) -> Path:
    ds = pydicom.dcmread(str(input_path), force=True)
    for tag in IDENTIFIER_TAGS:
        if hasattr(ds, tag):
            setattr(ds, tag, "ANONYMIZED")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(output_path))
    return output_path


def anonymize_folder(input_dir: str | Path, output_dir: str | Path) -> list[Path]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    written = []
    for path in input_dir.rglob("*"):
        if not path.is_file():
            continue
        target = output_dir / path.relative_to(input_dir)
        try:
            written.append(anonymize_dicom_file(path, target))
        except Exception:
            continue
    return written

