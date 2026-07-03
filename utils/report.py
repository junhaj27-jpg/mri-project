from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


MEDICAL_DISCLAIMER = (
    "본 리포트는 진단 목적이 아닌 MRI 분석 보조 및 추적 관리를 위한 참고 자료입니다. "
    "최종 의학적 판단은 담당 의료진의 판독을 따라야 합니다."
)


def generate_pdf_report(
    output_path: str | Path,
    study_date: str,
    series_description: str,
    slice_index: int,
    roi_area_mm2: float,
    estimated_volume_mm3: float,
    estimated_volume_ml: float,
    change_result: dict | None,
) -> Path:
    """Generate a compact PDF report with reportlab."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    font_name = register_korean_font()
    styles = build_styles(font_name)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, title="AIDLC-MRI Report")

    rows = [
        ["검사 날짜", study_date],
        ["SeriesDescription", series_description],
        ["Axial slice index", str(slice_index)],
        ["ROI 면적", f"{roi_area_mm2:.2f} mm²"],
        ["추정 부피", f"{estimated_volume_mm3:.2f} mm³ / {estimated_volume_ml:.3f} ml"],
    ]
    if change_result is not None:
        percent = change_result["change_percent"]
        percent_text = "계산 불가" if percent is None else f"{percent:+.2f}%"
        rows.extend(
            [
                ["이전 검사 부피", f"{change_result['previous_volume_ml']:.3f} ml"],
                ["현재 검사 부피", f"{change_result['current_volume_ml']:.3f} ml"],
                ["변화량", f"{change_result['change_ml']:+.3f} ml"],
                ["변화율", percent_text],
                ["판정", change_result["status"]],
            ]
        )

    table = Table(rows, colWidths=[145, 345])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story = [
        Paragraph("AIDLC-MRI 리포트", styles["TitleKo"]),
        Spacer(1, 8),
        Paragraph("진단 목적이 아닌 MRI 분석 보조 및 추적 관리 참고 자료", styles["BodyKo"]),
        Spacer(1, 14),
        table,
        Spacer(1, 18),
        Paragraph("의료적 주의사항", styles["HeadingKo"]),
        Paragraph(MEDICAL_DISCLAIMER, styles["BodyKo"]),
        Spacer(1, 8),
        Paragraph(f"생성 시각: {datetime.now().isoformat(timespec='seconds')}", styles["SmallKo"]),
    ]
    doc.build(story)
    return output_path


def register_korean_font() -> str:
    font_name = "HYSMyeongJo-Medium"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def build_styles(font_name: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "TitleKo": ParagraphStyle("TitleKo", parent=base["Title"], fontName=font_name, fontSize=20, leading=26),
        "HeadingKo": ParagraphStyle("HeadingKo", parent=base["Heading2"], fontName=font_name, fontSize=13, leading=18),
        "BodyKo": ParagraphStyle("BodyKo", parent=base["BodyText"], fontName=font_name, fontSize=10, leading=15),
        "SmallKo": ParagraphStyle("SmallKo", parent=base["BodyText"], fontName=font_name, fontSize=8, leading=11),
    }

