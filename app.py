from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from utils.dicom_loader import load_dicom_volume
from utils.report import create_viewer_report
from utils.skull_strip import brain_only_slice
from utils.tumor_analysis import calculate_mask_area_mm2, find_bright_candidate_mask


st.set_page_config(page_title="Brain MRI Viewer", layout="wide")


def main() -> None:
    st.title("Brain MRI Viewer")
    st.caption("DICOM 뇌 MRI 폴더를 불러와 axial slice를 확인하는 간단한 뷰어입니다.")
    st.warning("진단 목적이 아닌 개인 확인용 뷰어입니다. 종양 판정은 반드시 의료진 판독을 따라야 합니다.")

    folder_path = st.text_input("DICOM 폴더 경로", placeholder=r"C:\path\to\brain_mri_dicoms")
    if st.button("불러오기", type="primary"):
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

    show_viewer(st.session_state["volume"], st.session_state["info"])


def show_viewer(volume: np.ndarray, info: dict) -> None:
    total_slices = volume.shape[0]
    left, right = st.columns([1, 2])

    with left:
        st.metric("Slices", total_slices)
        st.write(f"StudyDate: `{info.get('StudyDate', 'Unknown')}`")
        st.write(f"Series: `{info.get('SeriesDescription', 'Unknown')}`")
        st.write(f"PixelSpacing: `{info.get('PixelSpacing', 'Unknown')}`")

        slice_index = st.slider("Axial slice", 0, total_slices - 1, total_slices // 2)
        brain_only = st.checkbox("뇌만 보기", value=True)
        strip_strength = st.slider("두개골 제거 강도", 0, 10, 4)

        st.divider()
        tumor_enabled = st.checkbox("종양 의심 후보 표시", value=False)
        tumor_percentile = st.slider("후보 밝기 기준(상위 %)", 80, 99, 95)
        min_area_px = st.slider("최소 후보 크기(px)", 10, 1000, 80)

        current = volume[slice_index]
        default_level = float(np.mean(current))
        window_range = float(max(np.max(volume) - np.min(volume), 1.0))
        default_width = min(float(max(np.std(current) * 4, 1.0)), window_range)
        level = st.slider("Window level", float(np.min(volume)), float(np.max(volume)), default_level)
        width = st.slider("Window width", 1.0, window_range, default_width)

    raw_slice = volume[slice_index]
    display_slice = brain_only_slice(raw_slice, erode_pixels=strip_strength) if brain_only else raw_slice

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
            st.metric("후보 영역 면적", f"{tumor_area_mm2:.2f} mm²")
            st.caption("밝기 기반 후보 표시입니다. 종양 진단이나 자동 판독이 아닙니다.")

    with left:
        if st.button("PDF 리포트 생성"):
            report_path = create_viewer_report(
                info=info,
                slice_index=slice_index,
                brain_only=brain_only,
                tumor_enabled=tumor_enabled,
                tumor_area_mm2=tumor_area_mm2,
            )
            st.success(f"PDF 생성 완료: {report_path}")
            with report_path.open("rb") as file:
                st.download_button("PDF 다운로드", file, report_path.name, "application/pdf")

    with right:
        image = apply_window(display_slice, level, width)
        st.pyplot(
            draw_slice(image, slice_index, total_slices, brain_only, tumor_mask),
            clear_figure=True,
        )


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    low = level - width / 2
    high = level + width / 2
    if high <= low:
        high = low + 1
    image = np.clip(image, low, high)
    return (image - low) / (high - low)


def draw_slice(
    image: np.ndarray,
    slice_index: int,
    total_slices: int,
    brain_only: bool,
    tumor_mask: np.ndarray | None,
):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    if tumor_mask is not None and np.any(tumor_mask):
        ax.contour(tumor_mask, colors=["red"], linewidths=1.5)
    suffix = "brain only" if brain_only else "original"
    ax.set_title(f"Axial slice {slice_index + 1} / {total_slices} ({suffix})")
    ax.axis("off")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()

