"""
AI CAM 4.0 — Viewport Overlays
================================

Status HUD, orientation cube, and grid renderer.
Drawn after the main 3D scene using GL_LINE primitives
and simple solid-color shaders.

Key constraints:
- All GL operations on main thread only
- None-guards on VAO/VBO before every draw call
- Overlays draw in screen space (orthographic projection)
- Grid draws in world space (perspective projection)
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core

from app.viewport.camera import OrbitCamera
from app.viewport.gl_constants import (
    COLOR_AXIS_X,
    COLOR_AXIS_Y,
    COLOR_AXIS_Z,
    COLOR_GRID_MAJOR,
    COLOR_GRID_MINOR,
    COLOR_OVERLAY_TEXT,
    GRID_SIZE,
    GRID_SPACING,
    FPS_SAMPLE_COUNT,
)
from app.viewport.renderer import ViewportRenderer
from app.viewport.renderer_utils import (
    compute_normal_matrix,
    set_uniform_mat4,
    set_uniform_vec4,
)

logger = logging.getLogger(__name__)


class StatusOverlay:
    """Displays FPS and camera information as text overlay.

    Uses QPainter for text rendering (not GL) so this doesn't need
    a GL context. The shell.py calls paint_status() during paintGL.
    """

    def __init__(self) -> None:
        """Initialize FPS calculation state."""
        self._frame_times: list[float] = []
        self._last_time: float = time.monotonic()
        self._fps: float = 0.0
        self._visible: bool = True

    def update(self) -> None:
        """Call once per frame to update FPS calculation."""
        now = time.monotonic()
        dt = now - self._last_time
        self._last_time = now

        self._frame_times.append(dt)
        if len(self._frame_times) > FPS_SAMPLE_COUNT:
            self._frame_times.pop(0)

        if len(self._frame_times) > 1:
            avg_dt = sum(self._frame_times) / len(self._frame_times)
            self._fps = 1.0 / avg_dt if avg_dt > 0 else 0.0

    @property
    def fps(self) -> float:
        """Current frames per second (smoothed)."""
        return self._fps

    @property
    def visible(self) -> bool:
        """Whether the status overlay is visible."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = value

    def get_status_text(self, camera: OrbitCamera) -> str:
        """Generate status text string for overlay.

        Args:
            camera: Current camera state.

        Returns:
            Multi-line status string.
        """
        if not self._visible:
            return ""

        cam_pos = camera.get_camera_position()
        lines = [
            f"FPS: {self._fps:.0f}",
            f"Camera: ({cam_pos[0]:.1f}, {cam_pos[1]:.1f}, {cam_pos[2]:.1f})",
            f"Distance: {camera.distance:.1f}",
            f"FOV: {camera.fov:.0f}°",
        ]
        return "\n".join(lines)


