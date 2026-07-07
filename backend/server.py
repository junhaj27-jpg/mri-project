from __future__ import annotations

import io
import json
import logging
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain_mask import create_brain_mask, create_filled_brain_surface_mask, refine_brain_mask
from mesh_builder import BrainMesh, build_brain_mesh_from_mask, export_glb
from mri_loader import MRIData, discover_dicom_series, load_dicom, load_nifti, load_nifti_mask, save_brain_extracted, save_nifti_mask
from preprocessing import normalize_intensity, plane_length, slice_from_plane
from report import DISCLAIMER
from skull_stripping import SkullStripResult, run_skull_stripping


HOST = "127.0.0.1"
PORT = 8000
ROOT = PROJECT_ROOT
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
OUTPUT_DIR = ROOT / "outputs"
MASK_PATH = OUTPUT_DIR / "filled_brain_mask.nii.gz"
RAW_MASK_PATH = OUTPUT_DIR / "brain_mask.nii.gz"
BRAIN_ONLY_VOLUME_PATH = OUTPUT_DIR / "brain_only.nii.gz"
FALLBACK_MASK_PATH = OUTPUT_DIR / "fallback_preview_mask.nii.gz"
DEBUG_RAW_SURFACE_PATH = OUTPUT_DIR / "debug_raw_surface.glb"
DEBUG_MASK_MESH_PATH = OUTPUT_DIR / "debug_mask_mesh.glb"
BRAIN_MASK_OVERLAY_PATH = OUTPUT_DIR / "brain_mask_overlay.png"
BRAIN_OVERLAY_PATH = OUTPUT_DIR / "brain_overlay.png"
DEBUG_MASK_OVERLAY_PATH = OUTPUT_DIR / "debug_mask_overlay.png"
STANDARD_OVERLAY_PLANES = ("axial", "sagittal", "coronal")
FINAL_OVERLAY_PREFIX = "brain_overlay"
DEBUG_OVERLAY_PREFIX = "debug_mask_overlay"
BRAIN_ONLY_MESH_PATH = OUTPUT_DIR / "brain_only_mesh.glb"

LOGGER = logging.getLogger("aidlc_mri.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATE: dict[str, object] = {
    "mri_data": None,
    "normalized": None,
    "series": None,
    "series_key": None,
    "mesh": None,
    "mask_result": None,
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
            elif path == "/viewer":
                self.send_static(FRONTEND_DIR / "viewer.html")
            elif path == "/review":
                self.send_static(FRONTEND_DIR / "viewer.html")
            elif path == "/three-d":
                self.send_static(FRONTEND_DIR / "three_d.html")
            elif path == "/studies":
                self.send_static(FRONTEND_DIR / "studies.html")
            elif path == "/volume":
                self.send_static(FRONTEND_DIR / "volume.html")
            elif path == "/ai":
                self.send_static(FRONTEND_DIR / "ai.html")
            elif path.startswith("/assets/"):
                self.send_static(FRONTEND_DIR / path.removeprefix("/"))
            elif path.startswith("/static/"):
                self.send_static(FRONTEND_DIR / path.removeprefix("/"))
            elif path == "/health":
                self.send_json({"status": "ok", "project": "aidlc-mri"})
            elif path == "/api/project-summary":
                self.send_json(api_project_summary())
            elif path == "/api/status":
                self.send_json(api_status())
            elif path == "/api/series":
                self.send_json(api_series(query))
            elif path == "/api/studies":
                self.send_json(api_studies(query))
            elif path == "/api/tracking":
                self.send_json(api_tracking())
            elif path == "/api/volume-result":
                self.send_json(api_volume_result())
            elif path == "/api/ai-results":
                self.send_json(api_ai_results())
            elif path == "/api/load":
                self.send_json(api_load(query))
            elif path == "/api/slice":
                self.send_bytes(api_slice_png(query), "image/png")
            elif path == "/api/mask":
                self.send_json(api_mask(query))
            elif path == "/api/mask_overlay":
                self.send_bytes(api_mask_overlay_png(query), "image/png")
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
        "mask_available": RAW_MASK_PATH.exists() or FALLBACK_MASK_PATH.exists(),
        "mask_reliable": BRAIN_ONLY_MESH_PATH.exists() or reliable_mask_file_exists(),
        "mesh_available": BRAIN_ONLY_MESH_PATH.exists() and reliable_mask_file_exists(),
        "debug_mesh_available": DEBUG_MASK_MESH_PATH.exists(),
        "disclaimer": DISCLAIMER,
    }


