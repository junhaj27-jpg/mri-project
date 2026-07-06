from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology

from brain_mask import create_brain_mask, create_filled_brain_surface_mask, largest_connected_component, refine_brain_mask
from mri_loader import MRIData, load_nifti_mask, save_brain_extracted, save_nifti_mask, save_nifti_volume


@dataclass
class SkullStripResult:
    raw_mask: np.ndarray
    refined_mask: np.ndarray
    filled_mask: np.ndarray
    mask: np.ndarray
    brain_extracted: np.ndarray
    mask_path: Path
    refined_mask_path: Path
    filled_mask_path: Path
    brain_path: Path
    method_used: str
    reliable_for_3d: bool
    debug_only: bool
    metadata: dict
    warnings: list[str]


def check_command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def get_skullstrip_status() -> dict[str, bool]:
    venv_scripts = project_venv_scripts_dir()
    venv_python = project_venv_python()
    return {
        "mri_synthstrip": check_command_exists("mri_synthstrip"),
        "hd-bet": check_command_exists("hd-bet"),
        "HD_BET": check_command_exists("HD_BET"),
        r".venv\Scripts\hd-bet.exe": (venv_scripts / "hd-bet.exe").exists(),
        r".venv\Scripts\HD_BET.exe": (venv_scripts / "HD_BET.exe").exists(),
        r".venv\Scripts\python.exe -m HD_BET.entry_point": module_exists("HD_BET.entry_point", venv_python),
    }


def get_torch_cuda_status() -> dict[str, object]:
    try:
        import torch

        available = bool(torch.cuda.is_available())
        return {
            "available": available,
            "torch_version": str(torch.__version__),
            "cuda_version": str(torch.version.cuda),
            "device_count": int(torch.cuda.device_count()),
            "device_name": torch.cuda.get_device_name(0) if available else "",
        }
    except Exception as exc:
        return {
            "available": False,
            "torch_version": "unknown",
            "cuda_version": "unknown",
            "device_count": 0,
            "device_name": "",
            "error": repr(exc),
        }


