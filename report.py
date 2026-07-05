from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table


REPORT_DIR = Path("outputs/reports")
DISCLAIMER = (
    "Viewer only. Not for diagnosis. This portfolio/MVP tool provides visual aids only. "
    "Final medical decisions must follow a clinician's interpretation."
)


def create_viewer_report(info: dict, slice_index: int, roi: dict | None = None, mesh_info: dict | None = None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"brain_mri_viewer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    rows = [
        ["StudyDate", str(info.get("StudyDate", "Unknown"))],
        ["SeriesDescription", str(info.get("SeriesDescription", "Unknown"))],
        ["Plane", str(info.get("Plane", "Unknown"))],
        ["Slice index", str(slice_index)],
        ["PixelSpacing", str(info.get("PixelSpacing", "Unknown"))],
        ["SliceThickness", str(info.get("SliceThickness", "Unknown"))],
        ["Volume shape", str(info.get("Shape", "Unknown"))],
    ]
    if roi is not None:
        rows.append(["ROI", f"x={roi['x']}, y={roi['y']}, width={roi['width']}, height={roi['height']}"])
    if mesh_info:
        rows.extend(
            [
                ["Raw brain mask", str(mesh_info.get("mask_path", ""))],
                ["Refined brain mask", str(mesh_info.get("refined_mask_path", ""))],
                ["Brain mesh", str(mesh_info.get("mesh_path", ""))],
            ]
        )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("AIDLC-MRI Viewer Report", styles["Title"]),
        Spacer(1, 12),
        Table(rows, colWidths=[130, 340]),
        Spacer(1, 16),
        Paragraph(DISCLAIMER, styles["BodyText"]),
    ]
    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)
    return output_path
