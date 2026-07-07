from __future__ import annotations

import io
import json
import logging
import mimetypes
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
from scipy import ndimage as ndi

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from brain_mask import create_brain_mask, create_filled_brain_surface_mask, refine_brain_mask
from mesh_builder import BrainMesh, build_brain_mesh_from_mask, build_final_brain_mesh_from_mask, export_glb
from mri_loader import MRIData, discover_dicom_series, load_dicom, load_nifti, load_nifti_mask, save_brain_extracted, save_nifti_mask, save_nifti_volume
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
INPUT_NIFTI_PATH = OUTPUT_DIR / "input.nii.gz"
DEBUG_RAW_SURFACE_PATH = OUTPUT_DIR / "debug_raw_surface.glb"
DEBUG_MASK_MESH_PATH = OUTPUT_DIR / "debug_mask_mesh.glb"
BRAIN_MASK_OVERLAY_PATH = OUTPUT_DIR / "brain_mask_overlay.png"
BRAIN_OVERLAY_PATH = OUTPUT_DIR / "brain_overlay.png"
DEBUG_MASK_OVERLAY_PATH = OUTPUT_DIR / "debug_mask_overlay.png"
STANDARD_OVERLAY_PLANES = ("axial", "sagittal", "coronal")
FINAL_OVERLAY_PREFIX = "brain_overlay"
DEBUG_OVERLAY_PREFIX = "debug_mask_overlay"
BRAIN_ONLY_MESH_PATH = OUTPUT_DIR / "brain_only_mesh.glb"
MASK_SOURCE_META_PATH = OUTPUT_DIR / "brain_mask_source.json"
RELIABLE_SKULL_STRIP_WARNING = (
    "Reliable skull stripping is not available. Current mask is debug only. "
    "Final 3D brain mesh is disabled."
)

