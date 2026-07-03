from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import streamlit as st

from utils.change_analysis import analyze_volume_change
from utils.dicom_loader import load_dicom_series
from utils.report import MEDICAL_DISCLAIMER, generate_pdf_report
from utils.roi import RectROI, calculate_estimated_volume, calculate_roi_area_mm2, clamp_roi


REPORT_DIR = Path("data/reports")


st.set_page_config(page_title="AIDLC-MRI", layout="wide")


def main() -> None:
    st.title("AIDLC-MRI")
    st.warning(MEDICAL_DISCLAIMER)

    folder_path = st.text_input("DICOM 폴더 경로", placeholder=r"C:\path\to\dicom_folder")
    if st.button("DICOM MRI 불러오기", type="primary"):
        load_series(folder_path)

    if "volume" not in st.session_state:
        st.info("DICOM 폴더 경로를 입력한 뒤 MRI 데이터를 불러오세요.")
        return

    render_viewer(st.session_state["volume"], st.session_state["metadata"])


def load_series(folder_path: str) -> None:
    """Load DICOM data and store it in Streamlit session state."""
    if not folder_path.strip():
        st.error("DICOM 폴더 경로를 입력해주세요.")
        return

    try:
        with st.spinner("DICOM 파일을 재귀 탐색하고 3D volume으로 변환하는 중입니다..."):
            series = load_dicom_series(folder_path)
        st.session_state["volume"] = series.volume
        st.session_state["metadata"] = series.metadata
        st.success("DICOM MRI volume을 불러왔습니다.")
    except Exception as exc:
        st.error(f"DICOM 로딩 실패: {exc}")


