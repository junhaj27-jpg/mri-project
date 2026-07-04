from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from utils.dicom_loader import load_dicom_volume


st.set_page_config(page_title="Brain MRI Viewer", layout="wide")


def main() -> None:
    st.title("Brain MRI Viewer")
    st.caption("DICOM 뇌 MRI 폴더를 불러와 axial slice만 확인하는 간단한 뷰어입니다.")

    folder_path = st.text_input("DICOM 폴더 경로", placeholder=r"C:\path\to\brain_mri_dicoms")
    if st.button("불러오기", type="primary"):
        try:
            volume, info = load_dicom_volume(folder_path)
            st.session_state["volume"] = volume
            st.session_state["info"] = info
            st.success("DICOM MRI를 불러왔습니다.")
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
        slice_index = st.slider("Axial slice", 0, total_slices - 1, total_slices // 2)

        current = volume[slice_index]
        default_level = float(np.mean(current))
        window_range = float(max(np.max(volume) - np.min(volume), 1.0))
        default_width = min(float(max(np.std(current) * 4, 1.0)), window_range)
        level = st.slider("Window level", float(np.min(volume)), float(np.max(volume)), default_level)
        width = st.slider("Window width", 1.0, window_range, default_width)

    with right:
        image = apply_window(volume[slice_index], level, width)
        st.pyplot(draw_slice(image, slice_index, total_slices), clear_figure=True)


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    low = level - width / 2
    high = level + width / 2
    if high <= low:
        high = low + 1
    image = np.clip(image, low, high)
    return (image - low) / (high - low)


def draw_slice(image: np.ndarray, slice_index: int, total_slices: int):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    ax.set_title(f"Axial slice {slice_index + 1} / {total_slices}")
    ax.axis("off")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    main()
