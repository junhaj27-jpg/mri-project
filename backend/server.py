from __future__ import annotations

import io
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http import cookies
from secrets import token_urlsafe
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
from mesh_builder import BrainMesh, build_brain_mesh_from_mask, build_final_brain_mesh_from_mask, build_mesh_from_mask, export_glb
from mri_loader import MRIData, discover_dicom_series, load_dicom, load_nifti, load_nifti_mask, save_brain_extracted, save_nifti_mask, save_nifti_volume
from preprocessing import normalize_intensity, plane_length, slice_from_plane
from region_segmentation import (
    REGION_COLORS,
    REGION_GROUPS,
    REGION_SEGMENTATION_DISABLED_MESSAGE,
    build_region_mesh,
    export_region_volumes_csv,
    fastsurfer_available,
    load_labelmap_array,
    load_region_labelmap,
    run_region_segmentation,
    slugify_region,
    synthseg_available as region_synthseg_available,
)
from report import DISCLAIMER
from skull_stripping import SkullStripResult, run_skull_stripping


HOST = "127.0.0.1"
PORT = 8000
ROOT = PROJECT_ROOT
FRONTEND_DIR = ROOT / "frontend"
STATIC_MESH_DIR = FRONTEND_DIR / "static" / "meshes"
DEFAULT_DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
OUTPUT_DIR = ROOT / "outputs"
AUTH_DIR = ROOT / "data" / "auth"
USERS_PATH = AUTH_DIR / "users.json"
SESSION_COOKIE_NAME = "aidlc_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
MASK_PATH = OUTPUT_DIR / "filled_brain_mask.nii.gz"
RAW_MASK_PATH = OUTPUT_DIR / "brain_mask.nii.gz"
PROCESSED_MASK_PATH = ROOT / "data" / "processed" / "brain_mask.nii.gz"
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
STATIC_BRAIN_MESH_PATH = STATIC_MESH_DIR / "brain.glb"
DEBUG_PREVIEW_MESH_PATH = STATIC_MESH_DIR / "debug_brain_preview.glb"
DEBUG_PREVIEW_META_PATH = STATIC_MESH_DIR / "debug_brain_preview.json"
MASK_SOURCE_META_PATH = OUTPUT_DIR / "brain_mask_source.json"
REGION_LABELMAP_PATH = OUTPUT_DIR / "regions_labelmap.nii.gz"
TARGET_MASK_PATH = OUTPUT_DIR / "target_mask.nii.gz"
REGION_MESH_DIR = OUTPUT_DIR / "meshes"
REGION_VOLUMES_CSV_PATH = OUTPUT_DIR / "region_volumes.csv"
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

SESSIONS: dict[str, dict[str, object]] = {}


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def now_timestamp() -> float:
    return datetime.now(timezone.utc).timestamp()


def hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = base64.b64decode(salt.encode("ascii")) if salt else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 120_000)
    return (
        "pbkdf2_sha256$120000$"
        + base64.b64encode(salt_bytes).decode("ascii")
        + "$"
        + base64.b64encode(digest).decode("ascii")
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256" or iterations != "120000":
            return False
        expected = hash_password(password, salt).rsplit("$", 1)[-1]
        return hmac.compare_digest(expected, digest)
    except ValueError:
        return False


def default_user_store() -> dict:
    return {
        "users": [
            {
                "username": "admin",
                "display_name": "Administrator",
                "role": "admin",
                "password_hash": hash_password("admin1234"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    }


def load_users() -> dict:
    if not USERS_PATH.exists():
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        store = default_user_store()
        USERS_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        return store
    return json.loads(USERS_PATH.read_text(encoding="utf-8"))


def save_users(store: dict) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    USERS_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def public_user(user: dict) -> dict:
    return {
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": user.get("role", "user"),
        "created_at": user.get("created_at", ""),
    }


def find_user(username: str) -> dict | None:
    username = username.strip().lower()
    for user in load_users().get("users", []):
        if user.get("username", "").lower() == username:
            return user
    return None


def create_session(user: dict) -> str:
    token = token_urlsafe(32)
    SESSIONS[token] = {
        "username": user["username"],
        "role": user.get("role", "user"),
        "expires_at": now_timestamp() + SESSION_MAX_AGE_SECONDS,
    }
    return token


def get_session_user_from_headers(headers) -> dict | None:
    raw_cookie = headers.get("Cookie", "")
    jar = cookies.SimpleCookie()
    jar.load(raw_cookie)
    morsel = jar.get(SESSION_COOKIE_NAME)
    if not morsel:
        return None
    token = morsel.value
    session = SESSIONS.get(token)
    if not session:
        return None
    if float(session.get("expires_at", 0)) < now_timestamp():
        SESSIONS.pop(token, None)
        return None
    user = find_user(str(session.get("username", "")))
    if not user:
        SESSIONS.pop(token, None)
        return None
    return user


def clear_session_from_headers(headers) -> None:
    raw_cookie = headers.get("Cookie", "")
    jar = cookies.SimpleCookie()
    jar.load(raw_cookie)
    morsel = jar.get(SESSION_COOKIE_NAME)
    if morsel:
        SESSIONS.pop(morsel.value, None)


class BackendHandler(BaseHTTPRequestHandler):
    server_version = "AIDLCMRI/0.1"

    PUBLIC_GET_PATHS = {"/login", "/health"}
    PUBLIC_POST_PATHS = {"/api/auth/login"}

    def current_user(self) -> dict | None:
        return get_session_user_from_headers(self.headers)

    def is_public_get(self, path: str) -> bool:
        return path in self.PUBLIC_GET_PATHS or path.startswith("/static/") or path.startswith("/assets/")

    def require_auth(self, path: str) -> dict | None:
        user = self.current_user()
        if user:
            return user
        if path.startswith("/api/"):
            self.send_json({"error": "Login required"}, status=401)
        else:
            self.redirect("/login")
        return None

    def require_admin(self) -> dict | None:
        user = self.require_auth(urlparse(self.path).path)
        if not user:
            return None
        if user.get("role") != "admin":
            self.send_json({"error": "Admin permission required"}, status=403)
            return None
        return user

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if not self.is_public_get(path) and not self.require_auth(path):
                return

            if path == "/login":
                if self.current_user():
                    self.redirect("/")
                else:
                    self.send_static(FRONTEND_DIR / "login.html")
            elif path == "/":
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
            elif path == "/guide":
                self.send_static(FRONTEND_DIR / "guide.html")
            elif path == "/admin":
                if not self.require_admin():
                    return
                self.send_static(FRONTEND_DIR / "admin.html")
            elif path.startswith("/assets/"):
                self.send_static(FRONTEND_DIR / path.removeprefix("/"))
            elif path.startswith("/static/"):
                self.send_static(FRONTEND_DIR / path.removeprefix("/"))
            elif path.startswith("/outputs/"):
                self.send_output_file(path)
            elif path == "/health":
                self.send_json({"status": "ok", "project": "aidlc-mri"})
            elif path == "/api/auth/session":
                self.send_json({"authenticated": True, "user": public_user(self.current_user())})
            elif path == "/api/admin/users":
                if not self.require_admin():
                    return
                users = [public_user(user) for user in load_users().get("users", [])]
                self.send_json({"users": users})
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
            elif path == "/api/mri/metadata":
                self.send_json(api_mri_metadata(query))
            elif path == "/api/mri/slice":
                self.send_mri_slice(query)
            elif path.startswith("/api/mri/slice/"):
                route_query = dict(query)
                route_query["plane"] = [path.rsplit("/", 1)[-1]]
                self.send_mri_slice(route_query)
            elif path == "/api/slice-info":
                self.send_json(api_slice_info(query))
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
            elif path == "/api/build-mesh":
                self.send_json(api_build_mesh(query))
            elif path == "/api/build-debug-mesh":
                self.send_json(api_build_debug_mesh(query))
            elif path == "/api/build-preview-mesh":
                self.send_json(api_build_preview_mesh(query))
            elif path == "/api/mri/mesh/debug-preview":
                self.send_json(api_build_preview_mesh(query))
            elif path == "/api/mri/mesh/debug-preview/status":
                self.send_json(api_debug_preview_mesh_status())
            elif path == "/api/mesh-status":
                self.send_json(api_mesh_status())
            elif path == "/api/regions/status":
                self.send_json(api_region_status())
            elif path == "/api/regions/run":
                self.send_json(api_run_region_segmentation())
            elif path == "/api/regions/load":
                self.send_json(api_load_regions())
            elif path == "/api/regions/build-mesh":
                self.send_json(api_build_region_mesh(query))
            elif path == "/api/regions/build-all-meshes":
                self.send_json(api_build_all_region_meshes())
            elif path == "/api/regions/export-volumes":
                self.send_json(api_export_region_volumes())
            elif path == "/api/regions/overlay":
                self.send_bytes(api_region_overlay_png(query), "image/png")
            elif path == "/api/regions/mesh_plot":
                self.send_bytes(api_region_mesh_plot(query).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/mask_overlay":
                self.send_bytes(api_mask_overlay_png(query), "image/png")
            elif path == "/api/mesh":
                self.send_json(api_mesh(query))
            elif path == "/api/mesh_plot":
                self.send_bytes(api_mesh_plot(query).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/threejs_viewer":
                self.send_bytes(api_threejs_viewer(query).encode("utf-8"), "text/html; charset=utf-8")
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

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path not in self.PUBLIC_POST_PATHS and not self.require_auth(parsed.path):
                return

            if parsed.path == "/api/auth/login":
                self.handle_login()
            elif parsed.path == "/api/auth/logout":
                clear_session_from_headers(self.headers)
                self.send_json({"ok": True}, clear_session=True)
            elif parsed.path == "/api/admin/users":
                if not self.require_admin():
                    return
                self.handle_create_user()
            elif parsed.path in {"/api/clear-outputs", "/api/clear_outputs"}:
                self.send_json(api_clear_outputs())
            elif parsed.path in {"/api/run-hdbet", "/api/run_hdbet"}:
                self.send_json(api_run_hdbet())
            elif parsed.path == "/api/build-mesh":
                self.send_json(api_build_mesh(query))
            elif parsed.path == "/api/build-debug-mesh":
                self.send_json(api_build_debug_mesh(query))
            elif parsed.path == "/api/build-preview-mesh":
                self.send_json(api_build_preview_mesh(query))
            elif parsed.path == "/api/mri/mesh/debug-preview":
                self.send_json(api_build_preview_mesh(query))
            elif parsed.path == "/api/regions/run":
                self.send_json(api_run_region_segmentation())
            elif parsed.path == "/api/regions/build-mesh":
                self.send_json(api_build_region_mesh(query))
            elif parsed.path == "/api/regions/build-all-meshes":
                self.send_json(api_build_all_region_meshes())
            elif parsed.path == "/api/regions/export-volumes":
                self.send_json(api_export_region_volumes())
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            LOGGER.error("post request failed: %s\n%s", exc, traceback.format_exc())
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False).encode("utf-8")
            )

    def log_message(self, fmt: str, *args) -> None:
        LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def handle_login(self) -> None:
        body = self.read_json_body()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))
        user = find_user(username)
        if not user or not verify_password(password, str(user.get("password_hash", ""))):
            self.send_json({"error": "Invalid username or password"}, status=401)
            return
        token = create_session(user)
        self.send_json({"ok": True, "user": public_user(user)}, session_token=token)

    def handle_create_user(self) -> None:
        body = self.read_json_body()
        username = str(body.get("username", "")).strip().lower()
        display_name = str(body.get("display_name", "")).strip() or username
        role = str(body.get("role", "user")).strip().lower()
        password = str(body.get("password", ""))
        if not username or not username.replace("_", "").replace("-", "").isalnum():
            self.send_json({"error": "Username must use letters, numbers, hyphen, or underscore."}, status=400)
            return
        if role not in {"user", "admin"}:
            self.send_json({"error": "Role must be user or admin."}, status=400)
            return
        if len(password) < 8:
            self.send_json({"error": "Password must be at least 8 characters."}, status=400)
            return
        store = load_users()
        if any(user.get("username", "").lower() == username for user in store.get("users", [])):
            self.send_json({"error": "Username already exists."}, status=409)
            return
        user = {
            "username": username,
            "display_name": display_name,
            "role": role,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.setdefault("users", []).append(user)
        save_users(store)
        self.send_json({"ok": True, "user": public_user(user)}, status=201)

    def redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def send_json(
        self,
        payload: dict | list,
        status: int = 200,
        session_token: str | None = None,
        clear_session: bool = False,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if session_token:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}={session_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_MAX_AGE_SECONDS}",
            )
        if clear_session:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
            )
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_mri_slice(self, query: dict[str, list[str]]) -> None:
        try:
            self.send_bytes(api_mri_slice_png(query), "image/png")
        except Exception as exc:
            LOGGER.error("MRI slice render failed: %s\n%s", exc, traceback.format_exc())
            payload = {
                "error": str(exc),
                "plane": first(query, "plane", "sagittal"),
                "slice_index": first(query, "index", "middle"),
                "volume_loaded": get_loaded_mri() is not None,
            }
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(format_slice_error(payload).encode("utf-8"))

    def send_static(self, path: Path) -> None:
        path = path.resolve()
        frontend_root = FRONTEND_DIR.resolve()
        if frontend_root not in path.parents and path != frontend_root:
            self.send_error(403, "Forbidden")
            return
        if not path.exists() or not path.is_file():
            self.send_error(404, "Static file not found")
            return
        content_type = "model/gltf-binary" if path.suffix.lower() == ".glb" else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_bytes(path.read_bytes(), content_type)

    def send_output_file(self, request_path: str) -> None:
        relative = request_path.removeprefix("/outputs/").replace("/", "\\")
        path = (OUTPUT_DIR / relative).resolve()
        output_root = OUTPUT_DIR.resolve()
        if output_root not in path.parents and path != output_root:
            self.send_error(403, "Forbidden")
            return
        if not path.exists() or not path.is_file():
            self.send_error(404, "Output file not found")
            return
        content_type = "model/gltf-binary" if path.suffix.lower() == ".glb" else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_bytes(path.read_bytes(), content_type)


def api_status() -> dict:
    mri_data = get_loaded_mri()
    mask_state = current_mask_state()
    mask_info = current_mask_info(mri_data)
    region_state = region_status_payload()
    volume_info = volume_diagnostics(mri_data)
    return {
        "loaded": mri_data is not None,
        "volume_loaded": volume_info["volume_loaded"],
        "source": mri_data.source_type if mri_data else None,
        "source_label": mri_data.source_label if mri_data else None,
        "shape": tuple(int(value) for value in mri_data.volume.shape) if mri_data else None,
        "volume_shape": volume_info["volume_shape"],
        "volume_dtype": volume_info["dtype"],
        "volume_min": volume_info["min_intensity"],
        "volume_max": volume_info["max_intensity"],
        "spacing": mri_data.spacing if mri_data else None,
        "slice_count": int(mri_data.volume.shape[0]) if mri_data else 0,
        "info": summarize_info(mri_data.info) if mri_data else {},
        "mask_available": RAW_MASK_PATH.exists() or FALLBACK_MASK_PATH.exists(),
        "mask_reliable": BRAIN_ONLY_MESH_PATH.exists() or reliable_mask_file_exists(),
        "mesh_available": BRAIN_ONLY_MESH_PATH.exists() and reliable_mask_file_exists(),
        "debug_mesh_available": DEBUG_MASK_MESH_PATH.exists(),
        "hdbet_installed": hdbet_installed(),
        "synthstrip_available": synthstrip_available(),
        "synthseg_available": region_synthseg_available(),
        "fastsurfer_available": fastsurfer_available(),
        "region_segmentation": region_state,
        "mask_source": mask_state["mask_source"],
        "mask_status": mask_state["mask_status"],
        "reliable_mask": mask_state["reliable_mask"],
        "input_nifti_path": str(INPUT_NIFTI_PATH) if INPUT_NIFTI_PATH.exists() else "",
        "brain_mask_path": str(RAW_MASK_PATH) if RAW_MASK_PATH.exists() else "",
        "brain_only_path": str(BRAIN_ONLY_VOLUME_PATH) if BRAIN_ONLY_VOLUME_PATH.exists() else "",
        "mesh_path": str(BRAIN_ONLY_MESH_PATH) if BRAIN_ONLY_MESH_PATH.exists() else "",
        "final_mesh_path": str(BRAIN_ONLY_MESH_PATH) if BRAIN_ONLY_MESH_PATH.exists() else "",
        "debug_mesh_path": str(DEBUG_MASK_MESH_PATH) if DEBUG_MASK_MESH_PATH.exists() else "",
        "mask_shape": mask_info.get("mask_shape"),
        "mask_unique_values": mask_info.get("mask_unique_values", []),
        "mask_sum": mask_info.get("mask_sum", 0),
        "mask_ratio": mask_info.get("mask_ratio", 0.0),
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
    region_state = region_status_payload()
    return {
        "engine": "HD-BET / skull-stripping assisted viewer",
        "mask_source": str(RAW_MASK_PATH) if reliable_ready else "not available",
        "mesh_source": str(BRAIN_ONLY_MESH_PATH) if mesh_ready else "not generated",
        "brain_only_source": str(BRAIN_ONLY_VOLUME_PATH) if reliable_ready and BRAIN_ONLY_VOLUME_PATH.exists() else "not generated",
        "brain_overlay_source": str(BRAIN_OVERLAY_PATH) if reliable_ready and BRAIN_OVERLAY_PATH.exists() else "not generated",
        "debug_mesh_source": str(DEBUG_MASK_MESH_PATH) if debug_mesh_ready else "not generated",
        "region_labelmap_source": str(REGION_LABELMAP_PATH) if REGION_LABELMAP_PATH.exists() else "not generated",
        "region_volumes_csv": str(REGION_VOLUMES_CSV_PATH) if REGION_VOLUMES_CSV_PATH.exists() else "not generated",
        "region_segmentation": region_state,
        "debug_raw_surface_source": str(DEBUG_RAW_SURFACE_PATH) if DEBUG_RAW_SURFACE_PATH.exists() else "not generated",
        "volume_shape": tuple(int(value) for value in mri_data.volume.shape) if mri_data else None,
        "mask_volume": mask_info,
        "checks": [
            {"label": "Brain mask available", "ok": RAW_MASK_PATH.exists() or FALLBACK_MASK_PATH.exists()},
            {"label": "Stable mesh exported", "ok": mesh_ready},
            {"label": "Region label map available", "ok": REGION_LABELMAP_PATH.exists()},
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
    save_input_nifti(mri_data)
    return api_status()


def api_slice_png(query: dict[str, list[str]]) -> bytes:
    return api_mri_slice_png(query)


def api_mri_metadata(query: dict[str, list[str]]) -> dict:
    mri_data = get_loaded_mri()
    if mri_data is None:
        try:
            load_startup_sample_volume()
        except Exception as exc:
            STATE["last_error"] = str(exc)
        mri_data = get_loaded_mri()
    mask_state = current_mask_state()
    mask_info = current_mask_info(mri_data)
    if mri_data is None:
        return {
            "ok": False,
            "volume_loaded": False,
            "message": "No MRI volume found",
            "search_order": startup_search_order(),
            "mask_source": mask_state["mask_source"],
            "mask_status": mask_state["mask_status"],
            "mask_exists": display_mask_path() is not None,
            "mask_ratio": mask_info.get("mask_ratio", 0.0),
            "mask_unique_values": mask_info.get("mask_unique_values", []),
        }
    series_meta = current_series_metadata()
    return {
        "ok": True,
        **volume_diagnostics(mri_data),
        "source": mri_data.source_type,
        "source_label": mri_data.source_label,
        "series": mri_data.info.get("SeriesDescription") or mri_data.source_label,
        "series_name": mri_data.info.get("SeriesDescription") or mri_data.source_label,
        "file_count": series_meta.get("file_count"),
        "info": summarize_info(mri_data.info),
        "mask_source": mask_state["mask_source"],
        "mask_status": mask_state["mask_status"],
        "mask_exists": display_mask_path() is not None,
        "reliable_mask": mask_state["reliable_mask"],
        "mask_ratio": mask_info.get("mask_ratio", 0.0),
        "mask_unique_values": mask_info.get("mask_unique_values", []),
        "mask_shape": mask_info.get("mask_shape"),
        "mask_sum": mask_info.get("mask_sum", 0),
        "last_error": str(STATE.get("last_error") or ""),
        "disclaimer": DISCLAIMER,
    }


def api_mri_slice_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    normalized = require_normalized()
    plane = normalize_plane(first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))))
    max_index = plane_length(mri_data.volume, plane) - 1
    index = parse_slice_index(first(query, "index", "middle"), max_index)
    image = slice_from_plane(normalized, plane, index)
    mask_slice = None
    overlay_requested = first(query, "overlay", first(query, "mask", "0")).lower() in {"1", "true", "yes", "on"}
    if overlay_requested:
        try:
            mask_path = display_mask_path()
            if mask_path is None:
                LOGGER.info("Mask overlay requested but no mask file exists. Rendering raw MRI slice only.")
            else:
                mask = load_mask_for_volume(mri_data, mask_path)
                mask_slice = slice_from_plane(binarize_mask(mask).astype(np.float32), plane, index)
        except Exception as exc:
            STATE["last_error"] = f"Mask overlay disabled: {exc}"
            LOGGER.exception("Mask overlay failed; rendering raw MRI slice only.")
    LOGGER.info(
        "slice render plane=%s index=%s max=%s image_shape=%s image_min=%.6f image_max=%.6f overlay=%s",
        plane,
        index,
        max_index,
        tuple(int(value) for value in image.shape),
        float(np.min(image)),
        float(np.max(image)),
        mask_slice is not None,
    )
    return draw_slice_png(image, mask_slice)


def api_slice_info(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    normalized = require_normalized()
    plane = normalize_plane(first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))))
    max_index = plane_length(mri_data.volume, plane) - 1
    requested_index = first(query, "index", "middle")
    index = parse_slice_index(requested_index, max_index)
    raw_slice = slice_from_plane(mri_data.volume, plane, index)
    normalized_slice = slice_from_plane(normalized, plane, index)
    overlay_enabled = first(query, "overlay", first(query, "mask", "0")).lower() in {"1", "true", "yes", "on"}
    overlay_available = False
    overlay_warning = ""
    if overlay_enabled:
        try:
            mask_path = display_mask_path()
            if mask_path is None:
                overlay_warning = "Mask not available. Overlay disabled."
            else:
                mask = load_mask_for_volume(mri_data, mask_path)
                overlay_available = mask.shape == mri_data.volume.shape
                if not overlay_available:
                    overlay_warning = f"Mask shape mismatch. Overlay disabled. mask={mask.shape} volume={mri_data.volume.shape}"
        except Exception as exc:
            overlay_warning = f"Mask overlay disabled: {exc}"
    info = {
        **volume_diagnostics(mri_data),
        "selected_plane": plane,
        "requested_slice_index": requested_index,
        "selected_slice_index": index,
        "max_slice_index": max_index,
        "slice_shape": tuple(int(value) for value in raw_slice.shape),
        "slice_dtype": str(raw_slice.dtype),
        "slice_min_intensity": float(np.nanmin(raw_slice)),
        "slice_max_intensity": float(np.nanmax(raw_slice)),
        "normalized_slice_min": float(np.nanmin(normalized_slice)),
        "normalized_slice_max": float(np.nanmax(normalized_slice)),
        "overlay_requested": overlay_enabled,
        "overlay_available": overlay_available,
        "overlay_warning": overlay_warning,
    }
    LOGGER.info("slice info: %s", info)
    return info


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


