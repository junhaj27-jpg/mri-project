from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage as ndi
from skimage import measure

LOGGER = logging.getLogger("aidlc_mri.mesh")
MAX_MESH_AXIS = 128
MAX_PLOTLY_FACES = 240_000


@dataclass
class BrainMesh:
    vertices: np.ndarray
    faces: np.ndarray
    spacing: tuple[float, float, float]
    quality_warnings: list[str] | None = None


def build_brain_mesh_from_mask(
    refined_mask: np.ndarray,
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
    Build a brain surface mesh from a refined brain mask only.
    Do not call this with the original MRI volume or a raw mask.
    """
    if refined_mask.ndim != 3:
        raise ValueError(f"Refined brain mask must be 3D, got shape {refined_mask.shape}.")

    spacing = spacing if spacing is not None else (1.0, 1.0, 1.0)
    factor = max(1, int(downsample_factor), int(math.ceil(max(refined_mask.shape) / MAX_MESH_AXIS)))
    step = max(1, int(step_size))
    last_error: Exception | None = None

    for attempt in range(5):
        try:
            mesh_mask = prepare_mesh_mask(refined_mask, factor, gaussian_sigma)
            mesh_spacing = tuple(float(value) * factor for value in spacing)
            LOGGER.info(
                "marching_cubes mask_shape=%s factor=%s step_size=%s voxels=%s",
                mesh_mask.shape,
                factor,
                step,
                int(np.count_nonzero(mesh_mask)),
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
            vertices, faces = process_mesh_with_trimesh(vertices, faces, decimate_ratio=decimate_ratio)
            if apply_mesh_smoothing:
                vertices = smooth_vertices(vertices, faces, int(smoothing_iterations))
            quality_warnings = validate_mesh_quality(vertices, faces, tuple(np.array(mesh_mask.shape) * np.array(mesh_spacing)))
            return BrainMesh(vertices=vertices, faces=faces, spacing=mesh_spacing, quality_warnings=quality_warnings)
        except Exception as exc:
            last_error = exc
            LOGGER.exception("marching_cubes failed with factor=%s step_size=%s", factor, step)
            factor += 1
            step = min(6, step + 1)

    raise RuntimeError(f"Brain mesh generation failed after downsample retries: {last_error}") from last_error


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
        raise ValueError("Brain mask is empty. Lower the threshold or check the input volume.")
    mesh_mask = ndi.binary_fill_holes(mesh_mask)
    mesh_mask = ndi.binary_closing(mesh_mask, iterations=1)
    if np.count_nonzero(mesh_mask) == 0:
        raise ValueError("Brain mask became empty after cleanup.")
    sigma = max(0.0, float(gaussian_sigma))
    if sigma <= 0:
        return mesh_mask.astype(np.float32)
    smooth_mask = ndi.gaussian_filter(mesh_mask.astype(np.float32), sigma=sigma)
    if float(smooth_mask.max()) < 0.5:
        raise ValueError("Smoothed mask is below marching-cubes level 0.5. Reduce mesh mask gaussian sigma.")
    return smooth_mask.astype(np.float32)


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
) -> tuple[np.ndarray, np.ndarray]:
    try:
        import trimesh  # type: ignore
    except Exception:
        return vertices, faces

    try:
        mesh: Any = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        if hasattr(mesh, "remove_duplicate_faces"):
            mesh.remove_duplicate_faces()
        if hasattr(mesh, "remove_degenerate_faces"):
            mesh.remove_degenerate_faces()
        if hasattr(mesh, "fill_holes"):
            mesh.fill_holes()
        mesh.process(validate=True)
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


def triangle_normal(triangle: np.ndarray) -> np.ndarray:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    norm = float(np.linalg.norm(normal))
    if norm == 0:
        return np.zeros(3, dtype=np.float32)
    return normal / norm