LOGGER = logging.getLogger("aidlc_mri.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATE: dict[str, object] = {
    "mri_data": None,
    "normalized": None,
    "series": None,
    "series_key": None,
    "mesh": None,
    "mask_result": None,
    "last_error": "",
    "last_hdbet_command": "",
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
            elif path == "/api/rebuild_mask":
                self.send_json(api_rebuild_mask())
            elif path == "/api/clear_outputs":
                self.send_json(api_clear_outputs())
            elif path == "/api/run_hdbet":
                self.send_json(api_run_hdbet())
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
    mask_state = current_mask_state()
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
        "hdbet_installed": hdbet_installed(),
        "mask_source": mask_state["mask_source"],
        "mask_status": mask_state["mask_status"],
        "reliable_mask": mask_state["reliable_mask"],
        "brain_mask_path": str(RAW_MASK_PATH) if RAW_MASK_PATH.exists() else "",
        "mesh_path": str(BRAIN_ONLY_MESH_PATH) if BRAIN_ONLY_MESH_PATH.exists() else "",
        "last_error": str(STATE.get("last_error") or ""),
        "last_hdbet_command": str(STATE.get("last_hdbet_command") or ""),
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
    diagnostics = effective_mask_diagnostics(result)
    final_allowed = is_final_mask_allowed(result, diagnostics)
    mask_path = RAW_MASK_PATH if final_allowed else FALLBACK_MASK_PATH
    overlay_path = BRAIN_OVERLAY_PATH if final_allowed else DEBUG_MASK_OVERLAY_PATH
    save_mask_overlay_png(mri_data, result.mask, overlay_path, query)
    if final_allowed:
        save_mask_overlay_png(mri_data, result.mask, BRAIN_MASK_OVERLAY_PATH, query)
    elif BRAIN_MASK_OVERLAY_PATH.exists():
        BRAIN_MASK_OVERLAY_PATH.unlink()
    overlay_paths = save_standard_mask_overlays(
        mri_data,
        result.mask,
        prefix=FINAL_OVERLAY_PREFIX if final_allowed else DEBUG_OVERLAY_PREFIX,
    )
    LOGGER.info(
        "Mask diagnostics: unique=%s ratio=%s status=%s components=%s largest=%s holes=%s edge_leakage=%s final_allowed=%s",
        diagnostics["mask_unique_values"],
        diagnostics["mask_ratio"],
        diagnostics["mask_status"],
        diagnostics["component_count"],
        diagnostics["largest_component_ratio"],
        diagnostics["hole_ratio"],
        diagnostics["edge_leakage"],
        final_allowed,
    )
    return {
        "method": result.method_used,
        "mask_source": mask_source_label(result),
        "reliable_for_3d": final_allowed,
        "debug_only": not final_allowed,
        "mask_path": str(mask_path),
        "overlay_path": str(overlay_path),
        "overlay_paths": {key: str(value) for key, value in overlay_paths.items()},
        "warnings": list(result.warnings or []) + list(diagnostics["warnings"]),
        "mask_ratio": diagnostics["mask_ratio"],
        "mask_unique_values": diagnostics["mask_unique_values"],
        "mask_status": diagnostics["mask_status"],
        "component_count": diagnostics["component_count"],
        "largest_component_ratio": diagnostics["largest_component_ratio"],
        "hole_ratio": diagnostics["hole_ratio"],
        "edge_leakage": diagnostics["edge_leakage"],
        "ellipse_like": diagnostics["ellipse_like"],
        "status_warning": ""
        if final_allowed
        else RELIABLE_SKULL_STRIP_WARNING,
        "reliable_mask": final_allowed,
        "metadata": result.metadata,
    }


def api_mask_overlay_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    return render_mask_overlay_png(mri_data, result.mask, query)


def api_rebuild_mask() -> dict:
    removed = clear_mask_cache(OUTPUT_DIR)
    STATE["mesh"] = None
    STATE["mask_result"] = None
    mri_data = get_loaded_mri()
    if mri_data is not None:
        STATE["normalized"] = normalize_intensity(mri_data.volume)
    LOGGER.warning("Mask cache rebuilt from scratch requested. Removed files: %s", removed)
    return {
        "ok": True,
        "removed": [str(path) for path in removed],
        "mask_source": "none",
        "mask_status": "missing",
        "reliable_mask": False,
        "message": "Mask cache cleared. Generate/check brain mask to rebuild from skull stripping tools or debug fallback.",
    }


def api_clear_outputs() -> dict:
    removed = clear_mask_cache(OUTPUT_DIR)
    STATE["mesh"] = None
    STATE["mask_result"] = None
    STATE["last_error"] = ""
    STATE["last_hdbet_command"] = ""
    return {
        "ok": True,
        "removed": [str(path) for path in removed],
        "mask_source": "none",
        "mask_status": "missing",
        "reliable_mask": False,
        "message": "Outputs cleared.",
    }


def api_run_hdbet() -> dict:
    mri_data = require_mri()
    STATE["mesh"] = None
    STATE["mask_result"] = None
    clear_mask_cache(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_nifti_volume(mri_data.volume, mri_data.affine, INPUT_NIFTI_PATH)

    install_probe = probe_hdbet_install()
    if not install_probe["installed"]:
        STATE["last_error"] = str(install_probe["stderr"] or "HD-BET is not importable.")
        return hdbet_failure_payload("HD-BET is not installed or not importable.", install_probe)

    attempts = run_hdbet_commands(INPUT_NIFTI_PATH, BRAIN_ONLY_VOLUME_PATH)
    result = attempts[-1]["result"] if attempts and attempts[-1].get("result") is not None else None
    mask_candidate = find_hdbet_output_mask(OUTPUT_DIR)
    if result is None or int(result.returncode) != 0 or mask_candidate is None:
        stderr = "\n\n".join(str(item.get("stderr") or "").strip() for item in attempts if item.get("stderr")).strip()
        stdout = "\n\n".join(str(item.get("stdout") or "").strip() for item in attempts if item.get("stdout")).strip()
        message = "HD-BET failed or did not produce a mask file."
        STATE["last_error"] = stderr or stdout or message
        return {
            **hdbet_failure_payload(message, install_probe),
            "command": str(STATE.get("last_hdbet_command") or ""),
            "attempts": strip_hdbet_attempts(attempts),
            "returncode": result.returncode if result is not None else None,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
            "mask_candidates": [str(path) for path in sorted(OUTPUT_DIR.glob("*mask*.nii.gz"))],
        }

    mask = binarize_mask(load_nifti_mask(mask_candidate))
    save_nifti_mask(mask, mri_data.affine, RAW_MASK_PATH)
    save_brain_extracted(mri_data.volume, mask, mri_data.affine, BRAIN_ONLY_VOLUME_PATH)
    diagnostics = mask_diagnostics(mask, debug_only=False)
    diagnostics["mask_status"] = "valid"
    metadata = {
        "method": "HD-BET",
        "mask_source": "hd-bet",
        "mask_status": "valid",
        "reliable_mask": True,
        "reliable_for_3d": True,
        "debug_only": False,
        "command": str(STATE.get("last_hdbet_command") or ""),
        "returncode": result.returncode,
        "stdout": (result.stdout or "")[-4000:],
        "stderr": (result.stderr or "")[-4000:],
        "tool_mask_path": str(mask_candidate),
        "tool_brain_path": str(BRAIN_ONLY_VOLUME_PATH),
        "quality_warnings": [],
    }
    save_mask_source_metadata_for("hd-bet", "HD-BET", "valid")
    save_mask_overlay_png(mri_data, mask, BRAIN_OVERLAY_PATH, {})
    save_mask_overlay_png(mri_data, mask, BRAIN_MASK_OVERLAY_PATH, {})
    save_standard_mask_overlays(mri_data, mask, prefix=FINAL_OVERLAY_PREFIX)
    skull_result = SkullStripResult(
        raw_mask=mask,
        refined_mask=mask,
        filled_mask=mask,
        mask=mask,
        brain_extracted=mri_data.volume * mask.astype(np.float32),
        mask_path=RAW_MASK_PATH,
        refined_mask_path=RAW_MASK_PATH,
        filled_mask_path=RAW_MASK_PATH,
        brain_path=BRAIN_ONLY_VOLUME_PATH,
        method_used="HD-BET",
        reliable_for_3d=True,
        debug_only=False,
        metadata=metadata,
        warnings=[],
    )
    STATE["mask_result"] = skull_result
    STATE["last_error"] = ""
    return {
        "ok": True,
        "hdbet_installed": True,
        "mask_source": "hd-bet",
        "mask_status": "valid",
        "reliable_mask": True,
        "brain_mask_path": str(RAW_MASK_PATH),
        "brain_only_path": str(BRAIN_ONLY_VOLUME_PATH),
        "mesh_path": str(BRAIN_ONLY_MESH_PATH) if BRAIN_ONLY_MESH_PATH.exists() else "",
        "command": str(STATE.get("last_hdbet_command") or ""),
        "attempts": strip_hdbet_attempts(attempts),
        "returncode": result.returncode,
        "stdout": (result.stdout or "")[-4000:],
        "stderr": (result.stderr or "")[-4000:],
    }


def api_mesh(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = effective_mask_diagnostics(result)
    reliable_mask = is_final_mask_allowed(result, diagnostics)
    debug_requested = first(query, "debug", "0") == "1"
    if not reliable_mask and not debug_requested:
        LOGGER.warning(RELIABLE_SKULL_STRIP_WARNING)
        return {
            "ok": False,
            "status": "debug_only",
            "message": "SynthStrip or HD-BET brain mask is required for final 3D brain mesh.",
            "warning": RELIABLE_SKULL_STRIP_WARNING,
            "mesh_path": None,
            "reliable_for_3d": False,
            "debug_only": True,
            "mask_source": mask_source_label(result),
            "mask_status": diagnostics["mask_status"],
        }
    mesh = get_or_build_mesh(query)
    metadata = mesh.metadata or {}
    output_path = metadata.get("mesh_path", str(DEBUG_MASK_MESH_PATH))
    return {
        "ok": bool(metadata.get("reliable_for_3d", False)),
        "status": "ready" if metadata.get("reliable_for_3d", False) else "debug_only",
        "message": "" if metadata.get("reliable_for_3d", False) else "Debug mask mesh only; final 3D brain mesh is disabled.",
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "quality_warnings": mesh.quality_warnings or [],
        "metadata": metadata,
        "mesh_path": output_path,
        "reliable_for_3d": bool(metadata.get("reliable_for_3d", False)),
        "debug_only": bool(metadata.get("debug_only", True)),
    }


def api_mesh_plot(query: dict[str, list[str]]) -> str:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = effective_mask_diagnostics(result)
    reliable_mask = is_final_mask_allowed(result, diagnostics)
    if not reliable_mask and first(query, "debug", "0") != "1":
        return (
            "<!doctype html><html><body style='font-family:system-ui;padding:24px;background:#0f172a;color:#e5e7eb'>"
            f"<h2>Final 3D brain mesh disabled</h2><p>{RELIABLE_SKULL_STRIP_WARNING}</p>"
            "<p>SynthStrip or HD-BET brain_mask.nii.gz is required.</p></body></html>"
        )
    mesh = get_or_build_mesh(query)
    fig = mesh_to_figure(mesh)
    return fig.to_html(include_plotlyjs=True, full_html=True, config={"displaylogo": False, "responsive": True})


def clear_mask_cache(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "brain_mask.npy",
        "input.nii.gz",
        "brain_mask.nii.gz",
        "debug_mask.npy",
        "debug_mask_mesh.glb",
        "debug_raw_surface.glb",
        "brain_only_mesh.glb",
        "brain_only.nii.gz",
        "brain_mask_source.json",
        "filled_brain_mask.nii.gz",
        "refined_brain_mask.nii.gz",
        "fallback_preview_mask.nii.gz",
        "debug_fallback_mask.nii.gz",
        "debug_brain_only.nii.gz",
        "brain_mask_overlay.png",
        "brain_overlay.png",
        "debug_mask_overlay.png",
    }
    patterns = ("*.png", "*.npy", "*mask*.nii.gz", "*mask*.npz")
    targets: set[Path] = {output_dir / name for name in names}
    for pattern in patterns:
        targets.update(output_dir.glob(pattern))

    removed: list[Path] = []
    for path in sorted(targets, key=lambda item: str(item).lower()):
        try:
            resolved = path.resolve()
            if output_dir.resolve() not in resolved.parents and resolved != output_dir.resolve():
                continue
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(path)
        except Exception:
            LOGGER.exception("Failed to remove cached mask file: %s", path)
    return removed


def invalidate_final_outputs() -> None:
    for path in (RAW_MASK_PATH, BRAIN_ONLY_VOLUME_PATH, BRAIN_ONLY_MESH_PATH, BRAIN_OVERLAY_PATH, MASK_SOURCE_META_PATH):
        try:
            if path.exists() and path.is_file():
                path.unlink()
                LOGGER.warning("Removed stale final output because current mask is not reliable: %s", path)
        except Exception:
            LOGGER.exception("Failed to remove stale final output: %s", path)


def probe_hdbet_install() -> dict:
    command = [sys.executable, "-c", "import HD_BET; print('HD_BET installed')"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, cwd=str(ROOT))
        return {
            "installed": result.returncode == 0,
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as exc:
        return {"installed": False, "command": " ".join(command), "returncode": None, "stdout": "", "stderr": repr(exc)}


def hdbet_installed() -> bool:
    cached = STATE.get("hdbet_installed")
    if isinstance(cached, bool):
        return cached
    installed = bool(probe_hdbet_install().get("installed", False))
    STATE["hdbet_installed"] = installed
    return installed


def find_hdbet_output_mask(output_dir: Path) -> Path | None:
    candidates = [
        output_dir / "brain_only_mask.nii.gz",
        output_dir / "brain_only_bet.nii.gz",
        output_dir / "input_mask.nii.gz",
        output_dir / "input_bet.nii.gz",
    ]
    candidates.extend(sorted(output_dir.glob("*mask*.nii.gz")))
    candidates.extend(sorted(output_dir.glob("*_mask.nii.gz")))
    candidates.extend(sorted(output_dir.glob("*_bet.nii.gz")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists() and path != RAW_MASK_PATH:
            unique.append(path)
    if not unique:
        return None
    return sorted(unique, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def run_hdbet_commands(input_path: Path, output_path: Path) -> list[dict]:
    commands = [
        [
            sys.executable,
            "-m",
            "HD_BET.run",
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-device",
            "cpu",
            "-mode",
            "fast",
        ],
        [
            sys.executable,
            "-m",
            "HD_BET.entry_point",
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-device",
            "cpu",
            "--disable_tta",
            "--save_bet_mask",
        ],
    ]
    attempts: list[dict] = []
    for command in commands:
        command_text = " ".join(command)
        STATE["last_hdbet_command"] = command_text
        LOGGER.warning("Running HD-BET command: %s", command_text)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800, cwd=str(ROOT))
            attempts.append(
                {
                    "command": command_text,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "result": result,
                }
            )
            mask_candidate = find_hdbet_output_mask(OUTPUT_DIR)
            if result.returncode == 0 and mask_candidate is not None:
                return attempts
            if "No module named HD_BET.run" not in (result.stderr or "") and command[2] == "HD_BET.run":
                return attempts
        except Exception as exc:
            attempts.append({"command": command_text, "returncode": None, "stdout": "", "stderr": repr(exc), "result": None})
    return attempts


def strip_hdbet_attempts(attempts: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in attempts:
        rows.append(
            {
                "command": item.get("command"),
                "returncode": item.get("returncode"),
                "stdout": str(item.get("stdout") or "")[-2000:],
                "stderr": str(item.get("stderr") or "")[-2000:],
            }
        )
    return rows


def hdbet_failure_payload(message: str, install_probe: dict) -> dict:
    STATE["mask_result"] = None
    invalidate_final_outputs()
    return {
        "ok": False,
        "hdbet_installed": bool(install_probe.get("installed", False)),
        "mask_source": "fallback_threshold",
        "mask_status": "debug_only",
        "reliable_mask": False,
        "brain_mask_path": "",
        "mesh_path": None,
        "message": message,
        "last_error": str(STATE.get("last_error") or message),
        "install_probe": install_probe,
    }


def current_mask_state() -> dict:
    cached = STATE.get("mask_result")
    if isinstance(cached, SkullStripResult):
        diagnostics = effective_mask_diagnostics(cached)
        reliable = is_final_mask_allowed(cached, diagnostics)
        return {
            "mask_source": mask_source_label(cached),
            "mask_status": diagnostics.get("mask_status", "missing"),
            "reliable_mask": reliable,
        }
    if RAW_MASK_PATH.exists():
        source_meta = load_mask_source_metadata()
        source = str(source_meta.get("mask_source") or "cached_unknown").lower()
        status = str(source_meta.get("mask_status") or "missing")
        reliable = source in {"synthstrip", "hd-bet"} and status == "valid"
        return {"mask_source": source if reliable else "cached_unknown", "mask_status": status, "reliable_mask": reliable}
    if FALLBACK_MASK_PATH.exists():
        return {"mask_source": "fallback_threshold", "mask_status": "invalid_threshold_noise", "reliable_mask": False}
    return {"mask_source": "none", "mask_status": "missing", "reliable_mask": False}


def get_or_build_mesh(query: dict[str, list[str]]) -> BrainMesh:
    cached = STATE.get("mesh")
    if isinstance(cached, BrainMesh):
        return cached
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    result_warnings = list(result.warnings or []) + list(result.metadata.get("quality_warnings", []) or [])
    diagnostics = effective_mask_diagnostics(result)
    result_warnings.extend(diagnostics["warnings"])
    debug_requested = first(query, "debug", "0") == "1"
    final_allowed = is_final_mask_allowed(result, diagnostics) and not result_warnings
    if not final_allowed and not debug_requested:
        raise RuntimeError("SynthStrip or HD-BET brain mask is required for final 3D brain mesh.")
    mask = binarize_mask(result.mask).astype(np.uint8)
    downsample_factor = int(first(query, "downsample", "2"))
    step_size = int(first(query, "step", "1"))
    gaussian_sigma = float(first(query, "sigma", "1.0"))
    smoothing_iterations = int(first(query, "smooth", "5"))
    if final_allowed:
        mesh = build_final_brain_mesh_from_mask(
            mask,
            spacing=mri_data.spacing,
            reliable_mask=True,
            mask_source=mask_source_label(result),
            brain_mask_path=RAW_MASK_PATH,
            gaussian_sigma=gaussian_sigma,
            step_size=step_size,
            downsample_factor=downsample_factor,
            smoothing_iterations=smoothing_iterations,
            apply_mesh_smoothing=True,
        )
    else:
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
            "mask_source_label": mask_source_label(result),
            "mesh_path": str(output_path),
            "mesh_mode": "brain-only reliable mask" if final_allowed else "debug-only mask surface",
            "surface_mode": "Stable brain mask surface" if final_allowed else "Debug mask preview",
            "method": result.method_used,
            "reliable_for_3d": final_allowed,
            "debug_only": not final_allowed,
            "quality_warnings": result_warnings,
            "mask_ratio": diagnostics["mask_ratio"],
            "mask_unique_values": diagnostics["mask_unique_values"],
            "mask_status": diagnostics["mask_status"],
            "component_count": diagnostics["component_count"],
            "largest_component_ratio": diagnostics["largest_component_ratio"],
            "hole_ratio": diagnostics["hole_ratio"],
            "edge_leakage": diagnostics["edge_leakage"],
            "warning": None
            if final_allowed
            else RELIABLE_SKULL_STRIP_WARNING,
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
    cached_result = load_cached_brain_mask_result(mri_data)
    if cached_result is not None:
        STATE["mask_result"] = cached_result
        return cached_result
    try:
        result = run_skull_stripping(mri_data, "synthstrip", OUTPUT_DIR)
    except Exception as reliable_error:
        result = run_skull_stripping(mri_data, "fallback", OUTPUT_DIR)
        result.warnings.append(f"Reliable skull stripping unavailable: {reliable_error}")

    diagnostics = effective_mask_diagnostics(result)
    final_mask_allowed = is_final_mask_allowed(result, diagnostics, require_mask_file=False)
    if final_mask_allowed:
        final_mask = binarize_mask(result.mask)
        save_nifti_mask(final_mask, mri_data.affine, RAW_MASK_PATH)
        save_mask_source_metadata(result, diagnostics)
        save_brain_extracted(mri_data.volume, final_mask, mri_data.affine, BRAIN_ONLY_VOLUME_PATH)
        save_mask_overlay_png(mri_data, final_mask, BRAIN_OVERLAY_PATH, {})
        save_standard_mask_overlays(mri_data, final_mask, prefix=FINAL_OVERLAY_PREFIX)
    else:
        invalidate_final_outputs()
        save_nifti_mask(binarize_mask(result.mask), mri_data.affine, FALLBACK_MASK_PATH)

    if final_mask_allowed:
        save_mask_overlay_png(mri_data, result.mask, BRAIN_MASK_OVERLAY_PATH, {})
    else:
        if BRAIN_MASK_OVERLAY_PATH.exists():
            BRAIN_MASK_OVERLAY_PATH.unlink()
        save_mask_overlay_png(mri_data, result.mask, DEBUG_MASK_OVERLAY_PATH, {})
        save_standard_mask_overlays(mri_data, result.mask, prefix=DEBUG_OVERLAY_PREFIX)
    STATE["mask_result"] = result
    return result


def is_final_mask_allowed(
    result: SkullStripResult,
    diagnostics: dict | None = None,
    require_mask_file: bool = True,
) -> bool:
    diagnostics = diagnostics or effective_mask_diagnostics(result)
    source = mask_source_label(result)
    return bool(
        result.reliable_for_3d
        and not result.debug_only
        and not result.metadata.get("quality_warnings")
        and source in {"synthstrip", "hd-bet"}
        and (RAW_MASK_PATH.exists() if require_mask_file else True)
        and diagnostics.get("mask_status") == "valid"
    )


def load_cached_brain_mask_result(mri_data: MRIData) -> SkullStripResult | None:
    if not RAW_MASK_PATH.exists():
        return None
    source_meta = load_mask_source_metadata()
    source = str(source_meta.get("mask_source", "")).lower()
    generated_at = str(source_meta.get("generated_at") or "")
    if source not in {"synthstrip", "hd-bet"} or not generated_at:
        LOGGER.warning(
            "Cached brain_mask.nii.gz has no reliable SynthStrip/HD-BET source and generated_at metadata; using fallback/debug path."
        )
        return None
    try:
        mask = binarize_mask(load_mask_for_volume(mri_data, RAW_MASK_PATH))
    except Exception:
        LOGGER.exception("cached brain_mask.nii.gz could not be loaded; regenerating")
        return None
    if not np.any(mask):
        return None
    save_brain_extracted(mri_data.volume, mask, mri_data.affine, BRAIN_ONLY_VOLUME_PATH)
    quality_warnings: list[str] = []
    metadata = {
        "method": "Cached brain_mask",
        "mask_source": source,
        "mask_status": "valid",
        "reliable_mask": True,
        "reliable_for_3d": True,
        "debug_only": False,
        "quality_warnings": quality_warnings,
        "cached_from": source_meta,
    }
    return SkullStripResult(
        raw_mask=mask,
        refined_mask=mask,
        filled_mask=mask,
        mask=mask,
        brain_extracted=mri_data.volume * mask.astype(np.float32),
        mask_path=RAW_MASK_PATH,
        refined_mask_path=RAW_MASK_PATH,
        filled_mask_path=RAW_MASK_PATH,
        brain_path=BRAIN_ONLY_VOLUME_PATH,
        method_used="Cached brain_mask",
        reliable_for_3d=True,
        debug_only=False,
        metadata=metadata,
        warnings=quality_warnings,
    )


def mask_source_label(result: SkullStripResult) -> str:
    source = str(result.metadata.get("mask_source") or result.metadata.get("method") or result.method_used or "").lower()
    if "synthstrip" in source:
        return "synthstrip"
    if "hd-bet" in source or "hdbet" in source:
        return "hd-bet"
    if "ellipse" in source:
        return "ellipse_debug"
    if "fallback" in source or result.debug_only:
        return "fallback_threshold"
    return "none"


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
        return is_final_mask_allowed(cached, require_mask_file=True)
    source = str(load_mask_source_metadata().get("mask_source", "")).lower()
    return RAW_MASK_PATH.exists() and source in {"synthstrip", "hd-bet"}


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


def effective_mask_diagnostics(result: SkullStripResult) -> dict:
    diagnostics = mask_diagnostics(result.mask, result.debug_only)
    source = mask_source_label(result)
    metadata_status = str(result.metadata.get("mask_status") or "").lower()
    if (
        source in {"synthstrip", "hd-bet"}
        and result.reliable_for_3d
        and not result.debug_only
        and metadata_status == "valid"
        and RAW_MASK_PATH.exists()
    ):
        diagnostics = {**diagnostics}
        diagnostics["mask_status"] = "valid"
        diagnostics["ellipse_like"] = False
        diagnostics["warnings"] = [
            warning
            for warning in diagnostics.get("warnings", [])
            if "ellipse-like" not in str(warning).lower()
            and "threshold tissue noise" not in str(warning).lower()
            and "debug" not in str(warning).lower()
        ]
    return diagnostics


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
    component_count = 0
    largest_component_ratio = 0.0
    hole_ratio = 0.0
    edge_leakage = False
    if np.any(binary):
        labels, component_count = ndi.label(binary)
        sizes = np.bincount(labels.ravel())
        if sizes.size:
            sizes[0] = 0
            largest = int(sizes.max())
            largest_component_ratio = float(largest / max(int(np.count_nonzero(binary)), 1))
        filled = ndi.binary_fill_holes(binary)
        hole_voxels = int(np.count_nonzero(filled & ~binary))
        hole_ratio = float(hole_voxels / max(int(np.count_nonzero(filled)), 1))
        edge_leakage = mask_touches_volume_edge(binary)

    ellipse_like = is_ellipse_like_mask(binary)
    if ratio < 0.02:
        status = "too small"
        warnings.append("mask too small")
    elif ratio > 0.60:
        status = "too large"
        warnings.append("mask too large / likely full-image overlay")
    elif component_count > 8 or largest_component_ratio < 0.85 or hole_ratio > 0.12:
        status = "invalid_threshold_noise"
        warnings.append("Mask looks like threshold tissue noise instead of a solid brain extraction.")
    elif edge_leakage:
        status = "skull_neck_leakage"
        warnings.append("Mask touches the volume edge; skull/scalp/neck leakage is likely.")
    elif ellipse_like:
        status = "ellipse_like"
        warnings.append("This is ellipse-like debug mask, not final brain extraction.")
    else:
        status = "valid"

    if debug_only:
        status = "invalid_threshold_noise"
        if "Mask looks like threshold tissue noise instead of a solid brain extraction." not in warnings:
            warnings.append("Mask looks like threshold tissue noise instead of a solid brain extraction.")
        warnings.append(RELIABLE_SKULL_STRIP_WARNING)

    if ratio > 0.60 and "mask too large / likely full-image overlay" not in warnings:
        warnings.append("mask too large / likely full-image overlay")

    return {
        "mask_ratio": round(ratio, 6),
        "mask_unique_values": shown_values,
        "mask_status": status,
        "component_count": int(component_count),
        "largest_component_ratio": round(largest_component_ratio, 6),
        "hole_ratio": round(hole_ratio, 6),
        "edge_leakage": bool(edge_leakage),
        "ellipse_like": ellipse_like,
        "warnings": warnings,
    }


def save_mask_source_metadata(result: SkullStripResult, diagnostics: dict) -> None:
    source = mask_source_label(result)
    save_mask_source_metadata_for(source, result.method_used, str(diagnostics.get("mask_status")))


def save_mask_source_metadata_for(source: str, method: str, mask_status: str) -> None:
    MASK_SOURCE_META_PATH.write_text(
        json.dumps(
            {
                "mask_source": source,
                "method": method,
                "mask_status": mask_status,
                "mask_path": str(RAW_MASK_PATH),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_mask_source_metadata() -> dict:
    if not MASK_SOURCE_META_PATH.exists():
        return {}
    try:
        return json.loads(MASK_SOURCE_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.exception("Could not read brain mask source metadata.")
        return {}


def mask_touches_volume_edge(mask: np.ndarray, margin: int = 1) -> bool:
    binary = np.asarray(mask).astype(bool)
    if not np.any(binary):
        return False
    margin = max(1, int(margin))
    for axis, size in enumerate(binary.shape):
        low = [slice(None)] * binary.ndim
        high = [slice(None)] * binary.ndim
        low[axis] = slice(0, min(margin, size))
        high[axis] = slice(max(0, size - margin), size)
        if np.any(binary[tuple(low)]) or np.any(binary[tuple(high)]):
            return True
    return False


def is_ellipse_like_mask(mask: np.ndarray) -> bool:
    binary = np.asarray(mask).astype(bool)
    coords = np.argwhere(binary)
    if coords.shape[0] < 512:
        return False
    lower = coords.min(axis=0)
    upper = coords.max(axis=0)
    extent = upper - lower + 1
    if np.any(extent < 8):
        return False
    bbox = binary[lower[0] : upper[0] + 1, lower[1] : upper[1] + 1, lower[2] : upper[2] + 1]
    center = (np.array(bbox.shape, dtype=np.float32) - 1.0) / 2.0
    radii = np.maximum(np.array(bbox.shape, dtype=np.float32) / 2.0, 1.0)
    grid = np.indices(bbox.shape, dtype=np.float32)
    distance = np.zeros(bbox.shape, dtype=np.float32)
    for axis in range(3):
        distance += ((grid[axis] - center[axis]) / radii[axis]) ** 2
    ellipsoid = distance <= 1.0
    intersection = int(np.count_nonzero(bbox & ellipsoid))
    union = int(np.count_nonzero(bbox | ellipsoid))
    if union == 0:
        return False
    jaccard = intersection / union
    fill_ratio = int(np.count_nonzero(bbox)) / max(int(np.count_nonzero(ellipsoid)), 1)
    return bool(jaccard > 0.72 and 0.70 <= fill_ratio <= 1.30)


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