def api_project_summary() -> dict:
    mri_data = get_loaded_mri()
    return {
        "project": "AIDLC-MRI",
        "mode": "private_local_research_viewer",
        "pages": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Studies", "url": "/studies"},
            {"label": "2D Viewer", "url": "/viewer"},
            {"label": "Volume", "url": "/volume"},
            {"label": "3D Viewer", "url": "/three-d"},
            {"label": "AI Assist", "url": "/ai"},
        ],
        "apis": [
            "/api/status",
            "/api/studies",
            "/api/tracking",
            "/api/volume-result",
            "/api/ai-results",
            "/api/series",
            "/api/load",
            "/api/slice",
            "/api/mesh",
            "/api/mesh_plot",
        ],
        "loaded": mri_data is not None,
        "shape": tuple(int(value) for value in mri_data.volume.shape) if mri_data else None,
        "warning": DISCLAIMER,
    }


def api_series(query: dict[str, list[str]]) -> dict:
    data_dir = Path(first(query, "data_dir", str(DEFAULT_DATA_DIR)))
    series = discover_dicom_series(str(data_dir))
    STATE["series"] = series
    return {"data_dir": str(data_dir), "series": series}


def api_studies(query: dict[str, list[str]]) -> list[dict]:
    rows = api_series(query)["series"]
    studies: list[dict] = []
    for index, item in enumerate(rows, start=1):
        description = str(item.get("description") or "Unknown series")
        file_count = int(item.get("file_count") or 0)
        shape = str(item.get("shape") or "")
        modality = "MRI" if file_count > 1 else "Reference"
        section = "Brain MRI" if "BRAIN" in description.upper() or file_count > 20 else "Reference image"
        studies.append(
            {
                "study_label": f"BRAIN_T{index:02d}",
                "series_key": item.get("key"),
                "description": description,
                "file_count": file_count,
                "shape": shape,
                "section": section,
                "modality": modality,
                "status": "ready" if file_count > 1 else "reference_only",
                "warning": "Viewer only. Not for diagnosis.",
            }
        )
    return studies


def api_tracking() -> dict:
    base_values = [52.8, 50.6, 48.9, 47.2, 44.8, 42.1, 39.8, 36.5, 35.1, 34.0, 32.7, 31.9, 31.0, 30.6]
    items = []
    previous = None
    for index, value in enumerate(base_values, start=1):
        change = None if previous is None else round(value - previous, 2)
        rate = None if previous in (None, 0) else round((value - previous) / previous * 100.0, 2)
        items.append(
            {
                "study_label": f"BRAIN_T{index:02d}",
                "volume_cm3": value,
                "previous_volume_cm3": previous,
                "change_cm3": change,
                "change_rate_percent": rate,
                "quality_flag": "baseline_reference" if index == 1 else "research_tracking",
                "note": "Mock longitudinal value for portfolio visualization.",
            }
        )
        previous = value
    return {
        "patient_code": "P001",
        "body_region": "BRAIN",
        "items": items,
        "warning": DISCLAIMER,
    }


def api_volume_result() -> dict:
    mask_info = mask_volume_info()
    tracking = api_tracking()
    latest = tracking["items"][-1]
    return {
        "patient_code": "P001",
        "study_label": latest["study_label"],
        "mock_tracking_latest_cm3": latest["volume_cm3"],
        "mask_volume": mask_info,
        "formula": "voxel_count * spacing_z_mm * spacing_y_mm * spacing_x_mm / 1000",
        "warning": DISCLAIMER,
    }


