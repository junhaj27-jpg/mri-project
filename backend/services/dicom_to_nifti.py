from pathlib import Path


def planned_nifti_output(patient_code: str, body_region: str, study_label: str) -> str:
    region_dir = "lumbar" if body_region == "LUMBAR_SPINE" else "brain"
    return str(Path("data") / "nifti" / patient_code / region_dir / f"{study_label}.nii.gz")


def convert_dicom_to_nifti_placeholder(patient_code: str, body_region: str, study_label: str) -> dict:
    return {
        "status": "planned",
        "nifti_path": planned_nifti_output(patient_code, body_region, study_label),
        "notice": "DICOM to NIfTI conversion is a placeholder. Install/configure conversion tools before clinical use.",
    }
