from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import Base, engine
from .routers import studies, analysis, tracking

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
MEDIA_DIR = BASE_DIR / "media"
ASSETS_DIR = BASE_DIR / "assets"
MRI_DIR = BASE_DIR / "mri"

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Brain MRI 3D Visualization & Volume Measurement Web Service",
    description="연구용 Brain MRI 3D 시각화 및 부피 계산 웹 프로토타입",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/mri", StaticFiles(directory=MRI_DIR), name="mri")

app.include_router(studies.router, prefix="/api/studies", tags=["studies"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(tracking.router, prefix="/api/tracking", tags=["tracking"])

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

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

@app.get("/health")
def health():
    return {"status": "ok", "project": "mri-3d-web"}
