# AIDLC-MRI Commands

Quick command reference for running, checking, and publishing the project.

## 1. Install Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Run Backend + Frontend Web App

```powershell
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
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
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

If Windows native HD-BET fails, use WSL2 Ubuntu, Docker, or SynthStrip.

## 7. Git Commands

```powershell
git status --short
git add .
git commit -m "your commit message"
git push origin main
```

## 8. Docker

```powershell
docker build -t brain-mri-viewer .
docker run --rm -p 8501:8501 brain-mri-viewer
```

With local MRI data:

```powershell
docker run --rm -p 8501:8501 -v C:\Users\user\Desktop\mri2\mri-project-main\data:/data -e MRI_DATA_DIR=/data brain-mri-viewer
```

## 9. Current Backend Layout

```text
backend/server.py         main backend/frontend HTTP server
backend_server.py         compatibility wrapper
run_backend_frontend.py   server launcher
frontend/                 HTML/CSS/JS frontend
```

## 10. Reminder

Viewer only. Not for diagnosis.
