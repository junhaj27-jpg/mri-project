from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import streamlit as st

from utils.dicom_loader import load_dicom_volume
from utils.report import create_viewer_report
from utils.skull_strip import brain_only_slice
from utils.tumor_analysis import calculate_mask_area_mm2, find_bright_candidate_mask


st.set_page_config(page_title="AIDLC-MRI 2D Viewer", layout="wide")


def main() -> None:
    clear_old_3d_query_params()
    st.title("AIDLC-MRI 2D Viewer")
    st.caption("DICOM MRI volume의 axial 2D slice를 grayscale로 확인하는 MVP입니다.")
    st.warning("진단 목적이 아닌 분석 보조/개인 확인용 뷰어입니다. 최종 의학적 판단은 의료진 판독을 따르세요.")

    folder_path = st.text_input("DICOM 폴더 경로", placeholder=r"C:\path\to\brain_mri_dicoms")
    if st.button("DICOM 불러오기", type="primary"):
        try:
            volume, info = load_dicom_volume(folder_path)
            st.session_state["volume"] = volume
            st.session_state["info"] = info
            st.success("DICOM MRI를 불러왔습니다.")
            if info.get("SkippedFiles", 0):
                st.info(f"PixelData가 없거나 읽을 수 없어 건너뛴 파일: {info['SkippedFiles']}개")
        except Exception as exc:
            st.error(f"로드 실패: {exc}")

    if "volume" not in st.session_state:
        st.info("DICOM 폴더 경로를 입력하고 불러오기를 누르세요.")
        return

    show_axial_viewer(st.session_state["volume"], st.session_state["info"])


def clear_old_3d_query_params() -> None:
    """Remove stale query params from older 3D/threshold experiments."""
    try:
        stale_keys = {"mode", "threshold", "azim", "tilt"}
        if any(key in st.query_params for key in stale_keys):
            st.query_params.clear()
    except Exception:
        pass


