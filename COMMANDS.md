# AIDLC-MRI Commands

Quick command reference for running, checking, and publishing the project.

## 1. Install Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Run Backend + Frontend Web App

```powershell
cd "$env:USERPROFILE\Desktop\mri2\mri-project-main"
.\.venv\Scripts\python.exe run_backend_frontend.py
```

Open:

```text
http://127.0.0.1:8000
```

Main pages:

```text
http://127.0.0.1:8000/studies
http://127.0.0.1:8000/viewer
http://127.0.0.1:8000/volume
http://127.0.0.1:8000/three-d
http://127.0.0.1:8000/ai
```

## 3. Run Streamlit MVP

```powershell
cd "$env:USERPROFILE\Desktop\mri2\mri-project-main"
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
```

Alternative direct command:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open:

```text
http://127.0.0.1:8501
```

## 4. Check Local API

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/project-summary
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/studies
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/status
```

## 5. Compile Check

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\server.py backend_server.py run_backend_frontend.py
```

## 6. Optional HD-BET Install

```powershell
.\.venv\Scripts\python.exe -m pip install hd-bet
where hd-bet
where HD_BET
```

Check HD-BET import:

```powershell
.\.venv\Scripts\python.exe -c "import HD_BET; print('HD_BET installed')"
```

Run HD-BET directly against the current exported input volume:

```powershell
.\.venv\Scripts\python.exe -m HD_BET.run -i outputs/input.nii.gz -o outputs/brain_only.nii.gz -device cpu -mode fast
```

If this installed HD-BET package does not expose `HD_BET.run`, use the app's Run HD-BET button. The backend falls back to:

```powershell
.\.venv\Scripts\python.exe -m HD_BET.entry_point -i outputs/input.nii.gz -o outputs/brain_only.nii.gz -device cpu --disable_tta --save_bet_mask
```

Clear generated outputs:

```powershell
Remove-Item -Recurse -Force outputs\* -ErrorAction SilentlyContinue
```

If Windows native HD-BET fails, use WSL2 Ubuntu, Docker, or SynthStrip.

## 7. Region Segmentation Flow

Region segmentation requires SynthSeg or FastSurfer. Threshold-based region segmentation is disabled.

Typical web-app flow:

```text
1. Load volume
2. Run brain extraction
3. Run region segmentation
4. Select region
5. Build selected region 3D
6. Export region volumes CSV
```

Check region status:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/regions/status
```

Run SynthSeg/FastSurfer-backed region segmentation:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/regions/run
```

Build a selected region mesh:

```powershell
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/regions/build-mesh?region=Cerebrum"
```

Export region volumes:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/regions/export-volumes
```

Expected region outputs:

```text
outputs/regions_labelmap.nii.gz
outputs/region_volumes.csv
outputs/meshes/cerebrum.glb
```

Target/tumor regions are not generated automatically. To preview a manual/model target mask, place it here:

```text
outputs/target_mask.nii.gz
```

## 8. Git Commands

```powershell
git status --short
git add .
git commit -m "your commit message"
git push origin main
```

## 9. Docker

```powershell
docker build -t brain-mri-viewer .
docker run --rm -p 8501:8501 brain-mri-viewer
```

With local MRI data:

```powershell
docker run --rm -p 8501:8501 -v C:\Users\user\Desktop\mri2\mri-project-main\data:/data -e MRI_DATA_DIR=/data brain-mri-viewer
```

## 10. Current Backend Layout

```text
backend/server.py         main backend/frontend HTTP server
backend_server.py         compatibility wrapper
run_backend_frontend.py   server launcher
frontend/                 HTML/CSS/JS frontend
```

## 11. Reminder

Viewer only. Not for diagnosis.