def render_viewer(volume: np.ndarray, metadata: dict) -> None:
    """Render axial viewer, ROI controls, change analysis, and PDF export."""
    total_slices = volume.shape[0]
    slice_thickness = float(metadata["SliceThickness"])
    pixel_spacing = metadata["PixelSpacing"]

    st.subheader("Axial Slice Viewer")
    cols = st.columns(4)
    cols[0].metric("전체 slice 수", total_slices)
    cols[1].metric("StudyDate", metadata.get("StudyDate", "Unknown"))
    cols[2].metric("SliceThickness", f"{slice_thickness:.3f} mm")
    cols[3].metric("PixelSpacing", f"{pixel_spacing[0]:.3f}, {pixel_spacing[1]:.3f} mm")
    st.caption(f"SeriesDescription: {metadata.get('SeriesDescription', 'Unknown')}")

    control_col, image_col = st.columns([0.95, 1.35], gap="large")
    with control_col:
        slice_index = st.slider("Axial slice index", 0, total_slices - 1, total_slices // 2)
        current_slice = volume[slice_index]
        level, width = window_controls(volume, current_slice)

        roi = roi_controls(current_slice.shape)
        roi_area_mm2 = calculate_roi_area_mm2(roi, pixel_spacing)
        area_list = area_list_controls(roi_area_mm2)
        volume_result = calculate_estimated_volume(area_list, slice_thickness)

        st.metric("현재 ROI 면적", f"{roi_area_mm2:.2f} mm²")
        st.metric("추정 부피", f"{volume_result['volume_mm3']:.2f} mm³ / {volume_result['volume_ml']:.3f} ml")
        change_result = change_controls(volume_result["volume_ml"])
        report_controls(metadata, slice_index, roi_area_mm2, volume_result, change_result)

    with image_col:
        windowed = apply_window(current_slice, level, width)
        st.pyplot(draw_slice(windowed, roi, slice_index, total_slices), clear_figure=True)
        st.caption(f"현재 slice index: {slice_index} / 전체 slice 수: {total_slices}")


def window_controls(volume: np.ndarray, current_slice: np.ndarray) -> tuple[float, float]:
    """Create window level and window width controls."""
    volume_min = float(np.min(volume))
    volume_max = float(np.max(volume))
    window_range = max(volume_max - volume_min, 1.0)
    default_level = float(np.mean(current_slice))
    default_width = min(max(float(np.std(current_slice) * 4), 1.0), window_range)

    level = st.slider("Window Level", volume_min, volume_max, default_level)
    width = st.slider("Window Width", 1.0, window_range, default_width)
    return level, width


def roi_controls(image_shape: tuple[int, int]) -> RectROI:
    """Create x, y, width, height rectangle ROI controls."""
    st.markdown("#### 수동 사각형 ROI")
    image_height, image_width = image_shape
    col1, col2 = st.columns(2)
    x = col1.number_input("x", min_value=0, max_value=image_width - 1, value=image_width // 3, step=1)
    y = col2.number_input("y", min_value=0, max_value=image_height - 1, value=image_height // 3, step=1)
    width = col1.number_input("width", min_value=1, max_value=image_width, value=max(image_width // 4, 1), step=1)
    height = col2.number_input("height", min_value=1, max_value=image_height, value=max(image_height // 4, 1), step=1)
    return clamp_roi(RectROI(int(x), int(y), int(width), int(height)), image_width, image_height)


def area_list_controls(default_area_mm2: float) -> list[float]:
    """Allow a multi-slice area list while keeping current slice area as default."""
    st.markdown("#### 여러 slice ROI 면적")
    area_text = st.text_area(
        "slice별 ROI 면적(mm²), 한 줄에 하나씩",
        value=f"{default_area_mm2:.2f}",
        height=90,
    )
    try:
        values = [float(line.strip()) for line in area_text.splitlines() if line.strip()]
        if not values:
            return [0.0]
        if any(value < 0 for value in values):
            raise ValueError
        return values
    except ValueError:
        st.error("ROI 면적 리스트는 0 이상의 숫자만 입력할 수 있습니다.")
        return [default_area_mm2]


def change_controls(current_volume_ml: float) -> dict | None:
    """Compare previous and current ROI volumes."""
    st.markdown("#### 이전 검사 대비 변화 분석")
    enabled = st.checkbox("변화량/변화율 계산")
    if not enabled:
        return None

    previous_volume_ml = st.number_input("이전 검사 부피(ml)", min_value=0.0, value=0.0, step=0.1)
    current_volume_input = st.number_input("현재 검사 부피(ml)", min_value=0.0, value=float(current_volume_ml), step=0.1)
    result = analyze_volume_change(previous_volume_ml, current_volume_input)

    percent_text = "계산 불가" if result["change_percent"] is None else f"{result['change_percent']:+.2f}%"
    st.metric("변화량", f"{result['change_ml']:+.3f} ml")
    st.metric("변화율", percent_text)
    st.metric("판정", result["status"])
    return result


def report_controls(
    metadata: dict,
    slice_index: int,
    roi_area_mm2: float,
    volume_result: dict,
    change_result: dict | None,
) -> None:
    """Generate and expose a PDF report download button."""
    st.markdown("#### PDF 리포트")
    if st.button("PDF 리포트 생성", use_container_width=True):
        report_path = REPORT_DIR / f"aidlc_mri_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        generated_path = generate_pdf_report(
            output_path=report_path,
            study_date=str(metadata.get("StudyDate", "Unknown")),
            series_description=str(metadata.get("SeriesDescription", "Unknown")),
            slice_index=slice_index,
            roi_area_mm2=roi_area_mm2,
            estimated_volume_mm3=volume_result["volume_mm3"],
            estimated_volume_ml=volume_result["volume_ml"],
            change_result=change_result,
        )
        st.success(f"PDF 리포트 생성 완료: {generated_path.name}")
        with generated_path.open("rb") as file:
            st.download_button("PDF 다운로드", file, generated_path.name, "application/pdf", use_container_width=True)


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    """Apply window level and width to an MRI slice."""
    low = level - width / 2.0
    high = level + width / 2.0
    if high <= low:
        high = low + 1.0
    clipped = np.clip(image, low, high)
    return (clipped - low) / (high - low)


def draw_slice(image: np.ndarray, roi: RectROI, slice_index: int, total_slices: int):
    """Draw current axial slice and red ROI rectangle."""
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    rect = Rectangle((roi.x, roi.y), roi.width, roi.height, linewidth=2, edgecolor="red", facecolor="none")
    ax.add_patch(rect)
    ax.set_title(f"Axial slice {slice_index + 1} / {total_slices}")
    ax.axis("off")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()

