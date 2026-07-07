from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology

LOGGER = logging.getLogger("aidlc_mri.mesh")
MAX_MESH_AXIS = 128
MAX_PLOTLY_FACES = 240_000


@dataclass
class BrainMesh:
    vertices: np.ndarray
    faces: np.ndarray
    spacing: tuple[float, float, float]
    quality_warnings: list[str] | None = None
    metadata: dict[str, Any] | None = None


def build_brain_mesh_from_mask(
    filled_brain_mask: np.ndarray,
    spacing: tuple[float, float, float] | None = None,
    gaussian_sigma: float = 1.0,
    level: float = 0.5,
    step_size: int = 2,
    apply_mesh_smoothing: bool = True,
    decimate_ratio: float | None = None,
    downsample_factor: int = 2,
    smoothing_iterations: int = 1,
) -> BrainMesh:
    """
    Build a brain surface mesh from a filled brain surface mask only.
    Do not call this with the original MRI volume or a raw mask.
    """
    if filled_brain_mask.ndim != 3:
        raise ValueError(f"Filled brain mask must be 3D, got shape {filled_brain_mask.shape}.")

    spacing = spacing if spacing is not None else (1.0, 1.0, 1.0)
    factor = max(1, int(downsample_factor), int(math.ceil(max(filled_brain_mask.shape) / MAX_MESH_AXIS)))
    step = max(1, int(step_size))
    last_error: Exception | None = None

    for attempt in range(5):
        try:
            mesh_mask = prepare_mesh_mask(filled_brain_mask, factor, gaussian_sigma=gaussian_sigma)
            mesh_spacing = tuple(float(value) * factor for value in spacing)
            LOGGER.info(
                "marching_cubes mask_shape=%s factor=%s step_size=%s voxels=%s",
                mesh_mask.shape,
                factor,
                step,
                int(np.count_nonzero(mesh_mask > 0.5)),
            )
            vertices, faces, _, _ = measure.marching_cubes(
                mesh_mask,
                level=float(level),
                spacing=mesh_spacing,
                step_size=step,
                allow_degenerate=False,
            )
            faces = faces.astype(np.int32)
            vertices = vertices.astype(np.float32)
            LOGGER.info("mesh result vertices=%s faces=%s", len(vertices), len(faces))
            if len(faces) > MAX_PLOTLY_FACES and attempt < 4:
                factor += 1
                step = min(6, step + 1)
                LOGGER.warning("mesh too large for Plotly; retrying with factor=%s step_size=%s", factor, step)
                continue
            faces = remove_degenerate_faces(vertices, faces)
            vertices, faces = compact_mesh(vertices, faces)
            vertices, faces = keep_largest_mesh_component(vertices, faces)
            vertices, faces = process_mesh_with_trimesh(
                vertices,
                faces,
                decimate_ratio=decimate_ratio,
                smoothing_iterations=int(smoothing_iterations) if apply_mesh_smoothing else 0,
            )
            if apply_mesh_smoothing:
                vertices = smooth_vertices(vertices, faces, int(smoothing_iterations))
            quality_warnings = validate_mesh_quality(vertices, faces, tuple(np.array(mesh_mask.shape) * np.array(mesh_spacing)))
            metadata = mesh_component_metadata(faces)
            metadata.update(
                {
                    "surface_mode": "Stable brain mask surface recommended",
                    "gaussian_sigma": float(gaussian_sigma),
                    "step_size": int(step),
                    "downsample_factor": int(factor),
                    "smoothing_iterations": int(smoothing_iterations) if apply_mesh_smoothing else 0,
                }
            )
            return BrainMesh(vertices=vertices, faces=faces, spacing=mesh_spacing, quality_warnings=quality_warnings, metadata=metadata)
        except Exception as exc:
            last_error = exc
            LOGGER.exception("marching_cubes failed with factor=%s step_size=%s", factor, step)
            factor += 1
            step = min(6, step + 1)

    raise RuntimeError(f"Brain mesh generation failed after downsample retries: {last_error}") from last_error


def build_final_brain_mesh_from_mask(
    brain_mask: np.ndarray,
    spacing: tuple[float, float, float] | None = None,
    reliable_mask: bool = False,
    mask_source: str = "",
    brain_mask_path: str | Path | None = None,
    **kwargs: Any,
) -> BrainMesh:
    source = str(mask_source or "").lower()
    path = Path(brain_mask_path) if brain_mask_path is not None else None
    if not reliable_mask or source not in {"synthstrip", "hd-bet", "cached_brain_mask"} or path is None or not path.exists():
        raise ValueError("SynthStrip or HD-BET brain_mask.nii.gz is required for final 3D brain mesh.")
    mask = np.asarray(brain_mask) > 0.5
    return build_brain_mesh_from_mask(mask.astype(np.uint8), spacing=spacing, level=0.5, **kwargs)


