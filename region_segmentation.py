from __future__ import annotations

import csv
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from skimage import measure

LOGGER = logging.getLogger("aidlc_mri.regions")

REGION_SEGMENTATION_DISABLED_MESSAGE = (
    "Region segmentation requires SynthSeg or FastSurfer. "
    "Threshold-based region segmentation is disabled."
)

REGION_COLORS: dict[str, str] = {
    "Whole brain": "#94a3b8",
    "Cerebrum": "#2563eb",
    "Cerebellum": "#16a34a",
    "Brainstem": "#7c3aed",
    "Ventricle": "#1e3a8a",
    "Hippocampus": "#06b6d4",
    "Basal Ganglia": "#facc15",
    "Thalamus": "#f97316",
    "White Matter": "#e5e7eb",
    "Gray Matter": "#64748b",
    "Other": "#a855f7",
    "Target Region/Tumor": "#dc2626",
}

# FreeSurfer/SynthSeg-style label ids. This mapping is intentionally grouped:
# it summarizes label-map output into viewer-friendly region families.
REGION_GROUPS: dict[str, list[int]] = {
    "Whole brain": [
        2,
        3,
        4,
        5,
        7,
        8,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        24,
        26,
        28,
        31,
        41,
        42,
        43,
        44,
        46,
        47,
        49,
        50,
        51,
        52,
        53,
        54,
        58,
        60,
        63,
    ],
    "Cerebrum": [2, 3, 41, 42],
    "Cerebellum": [7, 8, 46, 47],
    "Brainstem": [16],
    "Ventricle": [4, 5, 14, 15, 24, 43, 44],
    "Hippocampus": [17, 53],
    "Basal Ganglia": [11, 12, 13, 26, 50, 51, 52, 58],
    "Thalamus": [10, 49],
    "White Matter": [2, 41],
    "Gray Matter": [3, 42],
}

LABEL_NAMES: dict[int, str] = {
    2: "Left cerebral white matter",
    3: "Left cerebral cortex",
    4: "Left lateral ventricle",
    5: "Left inferior lateral ventricle",
    7: "Left cerebellum white matter",
    8: "Left cerebellum cortex",
    10: "Left thalamus",
    11: "Left caudate",
    12: "Left putamen",
    13: "Left pallidum",
    14: "Third ventricle",
    15: "Fourth ventricle",
    16: "Brainstem",
    17: "Left hippocampus",
    18: "Left amygdala",
    24: "CSF",
    26: "Left accumbens",
    28: "Left ventral DC",
    31: "Left choroid plexus",
    41: "Right cerebral white matter",
    42: "Right cerebral cortex",
    43: "Right lateral ventricle",
    44: "Right inferior lateral ventricle",
    46: "Right cerebellum white matter",
    47: "Right cerebellum cortex",
    49: "Right thalamus",
    50: "Right caudate",
    51: "Right putamen",
    52: "Right pallidum",
    53: "Right hippocampus",
    54: "Right amygdala",
    58: "Right accumbens",
    60: "Right ventral DC",
    63: "Right choroid plexus",
}


def synthseg_available() -> bool:
    return bool(find_synthseg_command())


def fastsurfer_available() -> bool:
    return bool(shutil.which("run_fastsurfer.sh") or shutil.which("fastsurfercnn") or shutil.which("run_fastsurfer"))


def find_synthseg_command() -> list[str] | None:
    command = shutil.which("mri_synthseg")
    if command:
        return [command]
    command = shutil.which("SynthSeg")
    if command:
        return [command]
    return None


