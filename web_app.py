from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from utils.dicom_loader import discover_dicom_series, load_dicom_volume
from utils.report import create_viewer_report


DATA_DIR = Path(r"C:\Users\user\Desktop\mri2\mri-project-main\data")
HOST = "127.0.0.1"
PORT = 8501

SERIES_CACHE: list[dict] | None = None
VOLUME_CACHE: dict[int, tuple[np.ndarray, dict]] = {}


def get_series() -> list[dict]:
    global SERIES_CACHE
    if SERIES_CACHE is None:
        SERIES_CACHE = discover_dicom_series(DATA_DIR)
    return SERIES_CACHE


def get_volume(index: int) -> tuple[np.ndarray, dict]:
    if index not in VOLUME_CACHE:
        series = get_series()
        VOLUME_CACHE[index] = load_dicom_volume(series[index]["paths"])
    return VOLUME_CACHE[index]


class MriHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/slice.png":
            self.serve_slice(parsed.query)
            return
        if parsed.path == "/report.pdf":
            self.serve_report(parsed.query)
            return
        self.serve_page(parsed.query)

    def serve_page(self, query: str) -> None:
        try:
            params = parse_qs(query)
            series = get_series()
            if not series:
                raise RuntimeError("No DICOM series found.")

            selected = clamp(to_int(params.get("series", ["0"])[0], 0), 0, len(series) - 1)
            volume, info = get_volume(selected)
            max_slice = int(volume.shape[0] - 1)
            slice_index = clamp(to_int(params.get("slice", [str(max_slice // 2)])[0], max_slice // 2), 0, max_slice)
            level, width = window_defaults(volume, slice_index, params)
            roi = roi_from_params(params, volume.shape[1:])
            roi_slices = roi_slices_from_params(params, max_slice + 1)
            body = render_page(series, selected, volume, info, slice_index, level, width, roi, roi_slices)
        except Exception as exc:
            body = render_error(exc)
        self.send_html(body)

    def serve_slice(self, query: str) -> None:
        params = parse_qs(query)
        series = get_series()
        selected = clamp(to_int(params.get("series", ["0"])[0], 0), 0, len(series) - 1)
        volume, info = get_volume(selected)
        max_slice = int(volume.shape[0] - 1)
        slice_index = clamp(to_int(params.get("slice", [str(max_slice // 2)])[0], max_slice // 2), 0, max_slice)
        level, width = window_defaults(volume, slice_index, params)
        roi = roi_from_params(params, volume.shape[1:])

        image = apply_window(volume[slice_index], level, width)
        png = draw_slice_png(image, slice_index, max_slice + 1, roi, str(info.get("Plane", "DICOM")).title())

        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def serve_report(self, query: str) -> None:
        params = parse_qs(query)
        series = get_series()
        selected = clamp(to_int(params.get("series", ["0"])[0], 0), 0, len(series) - 1)
        volume, info = get_volume(selected)
        max_slice = int(volume.shape[0] - 1)
        slice_index = clamp(to_int(params.get("slice", [str(max_slice // 2)])[0], max_slice // 2), 0, max_slice)
        roi = roi_from_params(params, volume.shape[1:])
        roi_slices = roi_slices_from_params(params, max_slice + 1)
        roi_area_mm2, roi_volume_mm3, roi_volume_ml = calculate_roi_metrics(roi, info, roi_slices)
        report_path = create_viewer_report(
            info=info,
            slice_index=slice_index,
            brain_only=False,
            tumor_enabled=False,
            tumor_area_mm2=0.0,
            roi=roi,
            roi_slices=roi_slices,
            roi_area_mm2=roi_area_mm2,
            roi_volume_mm3=roi_volume_mm3,
            roi_volume_ml=roi_volume_ml,
        )
        pdf = report_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
        self.send_header("Content-Length", str(len(pdf)))
        self.end_headers()
        self.wfile.write(pdf)

    def send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def render_page(
    series: list[dict],
    selected: int,
    volume: np.ndarray,
    info: dict,
    slice_index: int,
    level: float,
    width: float,
    roi: dict,
    roi_slices: int,
) -> str:
    options = "\n".join(
        f"<option value='{idx}' {'selected' if idx == selected else ''}>{escape(format_series_label(item))}</option>"
        for idx, item in enumerate(series)
    )
    max_slice = int(volume.shape[0] - 1)
    plane = str(info.get("Plane", "unknown"))
    plane_label = plane.title() if plane != "unknown" else "DICOM"
    roi_area_mm2, roi_volume_mm3, roi_volume_ml = calculate_roi_metrics(roi, info, roi_slices)
    query = roi_query(selected, slice_index, level, width, roi, roi_slices)
    image_url = f"/slice.png?{query}"
    report_url = f"/report.pdf?{query}"

    return page_shell(
        f"""
        <form class="toolbar" method="get">
          <label>Series
            <select name="series" onchange="this.form.submit()">{options}</select>
          </label>
          <label>{plane_label} slice
            <input name="slice" type="range" min="0" max="{max_slice}" value="{slice_index}" oninput="sliceValue.value=this.value">
            <output id="sliceValue">{slice_index}</output> / {max_slice}
          </label>
          <label>Window Level
            <input name="level" type="number" step="1" value="{level:.3f}">
          </label>
          <label>Window Width
            <input name="width" type="number" step="1" min="1" value="{width:.3f}">
          </label>
          <label>x<input name="x" type="number" min="0" value="{roi['x']}"></label>
          <label>y<input name="y" type="number" min="0" value="{roi['y']}"></label>
          <label>width<input name="roi_width" type="number" min="1" value="{roi['width']}"></label>
          <label>height<input name="roi_height" type="number" min="1" value="{roi['height']}"></label>
          <label>slices<input name="roi_slices" type="number" min="1" max="{max_slice + 1}" value="{roi_slices}"></label>
          <button type="submit">View</button>
        </form>
        <main>
          <section class="viewer">
            <img src="{image_url}" alt="{plane_label} MRI slice">
          </section>
          <section class="meta">
            <h2>Info</h2>
            <p><b>Mode</b><br>2D {escape(plane)} slice viewer</p>
            <p><b>Current slice</b><br>{slice_index + 1} / {max_slice + 1}</p>
            <p><b>StudyDate</b><br>{escape(str(info.get("StudyDate", "Unknown")))}</p>
            <p><b>Series</b><br>{escape(str(info.get("SeriesDescription", "Unknown")))}</p>
            <p><b>PixelSpacing</b><br>{escape(str(info.get("PixelSpacing", "Unknown")))}</p>
            <p><b>SliceThickness</b><br>{escape(str(info.get("SliceThickness", "Unknown")))}</p>
            <p><b>SpacingBetweenSlices</b><br>{escape(str(info.get("SpacingBetweenSlices", "Unknown")))}</p>
            <p><b>Volume shape</b><br>{escape(str(info.get("Shape", "Unknown")))}</p>
            <p><b>ROI area</b><br>{roi_area_mm2:.2f} mm2</p>
            <p><b>ROI volume</b><br>{roi_volume_mm3:.2f} mm3 / {roi_volume_ml:.4f} ml</p>
            <p><a class="download" href="{report_url}">Download PDF report</a></p>
            <p class="note">Viewer only. Not for diagnosis.</p>
          </section>
        </main>
        """
    )


def render_error(exc: Exception) -> str:
    return page_shell(
        f"""
        <main>
          <section class="error">
            <h2>Load failed</h2>
            <p>{escape(str(exc))}</p>
            <p>Data path: <code>{escape(str(DATA_DIR))}</code></p>
          </section>
        </main>
        """
    )


def page_shell(content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIDLC-MRI</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #1f2933; }}
    header {{ padding: 20px 28px; background: #fff; border-bottom: 1px solid #d8dde6; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    header p {{ margin: 0; color: #657287; }}
    .toolbar {{ display: grid; grid-template-columns: minmax(280px, 1fr) minmax(260px, 380px) repeat(7, minmax(92px, 140px)) auto; gap: 12px; align-items: end; padding: 16px 28px; background: #fff; border-bottom: 1px solid #d8dde6; }}
    label {{ font-size: 13px; color: #4b5563; }}
    select, input, button {{ width: 100%; box-sizing: border-box; margin-top: 6px; }}
    select, input, button {{ height: 36px; border: 1px solid #c8d0dc; border-radius: 6px; background: #fff; }}
    button, .download {{ padding: 0 18px; background: #0f766e; color: white; border-color: #0f766e; font-weight: 700; cursor: pointer; text-decoration: none; border-radius: 6px; display: inline-flex; align-items: center; height: 36px; }}
    main {{ display: grid; grid-template-columns: minmax(420px, 1fr) 310px; gap: 18px; padding: 18px 28px; }}
    .meta, .viewer, .error {{ background: #fff; border: 1px solid #d8dde6; border-radius: 8px; padding: 18px; }}
    .meta h2 {{ margin-top: 0; font-size: 18px; }}
    .meta p {{ line-height: 1.45; overflow-wrap: anywhere; }}
    .note {{ color: #b45309; }}
    .viewer {{ display: flex; justify-content: center; align-items: center; min-height: 70vh; }}
    .viewer img {{ max-width: 100%; max-height: 78vh; object-fit: contain; background: black; }}
    code {{ background: #eef2f7; padding: 2px 4px; border-radius: 4px; }}
    @media (max-width: 1100px) {{
      .toolbar, main {{ grid-template-columns: 1fr; }}
      .viewer {{ min-height: 42vh; }}
      .viewer img {{ max-height: 56vh; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>AIDLC-MRI</h1>
    <p>DICOM volume 2D slice viewer</p>
  </header>
  {content}
</body>
</html>"""


def format_series_label(item: dict) -> str:
    date = item.get("study_date") or "Unknown date"
    description = item.get("description") or "Unknown series"
    count = item.get("file_count", 0)
    shape = item.get("shape") or "unknown shape"
    return f"{date} | {description} | {count} files | {shape}"


def window_defaults(volume: np.ndarray, slice_index: int, params: dict) -> tuple[float, float]:
    current = volume[slice_index]
    default_level = float(np.mean(current))
    width_max = float(max(np.max(volume) - np.min(volume), 1.0))
    default_width = min(float(max(np.std(current) * 4.0, 1.0)), width_max)
    level = to_float(params.get("level", [str(default_level)])[0], default_level)
    width = max(1.0, to_float(params.get("width", [str(default_width)])[0], default_width))
    return level, width


def apply_window(image: np.ndarray, level: float, width: float) -> np.ndarray:
    low = level - width / 2.0
    high = level + width / 2.0
    if high <= low:
        high = low + 1.0
    clipped = np.clip(image, low, high)
    return (clipped - low) / (high - low)


def draw_slice_png(image: np.ndarray, slice_index: int, total_slices: int, roi: dict, plane_label: str) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1)
    rect = plt.Rectangle(
        (roi["x"], roi["y"]),
        roi["width"],
        roi["height"],
        fill=False,
        edgecolor="lime",
        linewidth=1.5,
    )
    ax.add_patch(rect)
    ax.set_title(f"{plane_label} slice {slice_index + 1} / {total_slices}")
    ax.axis("off")
    fig.tight_layout(pad=0)
    output = BytesIO()
    fig.savefig(output, format="png", dpi=120, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return output.getvalue()


def roi_from_params(params: dict, shape: tuple[int, int]) -> dict:
    rows, cols = shape
    roi = {
        "x": to_int(params.get("x", [str(cols // 4)])[0], cols // 4),
        "y": to_int(params.get("y", [str(rows // 4)])[0], rows // 4),
        "width": to_int(params.get("roi_width", [str(cols // 4)])[0], cols // 4),
        "height": to_int(params.get("roi_height", [str(rows // 4)])[0], rows // 4),
    }
    roi["x"] = clamp(roi["x"], 0, cols - 1)
    roi["y"] = clamp(roi["y"], 0, rows - 1)
    roi["width"] = clamp(roi["width"], 1, cols - roi["x"])
    roi["height"] = clamp(roi["height"], 1, rows - roi["y"])
    return roi


def roi_slices_from_params(params: dict, max_slices: int) -> int:
    return clamp(to_int(params.get("roi_slices", ["1"])[0], 1), 1, max_slices)


def calculate_roi_metrics(roi: dict, info: dict, roi_slices: int) -> tuple[float, float, float]:
    spacing = info.get("PixelSpacing", [1.0, 1.0])
    try:
        row_spacing, col_spacing = float(spacing[0]), float(spacing[1])
    except Exception:
        row_spacing, col_spacing = 1.0, 1.0
    try:
        slice_spacing = float(info.get("SliceSpacing") or info.get("SpacingBetweenSlices") or info.get("SliceThickness", 1.0))
    except Exception:
        slice_spacing = 1.0
    area = float(roi["width"] * roi["height"] * row_spacing * col_spacing)
    volume = float(area * slice_spacing * max(1, roi_slices))
    return area, volume, volume / 1000.0


def roi_query(series: int, slice_index: int, level: float, width: float, roi: dict, roi_slices: int) -> str:
    return (
        f"series={series}&slice={slice_index}&level={level:.6f}&width={width:.6f}"
        f"&x={roi['x']}&y={roi['y']}&roi_width={roi['width']}&roi_height={roi['height']}"
        f"&roi_slices={roi_slices}"
    )


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def to_int(value: str, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), MriHandler)
    print(f"Serving AIDLC-MRI at http://{HOST}:{PORT}")
    print(f"Data path: {DATA_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