def api_region_overlay_png(query: dict[str, list[str]]) -> bytes:
    mri_data = require_mri()
    region_name = first(query, "region", "Cerebrum")
    if region_name == "Target Region/Tumor":
        if not TARGET_MASK_PATH.exists():
            return draw_status_png("target_mask.nii.gz not found. Load a manual/model target mask first.")
        mask = load_nifti_mask(TARGET_MASK_PATH)
        return render_mask_overlay_png(mri_data, mask, query)
    if not REGION_LABELMAP_PATH.exists():
        return draw_status_png("Region label map missing. Run SynthSeg/FastSurfer first.")
    return render_region_overlay_png(mri_data, REGION_LABELMAP_PATH, query)


def api_region_mesh_plot(query: dict[str, list[str]]) -> str:
    region_name = first(query, "region", "Cerebrum")
    if region_name == "Target Region/Tumor":
        if not TARGET_MASK_PATH.exists():
            return status_html("Target mask missing", "Load outputs/target_mask.nii.gz from a separate tumor model or manual mask.")
        try:
            mri_data = require_mri()
            mask = load_nifti_mask(TARGET_MASK_PATH)
            mesh = build_brain_mesh_from_mask(mask.astype(np.uint8), spacing=mri_data.spacing, gaussian_sigma=0.5, step_size=1)
            fig = mesh_to_figure(mesh, color=REGION_COLORS.get(region_name, "#dc2626"), title=region_name)
            return fig.to_html(include_plotlyjs=True, full_html=True, config={"displaylogo": False, "responsive": True})
        except Exception as exc:
            LOGGER.exception("Target mesh preview failed.")
            return status_html("Mesh generation failed", str(exc))
    if not REGION_LABELMAP_PATH.exists():
        return status_html("No region label map", "Run region segmentation or load outputs/regions_labelmap.nii.gz.")
    label_ids = REGION_GROUPS.get(region_name)
    if not label_ids:
        return status_html("Selected region not found", f"Unknown region: {region_name}")
    try:
        labelmap, _ = load_labelmap_array(REGION_LABELMAP_PATH)
        region_mask = np.isin(labelmap, label_ids)
        if not np.any(region_mask):
            return status_html("Selected region not found", f"{region_name} has no voxels in the current label map.")
        mri_data = require_mri()
        mesh = build_brain_mesh_from_mask(
            region_mask.astype(np.uint8),
            spacing=mri_data.spacing,
            gaussian_sigma=0.5,
            step_size=1,
            downsample_factor=max(1, int(first(query, "downsample", "1"))),
            smoothing_iterations=max(0, int(first(query, "smooth", "2"))),
            apply_mesh_smoothing=True,
        )
        color = REGION_COLORS.get(region_name, "#94a3b8")
        fig = mesh_to_figure(mesh, color=color, title=region_name)
        return fig.to_html(include_plotlyjs=True, full_html=True, config={"displaylogo": False, "responsive": True})
    except Exception as exc:
        LOGGER.exception("Region mesh preview failed.")
        return status_html("Mesh generation failed", str(exc))


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
    save_input_nifti(mri_data)

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


