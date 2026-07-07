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

HD-BET can be installed into the project virtualenv:

```powershell
.\.venv\Scripts\python.exe -m pip install hd-bet
```

The local web app checks HD-BET with:

```powershell
.\.venv\Scripts\python.exe -c "import HD_BET; print('HD_BET installed')"
```

## Backend API

The local web frontend uses these endpoints:

- `GET /health`
- `GET /api/project-summary`
- `GET /api/status`
- `GET /api/series`
- `GET /api/studies`
- `GET /api/load`
- `GET /api/slice`
- `GET /api/mask`
- `GET /api/rebuild_mask`
- `GET /api/clear_outputs`
- `GET /api/run_hdbet`
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

The app treats a mask as reliable only when all of these are true:

- `mask_source` is `synthstrip` or `hd-bet`
- `mask_status` is `valid`
- `outputs/brain_mask.nii.gz` exists
- `reliable_mask` is `true`

Fallback threshold, cached unknown, ellipse/ROI/debug masks are always unreliable. If a reliable mask is not available, final 3D generation returns:

```json
{
  "ok": false,
  "status": "debug_only",
  "message": "SynthStrip or HD-BET brain mask is required for final 3D brain mesh.",
  "mesh_path": null
}
```

Final 3D mesh generation runs marching cubes only on `outputs/brain_mask.nii.gz`. It does not run marching cubes on the original MRI intensity volume or threshold fallback mask.

## HD-BET Workflow

On the 3D Viewer page:

```text
http://127.0.0.1:8000/three-d
```

Use these buttons:

- `Load volume`: load the selected DICOM series.
- `Clear outputs`: remove generated masks, meshes, NIfTI files, and overlay PNGs from `outputs/`.
- `Rebuild mask`: clear mask/mesh cache and reset mask state.
- `Run HD-BET`: convert the current DICOM series to `outputs/input.nii.gz`, run HD-BET, and save `outputs/brain_mask.nii.gz`.
- `Build final 3D mesh`: create `outputs/brain_only_mesh.glb` only when the HD-BET/SynthStrip mask is reliable.

The app first tries the requested command style:

```powershell
python -m HD_BET.run -i outputs/input.nii.gz -o outputs/brain_only.nii.gz -device cpu -mode fast
```

For installed `hd-bet` versions that expose `HD_BET.entry_point` instead of `HD_BET.run`, it falls back to:

```powershell
python -m HD_BET.entry_point -i outputs/input.nii.gz -o outputs/brain_only.nii.gz -device cpu --disable_tta --save_bet_mask
```

The app then searches HD-BET mask outputs such as:

```text
outputs/brain_only_mask.nii.gz
outputs/brain_only_bet.nii.gz
outputs/input_mask.nii.gz
outputs/input_bet.nii.gz
outputs/*mask*.nii.gz
outputs/*_mask.nii.gz
outputs/*_bet.nii.gz
```

When a valid HD-BET mask is found, it is copied/saved as:

```text
outputs/brain_mask.nii.gz
```

The preview overlay is then drawn from this binary mask only.

## Output Files

Common generated outputs:

```text
outputs/brain_mask.nii.gz
outputs/brain_mask_source.json
outputs/input.nii.gz
outputs/brain_only.nii.gz
outputs/brain_only_bet.nii.gz
outputs/brain_only_mesh.glb
outputs/brain_overlay.png
outputs/brain_overlay_axial.png
outputs/brain_overlay_sagittal.png
outputs/brain_overlay_coronal.png
```

Availability depends on the selected processing path and installed skull-stripping tools.

Debug-only fallback outputs may include:

```text
outputs/fallback_preview_mask.nii.gz
outputs/debug_mask_mesh.glb
outputs/debug_mask_overlay.png
outputs/debug_mask_overlay_axial.png
outputs/debug_mask_overlay_sagittal.png
outputs/debug_mask_overlay_coronal.png
```

These debug outputs are not final brain extraction results.

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
- `/three-d` runs HD-BET from the project virtualenv, saves `outputs/brain_mask.nii.gz`, and builds `outputs/brain_only_mesh.glb` only when `reliable_mask=true`.
- Threshold fallback remains `invalid_threshold_noise` / debug-only and cannot create final 3D output.

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
