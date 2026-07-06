from __future__ import annotations

import logging
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from brain_mask import create_brain_mask
from mesh_builder import BrainMesh, build_brain_intensity_mesh_from_volume, build_brain_mesh_from_mask, export_stl
from mri_loader import MRIData, discover_dicom_series, load_dicom, load_nifti, load_nifti_mask, save_nifti_mask
from preprocessing import normalize_intensity, plane_length, slice_from_plane
from report import DISCLAIMER, create_viewer_report
from skull_stripping import (
    get_hdbet_debug_info,
    get_skullstrip_status,
    get_torch_cuda_status,
    has_reliable_skullstrip_tool,
    run_skull_stripping,
    skullstrip_unavailable_message,
)


DEFAULT_DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
OUTPUT_DIR = Path("outputs")
MASK_PATH = OUTPUT_DIR / "brain_mask.nii.gz"
REFINED_MASK_PATH = OUTPUT_DIR / "refined_brain_mask.nii.gz"
FILLED_MASK_PATH = OUTPUT_DIR / "filled_brain_mask.nii.gz"
MESH_PATH = OUTPUT_DIR / "brain_mesh.stl"
BRAIN_PATH = OUTPUT_DIR / "brain_extracted.nii.gz"

st.set_page_config(page_title="AIDLC-MRI", layout="wide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("aidlc_mri")


def main() -> None:
    try:
        st.title("AIDLC-MRI")
        st.caption("Brain MRI viewer and brain-only 3D mesh MVP")
        st.warning(DISCLAIMER)

        default_mode = "3D" if str(st.query_params.get("mvp", "2d")).lower() == "3d" else "2D"
        with st.sidebar:
            sidebar_mode = st.radio("View mode", ["2D", "3D"], index=0 if default_mode == "2D" else 1)
            source_mode = st.radio("Input source", ["DICOM folder", "NIfTI upload"], index=0)

        view_mode = st.radio(
            "View mode",
            ["2D", "3D"],
            index=0 if sidebar_mode == "2D" else 1,
            horizontal=True,
            key=f"main_view_mode_{default_mode}",
        )

        try:
            mri_data = load_input(source_mode)
        except Exception as exc:
            log_exception("Failed to load MRI input", exc)
            st.error("Failed to load MRI input.")
            st.exception(exc)
            st.stop()
        if mri_data is None:
            st.info("Load a DICOM series or upload a NIfTI file to begin.")
            return

        st.session_state["mri_data"] = mri_data
        if view_mode == "3D":
            show_3d_mode(mri_data)
        else:
            show_2d_mode(mri_data)
    except Exception as exc:
        log_exception("Unhandled app error", exc)
        st.error("App error. The server is still running; check the traceback below.")
        st.exception(exc)
        if "mri_data" in st.session_state:
            st.warning("2D viewer is still available. Switch View mode to 2D.")


def load_input(source_mode: str) -> MRIData | None:
    with st.sidebar:
        if source_mode == "NIfTI upload":
            uploaded = st.file_uploader("NIfTI file", type=["nii", "gz"])
            if uploaded is None:
                return None
            upload_dir = Path("work/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            suffix = ".nii.gz" if uploaded.name.endswith(".nii.gz") else ".nii"
            upload_path = upload_dir / f"uploaded{suffix}"
            upload_path.write_bytes(uploaded.getbuffer())
            if st.button("Load NIfTI", type="primary") or st.session_state.get("loaded_path") != str(upload_path):
                with st.spinner("Loading NIfTI volume..."):
                    st.session_state["loaded_mri"] = cached_load_nifti(str(upload_path))
                    st.session_state["loaded_path"] = str(upload_path)
                    st.session_state["nifti_path"] = str(upload_path)
            return st.session_state.get("loaded_mri")

        folder_path = st.text_input("DICOM data folder", value=str(DEFAULT_DATA_DIR))
        folder_path = str(Path(folder_path))
        st.session_state["dicom_dir"] = folder_path
        scan_clicked = st.button("Scan series", type="primary")

    if scan_clicked or "series" not in st.session_state:
        try:
            st.session_state["series"] = cached_discover_dicom_series(folder_path)
        except Exception as exc:
            st.session_state["series"] = []
            st.error(f"Series scan failed: {exc}")

    series = st.session_state.get("series", [])
    if not series:
        return None

    labels = [format_series_label(item) for item in series]
    selected_label = st.sidebar.selectbox("DICOM series", labels)
    selected = series[labels.index(selected_label)]

    with st.sidebar:
        st.write(f"Files: `{selected['file_count']}`")
        st.write(f"Series: `{selected['description']}`")
        load_clicked = st.button("Load volume", type="primary")

    if load_clicked or st.session_state.get("loaded_key") != selected["key"]:
        with st.spinner("Loading DICOM volume..."):
            st.session_state["loaded_mri"] = cached_load_dicom(folder_path, str(selected["key"]))
            st.session_state["loaded_key"] = selected["key"]
            clear_mesh_state()
    return st.session_state.get("loaded_mri")


@st.cache_data(show_spinner=False, max_entries=8)
def cached_discover_dicom_series(folder_path: str) -> list[dict]:
    return discover_dicom_series(folder_path)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_load_dicom(dicom_dir: str, series_key: str) -> MRIData:
    dicom_dir = str(Path(dicom_dir))
    series = discover_dicom_series(dicom_dir)
    for item in series:
        if str(item.get("key")) == str(series_key):
            return load_dicom(str(dicom_dir), series_key=str(series_key))
    raise FileNotFoundError(f"DICOM series not found: {series_key}")


@st.cache_data(show_spinner=False, max_entries=4)
def cached_load_nifti(path: str) -> MRIData:
    return load_nifti(path)


def show_2d_mode(mri_data: MRIData) -> None:
    volume = mri_data.volume
    info = mri_data.info
    normalized = normalize_intensity(volume)

    with st.sidebar:
        plane = st.selectbox("Slice plane", ["axial", "sagittal", "coronal"], index=plane_default_index(info))
        max_index = plane_length(volume, plane) - 1
        slice_index = st.slider("Slice index", 0, max_index, max_index // 2)
        window_level = st.slider("Window Level", 0.0, 1.0, 0.5, 0.01)
        window_width = st.slider("Window Width", 0.05, 1.0, 0.6, 0.01)
        show_mask_overlay = st.checkbox("Show mask overlay on 2D", value=False)

    controls, viewer = st.columns([1, 2])
    image = apply_window(slice_from_plane(normalized, plane, slice_index), window_level, window_width)
    mask_slice = None
    if show_mask_overlay:
        mask = ensure_brain_mask(mri_data)
        mask_slice = slice_from_plane(mask.astype(np.float32), plane, slice_index)

    with controls:
        st.subheader("Info")
        st.write(f"Source: `{mri_data.source_type}`")
        st.write(f"Shape: `{tuple(int(v) for v in volume.shape)}`")
        st.write(f"Spacing z/y/x: `{mri_data.spacing}`")
        st.write(f"Series: `{info.get('SeriesDescription', 'Unknown')}`")
        st.write(f"Orientation: `{info.get('OrientationNote', 'Unknown')}`")
        st.subheader("ROI")
        x = st.number_input("x", min_value=0, max_value=max(image.shape[1] - 1, 0), value=image.shape[1] // 4)
        y = st.number_input("y", min_value=0, max_value=max(image.shape[0] - 1, 0), value=image.shape[0] // 4)
        roi_width = st.number_input("width", min_value=1, max_value=image.shape[1], value=image.shape[1] // 4)
        roi_height = st.number_input("height", min_value=1, max_value=image.shape[0], value=image.shape[0] // 4)
        roi = clamp_roi(int(x), int(y), int(roi_width), int(roi_height), image.shape)
        if st.button("Create PDF report"):
            path = create_viewer_report(info, slice_index=slice_index, roi=roi, mesh_info=st.session_state.get("mesh_info"))
            st.success(f"PDF created: {path}")

    with viewer:
        st.subheader(f"{plane.title()} slice")
        st.pyplot(draw_slice(image, roi, mask_slice), clear_figure=True)
        st.warning(DISCLAIMER)


def show_3d_mode(mri_data: MRIData) -> None:
    skullstrip_status = get_skullstrip_status()
    hdbet_debug = get_hdbet_debug_info(OUTPUT_DIR)
    cuda_status = get_torch_cuda_status()
    reliable_tool_available = has_reliable_skullstrip_tool(skullstrip_status)
    hdbet_ready = hdbet_debug.get("status") == "HD-BET ready"
    effective_tool_available = reliable_tool_available or hdbet_ready
    with st.sidebar:
        st.subheader("Brain-only segmentation")
        method = st.selectbox("Skull stripping method", ["SynthStrip recommended", "HD-BET", "Simple fallback debug only"], index=0)
        method_key = "SynthStrip" if method.startswith("SynthStrip") else ("HD-BET" if method == "HD-BET" else "Simple fallback")
        show_skullstrip_status(skullstrip_status, method, hdbet_ready=hdbet_ready)
        show_hdbet_debug_summary(hdbet_debug)
        synthstrip_command = st.text_input("SynthStrip command", value="mri_synthstrip")
        hdbet_command = st.text_input("HD-BET command", value="hd-bet")
        show_cuda_status(cuda_status)
        hdbet_devices = ["cuda", "cpu"] if cuda_status.get("available") else ["cpu"]
        hdbet_device = st.selectbox("HD-BET device", hdbet_devices, index=0)
        threshold_scale = st.slider("Brain mask threshold", 0.5, 1.5, 1.0, 0.05)
        peel_iterations = st.slider("Skin/skull peel iterations", 0, 10, 5)
        st.subheader("Mask refinement")
        mask_preview_mode = st.selectbox(
            "Mask preview mode",
            ["Filled mask", "Cleaned mask", "Raw mask", "Raw + cleaned + filled", "Extracted brain", "Mesh"],
            index=0,
        )
        fill_holes = st.checkbox("Fill holes", value=True)
        closing_radius = st.slider("Closing radius", 1, 8, 3)
        remove_small_holes_threshold = st.slider("Remove small holes threshold", 1000, 20000, 5000, step=500)
        remove_small_objects_threshold = st.slider("Remove small objects threshold", 5000, 100000, 20000, step=1000)
        mask_smoothing_sigma = st.slider("Gaussian smoothing sigma", 0.0, 3.0, 1.0, 0.1)
        mask_opacity = st.slider("Mask opacity", 0.05, 0.90, 0.35, 0.05)
        st.subheader("Mesh")
        surface_mode = st.selectbox("Surface mode", ["Brain mask surface", "Brain intensity surface"], index=1)
        iso_percentile = st.slider("Iso level percentile", 10, 80, 35, step=1)
        downsample_factor = st.slider("Downsample factor", 1, 5, 2)
        step_size = st.slider("Mesh step_size", 1, 4, 1)
        mesh_mask_gaussian_sigma = st.slider("Mesh mask gaussian sigma", 0.0, 3.0, 0.2, 0.1)
        mesh_smoothing_enabled = st.checkbox("Mesh smoothing", value=True)
        smoothing_iterations = st.slider("Mesh smoothing iterations", 0, 10, 1)
        mesh_opacity = st.slider("Mesh opacity", 0.15, 1.0, 0.86, 0.05)
        show_wireframe = st.checkbox("Show wireframe", value=False)
        skullstrip_run_disabled = not effective_tool_available and not method.startswith("Simple fallback")
        sidebar_preview_clicked = st.button("Generate refined mask", type="primary", disabled=skullstrip_run_disabled)
        sidebar_create_clicked = st.button("Generate final brain-only 3D mesh", disabled=method.startswith("Simple fallback") or not effective_tool_available)

    st.subheader("3D brain-only mesh")
    if not effective_tool_available:
        st.warning(skullstrip_unavailable_message())
        show_install_help()
    elif hdbet_ready:
        st.success("HD-BET: ready")
    if method.startswith("Simple fallback"):
        st.warning("Fallback mask is not reliable enough for final brain-only 3D mesh.")

    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        main_preview_clicked = st.button(
            "Generate refined mask",
            type="primary",
            use_container_width=True,
            disabled=not effective_tool_available and not method.startswith("Simple fallback"),
        )
    with cols[1]:
        main_create_clicked = st.button(
            "Generate final brain-only 3D mesh",
            use_container_width=True,
            disabled=method.startswith("Simple fallback") or not effective_tool_available,
        )
    with cols[2]:
        if st.button("Use default fast settings", use_container_width=True):
            threshold_scale = 1.0
            peel_iterations = 6
            downsample_factor = 2
            step_size = 1
            smoothing_iterations = 1
            mesh_mask_gaussian_sigma = 0.2
            mesh_smoothing_enabled = True
            main_preview_clicked = True
    with cols[3]:
        add_download_button("Export STL", st.session_state.get("mesh_info", {}).get("mesh_path"))

    preview_clicked = sidebar_preview_clicked or main_preview_clicked
    create_clicked = sidebar_create_clicked or main_create_clicked
    debug_create_clicked = False
    with st.expander("Debug fallback 3D, not brain-only"):
        st.warning("This is NOT brain-only. Debug only.")
        debug_create_clicked = st.button("Generate debug fallback 3D", use_container_width=True)

    if debug_create_clicked:
        method_key = "Simple fallback"
        preview_clicked = True

    if preview_clicked:
        try:
            if hdbet_ready and not reliable_tool_available and not method.startswith("Simple fallback"):
                result = load_existing_hdbet_result(mri_data, hdbet_debug)
                st.info("Loaded existing HD-BET output from outputs/.")
            else:
                with st.spinner("Creating brain mask from the full MRI volume..."):
                    result = cached_skull_stripping(
                        mri_data.volume,
                        mri_data.affine,
                        mri_data.spacing,
                        mri_data.info,
                        mri_data.source_type,
                        mri_data.source_label,
                        method_key,
                        str(OUTPUT_DIR),
                        synthstrip_command,
                        hdbet_command,
                        hdbet_device,
                        float(threshold_scale),
                        int(peel_iterations),
                        bool(fill_holes),
                        int(closing_radius),
                        int(remove_small_holes_threshold),
                        int(remove_small_objects_threshold),
                        float(mask_smoothing_sigma),
                    )
            st.session_state["raw_brain_mask"] = result.raw_mask
            st.session_state["cleaned_brain_mask"] = result.refined_mask
            st.session_state["filled_brain_mask"] = result.filled_mask
            st.session_state["refined_brain_mask"] = result.refined_mask
            st.session_state["brain_mask"] = result.filled_mask
            st.session_state["mask_meta"] = result.metadata
            st.session_state["skull_strip_warnings"] = result.warnings
            st.session_state["reliable_for_3d"] = result.reliable_for_3d
            st.session_state["debug_only_mask"] = result.debug_only
            st.session_state["brain_extracted"] = result.brain_extracted
            st.session_state["mesh_info"] = {
                "mask_path": result.mask_path,
                "refined_mask_path": result.refined_mask_path,
                "filled_mask_path": result.filled_mask_path,
                "brain_path": result.brain_path,
            }
            st.session_state.pop("brain_mesh", None)
        except Exception as exc:
            log_exception("3D skull stripping failed", exc)
            if "Reliable skull stripping tool is not available" in str(exc):
                st.warning(skullstrip_unavailable_message())
                show_command_attempts_text(str(exc))
                show_install_help()
            else:
                st.error("3D rendering failed. Check the log.")
                st.exception(exc)
                st.warning("2D viewer is still available.")
            return

    raw_mask = st.session_state.get("raw_brain_mask")
    cleaned_mask = st.session_state.get("cleaned_brain_mask")
    if cleaned_mask is None:
        cleaned_mask = st.session_state.get("refined_brain_mask")
    filled_mask = st.session_state.get("filled_brain_mask")
    if filled_mask is None:
        filled_mask = st.session_state.get("brain_mask")
    mask = filled_mask
    mask_meta = st.session_state.get("mask_meta", {})
    mesh_info = st.session_state.get("mesh_info", {})
    warnings = st.session_state.get("skull_strip_warnings", [])
    quality_warnings = list(mask_meta.get("quality_warnings", []))
    reliable_for_3d = bool(st.session_state.get("reliable_for_3d", False))
    debug_only_mask = bool(st.session_state.get("debug_only_mask", False))
    if warnings:
        for warning in warnings:
            st.warning(warning)
    if debug_only_mask:
        st.warning("Fallback mask is not reliable enough for final brain-only 3D mesh.")

    if mask is None and create_clicked and hdbet_ready and not reliable_tool_available:
        result = load_existing_hdbet_result(mri_data, hdbet_debug)
        st.session_state["raw_brain_mask"] = result.raw_mask
        st.session_state["cleaned_brain_mask"] = result.refined_mask
        st.session_state["filled_brain_mask"] = result.filled_mask
        st.session_state["refined_brain_mask"] = result.refined_mask
        st.session_state["brain_mask"] = result.filled_mask
        st.session_state["mask_meta"] = result.metadata
        st.session_state["skull_strip_warnings"] = result.warnings
        st.session_state["reliable_for_3d"] = result.reliable_for_3d
        st.session_state["debug_only_mask"] = result.debug_only
        st.session_state["brain_extracted"] = result.brain_extracted
        st.session_state["mesh_info"] = {
            "mask_path": result.mask_path,
            "refined_mask_path": result.refined_mask_path,
            "filled_mask_path": result.filled_mask_path,
            "brain_path": result.brain_path,
        }
        raw_mask = result.raw_mask
        cleaned_mask = result.refined_mask
        filled_mask = result.filled_mask
        mask = filled_mask
        mask_meta = result.metadata
        mesh_info = st.session_state["mesh_info"]
        reliable_for_3d = True
        debug_only_mask = False
        st.info("Loaded existing HD-BET output from outputs/.")

    if mask is None:
        st.info("First create and inspect the brain_mask overlay. Then create the 3D mesh from that mask.")
        return

    show_mask_preview(
        mri_data,
        raw_mask=raw_mask,
        cleaned_mask=cleaned_mask,
        filled_mask=filled_mask,
        brain_extracted=st.session_state.get("brain_extracted"),
        mesh=st.session_state.get("brain_mesh"),
        mask_meta=mask_meta,
        preview_mode=mask_preview_mode,
        opacity=mask_opacity,
    )
    show_command_attempts(mask_meta.get("tool_attempts", []))

    if debug_create_clicked:
        st.warning("This is NOT brain-only. Debug only.")
        try:
            with st.spinner("Building debug fallback surface mesh..."):
                mesh = cached_brain_mesh(
                    "Brain mask surface",
                    filled_mask,
                    st.session_state.get("brain_extracted"),
                    mri_data.spacing,
                    int(downsample_factor),
                    int(step_size),
                    int(smoothing_iterations),
                    float(mesh_mask_gaussian_sigma),
                    bool(mesh_smoothing_enabled),
                    float(iso_percentile),
                )
                mesh_path = export_stl(mesh, OUTPUT_DIR / "debug_fallback_mesh.stl")
            st.session_state["brain_mesh"] = mesh
            st.session_state["mesh_info"] = {**mesh_info, "mesh_path": mesh_path}
        except Exception as exc:
            log_exception("Debug fallback mesh generation failed", exc)
            st.error("Debug fallback 3D generation failed.")
            st.exception(exc)
            return

    if create_clicked:
        if debug_only_mask or not reliable_for_3d:
            st.warning(
                skullstrip_unavailable_message()
            )
            return
        if quality_warnings:
            st.warning("Mask quality warning: mesh may be inaccurate. Fix the overlay before generating 3D.")
            return

        try:
            with st.spinner("Building brain-only surface mesh..."):
                mesh = cached_brain_mesh(
                    surface_mode,
                    filled_mask,
                    st.session_state.get("brain_extracted"),
                    mri_data.spacing,
                    int(downsample_factor),
                    int(step_size),
                    int(smoothing_iterations),
                    float(mesh_mask_gaussian_sigma),
                    bool(mesh_smoothing_enabled),
                    float(iso_percentile),
                )
                mesh_path = export_stl(mesh, mesh_output_path(mask_meta, surface_mode))
            st.session_state["brain_mesh"] = mesh
            st.session_state["mesh_info"] = {**mesh_info, "mesh_path": mesh_path, "surface_mode": surface_mode}
        except Exception as exc:
            log_exception("3D mesh generation failed", exc)
            st.error("3D rendering failed. Check the log.")
            st.exception(exc)
            st.warning("2D viewer is still available.")
            return

    mesh = st.session_state.get("brain_mesh")
    mesh_info = st.session_state.get("mesh_info", {})
    if mesh is None:
        st.info("Mask preview is ready. Click Generate 3D mesh to run marching cubes on filled_brain_mask only.")
        return

    left, right = st.columns([1, 2])
    with left:
        st.subheader("Brain Mask / Mesh")
        st.write(f"Mask method: `{mask_meta.get('method', 'Unknown')}`")
        st.write(f"Mask source: `{mask_meta.get('method', 'Unknown')}`")
        status_text, reason_text = mesh_status(mask_meta, reliable_for_3d, debug_only_mask, quality_warnings)
        st.write(f"3D status: `{status_text}`")
        st.write(f"Reason: `{reason_text}`")
        st.write(f"Threshold: `{mask_meta.get('threshold', 'Unknown')}`")
        st.write(f"Raw mask voxels: `{mask_meta.get('raw_voxels', 'Unknown')}`")
        st.write(f"Cleaned mask voxels: `{mask_meta.get('cleaned_voxels', 'Unknown')}`")
        st.write(f"Filled mask voxels: `{mask_meta.get('voxels', 'Unknown')}`")
        st.write(f"Mesh vertices: `{len(mesh.vertices)}`")
        st.write(f"Mesh faces: `{len(mesh.faces)}`")
        st.write(f"Surface mode: `{mesh_info.get('surface_mode', 'Brain mask surface')}`")
        for mesh_warning in mesh.quality_warnings or []:
            st.warning(mesh_warning)
        st.write(f"brain_mask.nii.gz: `{mesh_info.get('mask_path', '')}`")
        st.write(f"refined_brain_mask.nii.gz: `{mesh_info.get('refined_mask_path', '')}`")
        st.write(f"filled_brain_mask.nii.gz: `{mesh_info.get('filled_mask_path', '')}`")
        st.write(f"brain_extracted.nii.gz: `{mesh_info.get('brain_path', '')}`")
        st.write(f"brain_mesh.stl: `{mesh_info.get('mesh_path', '')}`")
        add_download_button("Export STL", mesh_info.get("mesh_path"))
        st.button("Export GLB", disabled=True, help="GLB export can be enabled later by adding trimesh. STL export is available now.")

    with right:
        st.subheader(str(mesh_info.get("surface_mode", "Brain-only 3D surface")))
        try:
            st.plotly_chart(mesh_to_figure(mesh, opacity=mesh_opacity, show_wireframe=show_wireframe), use_container_width=True)
        except Exception as exc:
            log_exception("Plotly mesh rendering failed", exc)
            st.error("3D rendering failed. Check the log.")
            st.exception(exc)
            st.warning("2D viewer is still available.")
        st.warning(DISCLAIMER)


@st.cache_data(show_spinner=False, max_entries=2)
def cached_skull_stripping(
    volume: np.ndarray,
    affine: np.ndarray,
    spacing: tuple[float, float, float],
    info: dict,
    source_type: str,
    source_label: str,
    method: str,
    output_dir: str,
    synthstrip_command: str,
    hdbet_command: str,
    hdbet_device: str,
    threshold_scale: float,
    peel_iterations: int,
    fill_holes: bool,
    closing_radius: int,
    remove_small_holes_threshold: int,
    remove_small_objects_threshold: int,
    mask_smoothing_sigma: float,
):
    safe_data = MRIData(
        volume=np.asarray(volume, dtype=np.float32),
        affine=np.asarray(affine, dtype=np.float32),
        spacing=tuple(float(value) for value in spacing),
        info=dict(info),
        source_type=str(source_type),
        source_label=str(source_label),
    )
    return run_skull_stripping(
        safe_data,
        method=method,
        output_dir=Path(output_dir),
        synthstrip_command=synthstrip_command,
        hdbet_command=hdbet_command,
        hdbet_device=hdbet_device,
        threshold_scale=threshold_scale,
        peel_iterations=peel_iterations,
        fill_holes=fill_holes,
        closing_radius=closing_radius,
        remove_small_holes_threshold=remove_small_holes_threshold,
        remove_small_objects_threshold=remove_small_objects_threshold,
        mask_smoothing_sigma=mask_smoothing_sigma,
    )


def load_existing_hdbet_result(mri_data: MRIData, debug_info: dict):
    from skull_stripping import SkullStripResult

    output_dir = OUTPUT_DIR
    raw_path = output_dir / "brain_mask.nii.gz"
    refined_path = output_dir / "refined_brain_mask.nii.gz"
    filled_path = output_dir / "filled_brain_mask.nii.gz"
    brain_path = output_dir / "brain_extracted.nii.gz"
    if not filled_path.exists():
        mask_candidates = [Path(path) for path in debug_info.get("mask_candidates", [])]
        if not mask_candidates:
            raise FileNotFoundError("No existing HD-BET mask candidate found.")
        filled_mask = load_nifti_mask(mask_candidates[0])
        raw_mask = filled_mask
        refined_mask = filled_mask
    else:
        raw_mask = load_nifti_mask(raw_path) if raw_path.exists() else load_nifti_mask(filled_path)
        refined_mask = load_nifti_mask(refined_path) if refined_path.exists() else load_nifti_mask(filled_path)
        filled_mask = load_nifti_mask(filled_path)

    if brain_path.exists():
        brain_extracted = load_nifti(str(brain_path)).volume
    else:
        brain_extracted = mri_data.volume * filled_mask.astype(np.float32)

    metadata = {
        "method": "HD-BET",
        "reliable_for_3d": True,
        "debug_only": False,
        "tool_mask_path": str(raw_path),
        "tool_brain_path": str(brain_path),
        "raw_voxels": int(np.count_nonzero(raw_mask)),
        "cleaned_voxels": int(np.count_nonzero(refined_mask)),
        "voxels": int(np.count_nonzero(filled_mask)),
        "quality_warnings": [],
        "loaded_existing_output": True,
    }
    return SkullStripResult(
        raw_mask=raw_mask,
        refined_mask=refined_mask,
        filled_mask=filled_mask,
        mask=filled_mask,
        brain_extracted=brain_extracted,
        mask_path=raw_path,
        refined_mask_path=refined_path,
        filled_mask_path=filled_path,
        brain_path=brain_path,
        method_used="HD-BET",
        reliable_for_3d=True,
        debug_only=False,
        metadata=metadata,
        warnings=[],
    )


@st.cache_data(show_spinner=False, max_entries=2)
def cached_brain_mesh(
    surface_mode: str,
    mask: np.ndarray,
    brain_extracted: np.ndarray | None,
    spacing: tuple[float, float, float],
    downsample_factor: int,
    step_size: int,
    smoothing_iterations: int,
    mask_gaussian_sigma: float,
    mesh_smoothing_enabled: bool,
    iso_percentile: float,
) -> BrainMesh:
    if surface_mode == "Brain intensity surface":
        if brain_extracted is None:
            raise ValueError("Brain intensity surface requires brain_extracted volume from HD-BET.")
        return build_brain_intensity_mesh_from_volume(
            brain_extracted,
            mask,
            spacing=spacing,
            iso_percentile=float(iso_percentile),
            gaussian_sigma=mask_gaussian_sigma,
            step_size=step_size,
            apply_mesh_smoothing=mesh_smoothing_enabled,
            downsample_factor=downsample_factor,
            smoothing_iterations=smoothing_iterations,
        )
    return build_brain_mesh_from_mask(
        mask,
        spacing=spacing,
        gaussian_sigma=mask_gaussian_sigma,
        level=0.5,
        step_size=step_size,
        apply_mesh_smoothing=mesh_smoothing_enabled,
        decimate_ratio=None,
        downsample_factor=downsample_factor,
        smoothing_iterations=smoothing_iterations,
    )


def show_mask_preview(
    mri_data: MRIData,
    raw_mask: np.ndarray | None,
    cleaned_mask: np.ndarray | None,
    filled_mask: np.ndarray,
    brain_extracted: np.ndarray | None,
    mesh: BrainMesh | None,
    mask_meta: dict,
    preview_mode: str,
    opacity: float,
) -> None:
    plane = st.selectbox("Mask preview plane", ["axial", "sagittal", "coronal"], index=plane_default_index(mri_data.info))
    max_index = plane_length(mri_data.volume, plane) - 1
    slice_index = st.slider("Mask preview slice", 0, max_index, max_index // 2)
    normalized = normalize_intensity(mri_data.volume)
    image = apply_window(slice_from_plane(normalized, plane, slice_index), 0.5, 0.6)
    raw_slice = slice_from_plane(raw_mask.astype(np.float32), plane, slice_index) if raw_mask is not None else None
    cleaned_slice = slice_from_plane(cleaned_mask.astype(np.float32), plane, slice_index) if cleaned_mask is not None else None
    filled_slice = slice_from_plane(filled_mask.astype(np.float32), plane, slice_index)
    extracted_image = None
    if brain_extracted is not None:
        extracted_normalized = normalize_intensity(brain_extracted)
        extracted_image = apply_window(slice_from_plane(extracted_normalized, plane, slice_index), 0.5, 0.6)

    left, right = st.columns([1, 2])
    with left:
        st.subheader("Brain mask preview")
        st.write(f"Method: `{mask_meta.get('method', 'Unknown')}`")
        preview_quality_warnings = list(mask_meta.get("quality_warnings", []))
        preview_status, preview_reason = mesh_status(
            mask_meta,
            bool(mask_meta.get("reliable_for_3d", False)),
            bool(mask_meta.get("debug_only", False)),
            preview_quality_warnings,
        )
        st.write(f"Mask source: `{mask_meta.get('method', 'Unknown')}`")
        st.write(f"3D status: `{preview_status}`")
        st.write(f"Reason: `{preview_reason}`")
        st.write(f"Raw voxels: `{mask_meta.get('raw_voxels', int(np.count_nonzero(raw_mask)) if raw_mask is not None else 'Unknown')}`")
        st.write(f"Cleaned voxels: `{mask_meta.get('cleaned_voxels', int(np.count_nonzero(cleaned_mask)) if cleaned_mask is not None else 'Unknown')}`")
        st.write(f"Filled voxels: `{mask_meta.get('voxels', int(np.count_nonzero(filled_mask)))}`")
        st.write(f"Raw mask: `{MASK_PATH}`")
        st.write(f"Cleaned mask: `{REFINED_MASK_PATH}`")
        st.write(f"Filled mask: `{FILLED_MASK_PATH}`")
        st.write(f"Extracted brain: `{BRAIN_PATH}`")
    with right:
        if preview_mode == "Mesh" and mesh is not None:
            st.plotly_chart(mesh_to_figure(mesh), use_container_width=True)
        elif preview_mode == "Mesh":
            st.info("Generate 3D mesh to preview the mesh here.")
        elif preview_mode == "Extracted brain" and extracted_image is not None:
            st.pyplot(draw_mask_preview(extracted_image, opacity=opacity), clear_figure=True)
        else:
            st.pyplot(
                draw_mask_preview(
                    image,
                    raw_slice=raw_slice if preview_mode in {"Raw mask", "Raw + cleaned + filled"} else None,
                    cleaned_slice=cleaned_slice if preview_mode in {"Cleaned mask", "Raw + cleaned + filled"} else None,
                    filled_slice=filled_slice if preview_mode in {"Filled mask", "Raw + cleaned + filled"} else None,
                    opacity=opacity,
                ),
                clear_figure=True,
            )


def draw_mask_preview(
    image: np.ndarray,
    raw_slice: np.ndarray | None = None,
    cleaned_slice: np.ndarray | None = None,
    filled_slice: np.ndarray | None = None,
    opacity: float = 0.35,
):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if raw_slice is not None:
        raw_overlay = np.ma.masked_where(raw_slice <= 0, raw_slice)
        ax.imshow(raw_overlay, cmap="winter", alpha=max(0.05, float(opacity) * 0.75), vmin=0, vmax=1)
    if cleaned_slice is not None:
        cleaned_overlay = np.ma.masked_where(cleaned_slice <= 0, cleaned_slice)
        ax.imshow(cleaned_overlay, cmap="spring", alpha=max(0.05, float(opacity) * 0.75), vmin=0, vmax=1)
    if filled_slice is not None:
        filled_overlay = np.ma.masked_where(filled_slice <= 0, filled_slice)
        ax.imshow(filled_overlay, cmap="autumn", alpha=float(opacity), vmin=0, vmax=1)
    ax.axis("off")
    fig.tight_layout()
    return fig


def mesh_to_figure(mesh: BrainMesh, opacity: float = 0.86, show_wireframe: bool = False) -> go.Figure:
    vertices = mesh.vertices
    faces = mesh.faces
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("Mesh is empty.")
    if len(faces) > 250_000:
        raise ValueError(f"Mesh is too large for browser rendering: {len(faces)} faces. Increase downsample or step_size.")
    data = [
        go.Mesh3d(
            x=vertices[:, 2],
            y=vertices[:, 1],
            z=vertices[:, 0],
            i=faces[:, 0],
            j=faces[:, 1],
            k=faces[:, 2],
            color="lightgray",
            opacity=float(opacity),
            flatshading=False,
            lighting=dict(ambient=0.45, diffuse=0.85, specular=0.18, roughness=0.65),
        )
    ]
    if show_wireframe:
        x_lines, y_lines, z_lines = mesh_wireframe_lines(vertices, faces, max_edges=9000)
        data.append(
            go.Scatter3d(
                x=x_lines,
                y=y_lines,
                z=z_lines,
                mode="lines",
                line=dict(color="rgba(40, 40, 40, 0.22)", width=1),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig = go.Figure(
        data=data
    )
    fig.update_layout(
        height=720,
        margin=dict(l=0, r=0, t=10, b=0),
        scene=dict(aspectmode="data", xaxis_title="x", yaxis_title="y", zaxis_title="z"),
    )
    return fig


def mesh_wireframe_lines(vertices: np.ndarray, faces: np.ndarray, max_edges: int = 9000) -> tuple[list[float], list[float], list[float]]:
    edges: set[tuple[int, int]] = set()
    stride = max(1, int(len(faces) / max(1, max_edges // 3)))
    for face in faces[::stride]:
        a, b, c = [int(value) for value in face]
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add((min(u, v), max(u, v)))
            if len(edges) >= max_edges:
                break
        if len(edges) >= max_edges:
            break
    x_lines: list[float] = []
    y_lines: list[float] = []
    z_lines: list[float] = []
    for u, v in edges:
        for index in (u, v):
            z, y, x = vertices[index]
            x_lines.append(float(x))
            y_lines.append(float(y))
            z_lines.append(float(z))
        x_lines.append(None)  # type: ignore[arg-type]
        y_lines.append(None)  # type: ignore[arg-type]
        z_lines.append(None)  # type: ignore[arg-type]
    return x_lines, y_lines, z_lines


def show_skullstrip_status(status: dict[str, bool], selected_method: str, hdbet_ready: bool = False) -> None:
    st.caption("Skull stripping tools")
    for command, installed in status.items():
        label = "installed" if installed else "not found"
        st.write(f"{command}: `{label}`")
    final_enabled = (has_reliable_skullstrip_tool(status) or hdbet_ready) and not selected_method.startswith("Simple fallback")
    st.write(f"Selected method: `{selected_method}`")
    st.write(f"Final 3D mesh: `{'available' if final_enabled else 'disabled'}`")
    if not final_enabled and any(status.values()):
        st.caption("Windows native HD-BET was detected but is not treated as reliable for final 3D in this app.")


def show_hdbet_debug_summary(info: dict[str, object]) -> None:
    status = str(info.get("status", "unknown"))
    st.write(f"HD-BET: `{status}`")
    st.caption(str(info.get("reason", "")))
    if status != "HD-BET ready" and (
        info.get("local_hd_bet_exists") or info.get("which_hd_bet") or info.get("which_HD_BET")
    ):
        st.warning("HD-BET found but failed validation. Check the debug log below.")
    with st.expander("HD-BET detection/debug", expanded=status != "HD-BET ready"):
        st.write(f"sys.executable: `{info.get('sys_executable')}`")
        st.write(f"current working directory: `{info.get('cwd')}`")
        st.write(f"venv path: `{info.get('venv_path')}`")
        st.write(f"venv python: `{info.get('venv_python')}`")
        st.write(f"shutil.which('hd-bet'): `{info.get('which_hd_bet')}`")
        st.write(f"shutil.which('HD_BET'): `{info.get('which_HD_BET')}`")
        st.write(f".venv\\Scripts\\hd-bet.exe exists: `{info.get('local_hd_bet_exists')}`")
        st.write(f".venv\\Scripts\\HD_BET.exe exists: `{info.get('local_HD_BET_exists')}`")
        st.write(f"outputs/brain_extracted_hdbet.nii.gz exists: `{info.get('brain_extracted_hdbet_exists')}`")
        st.write("Mask candidates:")
        st.json(info.get("mask_candidates", []))
        st.write("HD-BET command candidates:")
        st.json(
            [
                {"label": item.get("label"), "resolved": item.get("resolved"), "cmd": item.get("cmd"), "error": item.get("error")}
                for item in info.get("command_candidates", [])
            ]
        )
        st.write("pip show hd-bet")
        show_probe(info.get("pip_show_hd_bet", {}))
        st.write("import HD_BET")
        show_probe(info.get("import_HD_BET", {}))
        st.warning(str(info.get("windows_native_note", "")))


def show_probe(probe: object) -> None:
    if not isinstance(probe, dict):
        st.write(probe)
        return
    st.code(str(probe.get("command", "")), language="powershell")
    st.write(f"returncode: `{probe.get('returncode')}`")
    stdout = str(probe.get("stdout") or "").strip()
    stderr = str(probe.get("stderr") or "").strip()
    if stdout:
        st.caption("stdout")
        st.code(stdout[-4000:])
    if stderr:
        st.caption("stderr")
        st.code(stderr[-4000:])


def show_cuda_status(status: dict[str, object]) -> None:
    st.caption("GPU / CUDA")
    if status.get("available"):
        st.write(f"CUDA: `available`")
        st.write(f"GPU: `{status.get('device_name', '')}`")
    else:
        st.write("CUDA: `not available`")
        st.caption(f"Torch: {status.get('torch_version', 'unknown')} / CUDA: {status.get('cuda_version', 'none')}")


def show_install_help() -> None:
    with st.expander("Install reliable skull stripping tools", expanded=True):
        st.markdown(
            """
Windows PowerShell:

```powershell
python -m pip install --upgrade pip
pip install hd-bet
```

After installation:

```powershell
where hd-bet
where HD_BET
python -m HD_BET -h
```

If the command is still not found, check the virtualenv Scripts path:

```powershell
.venv\\Scripts\\hd-bet.exe
.venv\\Scripts\\HD_BET.exe
```

SynthStrip usually requires FreeSurfer/SynthStrip installation. Final brain-only 3D mesh is enabled only when SynthStrip or HD-BET is available.

If Windows native HD-BET exits with `3221225786`, use WSL2 Ubuntu or Docker/SynthStrip. The viewer will keep running, but final brain-only 3D is disabled until a reliable skull stripping tool is available.
"""
        )


def show_command_attempts(attempts: list[dict]) -> None:
    if not attempts:
        return
    with st.expander("HD-BET command attempts", expanded=False):
        for attempt in attempts:
            st.markdown(f"**{attempt.get('label', 'command')}**: `{attempt.get('status', 'unknown')}`")
            st.code(str(attempt.get("command", "")), language="powershell")
            if attempt.get("returncode") is not None:
                st.write(f"returncode: `{attempt.get('returncode')}`")
            stdout = str(attempt.get("stdout") or "").strip()
            stderr = str(attempt.get("stderr") or "").strip()
            if stdout:
                st.caption("stdout")
                st.code(stdout[-4000:])
            if stderr:
                st.caption("stderr")
                st.code(stderr[-4000:])


def show_command_attempts_text(text: str) -> None:
    if "HD-BET failed with all command candidates" not in text and "HD-BET unavailable/failed" not in text:
        return
    with st.expander("HD-BET command attempts", expanded=True):
        st.code(text[-8000:])


def mesh_output_path(mask_meta: dict, surface_mode: str = "Brain mask surface") -> Path:
    method = str(mask_meta.get("method", "")).lower()
    mode_suffix = "_intensity" if surface_mode == "Brain intensity surface" else ""
    if "synthstrip" in method:
        return OUTPUT_DIR / f"brain_mesh_synthstrip{mode_suffix}.stl"
    if "hd-bet" in method:
        return OUTPUT_DIR / f"brain_mesh_hdbet{mode_suffix}.stl"
    if mode_suffix:
        return OUTPUT_DIR / f"brain_mesh{mode_suffix}.stl"
    return MESH_PATH


def mesh_status(mask_meta: dict, reliable_for_3d: bool, debug_only_mask: bool, quality_warnings: list[str]) -> tuple[str, str]:
    method = str(mask_meta.get("method", "Unknown"))
    if debug_only_mask or method.lower().startswith("simple fallback"):
        return "Disabled", "fallback mask does not produce reliable brain-only mesh"
    if not reliable_for_3d:
        return "Disabled", "SynthStrip or HD-BET mask is required"
    if quality_warnings:
        return "Disabled", "; ".join(quality_warnings)
    return "Enabled", "validated SynthStrip/HD-BET brain mask"


def ensure_brain_mask(mri_data: MRIData) -> np.ndarray:
    if "brain_mask" not in st.session_state:
        mask, meta = create_brain_mask(mri_data.volume, plane=str(mri_data.info.get("Plane", "unknown")))
        st.session_state["brain_mask"] = mask
        st.session_state["mask_meta"] = meta
    return st.session_state["brain_mask"]


def clear_mesh_state() -> None:
    for key in (
        "raw_brain_mask",
        "cleaned_brain_mask",
        "filled_brain_mask",
        "refined_brain_mask",
        "brain_mask",
        "mask_meta",
        "brain_mesh",
        "mesh_info",
        "skull_strip_warnings",
        "reliable_for_3d",
        "debug_only_mask",
        "brain_extracted",
    ):
        st.session_state.pop(key, None)


def log_exception(message: str, exc: Exception) -> None:
    LOGGER.error("%s: %s\n%s", message, exc, traceback.format_exc())


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    low = level - width / 2.0
    high = level + width / 2.0
    if high <= low:
        high = low + 1.0
    return np.clip((image - low) / (high - low), 0, 1)


def draw_slice(image: np.ndarray, roi: dict, mask: np.ndarray | None = None):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if mask is not None:
        overlay = np.ma.masked_where(mask <= 0, mask)
        ax.imshow(overlay, cmap="autumn", alpha=0.35, vmin=0, vmax=1)
    rect = plt.Rectangle((roi["x"], roi["y"]), roi["width"], roi["height"], fill=False, edgecolor="lime", linewidth=1.5)
    ax.add_patch(rect)
    ax.axis("off")
    fig.tight_layout()
    return fig


def clamp_roi(x: int, y: int, width: int, height: int, shape: tuple[int, int]) -> dict:
    rows, cols = shape
    x = max(0, min(x, cols - 1))
    y = max(0, min(y, rows - 1))
    width = max(1, min(width, cols - x))
    height = max(1, min(height, rows - y))
    return {"x": x, "y": y, "width": width, "height": height}


def add_download_button(label: str, path_value) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if path.exists():
        with path.open("rb") as file:
            st.download_button(label, file, file_name=path.name)


def plane_default_index(info: dict) -> int:
    plane = str(info.get("Plane", "axial")).lower()
    if plane == "sagittal":
        return 1
    if plane == "coronal":
        return 2
    return 0


def format_series_label(item: dict) -> str:
    date = item.get("study_date") or "Unknown date"
    description = item.get("description") or "Unknown series"
    count = item.get("file_count", 0)
    shape = item.get("shape") or "unknown shape"
    return f"{date} | {description} | {count} files | {shape}"


if __name__ == "__main__":
    main()