def module_exists(module_name: str, python_executable: Path | None = None) -> bool:
    try:
        executable = str(python_executable or sys.executable)
        result = subprocess.run(
            [executable, "-m", module_name, "-h"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


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
    filled_mask_path = output_dir / "filled_brain_mask.nii.gz"
    brain_path = output_dir / "brain_extracted.nii.gz"
    save_nifti_volume(mri_data.volume, mri_data.affine, input_path)

    preferred = method.lower()
    attempts: list[str]
    if preferred == "synthstrip":
        attempts = ["SynthStrip", "HD-BET"]
    elif preferred == "hd-bet":
        attempts = ["HD-BET", "SynthStrip"]
    else:
        attempts = ["Simple fallback"]

    warnings: list[str] = []
    for attempt in attempts:
        try:
            if attempt == "SynthStrip":
                tool_mask_path = output_dir / "brain_mask_synthstrip.nii.gz"
                tool_brain_path = output_dir / "brain_extracted_synthstrip.nii.gz"
                mask = run_synthstrip(input_path, tool_brain_path, tool_mask_path, synthstrip_command)
                metadata = {
                    "method": "SynthStrip",
                    "command": synthstrip_command,
                    "tool_mask_path": str(tool_mask_path),
                    "tool_brain_path": str(tool_brain_path),
                    "reliable_for_3d": True,
                    "debug_only": False,
                }
            elif attempt == "HD-BET":
                tool_mask_path = output_dir / "brain_mask_hdbet.nii.gz"
                tool_brain_path = output_dir / "brain_extracted_hdbet.nii.gz"
                mask, tool_attempts = run_hdbet(
                    input_path,
                    tool_brain_path,
                    tool_mask_path,
                    hdbet_command,
                    hdbet_device,
                )
                metadata = {
                    "method": "HD-BET",
                    "command": hdbet_command,
                    "device": hdbet_device,
                    "tool_attempts": tool_attempts,
                    "tool_mask_path": str(tool_mask_path),
                    "tool_brain_path": str(tool_brain_path),
                    "reliable_for_3d": True,
                    "debug_only": False,
                }
            else:
                mask_path = output_dir / "debug_fallback_mask.nii.gz"
                mask, metadata = create_brain_mask(
                    mri_data.volume,
                    threshold_scale=threshold_scale,
                    peel_iterations=peel_iterations,
                    method="Fallback Otsu",
                    plane=str(mri_data.info.get("Plane", "unknown")),
                )
                mask_path = save_nifti_mask(mask, mri_data.affine, mask_path)
                brain_path = save_brain_extracted(mri_data.volume, mask, mri_data.affine, brain_path)
                metadata = {
                    **metadata,
                    "method": "Simple fallback debug only",
                    "reliable_for_3d": False,
                    "debug_only": True,
                }

            raw_mask = clean_external_mask(mask)
            refined_mask, refine_metadata = refine_brain_mask(
                raw_mask,
                fill_holes=fill_holes,
                closing_radius=closing_radius,
                hole_area_threshold=remove_small_holes_threshold,
                min_object_size=remove_small_objects_threshold,
                gaussian_sigma=mask_smoothing_sigma,
            )
            filled_mask, filled_metadata = create_filled_brain_surface_mask(
                refined_mask,
                hole_area_threshold=max(int(remove_small_holes_threshold), 12000),
                closing_radius=max(int(closing_radius), 4),
                min_object_size=int(remove_small_objects_threshold),
            )
            mask_path = save_nifti_mask(raw_mask, mri_data.affine, mask_path)
            refined_mask_path = save_nifti_mask(refined_mask, mri_data.affine, refined_mask_path)
            filled_mask_path = save_nifti_mask(filled_mask, mri_data.affine, filled_mask_path)
            brain_path = save_brain_extracted(mri_data.volume, filled_mask, mri_data.affine, brain_path)
            quality_warnings = validate_brain_mask(
                filled_mask,
                mri_data.volume.shape,
                source=str(metadata.get("method", attempt)),
                debug_only=bool(metadata.get("debug_only", False)),
            )
            return SkullStripResult(
                raw_mask=raw_mask,
                refined_mask=refined_mask,
                filled_mask=filled_mask,
                mask=filled_mask,
                brain_extracted=mri_data.volume * filled_mask.astype(np.float32),
                mask_path=mask_path,
                refined_mask_path=refined_mask_path,
                filled_mask_path=filled_mask_path,
                brain_path=brain_path,
                method_used=attempt,
                reliable_for_3d=bool(metadata.get("reliable_for_3d", False)),
                debug_only=bool(metadata.get("debug_only", False)),
                metadata={
                    **metadata,
                    **refine_metadata,
                    **filled_metadata,
                    "raw_voxels": int(np.count_nonzero(raw_mask)),
                    "cleaned_voxels": int(np.count_nonzero(refined_mask)),
                    "voxels": int(np.count_nonzero(filled_mask)),
                    "quality_warnings": quality_warnings,
                },
                warnings=warnings + quality_warnings,
            )
        except Exception as exc:
            warnings.append(f"{attempt} unavailable/failed: {exc}")

    raise RuntimeError(
        "Reliable skull stripping tool is not available. Install SynthStrip or HD-BET to generate brain-only 3D mesh. "
        + ("; ".join(warnings) if warnings else "Skull stripping failed.")
    )


def run_synthstrip(input_path: Path, brain_path: Path, mask_path: Path, command: str) -> np.ndarray:
    if not check_command_exists(command):
        raise FileNotFoundError(f"Command not found: {command}")
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


def run_hdbet(
    input_path: Path,
    brain_path: Path,
    mask_path: Path,
    command: str,
    device: str = "cuda",
) -> tuple[np.ndarray, list[dict]]:
    output_no_ext = strip_nii_suffix(brain_path)
    requested_device = "cuda" if str(device).lower() in {"cuda", "gpu"} else "cpu"
    device_candidates = [requested_device]
    if requested_device == "cuda":
        device_candidates.append("cpu")
    attempts: list[dict] = []
    for candidate in hdbet_command_candidates(command):
        label = str(candidate["label"])
        cmd = list(candidate["cmd"])
        resolved = bool(candidate.get("resolved", True))
        if not resolved:
            attempts.append(
                {
                    "label": label,
                    "command": " ".join(cmd),
                    "status": "not found",
                    "returncode": None,
                    "stdout": "",
                    "stderr": str(candidate.get("error", "command not found")),
                }
            )
            continue
        for run_device in device_candidates:
            try:
                hdbet_args = ["-i", str(input_path), "-o", str(brain_path), "-device", run_device, "--save_bet_mask"]
                if run_device == "cpu":
                    hdbet_args.append("--disable_tta")
                result = subprocess.run(
                    cmd + hdbet_args,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
                attempts.append(
                    {
                        "label": f"{label} ({run_device})",
                        "command": " ".join(cmd + hdbet_args),
                        "status": "succeeded",
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
                break
            except subprocess.CalledProcessError as exc:
                attempts.append(
                    {
                        "label": f"{label} ({run_device})",
                        "command": " ".join(cmd + hdbet_args),
                        "status": "failed",
                        "returncode": exc.returncode,
                        "stdout": exc.stdout or "",
                        "stderr": exc.stderr or "",
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "label": f"{label} ({run_device})",
                        "command": " ".join(cmd + hdbet_args),
                        "status": "failed",
                        "returncode": None,
                        "stdout": "",
                        "stderr": repr(exc),
                    }
                )
        if attempts and attempts[-1].get("status") == "succeeded":
            break
    else:
        raise RuntimeError("HD-BET failed with all command candidates:\n" + format_command_attempts(attempts))

    mask_candidate = find_hdbet_mask(brain_path, mask_path)
    if mask_candidate is not None:
        return load_nifti_mask(mask_candidate), attempts
    generated = sorted(str(path) for path in brain_path.parent.glob("*.nii.gz"))
    raise FileNotFoundError("HD-BET did not create a mask file. Generated files: " + "; ".join(generated))


def project_venv_scripts_dir() -> Path:
    return Path(__file__).resolve().parent / ".venv" / "Scripts"


def project_venv_python() -> Path:
    return project_venv_scripts_dir() / "python.exe"


def hdbet_command_candidates(command: str | None = None) -> list[dict]:
    venv_scripts = project_venv_scripts_dir()
    venv_python = project_venv_python()
    candidates = [
        command_candidate_from_which("hd-bet"),
        command_candidate_from_which("HD_BET"),
        {
            "label": r".venv\Scripts\python.exe -m HD_BET.entry_point",
            "cmd": [str(venv_python), "-m", "HD_BET.entry_point"],
            "resolved": venv_python.exists(),
            "error": "" if venv_python.exists() else f"File not found: {venv_python}",
        },
        command_candidate_from_path(r".venv\Scripts\hd-bet.exe", venv_scripts / "hd-bet.exe"),
        command_candidate_from_path(r".venv\Scripts\HD_BET.exe", venv_scripts / "HD_BET.exe"),
    ]
    custom = str(command or "").strip()
    if custom and custom.lower() not in {"hd-bet", "hd_bet"} and custom not in {str(item["cmd"][0]) for item in candidates if item["cmd"]}:
        candidates.insert(0, command_candidate_from_custom(custom))
    return candidates


def find_hdbet_mask(brain_path: Path, mask_path: Path) -> Path | None:
    output_no_ext = strip_nii_suffix(brain_path)
    explicit_candidates = [
        mask_path,
        output_no_ext.with_name(output_no_ext.name + "_bet.nii.gz"),
        output_no_ext.with_name(output_no_ext.name + "_mask.nii.gz"),
        output_no_ext.with_name(output_no_ext.name + "_bet_mask.nii.gz"),
        output_no_ext.with_name(output_no_ext.name + "_bet.nii"),
        output_no_ext.with_name(output_no_ext.name + "_mask.nii"),
    ]
    for candidate in explicit_candidates:
        if candidate.exists():
            return candidate

    generated: list[Path] = []
    for pattern in ("*hdbet*.nii.gz", "*bet*.nii.gz", "*mask*.nii.gz", "*.nii.gz"):
        generated.extend(brain_path.parent.glob(pattern))

    seen: set[Path] = set()
    unique = []
    for path in generated:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)

    preferred = [
        path
        for path in unique
        if path != brain_path and any(token in path.name.lower() for token in ("mask", "bet", "hdbet"))
    ]
    if preferred:
        return sorted(preferred, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    return None


def command_candidate_from_which(command: str) -> dict:
    found = shutil.which(command)
    if found:
        return {"label": command, "cmd": [found], "resolved": True, "error": ""}
    return {"label": command, "cmd": [command], "resolved": False, "error": f"Command not found: {command}"}


def command_candidate_from_path(label: str, path: Path) -> dict:
    if path.exists():
        return {"label": label, "cmd": [str(path)], "resolved": True, "error": ""}
    return {"label": label, "cmd": [str(path)], "resolved": False, "error": f"File not found: {path}"}


def command_candidate_from_custom(command: str) -> dict:
    path = Path(command)
    if path.exists():
        return {"label": command, "cmd": [str(path)], "resolved": True, "error": ""}
    found = shutil.which(command)
    if found:
        return {"label": command, "cmd": [found], "resolved": True, "error": ""}
    return {"label": command, "cmd": [command], "resolved": False, "error": f"Command not found: {command}"}


def format_command_attempts(attempts: list[dict]) -> str:
    lines: list[str] = []
    for attempt in attempts:
        lines.append(f"- {attempt.get('label')}: {attempt.get('status')}")
        lines.append(f"  command: {attempt.get('command')}")
        if attempt.get("returncode") is not None:
            lines.append(f"  returncode: {attempt.get('returncode')}")
        stdout = str(attempt.get("stdout") or "").strip()
        stderr = str(attempt.get("stderr") or "").strip()
        if stdout:
            lines.append(f"  stdout: {stdout[-2000:]}")
        if stderr:
            lines.append(f"  stderr: {stderr[-2000:]}")
    return "\n".join(lines)


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


def validate_brain_mask(
    mask: np.ndarray,
    shape: tuple[int, ...],
    source: str = "Unknown",
    debug_only: bool = False,
) -> list[str]:
    warnings: list[str] = []
    source_text = str(source)
    if debug_only or source_text.lower().startswith("simple fallback"):
        warnings.append("Simple fallback mask is debug-only and cannot generate final brain-only 3D mesh.")
    if source_text not in {"SynthStrip", "HD-BET"}:
        warnings.append("Mask source must be SynthStrip or HD-BET for final 3D brain mesh.")

    voxels = int(np.count_nonzero(mask))
    total = int(np.prod(shape))
    ratio = voxels / max(total, 1)
    if ratio > 0.28:
        warnings.append("Mask is too large; skull/face/neck may still be included.")
    if ratio < 0.015:
        warnings.append("Mask is very small; brain tissue may be missing.")

    labels = measure.label(mask)
    if labels.max() > 1:
        component_sizes = np.bincount(labels.ravel())
        component_sizes[0] = 0
        largest = int(component_sizes.max()) if component_sizes.size else 0
        fragments = int(np.count_nonzero(component_sizes > max(64, largest * 0.01)))
        if fragments > 1:
            warnings.append("Mask has multiple connected components; skull stripping is not reliable.")

    coords = np.argwhere(mask)
    if coords.size:
        lower = coords.min(axis=0)
        upper = coords.max(axis=0)
        if np.any(lower <= 1) or np.any(upper >= np.array(shape) - 2):
            warnings.append("Mask touches image border; non-brain tissue may remain.")
        extent = (upper - lower + 1) / np.maximum(np.array(shape), 1)
        if np.any(extent > 0.88):
            warnings.append("Mask bounding box is too large; head/skull/neck may still be included.")
        if extent[1] > 0.82:
            warnings.append("Mask extends too far along the superior/inferior axis; neck or skull may be included.")

        center = np.array(shape, dtype=np.float32) / 2.0
        radii = np.maximum(np.array(shape, dtype=np.float32) * 0.12, 1.0)
        grid = np.indices(shape, dtype=np.float32)
        center_region = np.zeros(shape, dtype=np.float32)
        for axis in range(3):
            center_region += ((grid[axis] - center[axis]) / radii[axis]) ** 2
        center_region = center_region <= 1.0
        center_coverage = float(np.count_nonzero(mask & center_region)) / max(int(np.count_nonzero(center_region)), 1)
        if center_coverage < 0.25:
            warnings.append("Mask does not sufficiently include the central brain region.")

        filled = ndi.binary_fill_holes(mask.astype(bool))
        hole_voxels = int(np.count_nonzero(filled & ~mask.astype(bool)))
        hole_ratio = hole_voxels / max(int(np.count_nonzero(filled)), 1)
        if hole_ratio > 0.08:
            warnings.append("Mask has too many internal holes; skull stripping failed.")
    return warnings
