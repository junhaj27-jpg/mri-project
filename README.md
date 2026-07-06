# AIDLC-MRI

Brain MRI 2D/3D viewer MVP for portfolio and research visualization.

This project loads local DICOM MRI data, provides a 2D slice viewer, displays brain-mask overlays, and offers a 3D preview pipeline when a reliable skull-stripping result is available.

> Viewer only. Not for diagnosis. Final medical decisions must follow a clinician's interpretation.

## Current Data Path

The default local data folder is:

```text
C:\Users\user\Desktop\mri2\mri-project-main\data
```

The app scans this folder recursively and groups DICOM files by series.

## Main Screens

- Dashboard: project overview and quick links
- Studies: DICOM series list grouped into study-style rows
- 2D Viewer: grayscale MRI slice viewer with plane and slice controls
- Volume: mock longitudinal volume tracking plus current brain-mask volume summary
- 3D Viewer: brain mesh preview based on available brain mask
- AI Assist: skull-stripping, mask, mesh, and overlay status summary

## Local Web App

Run the backend/frontend server:

```powershell
.\.venv\Scripts\python.exe run_backend_frontend.py
```

Open:

```text
http://127.0.0.1:8000
```

Useful pages:

```text
http://127.0.0.1:8000/studies
http://127.0.0.1:8000/viewer
http://127.0.0.1:8000/volume
http://127.0.0.1:8000/three-d
http://127.0.0.1:8000/ai
```

See [COMMANDS.md](COMMANDS.md) for a compact command reference.

## Streamlit App

The original Streamlit MVP is still available:

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

## Install Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Optional brain extraction tools:

- HD-BET
- SynthStrip / FreeSurfer

See [INSTALL.md](INSTALL.md) for HD-BET and SynthStrip notes.

## Backend API

The local web frontend uses these endpoints:

- `GET /health`
- `GET /api/project-summary`
- `GET /api/status`
- `GET /api/series`
- `GET /api/studies`
- `GET /api/load`
- `GET /api/slice`
- `GET /api/mesh`
- `GET /api/mesh_plot`
- `GET /api/tracking`
- `GET /api/volume-result`
- `GET /api/ai-results`

## MRI Processing Notes

- DICOM series are sorted by `InstanceNumber`.
- Pixel data is loaded through `pydicom.pixel_array`.
- Orientation is inferred from DICOM metadata and series description.
- 2D display uses grayscale windowed slice rendering.
- ROI area uses `PixelSpacing`.
- ROI/brain volume calculations use slice spacing or slice thickness when available.

## Brain-Only 3D Policy

Final brain-only 3D mesh generation should use a reliable skull-stripping result:

- SynthStrip mask
- HD-BET mask

Simple threshold fallback is debug-only. It must not be treated as final brain-only 3D output.

3D mesh generation uses a processed brain mask or exported mask file, then renders with Plotly.

## Output Files

Common generated outputs:

```text
outputs/brain_mask.nii.gz
outputs/refined_brain_mask.nii.gz
outputs/filled_brain_mask.nii.gz
outputs/brain_extracted.nii.gz
outputs/brain_mesh_backend.stl
```

Availability depends on the selected processing path and installed skull-stripping tools.

## Repository Structure

```text
app.py                    Streamlit MVP
backend/server.py         Local backend/frontend HTTP server
backend_server.py         Compatibility wrapper for older run commands
run_backend_frontend.py   Starts the local web app server
mri_loader.py             DICOM/NIfTI loading
preprocessing.py          Normalization and slice helpers
brain_mask.py             Fallback mask/refinement logic
skull_stripping.py        SynthStrip/HD-BET integration helpers
mesh_builder.py           Marching cubes and mesh export
report.py                 PDF report helpers
frontend/                 Dashboard, viewer, 3D, studies, volume, AI pages
utils/                    DICOM helper loader
outputs/                  Generated masks and meshes
```

## Verification

Recent local verification:

- `/studies` loads DICOM series rows.
- `/volume` renders T01 to T14 mock tracking rows.
- `/ai` renders mask/mesh readiness checks.
- `/viewer` keeps the 2D grayscale slice workflow.
- `/three-d` keeps the 3D preview workflow.

## Docker

```powershell
docker build -t brain-mri-viewer .
docker run --rm -p 8501:8501 brain-mri-viewer
```

With local data mounted:

```powershell
docker run --rm -p 8501:8501 -v C:\Users\user\Desktop\mri2\mri-project-main\data:/data -e MRI_DATA_DIR=/data brain-mri-viewer
```

## Medical Disclaimer

This is not a diagnostic medical device.

It is a portfolio/MVP viewer for visual confirmation, research-style demonstration, and local MRI data exploration. It does not replace clinical interpretation, radiology workflow, or physician review.