class OrientationCube:
    """Small orientation indicator showing XYZ axes.

    Draws a fixed-size set of colored lines in a corner of the
    viewport to show the current camera orientation relative to
    world axes.
    """

    def __init__(self) -> None:
        """Initialize orientation cube state."""
        self._vao: Optional[int] = None
        self._vbo: Optional[int] = None
        self._color_vbo: Optional[int] = None
        self._needs_upload: bool = True
        self._visible: bool = True
        self._size: float = 0.15  # Fraction of viewport

        # Axis endpoint data: 3 lines, 2 vertices each = 6 vertices
        # Each vertex: position (3) + color (4)
        self._build_geometry()

    def _build_geometry(self) -> None:
        """Build axis line geometry."""
        # Origin + 3 axis endpoints
        # Each line: [start_x, start_y, start_z, r, g, b, a, end_x, end_y, end_z, r, g, b, a]
        s = 1.0  # Unit length, scaled by projection
        data = np.array([
            # X axis (red)
            0, 0, 0, *COLOR_AXIS_X,
            s, 0, 0, *COLOR_AXIS_X,
            # Y axis (green)
            0, 0, 0, *COLOR_AXIS_Y,
            0, s, 0, *COLOR_AXIS_Y,
            # Z axis (blue)
            0, 0, 0, *COLOR_AXIS_Z,
            0, 0, s, *COLOR_AXIS_Z,
        ], dtype=np.float32)
        self._geometry = data
        self._vertex_count = 6

    def upload_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Upload orientation cube geometry to GPU."""
        if not self._needs_upload:
            return

        r = ViewportRenderer()

        # Clean old
        if self._vao:
            r.safe_delete_vertex_array(gl, self._vao)
        if self._vbo:
            r.safe_delete_buffers(gl, self._vbo)

        self._vbo = r.create_vbo(gl, self._geometry)
        if self._vbo is None:
            return

        # Create VAO: position (loc=0, size=3, stride=28, offset=0)
        #              color    (loc=1, size=4, stride=28, offset=12)
        vao_list = [0]
        gl.glGenVertexArrays(1, vao_list)
        self._vao = vao_list[0]
        if self._vao == 0:
            return

        stride = 7 * 4  # 7 floats * 4 bytes = 28 bytes
        gl.glBindVertexArray(self._vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo)

        # Position attribute
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, stride, 0)
        # Color attribute
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 4, gl.GL_FLOAT, gl.GL_FALSE, stride, 12)

        gl.glBindVertexArray(0)
        self._needs_upload = False

    def draw(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
        camera: OrbitCamera,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        """Draw the orientation indicator in bottom-left corner.

        Args:
            gl: OpenGL functions handle.
            renderer: ViewportRenderer for shader programs.
            camera: Current camera (for view rotation).
            viewport_width: Viewport width in pixels.
            viewport_height: Viewport height in pixels.
        """
        if not self._visible:
            return
        if self._vao is None or self._vao == 0:
            if self._needs_upload:
                self.upload_gl(gl)
            if self._vao is None or self._vao == 0:
                return

        program = renderer.use_solid_program(gl)
        if program is None:
            return

        # Compute position in NDC (bottom-left corner)
        margin = 40
        size_px = min(viewport_width, viewport_height) * self._size
        cx = margin + size_px / 2
        cy = margin + size_px / 2

        # Build a small orthographic projection for the indicator
        # Map the indicator's local space to a small corner of the viewport
        aspect = viewport_width / max(viewport_height, 1)
        ndc_cx = (2.0 * cx / viewport_width - 1.0) * aspect
        ndc_cy = 2.0 * cy / viewport_height - 1.0

        # View rotation only (no translation) — extracts orientation
        view = camera.get_view_matrix()
        # Remove translation (set last column to identity)
        view_rot = view.copy()
        view_rot[3, 0] = 0
        view_rot[3, 1] = 0
        view_rot[3, 2] = 0
        view_rot[3, 3] = 1.0

        # Orthographic projection for the indicator
        scale = size_px / 2.0
        proj = np.eye(4, dtype=np.float32)
        proj[0, 0] = 2.0 * aspect / (viewport_width * self._size)
        proj[1, 1] = 2.0 / (viewport_height * self._size)
        proj[3, 0] = ndc_cx
        proj[3, 1] = ndc_cy

        mvp = proj @ view_rot

        set_uniform_mat4(gl, program, "u_mvp", mvp)

        # Set per-vertex colors via VBO (solid shader uses u_color,
        # but we want per-axis colors, so we use a slight trick:
        # Draw each axis separately)
        gl.glBindVertexArray(self._vao)
        gl.glLineWidth(3.0)

        # Draw X axis (first 2 vertices)
        for axis, color in enumerate([COLOR_AXIS_X, COLOR_AXIS_Y, COLOR_AXIS_Z]):
            set_uniform_vec4(gl, program, "u_color", color)
            gl.glDrawArrays(gl.GL_LINES, axis * 2, 2)

        gl.glLineWidth(1.0)
        gl.glBindVertexArray(0)

    def cleanup_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Release GL resources."""
        r = ViewportRenderer()
        if self._vao:
            r.safe_delete_vertex_array(gl, self._vao)
        if self._vbo:
            r.safe_delete_buffers(gl, self._vbo)
        self._vao = None
        self._vbo = None