def run_region_segmentation(
    input_path: str | Path,
    output_path: str | Path,
    project_root: str | Path,
) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    project_root = Path(project_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        return {
            "ok": False,
            "status": "missing_input",
            "message": f"Input NIfTI not found: {input_path}",
            "labelmap_path": None,
        }

    synthseg = find_synthseg_command()
    if synthseg:
        command = synthseg + ["--i", str(input_path), "--o", str(output_path)]
        return run_segmentation_command(command, output_path, project_root, "synthseg")

    if fastsurfer_available():
        return {
            "ok": False,
            "status": "fastsurfer_available_manual_setup_required",
            "method": "fastsurfer",
            "message": (
                "FastSurfer appears available, but automatic FastSurfer subject setup is not configured. "
                "Place/export a compatible label map as outputs/regions_labelmap.nii.gz."
            ),
            "labelmap_path": None,
        }

    return {
        "ok": False,
        "status": "disabled",
        "method": "none",
        "message": REGION_SEGMENTATION_DISABLED_MESSAGE,
        "labelmap_path": None,
    }


def run_segmentation_command(command: list[str], output_path: Path, cwd: Path, method: str) -> dict[str, Any]:
    command_text = " ".join(command)
    LOGGER.warning("Running region segmentation command: %s", command_text)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=7200, cwd=str(cwd))
        ok = result.returncode == 0 and output_path.exists()
        return {
            "ok": ok,
            "status": "valid" if ok else "failed",
            "method": method,
            "message": "Region label map generated." if ok else "Region segmentation failed.",
            "labelmap_path": str(output_path) if output_path.exists() else None,
            "command": command_text,
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[-4000:],
            "stderr": (result.stderr or "")[-4000:],
        }
    except Exception as exc:
        LOGGER.exception("Region segmentation command failed.")
        return {
            "ok": False,
            "status": "failed",
            "method": method,
            "message": f"Region segmentation failed: {exc}",
            "labelmap_path": None,
            "command": command_text,
            "returncode": None,
            "stdout": "",
            "stderr": repr(exc),
        }


def load_region_labelmap(path: str | Path = "outputs/regions_labelmap.nii.gz") -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "message": "Label map not found. Run region segmentation or place outputs/regions_labelmap.nii.gz.",
            "labelmap_path": str(path),
            "regions": [],
        }

    data, spacing = load_labelmap_array(path)
    unique = [int(value) for value in np.unique(data) if int(value) != 0]
    voxel_volume_mm3 = float(np.prod(spacing))
    regions = compute_region_volumes(data, spacing)
    return {
        "ok": True,
        "status": "valid",
        "message": "Region label map loaded.",
        "labelmap_path": str(path),
        "shape": tuple(int(value) for value in data.shape),
        "spacing": spacing,
        "unique_labels": unique,
        "label_names": {str(label): LABEL_NAMES.get(label, f"Label {label}") for label in unique},
        "voxel_volume_mm3": voxel_volume_mm3,
        "regions": regions,
        "region_names": list(REGION_GROUPS.keys()),
        "colors": REGION_COLORS,
    }


def compute_region_volumes(labelmap: np.ndarray, spacing: tuple[float, float, float]) -> list[dict[str, Any]]:
    voxel_volume_mm3 = float(np.prod(spacing))
    rows: list[dict[str, Any]] = []
    for name, label_ids in REGION_GROUPS.items():
        mask = np.isin(labelmap, label_ids)
        voxel_count = int(np.count_nonzero(mask))
        volume_mm3 = float(voxel_count * voxel_volume_mm3)
        rows.append(
            {
                "region_name": name,
                "label_ids": label_ids,
                "voxel_count": voxel_count,
                "volume_mm3": round(volume_mm3, 3),
                "volume_ml": round(volume_mm3 / 1000.0, 3),
                "color": REGION_COLORS.get(name, "#94a3b8"),
                "mesh_path": "",
            }
        )
    return rows


