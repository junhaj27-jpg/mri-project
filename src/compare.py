from __future__ import annotations


MAINTAIN_THRESHOLD_PERCENT = 3.0


def compare_mri_results(
    previous_date: str,
    current_date: str,
    previous_volume_cm3: float,
    current_volume_cm3: float,
) -> dict:
    if previous_volume_cm3 < 0 or current_volume_cm3 < 0:
        raise ValueError("Volume values must be greater than or equal to zero.")

    change_cm3 = float(current_volume_cm3 - previous_volume_cm3)
    change_percent = calculate_change_percent(previous_volume_cm3, current_volume_cm3)

    return {
        "previous_date": previous_date,
        "current_date": current_date,
        "previous_volume_cm3": float(previous_volume_cm3),
        "current_volume_cm3": float(current_volume_cm3),
        "change_cm3": change_cm3,
        "change_percent": change_percent,
        "status": classify_change(change_cm3, change_percent),
    }


def calculate_change_percent(previous_volume_cm3: float, current_volume_cm3: float) -> float | None:
    if previous_volume_cm3 == 0:
        return None
    return float((current_volume_cm3 - previous_volume_cm3) / previous_volume_cm3 * 100.0)


def classify_change(change_cm3: float, change_percent: float | None) -> str:
    if change_percent is not None and abs(change_percent) <= MAINTAIN_THRESHOLD_PERCENT:
        return "유지"
    if change_cm3 > 0:
        return "증가"
    if change_cm3 < 0:
        return "감소"
    return "유지"