def build_mesh_from_mask(
    mask_path: str | Path = "outputs/brain_mask.nii.gz",
    output_path: str | Path = "outputs/brain_only_mesh.glb",
    spacing: tuple[float, float, float] | None = None,
    smooth: bool = True,
) -> dict[str, Any]:
    mask_path = Path(mask_path)
    output_path = Path(output_path)
    info: dict[str, Any] = {
        "mask_path": str(mask_path),
        "output_path": str(output_path),
        "mask_shape": None,
        "mask_unique_values": [],
        "mask_sum": 0,
    }
    try:
        import nibabel as nib  # type: ignore
        import trimesh  # type: ignore

        if not mask_path.exists():
            raise FileNotFoundError(f"Mask file not found: {mask_path}")

        nii = nib.load(str(mask_path))
        data = np.asarray(nii.get_fdata())
        mask = data > 0.5
        unique_values = np.unique(data)
        shown_unique = unique_values[:12]
        info.update(
            {
                "mask_shape": tuple(int(value) for value in mask.shape),
                "mask_unique_values": [json_safe_number(value) for value in shown_unique],
                "mask_sum": int(np.count_nonzero(mask)),
            }
        )
        if info["mask_sum"] == 0:
            raise ValueError("Brain mask is empty after binary thresholding.")

        if spacing is None:
            zooms = tuple(float(value) for value in nii.header.get_zooms()[:3])
            spacing = zooms if len(zooms) == 3 else (1.0, 1.0, 1.0)

        vertices, faces, _, _ = measure.marching_cubes(
            mask.astype(np.float32),
            level=0.5,
            spacing=tuple(float(value) for value in spacing),
            allow_degenerate=False,
        )
        faces = remove_degenerate_faces(vertices.astype(np.float32), faces.astype(np.int32))
        vertices, faces = compact_mesh(vertices.astype(np.float32), faces.astype(np.int32))
        vertices, faces = keep_largest_mesh_component(vertices, faces)

        tri_mesh: Any = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        if smooth:
            try:
                trimesh.smoothing.filter_laplacian(tri_mesh, iterations=3)
            except Exception:
                LOGGER.exception("trimesh smoothing failed; exporting unsmoothed mesh")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tri_mesh.export(str(output_path), file_type="glb")
        return {
            **info,
            "ok": True,
            "status": "ready",
            "message": "3D mesh loaded",
            "mesh_path": str(output_path),
            "vertices": int(len(tri_mesh.vertices)),
            "faces": int(len(tri_mesh.faces)),
        }
    except Exception as exc:
        LOGGER.exception(
            "Mesh generation failed mask_path=%s shape=%s sum=%s output_path=%s",
            mask_path,
            info.get("mask_shape"),
            info.get("mask_sum"),
            output_path,
        )
        return {
            **info,
            "ok": False,
            "status": "failed",
            "message": f"Mesh generation failed: {exc}",
            "mesh_path": None,
            "exception": str(exc),
        }


