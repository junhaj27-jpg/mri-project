from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology

from brain_mask import create_brain_mask, largest_connected_component, refine_brain_mask
from mri_loader import MRIData, load_nifti_mask, save_brain_extracted, save_nifti_mask, save_nifti_volume


@dataclass
class SkullStripResult:
    raw_mask: np.ndarray
    refined_mask: np.ndarray
    mask: np.ndarray
    brain_extracted: np.ndarray
    mask_path: Path
    refined_mask_path: Path
    brain_path: Path
    method_used: str
    metadata: dict
    warnings: list[str]


def run_skull_stripping(
    mri_data: MRIData,
    method: str,
    output_dir: str | Path,
    synthstrip_command: str = "mri_synthstrip",
    hdbet_command: str = "hd-bet",
    hdbet_device: str = "cuda",
    threshold_scale: float = 1.0,
    peel_iterations: int = 6,
    fill_holes: bool = True,
    closing_radius: int = 3,
    remove_small_holes_threshold: int = 5000,
    remove_small_objects_threshold: int = 20000,
    mask_smoothing_sigma: float = 0.8,
) -> SkullStripResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "input_volume.nii.gz"
    mask_path = output_dir / "brain_mask.nii.gz"
    refined_mask_path = output_dir / "refined_brain_mask.nii.gz"
    brain_path = output_dir / "brain_extracted.nii.gz"
    save_nifti_volume(mri_data.volume, mri_data.affine, input_path)

    preferred = method.lower()
    attempts: list[str]
    if preferred == "synthstrip":
        attempts = ["SynthStrip", "HD-BET", "Simple fallback"]
    elif preferred == "hd-bet":
        attempts = ["HD-BET", "SynthStrip", "Simple fallback"]
    else:
        attempts = ["Simple fallback"]

    warnings: list[str] = []
    for attempt in attempts:
        try:
            if attempt == "SynthStrip":
                mask = run_synthstrip(input_path, brain_path, mask_path, synthstrip_command)
                metadata = {"method": "SynthStrip", "command": synthstrip_command}
            elif attempt == "HD-BET":
                mask = run_hdbet(input_path, brain_path, mask_path, hdbet_command, hdbet_device)
                metadata = {"method": "HD-BET", "command": hdbet_command, "device": hdbet_device}
            else:
                mask, metadata = create_brain_mask(
                    mri_data.volume,
                    threshold_scale=threshold_scale,
                    peel_iterations=peel_iterations,
                    method="Fallback Otsu",
                    plane=str(mri_data.info.get("Plane", "unknown")),
                )
                mask_path = save_nifti_mask(mask, mri_data.affine, mask_path)
                brain_path = save_brain_extracted(mri_data.volume, mask, mri_data.affine, brain_path)
                metadata = {**metadata, "method": "Simple fallback"}

            raw_mask = clean_external_mask(mask)
            refined_mask, refine_metadata = refine_brain_mask(
                raw_mask,
                fill_holes=fill_holes,
                closing_radius=closing_radius,
                hole_area_threshold=remove_small_holes_threshold,
                min_object_size=remove_small_objects_threshold,
                gaussian_sigma=mask_smoothing_sigma,
            )
            mask_path = save_nifti_mask(raw_mask, mri_data.affine, mask_path)
            refined_mask_path = save_nifti_mask(refined_mask, mri_data.affine, refined_mask_path)
            brain_path = save_brain_extracted(mri_data.volume, refined_mask, mri_data.affine, brain_path)
            quality_warnings = validate_brain_mask(refined_mask, mri_data.volume.shape)
            return SkullStripResult(
                raw_mask=raw_mask,
                refined_mask=refined_mask,
                mask=refined_mask,
                brain_extracted=mri_data.volume * refined_mask.astype(np.float32),
                mask_path=mask_path,
                refined_mask_path=refined_mask_path,
                brain_path=brain_path,
                method_used=attempt,
                metadata={
                    **metadata,
                    **refine_metadata,
                    "raw_voxels": int(np.count_nonzero(raw_mask)),
                    "voxels": int(np.count_nonzero(refined_mask)),
                    "quality_warnings": quality_warnings,
                },
                warnings=warnings + quality_warnings,
            )
        except Exception as exc:
            warnings.append(f"{attempt} unavailable/failed: {exc}")

    raise RuntimeError("; ".join(warnings) or "Skull stripping failed.")


