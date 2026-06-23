from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine, ensure_study_optional_columns
from .routers import analysis, private_analysis, studies, tracking

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
MEDIA_DIR = BASE_DIR / "media"
ASSETS_DIR = BASE_DIR / "assets"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

Base.metadata.create_all(bind=engine)
ensure_study_optional_columns()

app = FastAPI(
    title="MRI Demo and Private Analysis Web Service",
    description="Public Kaggle-style 2D MRI demo and private NIfTI/DICOM 3D analysis prototype.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/sample_data", StaticFiles(directory=SAMPLE_DATA_DIR), name="sample_data")

app.include_router(studies.router, prefix="/api/studies", tags=["studies"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(tracking.router, prefix="/api/tracking", tags=["tracking"])
app.include_router(private_analysis.router, prefix="/api/private", tags=["private-analysis"])


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/clinical")
def clinical_page():
    return FileResponse(FRONTEND_DIR / "clinical.html")


@app.get("/studies")
def studies_page():
    return FileResponse(FRONTEND_DIR / "studies.html")


@app.get("/viewer")
def viewer_page():
    return FileResponse(FRONTEND_DIR / "viewer.html")


@app.get("/volume")
def volume_page():
    return FileResponse(FRONTEND_DIR / "volume.html")


@app.get("/three-d")
def three_d_page():
    return FileResponse(FRONTEND_DIR / "three_d.html")


@app.get("/private")
def private_page():
    return FileResponse(FRONTEND_DIR / "private.html")


@app.get("/health")
def health():
    return {"status": "ok", "project": "mri-3d-web"}
