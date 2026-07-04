from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table


REPORT_DIR = Path("data/reports")
DISCLAIMER = "This viewer is not for diagnosis. Candidate regions are only visual aids. Final medical decisions must follow a clinician's interpretation."


def create_viewer_report(
    info: dict,
    slice_index: int,
    brain_only: bool,
    tumor_enabled: bool = False,
    tumor_area_mm2: float = 0.0,
) -> Path:
    """Create a minimal PDF report under data/reports."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"brain_mri_viewer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    styles = getSampleStyleSheet()
    rows = [
        ["StudyDate", str(info.get("StudyDate", "Unknown"))],
        ["SeriesDescription", str(info.get("SeriesDescription", "Unknown"))],
        ["Slice index", str(slice_index)],
        ["Brain-only view", "On" if brain_only else "Off"],
        ["PixelSpacing", str(info.get("PixelSpacing", "Unknown"))],
        ["SliceThickness", str(info.get("SliceThickness", "Unknown"))],
        ["Volume shape", str(info.get("Shape", "Unknown"))],
        ["Tumor candidate overlay", "On" if tumor_enabled else "Off"],
        ["Candidate area", f"{tumor_area_mm2:.2f} mm2"],
    ]

    story = [
        Paragraph("Brain MRI Viewer Report", styles["Title"]),
        Spacer(1, 12),
        Table(rows, colWidths=[130, 340]),
        Spacer(1, 16),
        Paragraph(DISCLAIMER, styles["BodyText"]),
    ]
    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)
    return output_path
