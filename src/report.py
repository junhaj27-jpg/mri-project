from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DISCLAIMER = (
    "본 리포트는 진단 목적이 아닌 MRI 분석 보조 및 추적 관리를 위한 참고 자료입니다. "
    "최종 의학적 판단은 담당 의료진의 판독을 따라야 합니다."
)


def create_pdf_report(
    output_path: str | Path,
    study_date: str,
    series_description: str,
    roi_area_mm2: float,
    estimated_volume_cm3: float,
    change_summary: dict | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    font_name = register_korean_font()
    styles = build_styles(font_name)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, title="AIDLC-MRI Report")

    rows = [
        ["검사 날짜", study_date],
        ["SeriesDescription", series_description],
        ["ROI 면적", f"{roi_area_mm2:.2f} mm²"],
        ["추정 부피", f"{estimated_volume_cm3:.3f} cm³"],
    ]
    if change_summary:
        rows.extend(
            [
                ["이전 검사일", str(change_summary.get("previous_date", ""))],
                ["현재 검사일", str(change_summary.get("current_date", ""))],
                ["이전 검사 대비 변화량", format_change(change_summary)],
                ["판정", str(change_summary.get("status", ""))],
            ]
        )

    table = Table(rows, colWidths=[150, 340])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story = [
        Paragraph("AIDLC-MRI 리포트", styles["TitleKo"]),
        Spacer(1, 12),
        Paragraph("진단 목적이 아닌 MRI 분석 보조 및 추적 관리 참고 자료", styles["BodyKo"]),
        Spacer(1, 12),
        table,
        Spacer(1, 18),
        Paragraph("주의 문구", styles["HeadingKo"]),
        Paragraph(DISCLAIMER, styles["BodyKo"]),
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
        "TitleKo": ParagraphStyle(
            "TitleKo",
            parent=base["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
        ),
        "HeadingKo": ParagraphStyle(
            "HeadingKo",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=18,
        ),
        "BodyKo": ParagraphStyle(
            "BodyKo",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=15,
        ),
    }


def format_change(change_summary: dict) -> str:
    change_cm3 = float(change_summary.get("change_cm3", 0.0))
    change_percent = change_summary.get("change_percent")
    if change_percent is None:
        return f"{change_cm3:+.3f} cm³"
    return f"{change_cm3:+.3f} cm³ ({float(change_percent):+.2f}%)"

