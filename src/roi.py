from __future__ import annotations

import numpy as np
from skimage.draw import polygon


def parse_roi_points(text: str) -> list[tuple[float, float]]:
    points = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) != 2:
            raise ValueError(f"좌표 형식 오류: {raw_line}")
        points.append((float(parts[0]), float(parts[1])))
    if len(points) < 3:
        raise ValueError("ROI polygon은 최소 3개 좌표가 필요합니다.")
    return points


def polygon_to_mask(shape_yx: tuple[int, int], points_xy: list[tuple[float, float]]) -> np.ndarray:
    xs = np.array([point[0] for point in points_xy], dtype=float)
    ys = np.array([point[1] for point in points_xy], dtype=float)
    rr, cc = polygon(ys, xs, shape=shape_yx)
    mask = np.zeros(shape_yx, dtype=bool)
    mask[rr, cc] = True
    return mask

