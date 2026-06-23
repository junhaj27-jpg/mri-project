from __future__ import annotations


def measure_volume_placeholder(voxel_count: int, voxel_volume_mm3: float = 1.0) -> dict:
    volume_cc = voxel_count * voxel_volume_mm3 / 1000.0
    return {
        "voxel_count": voxel_count,
        "voxel_volume_mm3": voxel_volume_mm3,
        "volume_cc": round(volume_cc, 3),
        "status": "placeholder",
    }
