# sample_data policy

This directory is safe to commit to GitHub.

Allowed contents:

- Kaggle-style 2D demo images or metadata for UI demonstration only.
- Mock longitudinal records that do not come from a real patient.
- Public, synthetic, or fully anonymized demo metadata.

Not allowed contents:

- Real DICOM files.
- Real NIfTI volumes or masks.
- Real GLB meshes generated from private MRI data.
- Real volume measurement result files.
- Any identifier that can reveal a patient, hospital visit, scan date, or institution.

The Kaggle demo data is for 2D viewing only. It is not used as an input for real 3D volume calculation. Real 3D analysis must use private local DICOM/NIfTI volume inputs stored outside Git tracking.
