from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import streamlit as st

from src.compare import compare_mri_results
from src.dicom_loader import load_dicom_volume, public_metadata
from src.report import create_pdf_report
from src.volume import calculate_volume_from_slice_areas


REPORT_DIR = Path("data/reports")


st.set_page_config(page_title="AIDLC-MRI", layout="wide")


def main() -> None:
    st.title("AIDLC-MRI")
    st.caption("진단 목적이 아닌 MRI 분석 보조 및 추적 관리 MVP입니다. 환자 개인정보는 화면에 직접 표시하지 않습니다.")

    folder_path = st.text_input("DICOM 폴더 경로", placeholder=r"C:\path\to\dicom_folder")
    if st.button("MRI volume 불러오기", type="primary"):
        load_volume(folder_path)

    if "volume" not in st.session_state:
        st.info("DICOM 폴더 경로를 입력한 뒤 MRI volume을 불러오세요.")
        return

    render_viewer(st.session_state["volume"], st.session_state["metadata"])


def load_volume(folder_path: str) -> None:
    if not folder_path.strip():
        st.warning("DICOM 폴더 경로를 입력해주세요.")
        return

    try:
        with st.spinner("DICOM 파일을 읽고 3D volume을 생성하는 중입니다..."):
            volume, metadata = load_dicom_volume(folder_path)
        st.session_state["volume"] = volume
        st.session_state["metadata"] = metadata
        st.success("MRI volume을 불러왔습니다.")
    except Exception as exc:
        st.error(f"로드 실패: {exc}")