def api_ai_results() -> dict:
    mri_data = get_loaded_mri()
    mask_info = mask_volume_info()
    reliable_ready = reliable_mask_file_exists()
    mesh_ready = reliable_ready and BRAIN_ONLY_MESH_PATH.exists()
    debug_mesh_ready = DEBUG_MASK_MESH_PATH.exists()
    return {
        "engine": "HD-BET / skull-stripping assisted viewer",
        "mask_source": str(RAW_MASK_PATH) if reliable_ready else "not available",
        "mesh_source": str(BRAIN_ONLY_MESH_PATH) if mesh_ready else "not generated",
        "brain_only_source": str(BRAIN_ONLY_VOLUME_PATH) if reliable_ready and BRAIN_ONLY_VOLUME_PATH.exists() else "not generated",
        "brain_overlay_source": str(BRAIN_OVERLAY_PATH) if reliable_ready and BRAIN_OVERLAY_PATH.exists() else "not generated",
        "debug_mesh_source": str(DEBUG_MASK_MESH_PATH) if debug_mesh_ready else "not generated",
        "debug_raw_surface_source": str(DEBUG_RAW_SURFACE_PATH) if DEBUG_RAW_SURFACE_PATH.exists() else "not generated",
        "volume_shape": tuple(int(value) for value in mri_data.volume.shape) if mri_data else None,
        "mask_volume": mask_info,
        "checks": [
            {"label": "Brain mask available", "ok": RAW_MASK_PATH.exists() or FALLBACK_MASK_PATH.exists()},
            {"label": "Stable mesh exported", "ok": mesh_ready},
            {"label": "2D overlay supported", "ok": BRAIN_MASK_OVERLAY_PATH.exists()},
            {"label": "Diagnostic claim blocked", "ok": True},
        ],
        "warning": DISCLAIMER,
    }


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
    STATE["mask_result"] = None
    return api_status()