def json_safe_number(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def build_brain_intensity_mesh_from_volume(
    brain_extracted: np.ndarray,
    brain_mask: np.ndarray,
    spacing: tuple[float, float, float] | None = None,
    iso_percentile: float = 35.0,
    gaussian_sigma: float = 0.2,
    step_size: int = 1,
    apply_mesh_smoothing: bool = True,
    downsample_factor: int = 1,
    smoothing_iterations: int = 1,
) -> BrainMesh:
    """
    Build an intensity iso-surface from skull-stripped brain only.
    This must not be called with an unmasked head volume.
    """
    if brain_extracted.ndim != 3 or brain_mask.ndim != 3:
        raise ValueError("Brain extracted volume and mask must both be 3D.")
    if brain_extracted.shape != brain_mask.shape:
        raise ValueError(f"Volume/mask shape mismatch: {brain_extracted.shape} vs {brain_mask.shape}.")

    spacing = spacing if spacing is not None else (1.0, 1.0, 1.0)
    factor = max(1, int(downsample_factor), int(math.ceil(max(brain_extracted.shape) / MAX_MESH_AXIS)))
    step = max(1, int(step_size))
    last_error: Exception | None = None

    for attempt in range(5):
        try:
            mask = brain_mask[::factor, ::factor, ::factor].astype(bool)
            if np.count_nonzero(mask) == 0:
                raise ValueError("Brain mask is empty.")
            masked_volume = np.asarray(brain_extracted[::factor, ::factor, ::factor], dtype=np.float32).copy()
            masked_volume[~mask] = 0
            if gaussian_sigma > 0:
                masked_volume = ndi.gaussian_filter(masked_volume, sigma=float(gaussian_sigma))
                masked_volume[~mask] = 0
            values = masked_volume[mask]
            values = values[np.isfinite(values)]
            values = values[values > 0]
            if values.size == 0:
                raise ValueError("Brain extracted volume has no positive intensities inside mask.")
            level = float(np.percentile(values, float(iso_percentile)))
            mesh_spacing = tuple(float(value) * factor for value in spacing)
            vertices, faces, _, _ = measure.marching_cubes(
                masked_volume,
                level=level,
                spacing=mesh_spacing,
                step_size=step,
                allow_degenerate=False,
            )
            faces = faces.astype(np.int32)
            vertices = vertices.astype(np.float32)
            if len(faces) > MAX_PLOTLY_FACES and attempt < 4:
                factor += 1
                step = min(6, step + 1)
                continue
            faces = remove_degenerate_faces(vertices, faces)
            vertices, faces = compact_mesh(vertices, faces)
            raw_component_meta = mesh_component_metadata(faces)
            if (
                raw_component_meta.get("components", 0) > 20
                or float(raw_component_meta.get("largest_component_face_ratio", 1.0)) < 0.70
            ):
                raise ValueError(
                    "Experimental intensity surface is fragmented; use Stable brain mask surface recommended."
                )
            vertices, faces = keep_largest_mesh_component(vertices, faces)
            vertices, faces = process_mesh_with_trimesh(
                vertices,
                faces,
                decimate_ratio=None,
                smoothing_iterations=int(smoothing_iterations) if apply_mesh_smoothing else 0,
            )
            if apply_mesh_smoothing:
                vertices = smooth_vertices(vertices, faces, int(smoothing_iterations))
            quality_warnings = validate_mesh_quality(vertices, faces, tuple(np.array(masked_volume.shape) * np.array(mesh_spacing)))
            quality_warnings.append(f"Intensity iso level percentile={float(iso_percentile):.1f}, level={level:.4g}.")
            metadata = mesh_component_metadata(faces)
            metadata.update(
                {
                    "surface_mode": "Experimental intensity surface",
                    "raw_components_before_largest_only": raw_component_meta.get("components", 0),
                    "raw_largest_component_face_ratio": raw_component_meta.get("largest_component_face_ratio", 1.0),
                    "gaussian_sigma": float(gaussian_sigma),
                    "iso_percentile": float(iso_percentile),
                    "iso_level": float(level),
                    "step_size": int(step),
                    "downsample_factor": int(factor),
                    "smoothing_iterations": int(smoothing_iterations) if apply_mesh_smoothing else 0,
                }
            )
            return BrainMesh(vertices=vertices, faces=faces, spacing=mesh_spacing, quality_warnings=quality_warnings, metadata=metadata)
        except Exception as exc:
            last_error = exc
            LOGGER.exception("intensity marching_cubes failed with factor=%s step_size=%s", factor, step)
            factor += 1
            step = min(6, step + 1)

    raise RuntimeError(f"Brain intensity mesh generation failed after downsample retries: {last_error}") from last_error


def build_brain_mesh(
    brain_mask: np.ndarray,
    spacing: tuple[float, float, float],
    downsample_factor: int = 2,
    step_size: int = 2,
    smoothing_iterations: int = 1,
    mask_gaussian_sigma: float = 1.0,
    mesh_smoothing_enabled: bool = True,
) -> BrainMesh:
    return build_brain_mesh_from_mask(
        brain_mask,
        spacing=spacing,
        gaussian_sigma=mask_gaussian_sigma,
        level=0.5,
        step_size=step_size,
        apply_mesh_smoothing=mesh_smoothing_enabled,
        decimate_ratio=None,
        downsample_factor=downsample_factor,
        smoothing_iterations=smoothing_iterations,
    )


def prepare_mesh_mask(brain_mask: np.ndarray, factor: int, gaussian_sigma: float = 1.0) -> np.ndarray:
    mesh_mask = brain_mask[::factor, ::factor, ::factor].astype(bool)
    if np.count_nonzero(mesh_mask) == 0:
        raise ValueError("Filled brain surface mask is empty. Regenerate the filled mask.")
    mesh_mask = ndi.binary_fill_holes(mesh_mask)
    mesh_mask = morphology.remove_small_objects(mesh_mask, min_size=max(64, 10000 // max(1, factor**3)))
    mesh_mask = morphology.remove_small_holes(mesh_mask, area_threshold=max(64, 10000 // max(1, factor**3)))
    mesh_mask = morphology.binary_closing(mesh_mask, morphology.ball(2))
    mesh_mask = ndi.binary_fill_holes(mesh_mask)
    if np.count_nonzero(mesh_mask) == 0:
        raise ValueError("Filled brain surface mask became empty after cleanup.")
    return mesh_mask.astype(np.float32)


def remove_degenerate_faces(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    if len(faces) == 0:
        return faces
    triangles = vertices[faces]
    areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) * 0.5
    valid = areas > 1e-7
    unique_indices = np.array([len(set(face.tolist())) == 3 for face in faces], dtype=bool)
    return faces[valid & unique_indices]


def compact_mesh(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(faces) == 0:
        return vertices, faces
    used = np.unique(faces.ravel())
    inverse = np.full(len(vertices), -1, dtype=np.int32)
    inverse[used] = np.arange(len(used), dtype=np.int32)
    return vertices[used], inverse[faces]


def process_mesh_with_trimesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    decimate_ratio: float | None = None,
    smoothing_iterations: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        import trimesh  # type: ignore
    except Exception:
        return vertices, faces

    try:
        mesh: Any = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        components = mesh.split(only_watertight=False)
        if len(components) > 0:
            mesh = max(components, key=lambda item: len(item.faces))
        if hasattr(mesh, "remove_duplicate_faces"):
            mesh.remove_duplicate_faces()
        if hasattr(mesh, "remove_degenerate_faces"):
            mesh.remove_degenerate_faces()
        if hasattr(mesh, "remove_unreferenced_vertices"):
            mesh.remove_unreferenced_vertices()
        if hasattr(mesh, "fill_holes"):
            mesh.fill_holes()
        mesh.process(validate=True)
        if smoothing_iterations > 0:
            try:
                trimesh.smoothing.filter_laplacian(mesh, iterations=int(smoothing_iterations))
            except Exception:
                LOGGER.exception("trimesh laplacian smoothing failed; continuing without it")
        if decimate_ratio is not None and 0.0 < float(decimate_ratio) < 1.0 and len(mesh.faces) > 1000:
            target_faces = max(1000, int(len(mesh.faces) * float(decimate_ratio)))
            if hasattr(mesh, "simplify_quadric_decimation"):
                mesh = mesh.simplify_quadric_decimation(target_faces)
        return np.asarray(mesh.vertices, dtype=np.float32), np.asarray(mesh.faces, dtype=np.int32)
    except Exception:
        LOGGER.exception("trimesh post-processing failed; continuing with scipy/skimage mesh")
        return vertices, faces


def validate_mesh_quality(vertices: np.ndarray, faces: np.ndarray, physical_shape: tuple[float, float, float]) -> list[str]:
    warnings: list[str] = []
    if len(vertices) == 0 or len(faces) == 0:
        warnings.append("Mesh is empty.")
        return warnings
    components = count_mesh_components(faces)
    if components > 1:
        warnings.append(f"Mesh has {components} connected components; mask may contain fragments or holes.")
    edge_count: dict[tuple[int, int], int] = {}
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (int(min(u, v)), int(max(u, v)))
            edge_count[key] = edge_count.get(key, 0) + 1
    boundary_edges = sum(1 for count in edge_count.values() if count == 1)
    if boundary_edges > max(100, len(faces) * 0.01):
        warnings.append("Mesh has many open boundary edges; holes may remain.")
    lower = vertices.min(axis=0)
    upper = vertices.max(axis=0)
    extent = upper - lower
    if np.any(extent >= np.array(physical_shape, dtype=np.float32) * 0.92):
        warnings.append("Mesh spans most of the preview volume; head/skull tissue may still be included.")
    return warnings


def count_mesh_components(faces: np.ndarray) -> int:
    if len(faces) == 0:
        return 0
    vertex_to_faces: dict[int, list[int]] = {}
    for face_index, face in enumerate(faces):
        for vertex in face:
            vertex_to_faces.setdefault(int(vertex), []).append(face_index)
    seen = np.zeros(len(faces), dtype=bool)
    components = 0
    for start in range(len(faces)):
        if seen[start]:
            continue
        components += 1
        stack = [start]
        seen[start] = True
        while stack:
            face_index = stack.pop()
            for vertex in faces[face_index]:
                for neighbor in vertex_to_faces[int(vertex)]:
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        stack.append(neighbor)
    return components


def mesh_component_metadata(faces: np.ndarray) -> dict[str, float | int]:
    sizes = mesh_component_face_sizes(faces)
    if not sizes:
        return {"components": 0, "largest_component_faces": 0, "largest_component_face_ratio": 0.0}
    largest = max(sizes)
    total = sum(sizes)
    return {
        "components": len(sizes),
        "largest_component_faces": int(largest),
        "largest_component_face_ratio": float(largest / total) if total else 0.0,
    }


def mesh_component_face_sizes(faces: np.ndarray) -> list[int]:
    if len(faces) == 0:
        return []
    vertex_to_faces: dict[int, list[int]] = {}
    for face_index, face in enumerate(faces):
        for vertex in face:
            vertex_to_faces.setdefault(int(vertex), []).append(face_index)
    seen = np.zeros(len(faces), dtype=bool)
    sizes: list[int] = []
    for start in range(len(faces)):
        if seen[start]:
            continue
        count = 0
        stack = [start]
        seen[start] = True
        while stack:
            face_index = stack.pop()
            count += 1
            for vertex in faces[face_index]:
                for neighbor in vertex_to_faces[int(vertex)]:
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        stack.append(neighbor)
        sizes.append(count)
    return sizes


def keep_largest_mesh_component(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(faces) == 0:
        return vertices, faces
    vertex_to_faces: dict[int, list[int]] = {}
    for face_index, face in enumerate(faces):
        for vertex in face:
            vertex_to_faces.setdefault(int(vertex), []).append(face_index)

    seen = np.zeros(len(faces), dtype=bool)
    components: list[list[int]] = []
    for start in range(len(faces)):
        if seen[start]:
            continue
        component: list[int] = []
        stack = [start]
        seen[start] = True
        while stack:
            face_index = stack.pop()
            component.append(face_index)
            for vertex in faces[face_index]:
                for neighbor in vertex_to_faces[int(vertex)]:
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        stack.append(neighbor)
        components.append(component)
    if not components:
        return vertices, faces
    largest = max(components, key=len)
    return compact_mesh(vertices, faces[np.asarray(largest, dtype=np.int32)])


def smooth_vertices(vertices: np.ndarray, faces: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0 or len(vertices) == 0:
        return vertices

    neighbors = [set() for _ in range(len(vertices))]
    for a, b, c in faces:
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))

    smoothed = vertices.copy()
    for _ in range(iterations):
        updated = smoothed.copy()
        for index, items in enumerate(neighbors):
            if items:
                updated[index] = 0.65 * smoothed[index] + 0.35 * np.mean(smoothed[list(items)], axis=0)
        smoothed = updated
    return smoothed


def export_stl(mesh: BrainMesh, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vertices = mesh.vertices
    faces = mesh.faces

    with output_path.open("w", encoding="ascii") as file:
        file.write("solid brain_mesh\n")
        for face in faces:
            tri = vertices[face]
            normal = triangle_normal(tri)
            file.write(f"  facet normal {normal[0]:.6g} {normal[1]:.6g} {normal[2]:.6g}\n")
            file.write("    outer loop\n")
            for vertex in tri:
                file.write(f"      vertex {vertex[0]:.6g} {vertex[1]:.6g} {vertex[2]:.6g}\n")
            file.write("    endloop\n")
            file.write("  endfacet\n")
        file.write("endsolid brain_mesh\n")
    return output_path


def export_glb(mesh: BrainMesh, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import trimesh  # type: ignore
    except Exception as exc:
        raise RuntimeError("GLB export requires trimesh. Install requirements.txt first.") from exc

    tri_mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=True)
    tri_mesh.export(str(output_path), file_type="glb")
    return output_path


def triangle_normal(triangle: np.ndarray) -> np.ndarray:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    norm = float(np.linalg.norm(normal))
    if norm == 0:
        return np.zeros(3, dtype=np.float32)
    return normal / norm