def api_mesh_status() -> dict:
    mask_state = current_mask_state()
    mri_data = get_loaded_mri()
    mask_info = current_mask_info(mri_data)
    debug_file_status = api_debug_preview_mesh_status()
    mesh_available = BRAIN_ONLY_MESH_PATH.exists() and bool(mask_state["reliable_mask"])
    debug_mesh_available = DEBUG_PREVIEW_MESH_PATH.exists() or DEBUG_MASK_MESH_PATH.exists()
    mask_type = mesh_mask_type(mask_state, mask_info)
    if mesh_available:
        status = "3D mesh loaded"
    elif debug_mesh_available and mask_type == "debug":
        status = "debug preview mesh ready"
    elif mask_type == "debug":
        status = "Debug brain mask detected. Preview 3D mesh can be generated, but final medical brain-only 3D is disabled."
    else:
        status = "No mesh generated yet"
    return {
        "ok": True,
        "status": status,
        "mask_type": mask_type,
        "mesh_status": "ready" if mesh_available or debug_mesh_available else "none",
        "volume_loaded": mri_data is not None,
        "mesh_available": mesh_available,
        "debug_mesh_available": debug_mesh_available,
        "mesh_path": str(BRAIN_ONLY_MESH_PATH) if mesh_available else "",
        "debug_mesh_path": str(DEBUG_PREVIEW_MESH_PATH) if DEBUG_PREVIEW_MESH_PATH.exists() else (str(DEBUG_MASK_MESH_PATH) if DEBUG_MASK_MESH_PATH.exists() else ""),
        "debug_mesh_url": "/static/meshes/debug_brain_preview.glb" if DEBUG_PREVIEW_MESH_PATH.exists() else "",
        "glb_url": debug_file_status.get("mesh_url", ""),
        "file_exists": debug_file_status.get("file_exists", False),
        "file_size": debug_file_status.get("file_size", 0),
        "vertex_count": debug_file_status.get("vertex_count"),
        "face_count": debug_file_status.get("face_count"),
        "mesh_api_status": debug_file_status.get("mesh_status", "none"),
        "mask_source": mask_state["mask_source"],
        "mask_status": mask_state["mask_status"],
        "reliable_mask": mask_state["reliable_mask"],
        "input_nifti_path": str(INPUT_NIFTI_PATH) if INPUT_NIFTI_PATH.exists() else "",
        "brain_mask_path": str(RAW_MASK_PATH) if RAW_MASK_PATH.exists() else "",
        "brain_only_path": str(BRAIN_ONLY_VOLUME_PATH) if BRAIN_ONLY_VOLUME_PATH.exists() else "",
        "final_mesh_path": str(BRAIN_ONLY_MESH_PATH) if mesh_available else "",
        "mask_shape": mask_info.get("mask_shape"),
        "mask_unique_values": mask_info.get("mask_unique_values", []),
        "mask_sum": mask_info.get("mask_sum", 0),
        "mask_ratio": mask_info.get("mask_ratio", 0.0),
        "last_error": str(STATE.get("last_error") or ""),
    }


def mesh_mask_type(mask_state: dict, mask_info: dict) -> str:
    if mask_state.get("reliable_mask"):
        return "final"
    if FALLBACK_MASK_PATH.exists() or int(mask_info.get("mask_sum") or 0) > 0:
        return "debug"
    return "none"


def region_status_payload() -> dict:
    info = load_region_labelmap(REGION_LABELMAP_PATH)
    return {
        "synthseg_available": region_synthseg_available(),
        "fastsurfer_available": fastsurfer_available(),
        "labelmap_available": REGION_LABELMAP_PATH.exists(),
        "labelmap_path": str(REGION_LABELMAP_PATH) if REGION_LABELMAP_PATH.exists() else "",
        "target_mask_available": TARGET_MASK_PATH.exists(),
        "target_mask_path": str(TARGET_MASK_PATH) if TARGET_MASK_PATH.exists() else "",
        "status": info.get("status", "missing"),
        "message": info.get("message", REGION_SEGMENTATION_DISABLED_MESSAGE),
        "region_names": list(REGION_GROUPS.keys()),
        "colors": REGION_COLORS,
        "regions": info.get("regions", []),
        "unique_labels": info.get("unique_labels", []),
        "volumes_csv_path": str(REGION_VOLUMES_CSV_PATH) if REGION_VOLUMES_CSV_PATH.exists() else "",
        "disabled_warning": ""
        if REGION_LABELMAP_PATH.exists() or region_synthseg_available() or fastsurfer_available()
        else REGION_SEGMENTATION_DISABLED_MESSAGE,
    }


def api_region_status() -> dict:
    return {"ok": True, **region_status_payload()}


def api_run_region_segmentation() -> dict:
    mri_data = require_mri()
    if not INPUT_NIFTI_PATH.exists():
        save_input_nifti(mri_data)
    input_path = BRAIN_ONLY_VOLUME_PATH if BRAIN_ONLY_VOLUME_PATH.exists() else INPUT_NIFTI_PATH
    result = run_region_segmentation(input_path, REGION_LABELMAP_PATH, ROOT)
    if result.get("ok"):
        volumes = export_region_volumes_csv(REGION_LABELMAP_PATH, REGION_VOLUMES_CSV_PATH, REGION_MESH_DIR)
        result["volumes"] = volumes.get("regions", [])
        result["volumes_csv_path"] = volumes.get("csv_path", "")
        STATE["last_error"] = ""
    else:
        STATE["last_error"] = result.get("message", REGION_SEGMENTATION_DISABLED_MESSAGE)
    return {**result, "region_status": region_status_payload()}


def api_load_regions() -> dict:
    info = load_region_labelmap(REGION_LABELMAP_PATH)
    if info.get("ok"):
        csv_result = export_region_volumes_csv(REGION_LABELMAP_PATH, REGION_VOLUMES_CSV_PATH, REGION_MESH_DIR)
        info["volumes_csv_path"] = csv_result.get("csv_path", "")
        info["regions"] = csv_result.get("regions", info.get("regions", []))
    else:
        STATE["last_error"] = info.get("message", "Label map missing.")
    return info


def api_build_region_mesh(query: dict[str, list[str]]) -> dict:
    region_name = first(query, "region", "Cerebrum")
    if region_name == "Target Region/Tumor":
        if not TARGET_MASK_PATH.exists():
            return {
                "ok": False,
                "status": "missing",
                "message": "target_mask.nii.gz not found. Target/tumor segmentation requires a separate model or manual mask.",
                "mesh_path": None,
            }
        output_path = REGION_MESH_DIR / "target_region_tumor.glb"
        result = build_mesh_from_mask(TARGET_MASK_PATH, output_path)
        result.update({"region_name": region_name, "reliable_for_3d": False, "debug_only": False})
        return result
    if not REGION_LABELMAP_PATH.exists():
        return {
            "ok": False,
            "status": "missing",
            "message": "Label map not found. Run region segmentation or load outputs/regions_labelmap.nii.gz.",
            "mesh_path": None,
        }
    output_path = REGION_MESH_DIR / f"{slugify_region(region_name)}.glb"
    result = build_region_mesh(REGION_LABELMAP_PATH, region_name, output_path)
    if result.get("ok"):
        export_region_volumes_csv(REGION_LABELMAP_PATH, REGION_VOLUMES_CSV_PATH, REGION_MESH_DIR)
        STATE["last_error"] = ""
    else:
        STATE["last_error"] = result.get("message", "Region mesh generation failed.")
    return result


def api_build_all_region_meshes() -> dict:
    if not REGION_LABELMAP_PATH.exists():
        return {
            "ok": False,
            "status": "missing",
            "message": "Label map not found. Run region segmentation or load outputs/regions_labelmap.nii.gz.",
            "results": [],
        }
    results = []
    for region_name in REGION_GROUPS:
        if region_name == "Whole brain":
            continue
        output_path = REGION_MESH_DIR / f"{slugify_region(region_name)}.glb"
        results.append(build_region_mesh(REGION_LABELMAP_PATH, region_name, output_path))
    export_result = export_region_volumes_csv(REGION_LABELMAP_PATH, REGION_VOLUMES_CSV_PATH, REGION_MESH_DIR)
    ok = any(item.get("ok") for item in results)
    return {
        "ok": ok,
        "status": "ready" if ok else "failed",
        "message": "Region meshes built." if ok else "No region mesh could be generated.",
        "results": results,
        "volumes_csv_path": export_result.get("csv_path", ""),
    }


def api_export_region_volumes() -> dict:
    return export_region_volumes_csv(REGION_LABELMAP_PATH, REGION_VOLUMES_CSV_PATH, REGION_MESH_DIR)


