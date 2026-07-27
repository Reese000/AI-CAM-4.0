"""
AI CAM 4.0 — Mesh + Toolpath Renderer
=======================================

Renders STL meshes and toolpath lines. Separate from the stock
renderer because meshes use indexed drawing while toolpaths
use line strip drawing.

Key constraints:
- All GL operations on main thread only
- None-guards on VAO/VBO/IBO before every GL call
- Shader errors logged, never silently swallowed
- Uploads happen lazily on first draw (when GL context is ready)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core

from app.viewport.gl_constants import (
    COLOR_MESH,
    COLOR_RAPID,
    COLOR_TOOLPATH,
    NORMAL_OFFSET,
    POSITION_OFFSET,
    VERTEX_STRIDE,
)
from app.viewport.renderer import ViewportRenderer

logger = logging.getLogger(__name__)


class MeshData:
    """CPU-side mesh data before GPU upload."""

    __slots__ = ("vertices", "indices", "index_count", "label")

    def __init__(
        self,
        vertices: NDArray[np.float32],
        indices: NDArray[np.uint32],
        label: str = "mesh",
    ) -> None:
        self.vertices = vertices
        self.indices = indices
        self.index_count = len(indices)
        self.label = label


class ToolpathData:
    """CPU-side toolpath data before GPU upload."""

    __slots__ = ("positions", "color", "line_width", "is_rapid", "point_count")

    def __init__(
        self,
        positions: NDArray[np.float32],
        color: NDArray[np.float32] | None = None,
        line_width: float = 2.0,
        is_rapid: bool = False,
    ) -> None:
        self.positions = np.ascontiguousarray(positions, dtype=np.float32)
        self.color = (
            color if color is not None
            else (COLOR_RAPID.copy() if is_rapid else COLOR_TOOLPATH.copy())
        )
        self.line_width = line_width
        self.is_rapid = is_rapid
        self.point_count = len(self.positions) // 3


class MeshRenderer:
    """Renders STL meshes and toolpath lines.

    Supports multiple meshes and toolpaths, each with its own VAO/VBO.
    Draw order: meshes first (opaque), then toolpaths (lines).

    Usage:
        renderer = MeshRenderer()
        renderer.upload_mesh(vertices, normals, faces)
        renderer.upload_toolpath(toolpath_positions)
        # In paintGL:
        renderer.draw(gl, viewport_renderer)
    """

    def __init__(self) -> None:
        """Initialize renderer. No GL calls until draw()."""
        # Mesh GL resources
        self._mesh_vao: Optional[int] = None
        self._mesh_vbo: Optional[int] = None
        self._mesh_ibo: Optional[int] = None
        self._mesh_index_count: int = 0
        self._mesh_color: NDArray[np.float32] = COLOR_MESH.copy()

        # Toolpath GL resources (all toolpaths share one VBO for simplicity)
        self._toolpath_vao: Optional[int] = None
        self._toolpath_vbo: Optional[int] = None
        self._toolpath_point_count: int = 0
        self._toolpath_color: NDArray[np.float32] = COLOR_TOOLPATH.copy()
        self._toolpath_line_width: float = 2.0

        # Rapid (retract) paths
        self._rapid_vao: Optional[int] = None
        self._rapid_vbo: Optional[int] = None
        self._rapid_point_count: int = 0
        self._rapid_color: NDArray[np.float32] = COLOR_RAPID.copy()
        self._rapid_line_width: float = 1.0

        # Model matrices
        self._mesh_model: NDArray[np.float32] = np.eye(4, dtype=np.float32)
        self._toolpath_model: NDArray[np.float32] = np.eye(4, dtype=np.float32)

        # Upload flags
        self._mesh_needs_upload: bool = False
        self._toolpath_needs_upload: bool = False
        self._rapid_needs_upload: bool = False

        # CPU data cache
        self._mesh_data: Optional[MeshData] = None
        self._toolpath_data: Optional[ToolpathData] = None
        self._rapid_data: Optional[ToolpathData] = None

    # ------------------------------------------------------------------
    # Mesh upload
    # ------------------------------------------------------------------
    def upload_mesh(
        self,
        vertices: NDArray[np.float32],
        normals: NDArray[np.float32],
        faces: NDArray[np.uint32],
        color: NDArray[np.float32] | None = None,
    ) -> None:
        """Upload a triangle mesh. Data is stored CPU-side; GL upload on first draw.

        Args:
            vertices: Flat position array, shape (N, 3).
            normals: Normal array, shape (N, 3). Must match vertex count.
            faces: Triangle index array, shape (M, 3) or flat (M*3,).
            color: Optional RGB/RGBA color override.
        """
        if vertices is None or len(vertices) == 0:
            logger.warning("upload_mesh: empty vertices, skipping")
            return
        if normals is None or len(normals) == 0:
            logger.warning("upload_mesh: empty normals, skipping")
            return

        vertices = np.asarray(vertices, dtype=np.float32)
        normals = np.asarray(normals, dtype=np.float32)
        faces = np.asarray(faces, dtype=np.uint32).ravel()

        # Validate normals match vertex count
        if len(normals) != len(vertices):
            logger.error(
                "upload_mesh: normals count (%d) != vertices count (%d)",
                len(normals), len(vertices),
            )
            return

        # Interleave position + normal
        interleaved = np.zeros((len(vertices), 6), dtype=np.float32)
        interleaved[:, 0:3] = vertices
        interleaved[:, 3:6] = normals

        self._mesh_data = MeshData(interleaved, faces, "mesh")
        self._mesh_index_count = self._mesh_data.index_count
        if color is not None:
            self._mesh_color = np.asarray(color[:4], dtype=np.float32)

        self._mesh_needs_upload = True
        logger.info(
            "Mesh queued for upload: %d vertices, %d triangles",
            len(vertices), len(faces) // 3,
        )

    def set_toolpath_model(self, model: NDArray[np.float32]) -> None:
        """Set the model matrix for toolpath lines."""
        self._toolpath_model = np.ascontiguousarray(model, dtype=np.float32)

    def set_mesh_model(self, model: NDArray[np.float32]) -> None:
        """Set the model matrix for the mesh."""
        self._mesh_model = np.ascontiguousarray(model, dtype=np.float32)

    # ------------------------------------------------------------------
    # Toolpath upload
    # ------------------------------------------------------------------
    def upload_toolpath(
        self,
        toolpath_data: NDArray[np.float32],
        color: NDArray[np.float32] | None = None,
        line_width: float = 2.0,
        is_rapid: bool = False,
    ) -> None:
        """Upload toolpath line data. Flat float32 array of xyz positions.

        Args:
            toolpath_data: Flat position array [x1,y1,z1, x2,y2,z2, ...].
            color: Optional RGBA color.
            line_width: Line width in pixels.
            is_rapid: True for rapid (retract) moves, uses different color.
        """
        if toolpath_data is None or len(toolpath_data) == 0:
            logger.warning("upload_toolpath: empty data, skipping")
            return

        positions = np.ascontiguousarray(toolpath_data, dtype=np.float32).ravel()
        if len(positions) % 3 != 0:
            logger.error(
                "upload_toolpath: position count not divisible by 3 (%d)",
                len(positions),
            )
            return

        data = ToolpathData(positions, color, line_width, is_rapid)

        if is_rapid:
            self._rapid_data = data
            self._rapid_point_count = data.point_count
            self._rapid_needs_upload = True
        else:
            self._toolpath_data = data
            self._toolpath_point_count = data.point_count
            self._toolpath_needs_upload = True

        logger.info(
            "Toolpath queued: %d points, rapid=%s, width=%.1f",
            data.point_count, is_rapid, line_width,
        )

    def clear_toolpaths(self) -> None:
        """Remove all toolpath data. Does NOT delete GL resources (call cleanup_gl first)."""
        self._toolpath_data = None
        self._rapid_data = None
        self._toolpath_needs_upload = True
        self._rapid_needs_upload = True

    # ------------------------------------------------------------------
    # GL upload
    # ------------------------------------------------------------------
    def _upload_mesh_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Upload mesh data to GPU."""
        if self._mesh_data is None:
            return

        r = ViewportRenderer()

        # Clean old resources
        if self._mesh_vao:
            r.safe_delete_vertex_array(gl, self._mesh_vao)
        if self._mesh_vbo:
            r.safe_delete_buffers(gl, self._mesh_vbo)
        if self._mesh_ibo:
            r.safe_delete_buffers(gl, self._mesh_ibo)

        self._mesh_vbo = r.create_vbo(gl, self._mesh_data.vertices)
        self._mesh_ibo = r.create_ibo(gl, self._mesh_data.indices)

        if self._mesh_vbo and self._mesh_ibo:
            self._mesh_vao = r.create_vao(
                gl, self._mesh_vbo, VERTEX_STRIDE,
                [
                    (0, 3, POSITION_OFFSET),
                    (1, 3, NORMAL_OFFSET),
                ],
                ibo=self._mesh_ibo,
            )

        self._mesh_index_count = self._mesh_data.index_count
        self._mesh_needs_upload = False

        if self._mesh_vao:
            logger.info("Mesh GL upload complete: %d triangles", self._mesh_index_count // 3)

    def _upload_toolpath_gl(
        self, gl: QOpenGLFunctions_3_3_Core, is_rapid: bool = False
    ) -> None:
        """Upload toolpath data to GPU."""
        data = self._rapid_data if is_rapid else self._toolpath_data
        if data is None or data.point_count < 2:
            return

        r = ViewportRenderer()

        if is_rapid:
            if self._rapid_vao:
                r.safe_delete_vertex_array(gl, self._rapid_vao)
            if self._rapid_vbo:
                r.safe_delete_buffers(gl, self._rapid_vbo)
        else:
            if self._toolpath_vao:
                r.safe_delete_vertex_array(gl, self._toolpath_vao)
            if self._toolpath_vbo:
                r.safe_delete_buffers(gl, self._toolpath_vbo)

        vbo = r.create_vbo(gl, data.positions)
        if vbo is None:
            return

        # Toolpath: position-only (location=0, size=3, stride=12)
        vao_list = [0]
        gl.glGenVertexArrays(1, vao_list)
        vao = vao_list[0]
        if vao == 0:
            r.safe_delete_buffers(gl, vbo)
            return

        gl.glBindVertexArray(vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, 12, 0)
        gl.glBindVertexArray(0)

        if is_rapid:
            self._rapid_vao = vao
            self._rapid_vbo = vbo
            self._rapid_point_count = data.point_count
            self._rapid_needs_upload = False
            self._rapid_color = data.color.copy()
            self._rapid_line_width = data.line_width
        else:
            self._toolpath_vao = vao
            self._toolpath_vbo = vbo
            self._toolpath_point_count = data.point_count
            self._toolpath_needs_upload = False
            self._toolpath_color = data.color.copy()
            self._toolpath_line_width = data.line_width

        logger.debug(
            "Toolpath GL upload: %d points, rapid=%s",
            data.point_count, is_rapid,
        )

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
    ) -> None:
        """Draw all meshes and toolpaths. None-guarded on all GL resources.

        Draw order: mesh (opaque) → toolpath lines → rapid lines.
        """
        # Lazy uploads
        if self._mesh_needs_upload:
            self._upload_mesh_gl(gl)
        if self._toolpath_needs_upload:
            self._upload_toolpath_gl(gl, is_rapid=False)
        if self._rapid_needs_upload:
            self._upload_toolpath_gl(gl, is_rapid=True)

        self._draw_mesh(gl, renderer)
        self._draw_toolpath(gl, renderer, is_rapid=False)
        self._draw_toolpath(gl, renderer, is_rapid=True)

    def _draw_mesh(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
    ) -> None:
        """Draw the indexed triangle mesh."""
        if self._mesh_vao is None or self._mesh_vao == 0:
            return
        if self._mesh_index_count == 0:
            return

        program = renderer.use_lit_program(gl)
        if program is None:
            return

        renderer.set_lit_uniforms(
            gl, program, self._mesh_model, self._mesh_color
        )

        gl.glBindVertexArray(self._mesh_vao)
        gl.glDrawElements(
            gl.GL_TRIANGLES,
            self._mesh_index_count,
            gl.GL_UNSIGNED_INT,
            0,
        )
        gl.glBindVertexArray(0)

    def _draw_toolpath(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
        is_rapid: bool = False,
    ) -> None:
        """Draw toolpath lines (GL_LINE_STRIP)."""
        vao = self._rapid_vao if is_rapid else self._toolpath_vao
        point_count = self._rapid_point_count if is_rapid else self._toolpath_point_count
        color = self._rapid_color if is_rapid else self._toolpath_color
        line_width = self._rapid_line_width if is_rapid else self._toolpath_line_width

        if vao is None or vao == 0:
            return
        if point_count < 2:
            return

        program = renderer.use_toolpath_program(gl)
        if program is None:
            return

        renderer.set_toolpath_uniforms(
            gl, program, self._toolpath_model, color
        )

        # Line width (clamp to driver limits)
        gl.glLineWidth(max(1.0, min(line_width, gl.GL_MAX_LINE_WIDTH if hasattr(gl, 'GL_MAX_LINE_WIDTH') else 10.0)))

        gl.glBindVertexArray(vao)
        gl.glDrawArrays(gl.GL_LINE_STRIP, 0, point_count)
        gl.glBindVertexArray(0)

        # Reset line width
        gl.glLineWidth(1.0)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Release all GL resources."""
        r = ViewportRenderer()

        # Mesh
        if self._mesh_vao:
            r.safe_delete_vertex_array(gl, self._mesh_vao)
        if self._mesh_vbo:
            r.safe_delete_buffers(gl, self._mesh_vbo)
        if self._mesh_ibo:
            r.safe_delete_buffers(gl, self._mesh_ibo)

        # Toolpath
        if self._toolpath_vao:
            r.safe_delete_vertex_array(gl, self._toolpath_vao)
        if self._toolpath_vbo:
            r.safe_delete_buffers(gl, self._toolpath_vbo)

        # Rapid
        if self._rapid_vao:
            r.safe_delete_vertex_array(gl, self._rapid_vao)
        if self._rapid_vbo:
            r.safe_delete_buffers(gl, self._rapid_vbo)

        self._mesh_vao = self._mesh_vbo = self._mesh_ibo = None
        self._toolpath_vao = self._toolpath_vbo = None
        self._rapid_vao = self._rapid_vbo = None
        self._mesh_index_count = 0
        self._toolpath_point_count = 0
        self._rapid_point_count = 0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @property
    def has_mesh(self) -> bool:
        """True if a mesh is loaded."""
        return self._mesh_data is not None and self._mesh_index_count > 0

    @property
    def has_toolpath(self) -> bool:
        """True if toolpath data is loaded."""
        return self._toolpath_point_count > 0 or self._rapid_point_count > 0

    @property
    def mesh_triangle_count(self) -> int:
        """Number of mesh triangles."""
        return self._mesh_index_count // 3

    @property
    def toolpath_point_count(self) -> int:
        """Total toolpath points (cut + rapid)."""
        return self._toolpath_point_count + self._rapid_point_count
