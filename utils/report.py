from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table


REPORT_DIR = Path("data/reports")
DISCLAIMER = "This viewer is not for diagnosis. Candidate regions and ROI measurements are visual aids only."


def create_viewer_report(
    info: dict,
    slice_index: int,
    roi: dict,
    roi_area_mm2: float,
    roi_volume_mm3: float,
    roi_volume_ml: float,
    brain_only: bool = False,
    tumor_enabled: bool = False,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"brain_mri_viewer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    styles = getSampleStyleSheet()
    rows = [
        ["StudyDate", str(info.get("StudyDate", "Unknown"))],
        ["SeriesDescription", str(info.get("SeriesDescription", "Unknown"))],
        ["Slice index", str(slice_index)],
        ["PixelSpacing", str(info.get("PixelSpacing", "Unknown"))],
        ["SliceThickness", str(info.get("SliceThickness", "Unknown"))],
        ["ROI", f"x={roi['x']}, y={roi['y']}, width={roi['width']}, height={roi['height']}"],
        ["ROI area", f"{roi_area_mm2:.2f} mm2"],
        ["Estimated ROI volume", f"{roi_volume_mm3:.2f} mm3 / {roi_volume_ml:.3f} ml"],
        ["Brain-only display", "On" if brain_only else "Off"],
        ["Tumor candidate overlay", "On" if tumor_enabled else "Off"],
    ]

    story = [
        Paragraph("AIDLC-MRI 2D Viewer Report", styles["Title"]),
        Spacer(1, 12),
        Table(rows, colWidths=[150, 330]),
        Spacer(1, 16),
        Paragraph(DISCLAIMER, styles["BodyText"]),
    ]
    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)
    return output_path

