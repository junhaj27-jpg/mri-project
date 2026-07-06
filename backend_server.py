from __future__ import annotations

import io
import json
import logging
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go

from mesh_builder import BrainMesh, build_brain_mesh_from_mask, export_stl
from mri_loader import MRIData, discover_dicom_series, load_dicom, load_nifti, load_nifti_mask
from preprocessing import normalize_intensity, plane_length, slice_from_plane
from report import DISCLAIMER


HOST = "127.0.0.1"
PORT = 8000
ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
OUTPUT_DIR = ROOT / "outputs"
MASK_PATH = OUTPUT_DIR / "filled_brain_mask.nii.gz"
MESH_PATH = OUTPUT_DIR / "brain_mesh_backend.stl"

LOGGER = logging.getLogger("aidlc_mri.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATE: dict[str, object] = {
    "mri_data": None,
    "normalized": None,
    "series": None,
    "series_key": None,
    "mesh": None,
}


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


class BackendHandler(BaseHTTPRequestHandler):
    server_version = "AIDLCMRI/0.1"

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/":
                self.send_static(FRONTEND_DIR / "index.html")
            elif path.startswith("/assets/"):
                self.send_static(FRONTEND_DIR / path.removeprefix("/"))
            elif path == "/api/status":
                self.send_json(api_status())
            elif path == "/api/series":
                self.send_json(api_series(query))
            elif path == "/api/load":
                self.send_json(api_load(query))
            elif path == "/api/slice":
                self.send_bytes(api_slice_png(query), "image/png")
            elif path == "/api/mesh":
                self.send_json(api_mesh(query))
            elif path == "/api/mesh_plot":
                self.send_bytes(api_mesh_plot(query).encode("utf-8"), "text/html; charset=utf-8")
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            LOGGER.error("request failed: %s\n%s", exc, traceback.format_exc())
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False).encode("utf-8")
            )

    def log_message(self, fmt: str, *args) -> None:
        LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def send_json(self, payload: dict | list) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_bytes(data, "application/json; charset=utf-8")

    def send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_static(self, path: Path) -> None:
        path = path.resolve()
        frontend_root = FRONTEND_DIR.resolve()
        if frontend_root not in path.parents and path != frontend_root:
            self.send_error(403, "Forbidden")
            return
        if not path.exists() or not path.is_file():
            self.send_error(404, "Static file not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(path.read_bytes(), content_type)


def api_status() -> dict:
    mri_data = get_loaded_mri()
    return {
        "loaded": mri_data is not None,
        "source": mri_data.source_type if mri_data else None,
        "source_label": mri_data.source_label if mri_data else None,
        "shape": tuple(int(value) for value in mri_data.volume.shape) if mri_data else None,
        "spacing": mri_data.spacing if mri_data else None,
        "info": summarize_info(mri_data.info) if mri_data else {},
        "mask_available": MASK_PATH.exists(),
        "mesh_available": MESH_PATH.exists(),
        "disclaimer": DISCLAIMER,
    }


def api_series(query: dict[str, list[str]]) -> dict:
    data_dir = Path(first(query, "data_dir", str(DEFAULT_DATA_DIR)))
    series = discover_dicom_series(str(data_dir))
    STATE["series"] = series
    return {"data_dir": str(data_dir), "series": series}


def api_load(query: dict[str, list[str]]) -> dict:
    data_dir = Path(first(query, "data_dir", str(DEFAULT_DATA_DIR)))
    source = first(query, "source", "dicom")
    if source == "nifti":
        path = first(query, "path", "")
        if not path:
            raise ValueError("NIfTI path is required.")
        mri_data = load_nifti(path)
        STATE["series_key"] = str(path)
    else:
        series_key = first(query, "series_key", "")
        if not series_key:
            series = STATE.get("series") or discover_dicom_series(str(data_dir))
            if not series:
                raise FileNotFoundError(f"No DICOM series found in {data_dir}")
            series_key = str(series[0]["key"])
        mri_data = load_dicom(str(data_dir), series_key=series_key)
        STATE["series_key"] = series_key
    STATE["mri_data"] = mri_data
    STATE["normalized"] = normalize_intensity(mri_data.volume)
    STATE["mesh"] = None
    return api_status()


def api_slice_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    normalized = require_normalized()
    plane = first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))).lower()
    max_index = plane_length(mri_data.volume, plane) - 1
    index = max(0, min(int(first(query, "index", str(max_index // 2))), max_index))
    image = slice_from_plane(normalized, plane, index)
    mask_slice = None
    if first(query, "mask", "1") == "1" and MASK_PATH.exists():
        mask = load_matching_mask(mri_data)
        mask_slice = slice_from_plane(mask.astype(np.float32), plane, index)
    return draw_slice_png(image, mask_slice)


def api_mesh(query: dict[str, list[str]]) -> dict:
    mesh = get_or_build_mesh(query)
    metadata = mesh.metadata or {}
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "quality_warnings": mesh.quality_warnings or [],
        "metadata": metadata,
        "mesh_path": str(MESH_PATH),
    }


def api_mesh_plot(query: dict[str, list[str]]) -> str:
    mesh = get_or_build_mesh(query)
    fig = mesh_to_figure(mesh)
    return fig.to_html(include_plotlyjs=True, full_html=True, config={"displaylogo": False, "responsive": True})


def get_or_build_mesh(query: dict[str, list[str]]) -> BrainMesh:
    cached = STATE.get("mesh")
    if isinstance(cached, BrainMesh):
        return cached
    mri_data = require_mri()
    mask = load_matching_mask(mri_data)
    downsample_factor = int(first(query, "downsample", "2"))
    step_size = int(first(query, "step", "1"))
    gaussian_sigma = float(first(query, "sigma", "1.0"))
    smoothing_iterations = int(first(query, "smooth", "5"))
    mesh = build_brain_mesh_from_mask(
        mask,
        spacing=mri_data.spacing,
        gaussian_sigma=gaussian_sigma,
        step_size=step_size,
        downsample_factor=downsample_factor,
        smoothing_iterations=smoothing_iterations,
        apply_mesh_smoothing=True,
    )
    export_stl(mesh, MESH_PATH)
    STATE["mesh"] = mesh
    return mesh


def get_loaded_mri() -> MRIData | None:
    mri_data = STATE.get("mri_data")
    return mri_data if isinstance(mri_data, MRIData) else None


def require_mri() -> MRIData:
    mri_data = get_loaded_mri()
    if mri_data is None:
        api_load({"data_dir": [str(DEFAULT_DATA_DIR)]})
        mri_data = get_loaded_mri()
    if mri_data is None:
        raise RuntimeError("MRI volume is not loaded.")
    return mri_data


def require_normalized() -> np.ndarray:
    normalized = STATE.get("normalized")
    if isinstance(normalized, np.ndarray):
        return normalized
    mri_data = require_mri()
    normalized = normalize_intensity(mri_data.volume)
    STATE["normalized"] = normalized
    return normalized


def load_matching_mask(mri_data: MRIData) -> np.ndarray:
    if not MASK_PATH.exists():
        raise FileNotFoundError(f"Brain mask not found: {MASK_PATH}")
    mask = load_nifti_mask(MASK_PATH)
    if mask.shape != mri_data.volume.shape:
        raise ValueError(f"Brain mask shape mismatch: {mask.shape} vs {mri_data.volume.shape}")
    return mask


def draw_slice_png(image: np.ndarray, mask_slice: np.ndarray | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if mask_slice is not None:
        overlay = np.ma.masked_where(mask_slice <= 0, mask_slice)
        ax.imshow(overlay, cmap="autumn", alpha=0.30, vmin=0, vmax=1)
    ax.axis("off")
    fig.tight_layout(pad=0)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return buffer.getvalue()


def mesh_to_figure(mesh: BrainMesh) -> go.Figure:
    vertices = mesh.vertices
    faces = mesh.faces
    fig = go.Figure(
        data=[
            go.Mesh3d(
                x=vertices[:, 2],
                y=vertices[:, 1],
                z=vertices[:, 0],
                i=faces[:, 0],
                j=faces[:, 1],
                k=faces[:, 2],
                color="lightgray",
                opacity=1.0,
                flatshading=False,
                lighting=dict(ambient=0.5, diffuse=0.8, specular=0.1, roughness=0.6, fresnel=0.1),
            )
        ]
    )
    fig.update_layout(
        height=680,
        margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(aspectmode="data", xaxis_title="", yaxis_title="", zaxis_title=""),
    )
    return fig


def summarize_info(info: dict) -> dict:
    keys = ["StudyDate", "SeriesDescription", "Plane", "PixelSpacing", "SliceThickness", "SliceSpacing", "OrientationNote"]
    return {key: info.get(key) for key in keys}


def first(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def run(host: str = HOST, port: int = PORT) -> None:
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), BackendHandler)
    LOGGER.info("AIDLC-MRI backend/frontend running at http://%s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    run()
