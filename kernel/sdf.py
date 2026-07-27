"""
Signed Distance Field (SDF) engine for AI CAM 4.0 kernel.

Implements Z-map heightfield representation for efficient
tool-part proximity queries and collision detection.

Usage:
    from kernel.sdf import SDFGrid, create_from_mesh
    sdf = create_from_mesh(vertices, faces)
    distance = sdf.query(Vec3(5.0, 5.0, 10.0))
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from kernel.types import Vec3


class SDFGrid:
    """Z-map heightfield signed distance field.

    Represents a 3D volume as a regular grid where each (x, y) cell stores
    the signed distance from the Z-height at that point to the nearest
    surface. Positive = outside the part, negative = inside.

    This is much faster than true 3D SDF for CNC applications where the
    primary concern is Z-height queries.
    """

    def __init__(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        z_heights: np.ndarray,
        resolution: float = 0.5,
    ):
        """Initialize SDFGrid from coordinate arrays and height map.

        Args:
            x_coords: 1D array of X coordinates (sorted ascending).
            y_coords: 1D array of Y coordinates (sorted ascending).
            z_heights: 2D array of shape (len(y), len(x)) with Z heights.
            resolution: Grid spacing in mm.
        """
        self.x_coords = x_coords
        self.y_coords = y_coords
        self.z_heights = z_heights
        self.resolution = resolution

        # Compute bounds
        self.x_min = float(x_coords[0])
        self.x_max = float(x_coords[-1])
        self.y_min = float(y_coords[0])
        self.y_max = float(y_coords[-1])

        self.z_min = float(z_heights.min())
        self.z_max = float(z_heights.max())

        # Build interpolator for fast queries
        self._interpolator: RegularGridInterpolator | None = None

    @property
    def shape(self) -> tuple[int, int]:
        """Grid dimensions (rows, cols)."""
        return (len(self.y_coords), len(self.x_coords))

    def _build_interpolator(self) -> RegularGridInterpolator:
        """Build scipy interpolator for smooth queries."""
        if self._interpolator is None:
            self._interpolator = RegularGridInterpolator(
                (self.y_coords, self.x_coords),
                self.z_heights,
                method="linear",
                bounds_error=False,
                fill_value=None,  # Extrapolate
            )
        return self._interpolator

    def query(self, point: Vec3) -> float:
        """Query the signed distance at a point.

        For a Z-map SDF:
        - Positive distance = point is above the surface (outside part)
        - Negative distance = point is below the surface (inside part)

        Args:
            point: Query point in world coordinates.

        Returns:
            Signed distance value.
        """
        # For Z-map, distance is simply the Z difference from surface height
        interp = self._build_interpolator()

        # Clamp to grid bounds for interpolation
        y = np.clip(point.y, self.y_coords[0], self.y_coords[-1])
        x = np.clip(point.x, self.x_coords[0], self.x_coords[-1])

        z_surface = float(interp([y, x])[0])

        # Positive = above surface, negative = below
        return point.z - z_surface

    def query_height(self, x: float, y: float) -> float:
        """Query the surface Z-height at an (x, y) position.

        Args:
            x: X coordinate.
            y: Y coordinate.

        Returns:
            Interpolated surface Z-height.
        """
        interp = self._build_interpolator()
        y_clamped = np.clip(y, self.y_coords[0], self.y_coords[-1])
        x_clamped = np.clip(x, self.x_coords[0], self.x_coords[-1])
        return float(interp([y_clamped, x_clamped])[0])

    def query_batch(self, points: np.ndarray) -> np.ndarray:
        """Query signed distances for multiple points.

        Args:
            points: Array of shape (N, 3) with [x, y, z] per row.

        Returns:
            Array of signed distance values, shape (N,).
        """
        interp = self._build_interpolator()
        n = len(points)
        results = np.zeros(n, dtype=np.float64)

        for i in range(n):
            y = np.clip(points[i, 1], self.y_coords[0], self.y_coords[-1])
            x = np.clip(points[i, 0], self.x_coords[0], self.x_coords[-1])
            z_surface = float(interp([y, x])[0])
            results[i] = points[i, 2] - z_surface

        return results

    def get_bounds(self) -> tuple[Vec3, Vec3]:
        """Get the bounding box of the SDF grid.

        Returns:
            Tuple of (min_point, max_point).
        """
        return (
            Vec3(self.x_min, self.y_min, self.z_min),
            Vec3(self.x_max, self.y_max, self.z_max),
        )

    def to_heightmap_array(self) -> np.ndarray:
        """Return the raw heightmap as a 2D numpy array."""
        return self.z_heights.copy()

    def __repr__(self) -> str:
        return (
            f"SDFGrid(shape={self.shape}, "
            f"resolution={self.resolution}, "
            f"Z range=[{self.z_min:.2f}, {self.z_max:.2f}])"
        )


def create_from_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    resolution: float = 0.5,
    z_margin: float = 10.0,
) -> SDFGrid:
    """Create an SDFGrid from a triangle mesh.

    Projects triangles onto a regular XY grid and computes the maximum
    Z-height at each grid cell, creating a heightfield representation.

    Args:
        vertices: Vertex positions, shape (N, 3).
        faces: Triangle face indices, shape (M, 3).
        resolution: Grid cell size in mm.
        z_margin: Extra Z margin above/below mesh for the grid bounds.

    Returns:
        SDFGrid with the heightfield data.
    """
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("Empty mesh — cannot create SDF")

    # Compute XY bounds
    x_min, y_min = float(vertices[:, 0].min()), float(vertices[:, 1].min())
    x_max, y_max = float(vertices[:, 0].max()), float(vertices[:, 1].max())
    z_min = float(vertices[:, 2].min())
    z_max = float(vertices[:, 2].max())

    # Create grid coordinates
    x_coords = np.arange(x_min, x_max + resolution, resolution)
    y_coords = np.arange(y_min, y_max + resolution, resolution)

    if len(x_coords) < 2 or len(y_coords) < 2:
        raise ValueError("Mesh too small for given resolution")

    # Initialize heightmap with minimum Z
    heightmap = np.full((len(y_coords), len(x_coords)), z_min - z_margin, dtype=np.float64)

    # Project each triangle onto the grid
    for face in faces:
        v0 = vertices[face[0]]
        v1 = vertices[face[1]]
        v2 = vertices[face[2]]

        # Triangle bounding box in grid coordinates
        tri_x = np.array([v0[0], v1[0], v2[0]])
        tri_y = np.array([v0[1], v1[1], v2[1]])
        tri_z = np.array([v0[2], v1[2], v2[2]])

        tri_x_min_idx = max(0, int((tri_x.min() - x_min) / resolution))
        tri_x_max_idx = min(len(x_coords) - 1, int((tri_x.max() - x_min) / resolution))
        tri_y_min_idx = max(0, int((tri_y.min() - y_min) / resolution))
        tri_y_max_idx = min(len(y_coords) - 1, int((tri_y.max() - y_min) / resolution))

        # For each grid cell in the triangle's bounding box,
        # sample the triangle's Z at that point
        for yi in range(tri_y_min_idx, tri_y_max_idx + 1):
            for xi in range(tri_x_min_idx, tri_x_max_idx + 1):
                px = x_coords[xi]
                py = y_coords[yi]

                z = _sample_triangle_z(v0, v1, v2, px, py)
                if z is not None and z > heightmap[yi, xi]:
                    heightmap[yi, xi] = z

    return SDFGrid(
        x_coords=x_coords,
        y_coords=y_coords,
        z_heights=heightmap,
        resolution=resolution,
    )


def _sample_triangle_z(
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    px: float,
    py: float,
) -> float | None:
    """Sample Z value of a triangle at a given (px, py) position.

    Uses barycentric interpolation. Returns None if the point is
    outside the triangle.
    """
    # Edge vectors
    e1x, e1y = v1[0] - v0[0], v1[1] - v0[1]
    e2x, e2y = v2[0] - v0[0], v2[1] - v0[1]
    dx, dy = px - v0[0], py - v0[1]

    # Barycentric coordinates
    denom = e1x * e2y - e2x * e1y
    if abs(denom) < 1e-12:
        return None

    u = (dx * e2y - e2x * dy) / denom
    v = (e1x * dy - dx * e1y) / denom

    # Check if point is inside triangle
    if u < -1e-6 or v < -1e-6 or (u + v) > 1.0 + 1e-6:
        return None

    # Interpolate Z
    return float((1 - u - v) * v0[2] + u * v1[2] + v * v2[2])