def run_synthstrip(input_path: Path, brain_path: Path, mask_path: Path, command: str) -> np.ndarray:
    executable = resolve_command(command)
    subprocess.run(
        [executable, "-i", str(input_path), "-o", str(brain_path), "-m", str(mask_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if not mask_path.exists():
        raise FileNotFoundError(f"SynthStrip did not create {mask_path}.")
    return load_nifti_mask(mask_path)


def run_hdbet(input_path: Path, brain_path: Path, mask_path: Path, command: str, device: str = "cuda") -> np.ndarray:
    executable = resolve_command(command)
    output_no_ext = strip_nii_suffix(brain_path)
    device = "cuda" if str(device).lower() in {"cuda", "gpu"} else "cpu"
    subprocess.run(
        [executable, "-i", str(input_path), "-o", str(output_no_ext), "-device", device, "-mode", "fast"],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )
    candidates = [
        mask_path,
        output_no_ext.with_name(output_no_ext.name + "_mask.nii.gz"),
        output_no_ext.with_name(output_no_ext.name + "_mask.nii"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return load_nifti_mask(candidate)
    raise FileNotFoundError("HD-BET did not create a mask file.")


def resolve_command(command: str) -> str:
    command = str(command or "").strip()
    if not command:
        raise FileNotFoundError("Empty command.")
    found = shutil.which(command)
    if found:
        return found
    path = Path(command)
    if path.exists():
        return str(path)
    raise FileNotFoundError(f"Command not found: {command}")


def strip_nii_suffix(path: Path) -> Path:
    text = str(path)
    if text.endswith(".nii.gz"):
        return Path(text[:-7])
    if text.endswith(".nii"):
        return Path(text[:-4])
    return path


def clean_external_mask(mask: np.ndarray) -> np.ndarray:
    cleaned = mask.astype(bool)
    cleaned = morphology.remove_small_objects(cleaned, min_size=max(512, cleaned.size // 2000))
    cleaned = keep_largest_component(cleaned)
    cleaned = ndi.binary_fill_holes(cleaned)
    cleaned = morphology.binary_closing(cleaned, morphology.ball(2))
    cleaned = morphology.remove_small_holes(cleaned, area_threshold=max(2048, cleaned.size // 1000))
    return cleaned.astype(bool)


def keep_largest_component(mask: np.ndarray) -> np.ndarray:
    return largest_connected_component(mask)


def validate_brain_mask(mask: np.ndarray, shape: tuple[int, ...]) -> list[str]:
    warnings: list[str] = []
    voxels = int(np.count_nonzero(mask))
    total = int(np.prod(shape))
    ratio = voxels / max(total, 1)
    if ratio > 0.35:
        warnings.append("Mask is large; skull/face/neck may still be included.")
    if ratio < 0.02:
        warnings.append("Mask is very small; brain tissue may be missing.")
    labels = measure.label(mask)
    if labels.max() > 1:
        warnings.append("Mask has multiple components; small fragments may remain.")
    coords = np.argwhere(mask)
    if coords.size:
        lower = coords.min(axis=0)
        upper = coords.max(axis=0)
        if np.any(lower <= 1) or np.any(upper >= np.array(shape) - 2):
            warnings.append("Mask touches image border; non-brain tissue may remain.")
        extent = (upper - lower + 1) / np.maximum(np.array(shape), 1)
        if np.any(extent > 0.92):
            warnings.append("Mask spans almost the full image axis; face/head/skull may still be included.")
    return warnings
