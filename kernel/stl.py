"""
STL file parser for AI CAM 4.0 kernel.

Supports both binary and ASCII STL formats with automatic format detection.
Validates and fixes inverted face normals.

Usage:
    from kernel.stl import parse_stl
    mesh = parse_stl("part.stl")
    # mesh = {"vertices": np.ndarray, "normals": np.ndarray, "faces": np.ndarray}
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


def parse_stl(path: str | Path) -> dict:
    """Parse an STL file (binary or ASCII) and return mesh data.

    Args:
        path: Path to the STL file.

    Returns:
        Dict with keys:
            - 'vertices': np.ndarray of shape (N, 3) — unique vertex positions
            - 'normals': np.ndarray of shape (M, 3) — per-face normals
            - 'faces': np.ndarray of shape (M, 3) — triangle vertex indices

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file format is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"STL file not found: {path}")

    # Try binary first (more reliable detection)
    try:
        return _parse_binary_stl(path)
    except (ValueError, struct.error):
        pass

    # Fall back to ASCII
    try:
        return _parse_ascii_stl(path)
    except ValueError:
        pass

    raise ValueError(f"Unable to parse STL file: {path}")


def _parse_binary_stl(path: Path) -> dict:
    """Parse a binary STL file.

    Binary STL format:
        80 bytes   — header (ignored)
        4 bytes    — uint32 triangle count
        Per triangle (50 bytes each):
            12 bytes — float32x3 normal vector
            36 bytes — float32x3 x 3 vertices
            2 bytes  — uint16 attribute byte count (ignored)
    """
    with open(path, "rb") as f:
        # Skip 80-byte header
        f.read(80)

        # Read triangle count
        num_triangles = struct.unpack("<I", f.read(4))[0]

        if num_triangles == 0:
            raise ValueError("STL file contains zero triangles")

        if num_triangles > 10_000_000:
            raise ValueError(f"Suspicious triangle count: {num_triangles}")

        # Read all triangles
        normals = np.zeros((num_triangles, 3), dtype=np.float64)
        vertices_raw = np.zeros((num_triangles * 3, 3), dtype=np.float64)

        for i in range(num_triangles):
            data = f.read(50)
            if len(data) < 50:
                raise ValueError(f"Unexpected end of file at triangle {i}")

            # Unpack normal (3 floats)
            normals[i] = struct.unpack_from("<fff", data, 0)
            # Unpack 3 vertices (9 floats)
            for j in range(3):
                offset = 12 + j * 12
                vertices_raw[i * 3 + j] = struct.unpack_from("<fff", data, offset)

    return _build_mesh(normals, vertices_raw, num_triangles)


def _parse_ascii_stl(path: Path) -> dict:
    """Parse an ASCII STL file.

    ASCII STL format:
        solid name
          facet normal ni nj nk
            outer loop
              vertex v1x v1y v1z
              vertex v2x v2y v2z
              vertex v3x v3y v3z
            endloop
          endfacet
        endsolid name
    """
    normals_list: list[list[float]] = []
    vertices_list: list[list[float]] = []

    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("Empty ASCII STL file")

    # Check it starts with 'solid'
    first_line = lines[0].strip().lower()
    if not first_line.startswith("solid"):
        raise ValueError("Not a valid ASCII STL file")

    i = 1
    while i < len(lines):
        line = lines[i].strip().lower()

        if line.startswith("facet normal"):
            parts = line.split()
            if len(parts) >= 5:
                normal = [float(parts[2]), float(parts[3]), float(parts[4])]
            else:
                normal = [0.0, 0.0, 1.0]
            normals_list.append(normal)

            # Find the 3 vertices
            verts = []
            i += 1
            while i < len(lines) and len(verts) < 3:
                vline = lines[i].strip().lower()
                if vline.startswith("vertex"):
                    parts = vline.split()
                    if len(parts) >= 4:
                        verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                i += 1

            if len(verts) == 3:
                vertices_list.extend(verts)

        i += 1

    if not normals_list:
        raise ValueError("No triangles found in ASCII STL")

    normals = np.array(normals_list, dtype=np.float64)
    vertices_raw = np.array(vertices_list, dtype=np.float64)
    num_triangles = len(normals_list)

    return _build_mesh(normals, vertices_raw, num_triangles)


