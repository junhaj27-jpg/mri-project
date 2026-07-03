from __future__ import annotations


STABLE_THRESHOLD_PERCENT = 3.0


def analyze_volume_change(previous_volume_ml: float, current_volume_ml: float) -> dict:
    """Compare previous and current MRI ROI volume values."""
    if previous_volume_ml < 0 or current_volume_ml < 0:
        raise ValueError("Volume values must not be negative.")

    change_ml = float(current_volume_ml - previous_volume_ml)
    change_percent = None
    if previous_volume_ml > 0:
        change_percent = float(change_ml / previous_volume_ml * 100.0)

    return {
        "previous_volume_ml": float(previous_volume_ml),
        "current_volume_ml": float(current_volume_ml),
        "change_ml": change_ml,
        "change_percent": change_percent,
        "status": classify_change(change_ml, change_percent),
    }


def classify_change(change_ml: float, change_percent: float | None) -> str:
    """Return Korean status label: increase, decrease, or stable."""
    if change_percent is not None and abs(change_percent) <= STABLE_THRESHOLD_PERCENT:
        return "유지"
    if change_ml > 0:
        return "증가"
    if change_ml < 0:
        return "감소"
    return "유지"