def api_build_mesh(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = effective_mask_diagnostics(result)
    source = mask_source_label(result)
    reliable_mask = bool(
        source in {"hd-bet", "synthstrip", "cached_brain_mask"}
        and diagnostics.get("mask_status") == "valid"
        and RAW_MASK_PATH.exists()
        and is_final_mask_allowed(result, diagnostics)
    )
    if not reliable_mask:
        if BRAIN_ONLY_MESH_PATH.exists():
            BRAIN_ONLY_MESH_PATH.unlink()
        message = "Final 3D is disabled because reliable skull stripping mask is not available."
        STATE["last_error"] = message
        LOGGER.warning("%s source=%s status=%s path=%s", message, source, diagnostics.get("mask_status"), RAW_MASK_PATH)
        return {
            "ok": False,
            "status": "debug_only",
            "message": "HD-BET or SynthStrip brain mask is required for final 3D brain mesh.",
            "warning": message,
            "mesh_path": None,
            "mask_path": str(RAW_MASK_PATH),
            "mask_source": source,
            "mask_status": diagnostics.get("mask_status"),
            "reliable_mask": False,
            "debug_only": True,
            "mask_shape": tuple(int(value) for value in result.mask.shape),
            "mask_unique_values": diagnostics.get("mask_unique_values"),
            "mask_sum": int(np.count_nonzero(binarize_mask(result.mask))),
        }

    STATE["mesh"] = None
    mesh_result = build_mesh_from_mask(
        mask_path=RAW_MASK_PATH,
        output_path=BRAIN_ONLY_MESH_PATH,
        spacing=mri_data.spacing,
        smooth=int(first(query, "smooth", "1")) > 0,
    )
    mesh_result.update(
        {
            "mask_source": source,
            "mask_status": diagnostics.get("mask_status"),
            "reliable_mask": bool(mesh_result.get("ok")),
            "reliable_for_3d": bool(mesh_result.get("ok")),
            "debug_only": False,
        }
    )
    if mesh_result.get("ok"):
        STATIC_MESH_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BRAIN_ONLY_MESH_PATH, STATIC_BRAIN_MESH_PATH)
        mesh_result["static_mesh_path"] = str(STATIC_BRAIN_MESH_PATH)
        mesh_result["static_mesh_url"] = "/static/meshes/brain.glb"
        STATE["last_error"] = ""
        LOGGER.info("3D mesh loaded path=%s vertices=%s faces=%s", mesh_result.get("mesh_path"), mesh_result.get("vertices"), mesh_result.get("faces"))
    else:
        STATE["last_error"] = str(mesh_result.get("message") or "Mesh generation failed.")
        LOGGER.error(
            "Mesh generation failed mask_path=%s shape=%s unique=%s sum=%s output=%s error=%s",
            mesh_result.get("mask_path"),
            mesh_result.get("mask_shape"),
            mesh_result.get("mask_unique_values"),
            mesh_result.get("mask_sum"),
            mesh_result.get("output_path"),
            mesh_result.get("exception") or mesh_result.get("message"),
        )
    return mesh_result