def show_axial_viewer(volume: np.ndarray, info: dict) -> None:
    total_slices = int(volume.shape[0])
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.subheader("2D Axial Slice")
        st.metric("Slices", total_slices)
        st.write(f"StudyDate: `{info.get('StudyDate', 'Unknown')}`")
        st.write(f"Series: `{info.get('SeriesDescription', 'Unknown')}`")
        st.write(f"PixelSpacing: `{info.get('PixelSpacing', [1.0, 1.0])}`")
        st.write(f"SliceThickness: `{info.get('SliceThickness', 1.0)}`")

        slice_index = st.slider("Slice index", 0, total_slices - 1, total_slices // 2)
        raw_slice = volume[slice_index]

        level, width = window_controls(volume, raw_slice)
        roi = roi_controls(raw_slice.shape)
        roi_area_mm2, roi_volume_mm3, roi_volume_ml = roi_measurements(roi, info)
        st.metric("ROI area", f"{roi_area_mm2:.2f} mm²")
        st.metric("Estimated volume", f"{roi_volume_mm3:.2f} mm³ / {roi_volume_ml:.3f} ml")

        with st.expander("Advanced display options", expanded=False):
            brain_only = st.checkbox("뇌만 보기(표시용)", value=False)
            strip_strength = st.slider("두개골 제거 강도", 0, 10, 4)
            tumor_enabled = st.checkbox("종양 의심 후보 표시(보조)", value=False)
            tumor_percentile = st.slider("후보 밝기 기준(상위 %)", 80, 99, 95)
            min_area_px = st.slider("최소 후보 크기(px)", 10, 1000, 80)

        if st.button("PDF 리포트 생성"):
            report_path = create_viewer_report(
                info=info,
                slice_index=slice_index,
                roi=roi,
                roi_area_mm2=roi_area_mm2,
                roi_volume_mm3=roi_volume_mm3,
                roi_volume_ml=roi_volume_ml,
                brain_only=brain_only,
                tumor_enabled=tumor_enabled,
            )
            st.success(f"PDF 생성 완료: {report_path}")
            with report_path.open("rb") as file:
                st.download_button("PDF 다운로드", file, report_path.name, "application/pdf")

    display_slice = raw_slice
    if brain_only:
        display_slice = brain_only_slice(display_slice, erode_pixels=strip_strength)

    tumor_mask = None
    tumor_area_mm2 = 0.0
    if tumor_enabled:
        tumor_mask = find_bright_candidate_mask(
            display_slice,
            percentile=float(tumor_percentile),
            min_area_px=int(min_area_px),
        )
        tumor_area_mm2 = calculate_mask_area_mm2(tumor_mask, info.get("PixelSpacing", [1.0, 1.0]))

    with left:
        if tumor_enabled:
            st.metric("Candidate area", f"{tumor_area_mm2:.2f} mm²")
            st.caption("밝기 기반 후보 표시이며 종양 진단 또는 자동 판독이 아닙니다.")

    with right:
        image = apply_window(display_slice, level, width)
        st.pyplot(
            draw_axial_slice(image, slice_index, total_slices, roi, tumor_mask),
            clear_figure=True,
        )


def window_controls(volume: np.ndarray, current_slice: np.ndarray) -> tuple[float, float]:
    volume_min = float(np.min(volume))
    volume_max = float(np.max(volume))
    window_range = float(max(volume_max - volume_min, 1.0))
    default_level = float(np.mean(current_slice))
    default_width = min(float(max(np.std(current_slice) * 4, 1.0)), window_range)
    level = st.slider("Window Level", volume_min, volume_max, default_level)
    width = st.slider("Window Width", 1.0, window_range, default_width)
    return level, width


def roi_controls(image_shape: tuple[int, int]) -> dict:
    image_height, image_width = image_shape
    st.subheader("ROI")
    col1, col2 = st.columns(2)
    x = col1.number_input("x", min_value=0, max_value=image_width - 1, value=image_width // 3, step=1)
    y = col2.number_input("y", min_value=0, max_value=image_height - 1, value=image_height // 3, step=1)
    width = col1.number_input("width", min_value=1, max_value=image_width, value=max(image_width // 4, 1), step=1)
    height = col2.number_input("height", min_value=1, max_value=image_height, value=max(image_height // 4, 1), step=1)

    x = int(x)
    y = int(y)
    width = min(int(width), image_width - x)
    height = min(int(height), image_height - y)
    return {"x": x, "y": y, "width": width, "height": height}


def roi_measurements(roi: dict, info: dict) -> tuple[float, float, float]:
    pixel_spacing = info.get("PixelSpacing", [1.0, 1.0])
    try:
        row_spacing = float(pixel_spacing[0])
        col_spacing = float(pixel_spacing[1])
    except Exception:
        row_spacing = 1.0
        col_spacing = 1.0
    try:
        slice_thickness = float(info.get("SliceThickness", 1.0))
    except Exception:
        slice_thickness = 1.0

    area_mm2 = float(roi["width"] * roi["height"] * row_spacing * col_spacing)
    volume_mm3 = float(area_mm2 * slice_thickness)
    volume_ml = volume_mm3 / 1000.0
    return area_mm2, volume_mm3, volume_ml


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    low = level - width / 2.0
    high = level + width / 2.0
    if high <= low:
        high = low + 1.0
    clipped = np.clip(image, low, high)
    return (clipped - low) / (high - low)


def draw_axial_slice(
    image: np.ndarray,
    slice_index: int,
    total_slices: int,
    roi: dict,
    tumor_mask: np.ndarray | None,
):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    ax.add_patch(
        Rectangle(
            (roi["x"], roi["y"]),
            roi["width"],
            roi["height"],
            linewidth=1.8,
            edgecolor="yellow",
            facecolor="none",
        )
    )
    if tumor_mask is not None and np.any(tumor_mask):
        ax.contour(tumor_mask, colors=["red"], linewidths=1.5)
    ax.set_title(f"Axial slice {slice_index + 1} / {total_slices}")
    ax.axis("off")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()