def export_region_volumes_csv(
    labelmap_path: str | Path,
    output_csv_path: str | Path,
    mesh_dir: str | Path | None = None,
) -> dict[str, Any]:
    info = load_region_labelmap(labelmap_path)
    if not info.get("ok"):
        return info

    output_csv_path = Path(output_csv_path)
    mesh_dir = Path(mesh_dir) if mesh_dir is not None else output_csv_path.parent / "meshes"
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in info["regions"]:
        mesh_path = mesh_dir / f"{slugify_region(row['region_name'])}.glb"
        rows.append({**row, "mesh_path": str(mesh_path) if mesh_path.exists() else ""})

    with output_csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["region_name", "label_ids", "voxel_count", "volume_mm3", "volume_ml", "mesh_path"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "region_name": row["region_name"],
                    "label_ids": " ".join(str(value) for value in row["label_ids"]),
                    "voxel_count": row["voxel_count"],
                    "volume_mm3": row["volume_mm3"],
                    "volume_ml": row["volume_ml"],
                    "mesh_path": row["mesh_path"],
                }
            )

    return {
        "ok": True,
        "status": "ready",
        "message": "Region volumes CSV exported.",
        "csv_path": str(output_csv_path),
        "regions": rows,
    }


def build_region_mesh(
    labelmap_path: str | Path,
    region_name: str,
    output_path: str | Path,
    smooth: bool = True,
) -> dict[str, Any]:
    labelmap_path = Path(labelmap_path)
    output_path = Path(output_path)
    info = load_region_labelmap(labelmap_path)
    if not info.get("ok"):
        return info
    label_ids = REGION_GROUPS.get(region_name)
    if not label_ids:
        return {
            "ok": False,
            "status": "missing_region",
            "message": f"Unknown region: {region_name}",
            "mesh_path": None,
        }

    labelmap, spacing = load_labelmap_array(labelmap_path)
    region_mask = np.isin(labelmap, label_ids)
    voxel_count = int(np.count_nonzero(region_mask))
    if voxel_count == 0:
        return {
            "ok": False,
            "status": "missing_region",
            "message": "Selected region not found",
            "region_name": region_name,
            "label_ids": label_ids,
            "mesh_path": None,
            "voxel_count": 0,
        }

    try:
        import trimesh  # type: ignore

        verts, faces, _, _ = measure.marching_cubes(
            region_mask.astype(np.float32),
            level=0.5,
            spacing=spacing,
            allow_degenerate=False,
        )
        mesh: Any = trimesh.Trimesh(vertices=verts.astype(np.float32), faces=faces.astype(np.int32), process=True)
        if smooth:
            try:
                trimesh.smoothing.filter_laplacian(mesh, iterations=3)
            except Exception:
                LOGGER.exception("Region mesh smoothing failed; exporting unsmoothed mesh.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(output_path), file_type="glb")
        return {
            "ok": True,
            "status": "ready",
            "message": "3D mesh loaded",
            "region_name": region_name,
            "label_ids": label_ids,
            "voxel_count": voxel_count,
            "mesh_path": str(output_path),
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "color": REGION_COLORS.get(region_name, "#94a3b8"),
        }
    except Exception as exc:
        LOGGER.exception("Region mesh generation failed.")
        return {
            "ok": False,
            "status": "failed",
            "message": f"Mesh generation failed: {exc}",
            "region_name": region_name,
            "label_ids": label_ids,
            "voxel_count": voxel_count,
            "mesh_path": None,
            "exception": str(exc),
        }


def slugify_region(region_name: str) -> str:
    return (
        str(region_name)
        .strip()
        .lower()
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
    )


def load_labelmap_array(path: str | Path) -> tuple[np.ndarray, tuple[float, float, float]]:
    img = nib.as_closest_canonical(nib.load(str(path)))
    data = np.asarray(img.get_fdata()).astype(np.int32)
    if data.ndim == 4:
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError(f"Expected a 3D region label map, got shape {data.shape}.")
    viewer_data = np.transpose(data, (2, 1, 0)).astype(np.int32)
    zooms = img.header.get_zooms()[:3]
    spacing = (float(zooms[2]), float(zooms[1]), float(zooms[0]))
    return viewer_data, spacing