def api_build_debug_mesh(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = effective_mask_diagnostics(result)
    debug_mask = binarize_mask(result.mask)
    save_nifti_mask(debug_mask, mri_data.affine, FALLBACK_MASK_PATH)
    mesh_result = build_mesh_from_mask(
        mask_path=FALLBACK_MASK_PATH,
        output_path=DEBUG_MASK_MESH_PATH,
        spacing=mri_data.spacing,
        smooth=int(first(query, "smooth", "1")) > 0,
    )
    mesh_result.update(
        {
            "ok": bool(mesh_result.get("ok")),
            "status": "debug_only" if mesh_result.get("ok") else "failed",
            "message": "DEBUG ONLY - not final brain extraction"
            if mesh_result.get("ok")
            else mesh_result.get("message", "Mesh generation failed."),
            "warning": "DEBUG ONLY - not final brain extraction",
            "mask_source": mask_source_label(result),
            "mask_status": diagnostics.get("mask_status"),
            "reliable_mask": False,
            "reliable_for_3d": False,
            "debug_only": True,
        }
    )
    STATE["last_error"] = "" if mesh_result.get("ok") else str(mesh_result.get("message") or "Debug mesh generation failed.")
    LOGGER.info(
        "Debug mesh status=%s mask_path=%s shape=%s sum=%s output=%s",
        mesh_result.get("status"),
        mesh_result.get("mask_path"),
        mesh_result.get("mask_shape"),
        mesh_result.get("mask_sum"),
        mesh_result.get("output_path"),
    )
    return mesh_result


def api_build_preview_mesh(query: dict[str, list[str]]) -> dict:
    mri_data = require_mri()
    result = ensure_mask_result(mri_data)
    diagnostics = effective_mask_diagnostics(result)
    debug_mask = binarize_mask(result.mask)
    mask_voxels = int(np.count_nonzero(debug_mask))
    save_nifti_mask(debug_mask, mri_data.affine, FALLBACK_MASK_PATH)
    STATIC_MESH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if mask_voxels == 0:
            raise ValueError("Debug mask is empty; cannot build preview mesh.")
        mesh = build_brain_mesh_from_mask(
            debug_mask.astype(np.uint8),
            spacing=mri_data.spacing,
            gaussian_sigma=float(first(query, "sigma", "1.0")),
            step_size=max(1, int(first(query, "step", "1"))),
            downsample_factor=max(2, int(first(query, "downsample", "4"))),
            smoothing_iterations=max(0, int(first(query, "smooth", "3"))),
            apply_mesh_smoothing=True,
        )
        export_glb(mesh, DEBUG_PREVIEW_MESH_PATH)
        vertex_count = int(len(mesh.vertices))
        face_count = int(len(mesh.faces))
        file_size = int(DEBUG_PREVIEW_MESH_PATH.stat().st_size) if DEBUG_PREVIEW_MESH_PATH.exists() else 0
        meta_payload = {
            "ok": True,
            "mask_type": "debug",
            "mesh_status": "ready",
            "mesh_path": "/static/meshes/debug_brain_preview.glb",
            "mesh_url": "/static/meshes/debug_brain_preview.glb",
            "filesystem_path": str(DEBUG_PREVIEW_MESH_PATH),
            "file_exists": DEBUG_PREVIEW_MESH_PATH.exists(),
            "file_size": file_size,
            "voxel_count": mask_voxels,
            "mask_voxel_count": mask_voxels,
            "vertex_count": vertex_count,
            "face_count": face_count,
            "message": "Debug preview mesh generated",
            "warning": "Debug mask only. Not for diagnosis. Preview mesh only. Final brain-only 3D requires SynthStrip or HD-BET.",
        }
        DEBUG_PREVIEW_META_PATH.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        STATE["last_error"] = ""
        return {
            **meta_payload,
            "ok": True,
            "status": "ready",
            "mesh_status": "ready",
            "message": "Debug preview mesh generated",
            "mask_type": "debug",
            "mask_source": mask_source_label(result),
            "mask_status": diagnostics.get("mask_status"),
            "mask_shape": tuple(int(value) for value in debug_mask.shape),
            "vertices": vertex_count,
            "faces": face_count,
            "reliable_mask": False,
            "reliable_for_3d": False,
            "debug_only": True,
        }
    except Exception as exc:
        trace = traceback.format_exc(limit=8)
        message = f"Preview mesh generation failed: {exc}"
        STATE["last_error"] = message
        LOGGER.error("%s\n%s", message, trace)
        return {
            "ok": False,
            "status": "failed",
            "mesh_status": "failed",
            "error": str(exc),
            "message": message,
            "traceback": trace[-4000:],
            "mask_type": "debug",
            "mask_source": mask_source_label(result),
            "mask_status": diagnostics.get("mask_status"),
            "mask_shape": tuple(int(value) for value in debug_mask.shape),
            "mask_voxel_count": mask_voxels,
            "mesh_path": "/static/meshes/debug_brain_preview.glb",
            "filesystem_path": str(DEBUG_PREVIEW_MESH_PATH),
            "file_exists": DEBUG_PREVIEW_MESH_PATH.exists(),
            "file_size": int(DEBUG_PREVIEW_MESH_PATH.stat().st_size) if DEBUG_PREVIEW_MESH_PATH.exists() else 0,
            "mesh_url": "",
            "reliable_mask": False,
            "debug_only": True,
        }


def api_debug_preview_mesh_status() -> dict:
    payload = {
        "ok": DEBUG_PREVIEW_MESH_PATH.exists(),
        "mask_type": "debug" if FALLBACK_MASK_PATH.exists() else "none",
        "mesh_status": "ready" if DEBUG_PREVIEW_MESH_PATH.exists() else "none",
        "mesh_path": "/static/meshes/debug_brain_preview.glb",
        "mesh_url": "/static/meshes/debug_brain_preview.glb",
        "filesystem_path": str(DEBUG_PREVIEW_MESH_PATH),
        "file_exists": DEBUG_PREVIEW_MESH_PATH.exists(),
        "file_size": int(DEBUG_PREVIEW_MESH_PATH.stat().st_size) if DEBUG_PREVIEW_MESH_PATH.exists() else 0,
        "vertex_count": None,
        "face_count": None,
        "voxel_count": None,
        "last_error": str(STATE.get("last_error") or ""),
    }
    if DEBUG_PREVIEW_META_PATH.exists():
        try:
            stored = json.loads(DEBUG_PREVIEW_META_PATH.read_text(encoding="utf-8"))
            payload.update(stored)
            payload["file_exists"] = DEBUG_PREVIEW_MESH_PATH.exists()
            payload["file_size"] = int(DEBUG_PREVIEW_MESH_PATH.stat().st_size) if DEBUG_PREVIEW_MESH_PATH.exists() else 0
            payload["mesh_status"] = "ready" if DEBUG_PREVIEW_MESH_PATH.exists() else "none"
            payload["ok"] = DEBUG_PREVIEW_MESH_PATH.exists()
        except Exception as exc:
            payload["last_error"] = f"Failed to read debug mesh metadata: {exc}"
    return payload


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
    if first(query, "debug", "0") == "1":
        plot = fig.to_html(include_plotlyjs=True, full_html=False, config={"displaylogo": False, "responsive": True})
        return (
            "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>html,body{margin:0;width:100%;height:100%;background:#f6f7f9;font-family:Arial,sans-serif;}"
            ".banner{position:fixed;left:18px;top:18px;z-index:5;max-width:520px;padding:12px 14px;border:1px solid #f59e0b;border-radius:8px;background:#fff8e1;color:#713f12;box-shadow:0 10px 30px rgba(15,23,42,.12)}"
            ".banner strong{display:block;margin-bottom:4px}</style></head><body>"
            "<div class='banner'><strong>Preview only / Not for diagnosis</strong>"
            "Debug mask only. Preview mesh only. Final brain-only 3D requires SynthStrip or HD-BET.</div>"
            f"{plot}</body></html>"
        )
    return fig.to_html(include_plotlyjs=True, full_html=True, config={"displaylogo": False, "responsive": True})


def api_threejs_viewer(query: dict[str, list[str]]) -> str:
    model_url = first(query, "model", "/static/meshes/debug_brain_preview.glb")
    title = first(query, "title", "Debug mask preview mesh")
    warning = first(
        query,
        "warning",
        "Debug mask only. Not for diagnosis. Preview mesh only. Final brain-only 3D requires SynthStrip or HD-BET.",
    )
    safe_model = html_escape(model_url)
    safe_title = html_escape(title)
    safe_warning = html_escape(warning)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    html, body {{ margin:0; width:100%; height:100%; overflow:hidden; background:#f6f7f9; font-family:Arial, sans-serif; }}
    #stage {{ position:fixed; inset:0; }}
    .banner {{ position:fixed; left:18px; top:18px; z-index:3; max-width:520px; padding:12px 14px; border:1px solid #f59e0b; border-radius:8px; background:#fff8e1; color:#713f12; box-shadow:0 10px 30px rgba(15,23,42,.12); }}
    .banner strong {{ display:block; margin-bottom:4px; }}
    .status {{ position:fixed; left:18px; bottom:18px; z-index:3; padding:8px 10px; border-radius:8px; background:rgba(255,255,255,.86); color:#334155; font-size:12px; }}
  </style>
</head>
<body>
  <div id="stage"></div>
  <div class="banner"><strong>Preview only / Not for diagnosis</strong>{safe_warning}</div>
  <div class="status" id="status">Loading GLB...</div>
  <script>
    window.__meshReady = false;
    window.__fallbackTimer = window.setTimeout(() => {{
      if (!window.__meshReady) {{
        renderCanvasFallback();
      }}
    }}, 12000);
    async function renderCanvasFallback() {{
      if (window.__meshReady) return;
      const stage = document.getElementById('stage');
      const status = document.getElementById('status');
      status.textContent = 'Three.js unavailable; rendering canvas surface fallback...';
      stage.innerHTML = '';
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      stage.appendChild(canvas);
      function resize() {{
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
      }}
      resize();
      window.addEventListener('resize', resize);
      try {{
        const response = await fetch('{safe_model}', {{ cache: 'no-store' }});
        if (!response.ok) throw new Error('GLB fetch failed: ' + response.status);
        const buffer = await response.arrayBuffer();
        const view = new DataView(buffer);
        if (view.getUint32(0, true) !== 0x46546c67) throw new Error('Invalid GLB header');
        let offset = 12;
        let json = null;
        let binStart = 0;
        while (offset + 8 <= buffer.byteLength) {{
          const chunkLength = view.getUint32(offset, true);
          const chunkType = view.getUint32(offset + 4, true);
          offset += 8;
          if (chunkType === 0x4e4f534a) {{
            json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, offset, chunkLength)));
          }} else if (chunkType === 0x004e4942) {{
            binStart = offset;
          }}
          offset += chunkLength;
        }}
        if (!json || !binStart) throw new Error('GLB chunks missing');
        function componentArray(componentType) {{
          if (componentType === 5126) return Float32Array;
          if (componentType === 5125) return Uint32Array;
          if (componentType === 5123) return Uint16Array;
          if (componentType === 5121) return Uint8Array;
          throw new Error('Unsupported GLB component type: ' + componentType);
        }}
        function componentCount(type) {{
          return {{ SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }}[type] || 1;
        }}
        function readAccessor(index) {{
          const accessor = json.accessors?.[index];
          const bufferView = json.bufferViews?.[accessor?.bufferView];
          if (!accessor || !bufferView) throw new Error('Missing GLB accessor ' + index);
          const ArrayType = componentArray(accessor.componentType);
          const itemSize = componentCount(accessor.type);
          const byteOffset = binStart + (bufferView.byteOffset || 0) + (accessor.byteOffset || 0);
          const byteStride = bufferView.byteStride || (itemSize * ArrayType.BYTES_PER_ELEMENT);
          if (byteStride === itemSize * ArrayType.BYTES_PER_ELEMENT) {{
            return {{ array: new ArrayType(buffer, byteOffset, accessor.count * itemSize), count: accessor.count, itemSize }};
          }}
          const dense = new ArrayType(accessor.count * itemSize);
          for (let i = 0; i < accessor.count; i += 1) {{
            const row = new ArrayType(buffer, byteOffset + i * byteStride, itemSize);
            dense.set(row, i * itemSize);
          }}
          return {{ array: dense, count: accessor.count, itemSize }};
        }}
        const primitive = json.meshes?.[0]?.primitives?.[0];
        if (!primitive) throw new Error('GLB has no mesh primitive');
        const positionData = readAccessor(primitive.attributes?.POSITION);
        const positions = positionData.array;
        const indexData = primitive.indices === undefined ? null : readAccessor(primitive.indices);
        const indices = indexData?.array || null;
        const triangles = [];
        let cx = 0, cy = 0, cz = 0;
        for (let i = 0; i < positionData.count; i += 1) {{
          const x = positions[i * 3], y = positions[i * 3 + 1], z = positions[i * 3 + 2];
          cx += x; cy += y; cz += z;
        }}
        cx /= positionData.count; cy /= positionData.count; cz /= positionData.count;
        let radius = 1;
        for (let i = 0; i < positionData.count; i += 1) {{
          radius = Math.max(radius, Math.hypot(positions[i * 3] - cx, positions[i * 3 + 1] - cy, positions[i * 3 + 2] - cz));
        }}
        const faceCount = indices ? Math.floor(indices.length / 3) : Math.floor(positionData.count / 3);
        const faceStep = Math.max(1, Math.ceil(faceCount / 50000));
        for (let face = 0; face < faceCount; face += faceStep) {{
          const a = indices ? indices[face * 3] : face * 3;
          const b = indices ? indices[face * 3 + 1] : face * 3 + 1;
          const c = indices ? indices[face * 3 + 2] : face * 3 + 2;
          triangles.push([a, b, c]);
        }}
        let rotX = -0.55;
        let rotY = 0.75;
        let dragging = false;
        let lastX = 0;
        let lastY = 0;
        canvas.addEventListener('pointerdown', (event) => {{
          dragging = true;
          lastX = event.clientX;
          lastY = event.clientY;
          canvas.setPointerCapture(event.pointerId);
        }});
        canvas.addEventListener('pointermove', (event) => {{
          if (!dragging) return;
          rotY += (event.clientX - lastX) * 0.008;
          rotX += (event.clientY - lastY) * 0.008;
          lastX = event.clientX;
          lastY = event.clientY;
        }});
        canvas.addEventListener('pointerup', () => {{ dragging = false; }});
        function draw() {{
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#f6f7f9';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          const scale = Math.min(canvas.width, canvas.height) * 0.38 / radius;
          const sinX = Math.sin(rotX), cosX = Math.cos(rotX);
          const sinY = Math.sin(rotY), cosY = Math.cos(rotY);
          const projected = new Array(positionData.count);
          for (let i = 0; i < positionData.count; i += 1) {{
            let x = positions[i * 3] - cx, y = positions[i * 3 + 1] - cy, z = positions[i * 3 + 2] - cz;
            const x1 = x * cosY - z * sinY;
            const z1 = x * sinY + z * cosY;
            const y1 = y * cosX - z1 * sinX;
            const z2 = y * sinX + z1 * cosX;
            projected[i] = [canvas.width / 2 + x1 * scale, canvas.height / 2 - y1 * scale, z2];
          }}
          const drawFaces = triangles.map((face) => {{
            const pa = projected[face[0]], pb = projected[face[1]], pc = projected[face[2]];
            return {{ face, depth: (pa[2] + pb[2] + pc[2]) / 3 }};
          }}).sort((a, b) => a.depth - b.depth);
          ctx.lineWidth = 0.25;
          for (const item of drawFaces) {{
            const pa = projected[item.face[0]], pb = projected[item.face[1]], pc = projected[item.face[2]];
            const ux = pb[0] - pa[0], uy = pb[1] - pa[1];
            const vx = pc[0] - pa[0], vy = pc[1] - pa[1];
            if (Math.abs(ux * vy - uy * vx) < 0.08) continue;
            const shade = Math.max(122, Math.min(214, 168 + item.depth / radius * 52));
            ctx.beginPath();
            ctx.moveTo(pa[0], pa[1]);
            ctx.lineTo(pb[0], pb[1]);
            ctx.lineTo(pc[0], pc[1]);
            ctx.closePath();
            ctx.fillStyle = `rgba(${{shade}},${{shade}},${{shade}},0.88)`;
            ctx.strokeStyle = `rgba(92,100,112,0.12)`;
            ctx.fill();
            ctx.stroke();
          }}
          if (!dragging) rotY += 0.0025;
          requestAnimationFrame(draw);
        }}
        status.textContent = `Canvas surface fallback ready · render mode: Canvas surface mesh · vertices: ${{positionData.count}} · faces: ${{faceCount}}`;
        draw();
      }} catch (error) {{
        status.textContent = 'Preview fallback failed: ' + (error && error.message ? error.message : String(error));
      }}
    }}
  </script>
  <script type="module">
    Promise.all([
      import('https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.module.js'),
      import('https://cdn.jsdelivr.net/npm/three@0.164.1/examples/jsm/controls/OrbitControls.js'),
      import('https://cdn.jsdelivr.net/npm/three@0.164.1/examples/jsm/loaders/GLTFLoader.js')
    ]).then(([THREE, controlsModule, loaderModule]) => {{
    const {{ OrbitControls }} = controlsModule;
    const {{ GLTFLoader }} = loaderModule;
    const stage = document.getElementById('stage');
    const status = document.getElementById('status');
    const glbUrl = '{safe_model}';
    console.log('[3D] loading GLB:', glbUrl);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf6f7f9);
    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100000);
    const renderer = new THREE.WebGLRenderer({{ antialias: true }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    stage.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    scene.add(new THREE.HemisphereLight(0xffffff, 0xcbd5e1, 1.2));
    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(1, 2, 3);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.7);
    fill.position.set(-3, 1, -2);
    scene.add(fill);

    function fitCamera(object) {{
      const box = new THREE.Box3().setFromObject(object);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxSize = Math.max(size.x, size.y, size.z) || 1;
      const distance = maxSize / (2 * Math.tan((camera.fov * Math.PI / 180) / 2)) * 1.45;
      camera.position.set(center.x + distance, center.y + distance * 0.55, center.z + distance);
      camera.near = Math.max(distance / 1000, 0.01);
      camera.far = distance * 1000;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    }}

    const loader = new GLTFLoader();
    loader.load(glbUrl, (gltf) => {{
      const root = gltf.scene;
      root.traverse((node) => {{
        if (node.isMesh) {{
          node.material = new THREE.MeshStandardMaterial({{ color: 0xb6bcc6, roughness: 0.74, metalness: 0.02, opacity: 0.9, transparent: true, wireframe: false, side: THREE.DoubleSide }});
          node.castShadow = false;
          node.receiveShadow = false;
        }}
      }});
      scene.add(root);
      fitCamera(root);
      window.__meshReady = true;
      window.clearTimeout(window.__fallbackTimer);
      window.parent.postMessage({{ type: 'debugMeshReady' }}, '*');
      status.textContent = 'GLB surface mesh ready · render mode: GLB surface mesh';
    }}, (event) => {{
      if (event.lengthComputable) {{
        const pct = Math.round((event.loaded / event.total) * 100);
        status.textContent = 'Loading GLB... ' + pct + '%';
      }} else {{
        status.textContent = 'Loading GLB... ' + Math.round((event.loaded || 0) / 1024) + ' KB';
      }}
    }}, async (error) => {{
      let backendStatus = {{}};
      try {{
        const response = await fetch('/api/mri/mesh/debug-preview/status?t=' + Date.now(), {{ cache: 'no-store' }});
        backendStatus = await response.json();
      }} catch (statusError) {{
        backendStatus = {{ last_error: String(statusError) }};
      }}
      const message = error && error.message ? error.message : String(error);
      status.innerHTML = 'GLB load failed<br>requested GLB URL: ' + glbUrl
        + '<br>HTTP status: see Network tab'
        + '<br>error message: ' + message
        + '<br>mesh_path: ' + (backendStatus.mesh_path || '-')
        + '<br>file exists on backend: ' + Boolean(backendStatus.file_exists)
        + '<br>file size: ' + (backendStatus.file_size || 0);
      window.__meshReady = false;
      renderCanvasFallback();
    }});

    function animate() {{
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }}
    animate();
    window.addEventListener('resize', () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});
    }}).catch((error) => {{
      const status = document.getElementById('status');
      const glbUrl = '{safe_model}';
      const message = error && error.message ? error.message : String(error);
      status.innerHTML = 'Three.js import failed<br>requested GLB URL: ' + glbUrl
        + '<br>HTTP status: module import failed before GLB request'
        + '<br>error message: ' + message
        + '<br>mesh_path: /static/meshes/debug_brain_preview.glb'
        + '<br>file exists on backend: checking via fallback';
      renderCanvasFallback();
    }});
  </script>
</body>
</html>"""


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
        "regions_labelmap.nii.gz",
        "region_volumes.csv",
        "filled_brain_mask.nii.gz",
        "refined_brain_mask.nii.gz",
        "fallback_preview_mask.nii.gz",
        "debug_fallback_mask.nii.gz",
        "debug_brain_only.nii.gz",
        "brain_mask_overlay.png",
        "brain_overlay.png",
        "debug_mask_overlay.png",
    }
    patterns = ("*.png", "*.npy", "*.glb", "*.csv", "*mask*.nii.gz", "*labelmap*.nii.gz", "*mask*.npz")
    targets: set[Path] = {output_dir / name for name in names}
    for pattern in patterns:
        targets.update(output_dir.glob(pattern))
    if REGION_MESH_DIR.exists():
        targets.update(REGION_MESH_DIR.glob("*.glb"))

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


def save_input_nifti(mri_data: MRIData) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = save_nifti_volume(mri_data.volume, mri_data.affine, INPUT_NIFTI_PATH)
    LOGGER.info(
        "Saved current volume as NIfTI path=%s shape=%s spacing=%s series=%s",
        path,
        tuple(int(value) for value in mri_data.volume.shape),
        mri_data.spacing,
        mri_data.source_label,
    )
    return path


def current_mask_info(mri_data: MRIData | None) -> dict:
    mask_path = RAW_MASK_PATH if RAW_MASK_PATH.exists() else (FALLBACK_MASK_PATH if FALLBACK_MASK_PATH.exists() else None)
    if mri_data is None or mask_path is None:
        return {"mask_shape": None, "mask_unique_values": [], "mask_sum": 0, "mask_ratio": 0.0}
    try:
        mask = load_mask_for_volume(mri_data, mask_path)
        diagnostics = mask_diagnostics(mask, debug_only=mask_path != RAW_MASK_PATH)
        binary = binarize_mask(mask)
        return {
            "mask_shape": tuple(int(value) for value in mask.shape),
            "mask_unique_values": diagnostics.get("mask_unique_values", []),
            "mask_sum": int(np.count_nonzero(binary)),
            "mask_ratio": diagnostics.get("mask_ratio", 0.0),
        }
    except Exception as exc:
        LOGGER.exception("Could not collect current mask info.")
        return {
            "mask_shape": None,
            "mask_unique_values": [],
            "mask_sum": 0,
            "mask_ratio": 0.0,
            "mask_error": str(exc),
        }


def synthstrip_available() -> bool:
    return bool(shutil.which("mri_synthstrip") or shutil.which("synthstrip"))


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
        reliable = source in {"synthstrip", "hd-bet", "cached_brain_mask"} and status == "valid"
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
    processed_result = load_processed_brain_mask_result(mri_data)
    if processed_result is not None:
        STATE["mask_result"] = processed_result
        return processed_result
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


def load_processed_brain_mask_result(mri_data: MRIData) -> SkullStripResult | None:
    if not PROCESSED_MASK_PATH.exists():
        return None
    try:
        mask = binarize_mask(load_mask_for_volume(mri_data, PROCESSED_MASK_PATH))
    except Exception as exc:
        STATE["last_error"] = f"Processed brain mask rejected: {exc}"
        LOGGER.warning("Processed brain mask exists but is not usable: %s", exc)
        return None
    if mask.shape != mri_data.volume.shape or not np.any(mask):
        STATE["last_error"] = f"Processed brain mask shape/contents invalid: {mask.shape} vs {mri_data.volume.shape}"
        return None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_nifti_mask(mask, mri_data.affine, RAW_MASK_PATH)
    save_brain_extracted(mri_data.volume, mask, mri_data.affine, BRAIN_ONLY_VOLUME_PATH)
    save_mask_source_metadata_for("cached_brain_mask", "data/processed/brain_mask.nii.gz", "valid")
    metadata = {
        "method": "data/processed/brain_mask.nii.gz",
        "mask_source": "cached_brain_mask",
        "mask_status": "valid",
        "reliable_mask": True,
        "reliable_for_3d": True,
        "debug_only": False,
        "quality_warnings": [],
        "processed_mask_path": str(PROCESSED_MASK_PATH),
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
        method_used="data/processed/brain_mask.nii.gz",
        reliable_for_3d=True,
        debug_only=False,
        metadata=metadata,
        warnings=[],
    )


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
        and source in {"synthstrip", "hd-bet", "cached_brain_mask"}
        and (RAW_MASK_PATH.exists() if require_mask_file else True)
        and diagnostics.get("mask_status") == "valid"
    )


def load_cached_brain_mask_result(mri_data: MRIData) -> SkullStripResult | None:
    if not RAW_MASK_PATH.exists():
        return None
    source_meta = load_mask_source_metadata()
    source = str(source_meta.get("mask_source", "")).lower()
    generated_at = str(source_meta.get("generated_at") or "")
    if source not in {"synthstrip", "hd-bet", "cached_brain_mask"} or not generated_at:
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
    if "cached_brain_mask" in source or "cached brain_mask" in source:
        return "cached_brain_mask"
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
        load_startup_sample_volume()
        mri_data = get_loaded_mri()
    if mri_data is None:
        raise RuntimeError("No MRI volume found")
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
    return RAW_MASK_PATH.exists() and source in {"synthstrip", "hd-bet", "cached_brain_mask"}


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
        source in {"synthstrip", "hd-bet", "cached_brain_mask"}
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


def render_region_overlay_png(mri_data: MRIData, labelmap_path: Path, query: dict[str, list[str]]) -> bytes:
    normalized = require_normalized()
    plane = first(query, "plane", str(mri_data.info.get("Plane", "sagittal"))).lower()
    max_index = plane_length(mri_data.volume, plane) - 1
    index = max(0, min(int(first(query, "index", str(max_index // 2))), max_index))
    region_name = first(query, "region", "Cerebrum")
    mode = first(query, "mode", "selected")
    image = slice_from_plane(normalized, plane, index)
    labelmap, _ = load_labelmap_array(labelmap_path)
    label_slice = slice_from_plane(labelmap, plane, index)
    fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    rgba = np.zeros((*label_slice.shape, 4), dtype=np.float32)
    if mode == "all":
        for region, label_ids in REGION_GROUPS.items():
            if region == "Whole brain":
                continue
            binary = np.isin(label_slice, label_ids)
            rgba[binary] = (*hex_to_rgb_float(REGION_COLORS.get(region, "#94a3b8")), 0.42)
    else:
        label_ids = REGION_GROUPS.get(region_name, [])
        binary = np.isin(label_slice, label_ids)
        rgba[binary] = (*hex_to_rgb_float(REGION_COLORS.get(region_name, "#94a3b8")), 0.48)
    ax.imshow(rgba)
    ax.axis("off")
    fig.tight_layout(pad=0)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return buffer.getvalue()


def hex_to_rgb_float(color: str) -> tuple[float, float, float]:
    text = str(color).strip().lstrip("#")
    if len(text) != 6:
        return (0.58, 0.64, 0.72)
    return tuple(int(text[index : index + 2], 16) / 255.0 for index in (0, 2, 4))  # type: ignore[return-value]


def mesh_to_figure(mesh: BrainMesh, color: str = "lightgray", title: str = "") -> go.Figure:
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
                color=color,
                opacity=1.0,
                flatshading=False,
                lighting=dict(ambient=0.5, diffuse=0.8, specular=0.1, roughness=0.6, fresnel=0.1),
            )
        ]
    )
    layout = {
        "height": 680,
        "margin": dict(l=0, r=0, t=0, b=0),
        "scene": dict(aspectmode="data", xaxis_title="", yaxis_title="", zaxis_title=""),
    }
    if title:
        layout["title"] = dict(text=title, x=0.02, y=0.98)
    fig.update_layout(**layout)
    return fig


def status_html(title: str, message: str) -> str:
    safe_title = html_escape(title)
    safe_message = html_escape(message)
    return (
        "<!doctype html><html><body style='margin:0;min-height:100vh;display:grid;place-items:center;"
        "background:#f8fafc;color:#0f172a;font-family:system-ui,-apple-system,Segoe UI,sans-serif'>"
        "<div style='width:min(560px,84%);border:1px solid rgba(15,23,42,.12);border-left:6px solid #f59e0b;"
        "border-radius:8px;background:#fff;padding:22px 24px;box-shadow:0 18px 48px rgba(15,23,42,.10)'>"
        f"<strong style='display:block;font-size:18px;margin-bottom:8px'>{safe_title}</strong>"
        f"<span style='font-size:13px;color:#64748b'>{safe_message}</span>"
        "</div></body></html>"
    )


def html_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def draw_status_png(message: str) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
    ax.set_facecolor("#f8fafc")
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True, fontsize=11, color="#334155")
    ax.axis("off")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return buffer.getvalue()


def summarize_info(info: dict) -> dict:
    keys = ["StudyDate", "SeriesDescription", "Plane", "PixelSpacing", "SliceThickness", "SliceSpacing", "OrientationNote"]
    return {key: info.get(key) for key in keys}


def normalize_plane(value: str) -> str:
    plane = str(value or "sagittal").lower()
    if plane not in {"sagittal", "coronal", "axial"}:
        return "sagittal"
    return plane


def parse_slice_index(value: str, max_index: int) -> int:
    text = str(value or "middle").strip().lower()
    middle = max(0, int(max_index) // 2)
    if text in {"middle", "mid", "center", "centre", ""}:
        return middle
    try:
        requested = int(float(text))
    except ValueError:
        return middle
    if requested < 0 or requested > max_index:
        return middle
    return requested


def volume_diagnostics(mri_data: MRIData | None) -> dict:
    if mri_data is None:
        return {
            "volume_loaded": False,
            "volume_shape": None,
            "shape": None,
            "spacing": None,
            "dtype": None,
            "min_intensity": None,
            "max_intensity": None,
            "slice_counts": {},
        }
    volume = np.asarray(mri_data.volume)
    return {
        "volume_loaded": True,
        "volume_shape": tuple(int(value) for value in volume.shape),
        "shape": tuple(int(value) for value in volume.shape),
        "spacing": tuple(float(value) for value in mri_data.spacing),
        "dtype": str(volume.dtype),
        "min_intensity": float(np.nanmin(volume)),
        "max_intensity": float(np.nanmax(volume)),
        "slice_counts": {
            "axial": int(plane_length(volume, "axial")),
            "coronal": int(plane_length(volume, "coronal")),
            "sagittal": int(plane_length(volume, "sagittal")),
        },
    }


def current_series_metadata() -> dict:
    series_key = str(STATE.get("series_key") or "")
    series = STATE.get("series")
    if isinstance(series, list):
        for item in series:
            if str(item.get("key")) == series_key:
                return dict(item)
    mri_data = get_loaded_mri()
    return {
        "description": mri_data.source_label if mri_data else "",
        "file_count": int(mri_data.volume.shape[0]) if mri_data is not None else None,
    }


def startup_search_order() -> list[str]:
    return [
        str(ROOT / "data" / "processed" / "*.nii.gz"),
        str(ROOT / "data" / "input" / "*.nii.gz"),
        str(ROOT / "data" / "dicom" / "**" / "*"),
        str(DEFAULT_DATA_DIR / "**" / "*"),
    ]


def load_startup_sample_volume() -> MRIData | None:
    existing = get_loaded_mri()
    if existing is not None:
        return existing

    processed = sorted((ROOT / "data" / "processed").glob("*.nii.gz"))
    if processed:
        mri_data = load_nifti(str(processed[0]))
        STATE["mri_data"] = mri_data
        STATE["normalized"] = normalize_intensity(mri_data.volume)
        STATE["series_key"] = str(processed[0])
        save_input_nifti(mri_data)
        LOGGER.info("Loaded startup NIfTI from data/processed: %s", processed[0])
        return mri_data

    input_dir = ROOT / "data" / "input"
    inputs = sorted(input_dir.glob("*.nii.gz")) if input_dir.exists() else []
    if inputs:
        mri_data = load_nifti(str(inputs[0]))
        STATE["mri_data"] = mri_data
        STATE["normalized"] = normalize_intensity(mri_data.volume)
        STATE["series_key"] = str(inputs[0])
        save_input_nifti(mri_data)
        LOGGER.info("Loaded startup NIfTI from data/input: %s", inputs[0])
        return mri_data

    dicom_dir = ROOT / "data" / "dicom"
    search_dir = dicom_dir if dicom_dir.exists() else DEFAULT_DATA_DIR
    series = discover_dicom_series(str(search_dir))
    STATE["series"] = series
    if series:
        series_key = str(series[0]["key"])
        mri_data = load_dicom(str(search_dir), series_key=series_key)
        STATE["mri_data"] = mri_data
        STATE["normalized"] = normalize_intensity(mri_data.volume)
        STATE["series_key"] = series_key
        save_input_nifti(mri_data)
        LOGGER.info("Loaded startup DICOM series from %s: %s", search_dir, series_key)
        return mri_data

    STATE["last_error"] = "No MRI volume found"
    LOGGER.warning("No MRI volume found. Search order: %s", startup_search_order())
    return None


def format_slice_error(payload: dict) -> str:
    return (
        "MRI slice render failed\n"
        f"error: {payload.get('error')}\n"
        f"plane: {payload.get('plane')}\n"
        f"slice index: {payload.get('slice_index')}\n"
        f"volume loaded: {payload.get('volume_loaded')}"
    )


def first(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def run(host: str = HOST, port: int = PORT) -> None:
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    try:
        load_startup_sample_volume()
    except Exception as exc:
        STATE["last_error"] = str(exc)
        LOGGER.exception("Startup MRI volume auto-load failed.")
    server = ThreadingHTTPServer((host, port), BackendHandler)
    LOGGER.info("AIDLC-MRI backend/frontend running at http://%s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    run()