class GridRenderer:
    """Renders the ground-plane grid with major/minor lines.

    The grid is drawn in world space using the lit shader's
    solid-color mode (via the solid shader program).
    """

    def __init__(
        self,
        size: int = GRID_SIZE,
        spacing: float = GRID_SPACING,
    ) -> None:
        """Initialize grid renderer.

        Args:
            size: Number of grid cells in each direction (half-size).
            spacing: World units per grid cell.
        """
        self._size = size
        self._spacing = spacing

        # GL resources
        self._vao_major: Optional[int] = None
        self._vbo_major: Optional[int] = None
        self._major_count: int = 0

        self._vao_minor: Optional[int] = None
        self._vbo_minor: Optional[int] = None
        self._minor_count: int = 0

        self._needs_upload: bool = True
        self._visible: bool = True

        # Model matrix (identity — grid is in world space)
        self._model: NDArray[np.float32] = np.eye(4, dtype=np.float32)

    def upload_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Upload grid geometry to GPU."""
        if not self._needs_upload:
            return

        r = ViewportRenderer()

        # Clean old
        for vao, vbo in [
            (self._vao_major, self._vbo_major),
            (self._vao_minor, self._vbo_minor),
        ]:
            if vao:
                r.safe_delete_vertex_array(gl, vao)
            if vbo:
                r.safe_delete_buffers(gl, vbo)

        extent = self._size * self._spacing

        # Major lines (every 5th line)
        major_lines = []
        for i in range(-self._size, self._size + 1):
            if i % 5 == 0:
                w = i * self._spacing
                # Line along X
                major_lines.extend([-extent, 0.0, w, extent, 0.0, w])
                # Line along Z
                major_lines.extend([w, 0.0, -extent, w, 0.0, extent])

        if major_lines:
            major_data = np.array(major_lines, dtype=np.float32)
            self._vbo_major = r.create_vbo(gl, major_data)
            self._major_count = len(major_lines) // 3

            if self._vbo_major:
                vao_list = [0]
                gl.glGenVertexArrays(1, vao_list)
                self._vao_major = vao_list[0]
                if self._vao_major:
                    gl.glBindVertexArray(self._vao_major)
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo_major)
                    gl.glEnableVertexAttribArray(0)
                    gl.glVertexAttribPointer(
                        0, 3, gl.GL_FLOAT, gl.GL_FALSE, 12, 0
                    )
                    gl.glBindVertexArray(0)

        # Minor lines
        minor_lines = []
        for i in range(-self._size, self._size + 1):
            if i % 5 != 0:
                w = i * self._spacing
                minor_lines.extend([-extent, 0.0, w, extent, 0.0, w])
                minor_lines.extend([w, 0.0, -extent, w, 0.0, extent])

        if minor_lines:
            minor_data = np.array(minor_lines, dtype=np.float32)
            self._vbo_minor = r.create_vbo(gl, minor_data)
            self._minor_count = len(minor_lines) // 3

            if self._vbo_minor:
                vao_list = [0]
                gl.glGenVertexArrays(1, vao_list)
                self._vao_minor = vao_list[0]
                if self._vao_minor:
                    gl.glBindVertexArray(self._vao_minor)
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo_minor)
                    gl.glEnableVertexAttribArray(0)
                    gl.glVertexAttribPointer(
                        0, 3, gl.GL_FLOAT, gl.GL_FALSE, 12, 0
                    )
                    gl.glBindVertexArray(0)

        self._needs_upload = False
        logger.info(
            "Grid uploaded: %d major + %d minor lines",
            self._major_count // 2, self._minor_count // 2,
        )

    def draw(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
    ) -> None:
        """Draw the grid. None-guarded on all GL resources."""
        if not self._visible:
            return

        if self._needs_upload:
            self.upload_gl(gl)

        program = renderer.use_solid_program(gl)
        if program is None:
            return

        # Draw minor lines first (fainter)
        if self._vao_minor and self._vao_minor != 0 and self._minor_count > 0:
            set_uniform_vec4(gl, program, "u_color", COLOR_GRID_MINOR)
            gl.glBindVertexArray(self._vao_minor)
            gl.glLineWidth(1.0)
            gl.glDrawArrays(gl.GL_LINES, 0, self._minor_count)
            gl.glBindVertexArray(0)

        # Draw major lines on top
        if self._vao_major and self._vao_major != 0 and self._major_count > 0:
            set_uniform_vec4(gl, program, "u_color", COLOR_GRID_MAJOR)
            gl.glBindVertexArray(self._vao_major)
            gl.glLineWidth(1.0)
            gl.glDrawArrays(gl.GL_LINES, 0, self._major_count)
            gl.glBindVertexArray(0)

    def cleanup_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Release GL resources."""
        r = ViewportRenderer()
        for vao, vbo in [
            (self._vao_major, self._vbo_major),
            (self._vao_minor, self._vbo_minor),
        ]:
            if vao:
                r.safe_delete_vertex_array(gl, vao)
            if vbo:
                r.safe_delete_buffers(gl, vbo)

        self._vao_major = self._vbo_major = None
        self._vao_minor = self._vbo_minor = None
