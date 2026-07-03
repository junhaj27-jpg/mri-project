from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectROI:
    """Rectangle ROI in image pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height


def clamp_roi(roi: RectROI, image_width: int, image_height: int) -> RectROI:
    """Clamp ROI to the image boundary and keep width/height non-negative."""
    x = min(max(roi.x, 0), max(image_width - 1, 0))
    y = min(max(roi.y, 0), max(image_height - 1, 0))
    width = min(max(roi.width, 0), image_width - x)
    height = min(max(roi.height, 0), image_height - y)
    return RectROI(x=x, y=y, width=width, height=height)


def calculate_roi_area_mm2(roi: RectROI, pixel_spacing: list[float] | tuple[float, float]) -> float:
    """Calculate rectangle ROI area using DICOM PixelSpacing.

    DICOM PixelSpacing is ordered as row spacing, column spacing in millimeters.
    A rectangle width is in columns(x), height is in rows(y).
    """
    row_spacing_mm, col_spacing_mm = pixel_spacing
    return float(roi.width * roi.height * row_spacing_mm * col_spacing_mm)


def calculate_estimated_volume(area_mm2_values: list[float], slice_thickness_mm: float) -> dict:
    """Estimate ROI volume from multiple slice areas.

    1 ml is equivalent to 1 cm3, and 1 cm3 equals 1000 mm3.
    """
    if slice_thickness_mm <= 0:
        raise ValueError("SliceThickness must be greater than zero.")
    if any(area < 0 for area in area_mm2_values):
        raise ValueError("ROI area values must not be negative.")

    volume_mm3 = float(sum(area_mm2_values) * slice_thickness_mm)
    return {
        "volume_mm3": volume_mm3,
        "volume_ml": volume_mm3 / 1000.0,
    }