def render_viewer(volume, metadata: dict) -> None:
    total_slices = volume.shape[0]
    safe_metadata = public_metadata(metadata)

    st.subheader("Axial Slice Viewer")
    meta_cols = st.columns(4)
    meta_cols[0].metric("Total slices", total_slices)
    meta_cols[1].metric("StudyDate", safe_metadata.get("StudyDate", "Unknown"))
    meta_cols[2].metric("SliceThickness", f"{safe_metadata.get('SliceThickness', 1.0)} mm")
    meta_cols[3].metric("PixelSpacing", str(safe_metadata.get("PixelSpacing", "Unknown")))

    control_col, image_col = st.columns([0.95, 1.4], gap="large")
    with control_col:
        slice_index = st.slider("Axial slice index", 0, total_slices - 1, total_slices // 2)
        current_slice = volume[slice_index]
        window_level, window_width = window_controls(volume, current_slice)
        st.write(f"현재 slice index: **{slice_index}**")
        st.write(f"전체 slice 수: **{total_slices}**")
        st.write(f"SeriesDescription: `{safe_metadata.get('SeriesDescription', 'Unknown')}`")
        roi_result = roi_controls(current_slice.shape, metadata)
        change_summary = comparison_controls(metadata, roi_result["volume_cm3"])
        report_controls(metadata, roi_result, change_summary)

    with image_col:
        windowed = apply_window(volume[slice_index], window_level, window_width)
        st.pyplot(draw_slice(windowed, slice_index, total_slices, roi_result["box"]), clear_figure=True)


def window_controls(volume, current_slice) -> tuple[float, float]:
    default_level = float(current_slice.mean())
    window_range = float(max(volume.max() - volume.min(), 1.0))
    default_width = min(float(max(current_slice.std() * 4, 1.0)), window_range)
    window_level = st.slider("Window level", float(volume.min()), float(volume.max()), default_level)
    window_width = st.slider("Window width", 1.0, window_range, default_width)
    return window_level, window_width


def roi_controls(image_shape: tuple[int, int], metadata: dict) -> dict:
    st.markdown("#### 사각형 ROI")
    height, width = image_shape
    enabled = st.checkbox("ROI 표시 및 계산", value=True)
    if not enabled:
        return {"box": None, "area_mm2": 0.0, "volume_mm3": 0.0, "volume_cm3": 0.0}

    col1, col2 = st.columns(2)
    x1 = col1.number_input("x1", min_value=0, max_value=width - 1, value=max(width // 3, 0), step=1)
    y1 = col2.number_input("y1", min_value=0, max_value=height - 1, value=max(height // 3, 0), step=1)
    x2 = col1.number_input("x2", min_value=0, max_value=width - 1, value=min(width * 2 // 3, width - 1), step=1)
    y2 = col2.number_input("y2", min_value=0, max_value=height - 1, value=min(height * 2 // 3, height - 1), step=1)

    box = normalize_roi_box(int(x1), int(y1), int(x2), int(y2))
    area_mm2 = calculate_roi_area_mm2(box, metadata["PixelSpacing"])
    volume = calculate_volume_from_slice_areas([area_mm2], float(metadata["SliceThickness"]))

    st.metric("ROI 면적", f"{area_mm2:.2f} mm²")
    st.metric("추정 부피", f"{volume['volume_cm3']:.3f} cm³")
    return {"box": box, "area_mm2": area_mm2, **volume}


def comparison_controls(metadata: dict, current_volume_cm3: float) -> dict | None:
    st.markdown("#### 이전 검사 비교")
    enabled = st.checkbox("이전 검사 대비 변화율 계산")
    if not enabled:
        return None

    previous_date = st.text_input("이전 검사 날짜", value="")
    current_date = st.text_input("현재 검사 날짜", value=str(metadata.get("StudyDate", date.today().isoformat())))
    previous_volume_cm3 = st.number_input("이전 검사 부피(cm³)", min_value=0.0, value=0.0, step=0.1)
    current_volume_input = st.number_input("현재 검사 부피(cm³)", min_value=0.0, value=float(current_volume_cm3), step=0.1)

    summary = compare_mri_results(previous_date, current_date, previous_volume_cm3, current_volume_input)
    st.metric("변화량", f"{summary['change_cm3']:+.3f} cm³")
    change_percent = summary["change_percent"]
    st.metric("변화율", "계산 불가" if change_percent is None else f"{change_percent:+.2f}%")
    st.metric("판정", summary["status"])
    return summary


def report_controls(metadata: dict, roi_result: dict, change_summary: dict | None) -> None:
    st.markdown("#### PDF 리포트")
    if st.button("PDF 리포트 생성", use_container_width=True):
        output_path = REPORT_DIR / "aidlc_mri_report.pdf"
        report_path = create_pdf_report(
            output_path=output_path,
            study_date=str(metadata.get("StudyDate", "Unknown")),
            series_description=str(metadata.get("SeriesDescription", "Unknown")),
            roi_area_mm2=float(roi_result["area_mm2"]),
            estimated_volume_cm3=float(roi_result["volume_cm3"]),
            change_summary=change_summary,
        )
        st.success(f"PDF 리포트가 생성되었습니다: {report_path}")
        with report_path.open("rb") as file:
            st.download_button(
                "PDF 다운로드",
                data=file,
                file_name=report_path.name,
                mime="application/pdf",
                use_container_width=True,
            )


def apply_window(image, level: float, width: float):
    low = level - width / 2.0
    high = level + width / 2.0
    if high <= low:
        high = low + 1.0
    clipped = image.clip(low, high)
    return (clipped - low) / (high - low)


def normalize_roi_box(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    return left, top, right, bottom


def calculate_roi_area_mm2(roi_box: tuple[int, int, int, int], pixel_spacing: list[float]) -> float:
    x1, y1, x2, y2 = roi_box
    row_spacing_mm, col_spacing_mm = pixel_spacing
    width_px = abs(x2 - x1)
    height_px = abs(y2 - y1)
    return float(width_px * height_px * row_spacing_mm * col_spacing_mm)


def draw_slice(image, slice_index: int, total_slices: int, roi_box=None):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if roi_box:
        x1, y1, x2, y2 = roi_box
        rect = Rectangle((x1, y1), x2 - x1, y2 - y1, linewidth=2, edgecolor="red", facecolor="none")
        ax.add_patch(rect)
    ax.set_title(f"Axial slice {slice_index + 1} / {total_slices}")
    ax.axis("off")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()