def _build_mesh(
    normals: np.ndarray,
    vertices_raw: np.ndarray,
    num_triangles: int,
) -> dict:
    """Build mesh dict from raw normals and vertex data.

    - Deduplicates vertices and builds face index array.
    - Validates and fixes inverted normals (ensures outward-facing).
    """
    # Build face index array with unique vertices
    vertices_unique, face_indices = _deduplicate_vertices(vertices_raw)

    # Fix inverted normals
    normals = _fix_inverted_normals(normals, vertices_unique, face_indices)

    return {
        "vertices": vertices_unique,
        "normals": normals,
        "faces": face_indices,
    }


def _deduplicate_vertices(
    vertices: np.ndarray,
    tolerance: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Deduplicate vertices and return (unique_vertices, face_indices).

    Args:
        vertices: Raw vertex array of shape (N*3, 3) — triples of vertices per face.
        tolerance: Distance threshold for considering vertices equal.

    Returns:
        Tuple of (unique_vertices, face_indices) where face_indices is (N, 3).
    """
    num_triangles = len(vertices) // 3
    unique_list: list[np.ndarray] = []
    index_map: dict[int, int] = {}
    face_indices = np.zeros((num_triangles, 3), dtype=np.int32)

    for i in range(len(vertices)):
        pt = vertices[i]

        # Find existing match
        found_idx = -1
        for j, existing in enumerate(unique_list):
            if np.linalg.norm(pt - existing) < tolerance:
                found_idx = j
                break

        if found_idx == -1:
            found_idx = len(unique_list)
            unique_list.append(pt)

        face_indices[i // 3, i % 3] = found_idx

    unique_vertices = np.array(unique_list, dtype=np.float64) if unique_list else np.zeros((0, 3))
    return unique_vertices, face_indices


def _fix_inverted_normals(
    normals: np.ndarray,
    vertices: np.ndarray,
    faces: np.ndarray,
) -> np.ndarray:
    """Fix inverted face normals to ensure consistent outward orientation.

    Uses the cross product of two edges to determine the geometric normal,
    then flips if it opposes the stored normal.
    """
    if len(faces) == 0:
        return normals

    fixed = normals.copy()

    for i in range(len(faces)):
        v0 = vertices[faces[i, 0]]
        v1 = vertices[faces[i, 1]]
        v2 = vertices[faces[i, 2]]

        # Compute geometric normal via cross product
        edge1 = v1 - v0
        edge2 = v2 - v0
        geo_normal = np.cross(edge1, edge2)

        geo_norm = np.linalg.norm(geo_normal)
        if geo_norm < 1e-12:
            # Degenerate triangle, skip
            continue

        geo_normal /= geo_norm
        stored_norm = normals[i]
        stored_mag = np.linalg.norm(stored_norm)

        if stored_mag < 1e-12:
            # No stored normal, use geometric
            fixed[i] = geo_normal
        else:
            stored_normalized = stored_norm / stored_mag
            # If dot product is negative, normal is inverted
            if np.dot(stored_normalized, geo_normal) < 0:
                fixed[i] = -stored_norm

    return fixed


def get_mesh_info(mesh: dict) -> str:
    """Return a human-readable summary of mesh data.

    Args:
        mesh: Dict returned by parse_stl().

    Returns:
        Multi-line string with mesh statistics.
    """
    vertices = mesh["vertices"]
    normals = mesh["normals"]
    faces = mesh["faces"]

    # Compute bounding box
    if len(vertices) > 0:
        min_pt = vertices.min(axis=0)
        max_pt = vertices.max(axis=0)
        size = max_pt - min_pt
    else:
        min_pt = max_pt = size = np.zeros(3)

    # Compute surface area
    total_area = 0.0
    for face in faces:
        v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        cross = np.cross(v1 - v0, v2 - v0)
        total_area += 0.5 * np.linalg.norm(cross)

    return (
        f"STL Mesh Info:\n"
        f"  Vertices: {len(vertices)}\n"
        f"  Faces: {len(faces)}\n"
        f"  Bounding Box: ({min_pt[0]:.3f}, {min_pt[1]:.3f}, {min_pt[2]:.3f}) "
        f"→ ({max_pt[0]:.3f}, {max_pt[1]:.3f}, {max_pt[2]:.3f})\n"
        f"  Size: {size[0]:.3f} × {size[1]:.3f} × {size[2]:.3f} mm\n"
        f"  Surface Area: {total_area:.2f} mm²"
    )