def api_slice_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    normalized = require_normalized()
    plane = first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))).lower()
    max_index = plane_length(mri_data.volume, plane) - 1
    index = max(0, min(int(first(query, "index", str(max_index // 2))), max_index))
    image = slice_from_plane(normalized, plane, index)
    mask_slice = None
    mask = None
    if first(query, "mask", "1") == "1":
        mask = ensure_mask_result(mri_data).mask
    if mask is not None:
        mask_slice = slice_from_plane(binarize_mask(mask).astype(np.float32), plane, index)
    return draw_slice_png(image, mask_slice)


def api_mask(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = mask_diagnostics(result.mask, result.debug_only)
    final_allowed = is_final_mask_allowed(result, diagnostics)
    mask_path = RAW_MASK_PATH if final_allowed else FALLBACK_MASK_PATH
    overlay_path = BRAIN_OVERLAY_PATH if final_allowed else DEBUG_MASK_OVERLAY_PATH
    save_mask_overlay_png(mri_data, result.mask, overlay_path, query)
    save_mask_overlay_png(mri_data, result.mask, BRAIN_MASK_OVERLAY_PATH, query)
    overlay_paths = save_standard_mask_overlays(
        mri_data,
        result.mask,
        prefix=FINAL_OVERLAY_PREFIX if final_allowed else DEBUG_OVERLAY_PREFIX,
    )
    LOGGER.info(
        "Mask diagnostics: unique=%s ratio=%s status=%s final_allowed=%s",
        diagnostics["mask_unique_values"],
        diagnostics["mask_ratio"],
        diagnostics["mask_status"],
        final_allowed,
    )
    return {
        "method": result.method_used,
        "reliable_for_3d": final_allowed,
        "debug_only": not final_allowed,
        "mask_path": str(mask_path),
        "overlay_path": str(overlay_path),
        "overlay_paths": {key: str(value) for key, value in overlay_paths.items()},
        "warnings": result.warnings,
        "mask_ratio": diagnostics["mask_ratio"],
        "mask_unique_values": diagnostics["mask_unique_values"],
        "mask_status": diagnostics["mask_status"],
        "metadata": result.metadata,
    }


def api_mask_overlay_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    return render_mask_overlay_png(mri_data, result.mask, query)


def api_mesh(query: dict[str, list[str]]) -> dict:
    mesh = get_or_build_mesh(query)
    metadata = mesh.metadata or {}
    output_path = metadata.get("mesh_path", str(DEBUG_MASK_MESH_PATH))
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "quality_warnings": mesh.quality_warnings or [],
        "metadata": metadata,
        "mesh_path": output_path,
        "reliable_for_3d": bool(metadata.get("reliable_for_3d", False)),
        "debug_only": bool(metadata.get("debug_only", True)),
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
    result = ensure_mask_result(mri_data)
    result_warnings = list(result.warnings or []) + list(result.metadata.get("quality_warnings", []) or [])
    diagnostics = mask_diagnostics(result.mask, result.debug_only)
    result_warnings.extend(diagnostics["warnings"])
    final_allowed = is_final_mask_allowed(result, diagnostics) and not result_warnings
    mask = binarize_mask(result.mask).astype(np.uint8)
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
    if mesh.metadata is None:
        mesh.metadata = {}
    output_path = BRAIN_ONLY_MESH_PATH if final_allowed else DEBUG_MASK_MESH_PATH
    export_glb(mesh, output_path)
    if not final_allowed:
        export_debug_raw_surface(result, mri_data, query)
    mesh.metadata.update(
        {
            "mask_source": str(RAW_MASK_PATH if result.reliable_for_3d else FALLBACK_MASK_PATH),
            "mesh_path": str(output_path),
            "mesh_mode": "brain-only reliable mask" if final_allowed else "debug-only mask surface",
            "method": result.method_used,
            "reliable_for_3d": final_allowed,
            "debug_only": not final_allowed,
            "quality_warnings": result_warnings,
            "mask_ratio": diagnostics["mask_ratio"],
            "mask_unique_values": diagnostics["mask_unique_values"],
            "mask_status": diagnostics["mask_status"],
            "warning": None
            if final_allowed
            else "Mask did not pass final brain-only criteria; mesh saved as debug only, not final brain mask.",
        }
    )
    STATE["mesh"] = mesh
    return mesh


def export_debug_raw_surface(result: SkullStripResult, mri_data: MRIData, query: dict[str, list[str]]) -> None:
    try:
        raw_mesh = build_brain_mesh_from_mask(
            binarize_mask(result.raw_mask).astype(np.uint8),
            spacing=mri_data.spacing,
            gaussian_sigma=float(first(query, "sigma", "1.0")),
            step_size=max(1, int(first(query, "step", "1"))),
            downsample_factor=max(2, int(first(query, "downsample", "2"))),
            smoothing_iterations=0,
            apply_mesh_smoothing=False,
        )
        export_glb(raw_mesh, DEBUG_RAW_SURFACE_PATH)
    except Exception:
        LOGGER.exception("debug raw surface export failed; continuing with processed debug mask mesh")


def ensure_mask_result(mri_data: MRIData) -> SkullStripResult:
    cached = STATE.get("mask_result")
    if isinstance(cached, SkullStripResult):
        return cached
    try:
        result = run_skull_stripping(mri_data, "synthstrip", OUTPUT_DIR)
    except Exception as reliable_error:
        result = run_skull_stripping(mri_data, "fallback", OUTPUT_DIR)
        result.warnings.append(f"Reliable skull stripping unavailable: {reliable_error}")

    diagnostics = mask_diagnostics(result.mask, result.debug_only)
    final_mask_allowed = is_final_mask_allowed(result, diagnostics)
    if final_mask_allowed:
        final_mask = binarize_mask(result.mask)
        save_nifti_mask(final_mask, mri_data.affine, RAW_MASK_PATH)
        save_brain_extracted(mri_data.volume, final_mask, mri_data.affine, BRAIN_ONLY_VOLUME_PATH)
        save_mask_overlay_png(mri_data, final_mask, BRAIN_OVERLAY_PATH, {})
        save_standard_mask_overlays(mri_data, final_mask, prefix=FINAL_OVERLAY_PREFIX)
    else:
        save_nifti_mask(binarize_mask(result.mask), mri_data.affine, FALLBACK_MASK_PATH)
        if BRAIN_ONLY_MESH_PATH.exists():
            LOGGER.warning("Ignoring stale brain-only mesh because current mask is not final-quality reliable: %s", BRAIN_ONLY_MESH_PATH)

    save_mask_overlay_png(mri_data, result.mask, BRAIN_MASK_OVERLAY_PATH, {})
    if not final_mask_allowed:
        save_mask_overlay_png(mri_data, result.mask, DEBUG_MASK_OVERLAY_PATH, {})
        save_standard_mask_overlays(mri_data, result.mask, prefix=DEBUG_OVERLAY_PREFIX)
    STATE["mask_result"] = result
    return result


def is_final_mask_allowed(result: SkullStripResult, diagnostics: dict | None = None) -> bool:
    diagnostics = diagnostics or mask_diagnostics(result.mask, result.debug_only)
    return bool(
        result.reliable_for_3d
        and not result.debug_only
        and not result.metadata.get("quality_warnings")
        and diagnostics.get("mask_status") == "valid"
    )


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


def load_mask_for_volume(mri_data: MRIData, path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Brain mask not found: {path}")
    mask = load_nifti_mask(path)
    if mask.shape != mri_data.volume.shape:
        raise ValueError(f"Brain mask shape mismatch: {mask.shape} vs {mri_data.volume.shape}")
    return mask


def mask_volume_info() -> dict:
    mri_data = get_loaded_mri()
    mask_path = display_mask_path()
    if mri_data is None or mask_path is None:
        return {"available": False}
    try:
        mask = load_mask_for_volume(mri_data, mask_path)
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    voxel_count = int(np.count_nonzero(mask))
    voxel_mm3 = float(mri_data.spacing[0] * mri_data.spacing[1] * mri_data.spacing[2])
    volume_mm3 = voxel_count * voxel_mm3
    return {
        "available": True,
        "voxel_count": voxel_count,
        "spacing_mm": mri_data.spacing,
        "volume_mm3": round(volume_mm3, 2),
        "volume_ml": round(volume_mm3 / 1000.0, 3),
        "mask_path": str(mask_path),
        "reliable_for_3d": mask_path == RAW_MASK_PATH and not FALLBACK_MASK_PATH.exists(),
    }


def reliable_mask_file_exists() -> bool:
    cached = STATE.get("mask_result")
    if isinstance(cached, SkullStripResult):
        return bool(cached.reliable_for_3d and not cached.debug_only and not cached.metadata.get("quality_warnings"))
    return RAW_MASK_PATH.exists() and not FALLBACK_MASK_PATH.exists()


def display_mask_path() -> Path | None:
    cached = STATE.get("mask_result")
    if isinstance(cached, SkullStripResult):
        return RAW_MASK_PATH if cached.reliable_for_3d and not cached.debug_only else FALLBACK_MASK_PATH
    if RAW_MASK_PATH.exists():
        return RAW_MASK_PATH
    if FALLBACK_MASK_PATH.exists():
        return FALLBACK_MASK_PATH
    return None


def binarize_mask(mask: np.ndarray) -> np.ndarray:
    return np.asarray(mask) > 0.5


def mask_diagnostics(mask: np.ndarray, debug_only: bool = False) -> dict:
    values = np.unique(np.asarray(mask))
    if values.size > 12:
        shown_values = [json_default(value) for value in values[:6]]
        shown_values.append("...")
        shown_values.extend(json_default(value) for value in values[-5:])
    else:
        shown_values = [json_default(value) for value in values]

    binary = binarize_mask(mask)
    ratio = float(np.count_nonzero(binary) / max(binary.size, 1))
    warnings: list[str] = []
    if ratio < 0.02:
        status = "too small"
        warnings.append("mask too small")
    elif ratio > 0.60:
        status = "too large"
        warnings.append("mask too large / likely full-image overlay")
    else:
        status = "valid"

    if debug_only:
        status = "debug only" if status == "valid" else f"debug only / {status}"

    if ratio > 0.60 and "mask too large / likely full-image overlay" not in warnings:
        warnings.append("mask too large / likely full-image overlay")

    return {
        "mask_ratio": round(ratio, 6),
        "mask_unique_values": shown_values,
        "mask_status": status,
        "warnings": warnings,
    }


def save_mask_overlay_png(mri_data: MRIData, mask: np.ndarray, path: Path, query: dict[str, list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_mask_overlay_png(mri_data, mask, query))
    return path


def save_standard_mask_overlays(mri_data: MRIData, mask: np.ndarray, prefix: str = FINAL_OVERLAY_PREFIX) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for plane in STANDARD_OVERLAY_PLANES:
        max_index = plane_length(mri_data.volume, plane) - 1
        index = max(0, max_index // 2)
        path = OUTPUT_DIR / f"{prefix}_{plane}.png"
        save_mask_overlay_png(mri_data, mask, path, {"plane": [plane], "index": [str(index)]})
        paths[plane] = path
    return paths


def render_mask_overlay_png(mri_data: MRIData, mask: np.ndarray, query: dict[str, list[str]]) -> bytes:
    normalized = require_normalized()
    plane = first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))).lower()
    max_index = plane_length(mri_data.volume, plane) - 1
    index = max(0, min(int(first(query, "index", str(max_index // 2))), max_index))
    image = slice_from_plane(normalized, plane, index)
    mask_slice = slice_from_plane(binarize_mask(mask).astype(np.float32), plane, index)
    return draw_slice_png(image, mask_slice)


def draw_slice_png(image: np.ndarray, mask_slice: np.ndarray | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if mask_slice is not None:
        binary = np.asarray(mask_slice) > 0.5
        rgba = np.zeros((*binary.shape, 4), dtype=np.float32)
        rgba[binary] = (1.0, 0.88, 0.0, 0.35)
        ax.imshow(rgba)
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
