"""
AI CAM 4.0 — Orbit Camera
==========================

Orbit camera with mouse-driven orbit, zoom, and pan.
Produces view and projection matrices for the renderer.

Camera conventions (right-handed, Y-up):
- Orbit: rotates around a target point
- Zoom: moves along the view direction
- Pan: translates perpendicular to view direction

All angles in radians. Matrix output is column-major float32
for direct upload to GLSL uniforms.
"""

from __future__ import annotations

import math
from typing import Final, NamedTuple

import numpy as np
from numpy.typing import NDArray

from app.viewport.gl_constants import (
    CAMERA_DEFAULT_DISTANCE,
    CAMERA_DEFAULT_FOV,
    CAMERA_FAR,
    CAMERA_NEAR,
    CAMERA_ORBIT_SENSITIVITY,
    CAMERA_PAN_SENSITIVITY,
    CAMERA_ZOOM_SENSITIVITY,
)


class CameraState(NamedTuple):
    """Snapshot of camera parameters for external consumers."""
    target: NDArray[np.float32]
    distance: float
    azimuth: float
    elevation: float
    fov: float


class OrbitCamera:
    """Spherical-coordinate orbit camera around a target point.

    Attributes:
        target: World-space point the camera orbits around.
        distance: Distance from target (zoom level).
        azimuth: Horizontal rotation angle (radians).
        elevation: Vertical rotation angle (radians, clamped).
        fov: Field of view in degrees.
        near: Near clipping plane.
        far: Far clipping plane.
        up: World up vector.
    """

    # Elevation clamp limits (prevent gimbal lock at poles)
    MIN_ELEVATION: Final[float] = -math.pi / 2.0 + 0.01
    MAX_ELEVATION: Final[float] = math.pi / 2.0 - 0.01

    # Zoom limits
    MIN_DISTANCE: Final[float] = 0.5
    MAX_DISTANCE: Final[float] = 5000.0

    # Default light direction (normalized)
    DEFAULT_LIGHT_DIR: Final[NDArray[np.float32]] = np.array(
        [0.5, 0.8, 0.6], dtype=np.float32
    )

    def __init__(
        self,
        target: NDArray[np.float32] | None = None,
        distance: float = CAMERA_DEFAULT_DISTANCE,
        azimuth: float = 0.785,  # ~45 degrees
        elevation: float = 0.523,  # ~30 degrees
        fov: float = CAMERA_DEFAULT_FOV,
    ) -> None:
        """Initialize orbit camera.

        Args:
            target: World-space focus point. Defaults to origin.
            distance: Initial distance from target.
            azimuth: Initial horizontal angle (radians).
            elevation: Initial vertical angle (radians).
            fov: Field of view in degrees.
        """
        self.target: NDArray[np.float32] = (
            np.asarray(target, dtype=np.float32)
            if target is not None
            else np.zeros(3, dtype=np.float32)
        )
        self.distance: float = max(self.MIN_DISTANCE, min(self.MAX_DISTANCE, distance))
        self.azimuth: float = azimuth
        self.elevation: float = np.clip(elevation, self.MIN_ELEVATION, self.MAX_ELEVATION)
        self.fov: float = fov
        self.near: float = CAMERA_NEAR
        self.far: float = CAMERA_FAR
        self.up: NDArray[np.float32] = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        # Derived caches (recomputed on parameter change)
        self._view_matrix: NDArray[np.float32] | None = None
        self._projection_matrix: NDArray[np.float32] | None = None
        self._camera_pos: NDArray[np.float32] | None = None
        self._view_direction: NDArray[np.float32] | None = None
        self._dirty: bool = True

    # ------------------------------------------------------------------
    # Camera controls
    # ------------------------------------------------------------------
    def orbit(self, delta_x: float, delta_y: float) -> None:
        """Rotate camera around target. Positive delta_x = orbit right.

        Args:
            delta_x: Horizontal mouse delta (pixels).
            delta_y: Vertical mouse delta (pixels).
        """
        self.azimuth += delta_x * CAMERA_ORBIT_SENSITIVITY
        self.elevation += delta_y * CAMERA_ORBIT_SENSITIVITY
        self.elevation = np.clip(
            self.elevation, self.MIN_ELEVATION, self.MAX_ELEVATION
        )
        # Wrap azimuth to [-pi, pi]
        self.azimuth = math.atan2(math.sin(self.azimuth), math.cos(self.azimuth))
        self._dirty = True

    def zoom(self, factor: float) -> None:
        """Zoom in/out by adjusting distance.

        Args:
            factor: Scroll delta. Positive = zoom in (closer).
        """
        self.distance -= factor * CAMERA_ZOOM_SENSITIVITY * self.distance
        self.distance = max(self.MIN_DISTANCE, min(self.MAX_DISTANCE, self.distance))
        self._dirty = True

    def pan(self, delta_x: float, delta_y: float) -> None:
        """Translate the target point (pan/orbit-dolly).

        Args:
            delta_x: Horizontal mouse delta (pixels).
            delta_y: Vertical mouse delta (pixels).
        """
        cam_pos = self._get_camera_position()
        forward = self._get_view_direction()
        right = np.cross(forward, self.up)
        right_norm = np.linalg.norm(right)
        if right_norm > 1e-8:
            right /= right_norm
        world_up = np.cross(right, forward)
        world_up_norm = np.linalg.norm(world_up)
        if world_up_norm > 1e-8:
            world_up /= world_up_norm

        pan_scale = self.distance * CAMERA_PAN_SENSITIVITY
        self.target -= right * delta_x * pan_scale
        self.target += world_up * delta_y * pan_scale
        self._dirty = True

    def set_target(self, target: NDArray[np.float32]) -> None:
        """Set the orbit target point."""
        self.target = np.asarray(target, dtype=np.float32).copy()
        self._dirty = True

    def set_fov(self, fov: float) -> None:
        """Set field of view in degrees."""
        self.fov = max(1.0, min(179.0, fov))
        self._dirty = True

    def focus_on(self, center: NDArray[np.float32], radius: float) -> None:
        """Frame a bounding sphere: set target and distance to fit.

        Args:
            center: World-space center of the object.
            radius: Bounding radius of the object.
        """
        self.target = np.asarray(center, dtype=np.float32).copy()
        # Distance to fit the sphere in the viewport
        half_fov_rad = math.radians(self.fov / 2.0)
        if half_fov_rad > 1e-6:
            self.distance = max(
                self.MIN_DISTANCE,
                min(self.MAX_DISTANCE, radius / math.sin(half_fov_rad) * 1.2),
            )
        else:
            self.distance = radius * 2.0
        self._dirty = True

    # ------------------------------------------------------------------
    # Matrix generation
    # ------------------------------------------------------------------
    def get_view_matrix(self) -> NDArray[np.float32]:
        """Compute and return the 4x4 view matrix (column-major)."""
        if self._dirty:
            self._recompute()
        return self._view_matrix

    def get_projection_matrix(
        self, aspect: float = 1.0
    ) -> NDArray[np.float32]:
        """Compute and return the 4x4 projection matrix.

        Args:
            aspect: Viewport width/height ratio.
        """
        if self._dirty:
            self._recompute()
        return _perspective_matrix(self.fov, aspect, self.near, self.far)

    def get_camera_position(self) -> NDArray[np.float32]:
        """Return world-space camera position."""
        if self._dirty:
            self._recompute()
        return self._camera_pos

    def get_view_direction(self) -> NDArray[np.float32]:
        """Return normalized view direction (camera → target)."""
        if self._dirty:
            self._recompute()
        return self._view_direction

    def get_state(self) -> CameraState:
        """Snapshot of camera parameters."""
        return CameraState(
            target=self.target.copy(),
            distance=self.distance,
            azimuth=self.azimuth,
            elevation=self.elevation,
            fov=self.fov,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _get_camera_position(self) -> NDArray[np.float32]:
        if self._dirty:
            self._recompute()
        return self._camera_pos

    def _get_view_direction(self) -> NDArray[np.float32]:
        if self._dirty:
            self._recompute()
        return self._view_direction

    def _recompute(self) -> None:
        """Recalculate camera position and cached matrices."""
        # Spherical to Cartesian
        cos_e = math.cos(self.elevation)
        sin_e = math.sin(self.elevation)
        cos_a = math.cos(self.azimuth)
        sin_a = math.sin(self.azimuth)

        offset = np.array(
            [
                self.distance * cos_e * sin_a,
                self.distance * sin_e,
                self.distance * cos_e * cos_a,
            ],
            dtype=np.float32,
        )
        self._camera_pos = self.target + offset

        # View direction (normalized)
        self._view_direction = self.target - self._camera_pos
        view_len = np.linalg.norm(self._view_direction)
        if view_len > 1e-8:
            self._view_direction /= view_len
        else:
            self._view_direction = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        self._view_matrix = _look_at(
            self._camera_pos, self.target, self.up
        )
        self._dirty = False


# ---------------------------------------------------------------------------
# Matrix construction functions
# ---------------------------------------------------------------------------
def _look_at(
    eye: NDArray[np.float32],
    target: NDArray[np.float32],
    up: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Construct a 4x4 look-at view matrix (column-major).

    Args:
        eye: Camera position in world space.
        target: Point the camera looks at.
        up: Up direction (typically [0,1,0]).

    Returns:
        4x4 float32 column-major view matrix.
    """
    f = target - eye
    f_len = np.linalg.norm(f)
    if f_len > 1e-8:
        f /= f_len
    else:
        f = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    s = np.cross(f, up)
    s_len = np.linalg.norm(s)
    if s_len > 1e-8:
        s /= s_len
    else:
        s = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    u = np.cross(s, f)

    mat = np.eye(4, dtype=np.float32)
    mat[0, 0] = s[0]
    mat[1, 0] = s[1]
    mat[2, 0] = s[2]
    mat[0, 1] = u[0]
    mat[1, 1] = u[1]
    mat[2, 1] = u[2]
    mat[0, 2] = -f[0]
    mat[1, 2] = -f[1]
    mat[2, 2] = -f[2]
    mat[3, 0] = -np.dot(s, eye)
    mat[3, 1] = -np.dot(u, eye)
    mat[3, 2] = np.dot(f, eye)

    return np.ascontiguousarray(mat.T, dtype=np.float32)


def _perspective_matrix(
    fov_deg: float, aspect: float, near: float, far: float
) -> NDArray[np.float32]:
    """Construct a 4x4 perspective projection matrix (column-major).

    Args:
        fov_deg: Vertical field of view in degrees.
        aspect: Viewport width / height.
        near: Near clipping plane distance.
        far: Far clipping plane distance.

    Returns:
        4x4 float32 column-major projection matrix.
    """
    if aspect <= 0.0:
        aspect = 1.0

    fov_rad = math.radians(fov_deg)
    f = 1.0 / math.tan(fov_rad / 2.0)

    mat = np.zeros((4, 4), dtype=np.float32)
    mat[0, 0] = f / aspect
    mat[1, 1] = f

    if abs(far - near) > 1e-8:
        mat[2, 2] = (far + near) / (near - far)
        mat[2, 3] = -1.0
        mat[3, 2] = (2.0 * far * near) / (near - far)
    else:
        # Degenerate: near == far — use orthographic-like
        mat[2, 2] = -1.0
        mat[2, 3] = -1.0
        mat[3, 2] = -2.0 * near

    return np.ascontiguousarray(mat.T, dtype=np.float32)
