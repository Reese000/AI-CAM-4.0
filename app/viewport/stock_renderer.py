"""
AI CAM 4.0 — Stock Renderer
============================

Renders the Z-map heightfield as a solid 3D surface.
Handles vertex/normal generation from numpy zmap arrays.

Key lesson from v3: Normals array MUST match vertex count exactly.
Every vertex gets a corresponding normal. The normal calculation
uses central differences on the heightfield grid.

All GL operations are on the main thread only.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core

from app.viewport.gl_constants import (
    COLOR_STOCK,
    NORMAL_OFFSET,
    POSITION_OFFSET,
    STOCK_DEFAULT_COLOR,
    VERTEX_STRIDE,
)
from app.viewport.renderer import ViewportRenderer

logger = logging.getLogger(__name__)


class StockRenderer:
    """Renders stock (Z-map heightfield) as a solid triangle mesh.

    Usage:
        stock = StockRenderer()
        stock.update_from_zmap(zmap_array)
        # In paintGL:
        stock.draw(gl, renderer)

    GL resources created lazily on first draw (after GL context is ready).
    """

    def __init__(self) -> None:
        """Initialize stock renderer state. No GL calls until draw()."""
        # GL resource handles
        self._vao: Optional[int] = None
        self._vbo: Optional[int] = None
        self._ibo: Optional[int] = None

        # CPU-side data
        self._vertices: Optional[NDArray[np.float32]] = None
        self._normals: Optional[NDArray[np.float32]] = None
        self._indices: Optional[NDArray[np.uint32]] = None
        self._index_count: int = 0

        # Z-map parameters
        self._grid_width: int = 0
        self._grid_height: int = 0
        self._spacing_x: float = 1.0
        self._spacing_y: float = 1.0
        self._origin_x: float = 0.0
        self._origin_y: float = 0.0

        # Model matrix (identity by default)
        self._model: NDArray[np.float32] = np.eye(4, dtype=np.float32)

        # GL state flags
        self._gl_initialized: bool = False
        self._needs_upload: bool = False

    def set_spacing(
        self, spacing_x: float, spacing_y: float,
        origin_x: float = 0.0, origin_y: float = 0.0,
    ) -> None:
        """Set grid spacing and origin for zmap-to-world conversion.

        Args:
            spacing_x: World units per grid column.
            spacing_y: World units per grid row.
            origin_x: World X of grid[0,0].
            origin_y: World Y of grid[0,0].
        """
        self._spacing_x = spacing_x
        self._spacing_y = spacing_y
        self._origin_x = origin_x
        self._origin_y = origin_y

    def set_model(self, model: NDArray[np.float32]) -> None:
        """Set the model (local→world) matrix."""
        self._model = np.ascontiguousarray(model, dtype=np.float32)

    def update_from_zmap(
        self,
        zmap: NDArray[np.float64 | np.float32],
        spacing_x: float = 1.0,
        spacing_y: float = 1.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
    ) -> None:
        """Generate vertex/normal/index data from a heightfield zmap.

        Args:
            zmap: 2D numpy array of Z heights. Shape (rows, cols).
            spacing_x: World units per grid column.
            spacing_y: World units per grid row.
            origin_x: World X of zmap[0,0].
            origin_y: World Y of zmap[0,0].

        The zmap is interpreted as:
            zmap[row, col] → world position:
                x = origin_x + col * spacing_x
                y = origin_y + row * spacing_y
                z = zmap[row, col]

        Vertices and normals are built on CPU. GL upload happens on draw().
        """
        if zmap is None or zmap.size == 0:
            logger.warning("update_from_zmap: empty zmap, skipping")
            return

        zmap = np.asarray(zmap, dtype=np.float32)
        if zmap.ndim != 2:
            logger.error("update_from_zmap: expected 2D array, got %dD", zmap.ndim)
            return

        rows, cols = zmap.shape
        if rows < 2 or cols < 2:
            logger.warning(
                "update_from_zmap: zmap too small (%d x %d), need at least 2x2",
                rows, cols,
            )
            return

        self._grid_width = cols
        self._grid_height = rows
        self._spacing_x = spacing_x
        self._spacing_y = spacing_y
        self._origin_x = origin_x
        self._origin_y = origin_y

        logger.info(
            "Generating stock mesh from zmap %dx%d (spacing=%.2f, %.2f)",
            cols, rows, spacing_x, spacing_y,
        )

        # Generate vertices: one per grid point
        # Layout: position (3) + normal (3) = 6 floats per vertex
        vertex_count = rows * cols
        self._vertices = np.zeros((vertex_count, 6), dtype=np.float32)

        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                self._vertices[idx, 0] = origin_x + c * spacing_x  # X
                self._vertices[idx, 1] = origin_y + r * spacing_y  # Y
                self._vertices[idx, 2] = zmap[r, c]                # Z

        # Generate normals using central differences
        self._normals = self._compute_normals(zmap, spacing_x, spacing_y)

        # CRITICAL: Verify normals match vertex count
        assert self._normals.shape[0] == vertex_count, (
            f"Normal count mismatch: {self._normals.shape[0]} normals "
            f"vs {vertex_count} vertices"
        )

        # Pack normals into the interleaved vertex array
        self._vertices[:, 3:6] = self._normals

        # Generate indices: two triangles per quad
        quads = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                i = r * cols + c
                # Triangle 1
                quads.append(i)
                quads.append(i + cols)
                quads.append(i + 1)
                # Triangle 2
                quads.append(i + 1)
                quads.append(i + cols)
                quads.append(i + cols + 1)

        self._indices = np.array(quads, dtype=np.uint32)
        self._index_count = len(self._indices)

        logger.info(
            "Stock mesh generated: %d vertices, %d indices (%d triangles)",
            vertex_count, self._index_count, self._index_count // 3,
        )

        self._needs_upload = True

    def _compute_normals(
        self,
        zmap: NDArray[np.float32],
        sx: float,
        sy: float,
    ) -> NDArray[np.float32]:
        """Compute per-vertex normals from heightfield using central differences.

        Returns:
            Float32 array of shape (vertex_count, 3) with normalized normals.
        """
        rows, cols = zmap.shape
        normals = np.zeros((rows * cols, 3), dtype=np.float32)

        for r in range(rows):
            for c in range(cols):
                # Central differences with edge clamping
                if c == 0:
                    dzdx = (zmap[r, c + 1] - zmap[r, c]) / sx
                elif c == cols - 1:
                    dzdx = (zmap[r, c] - zmap[r, c - 1]) / sx
                else:
                    dzdx = (zmap[r, c + 1] - zmap[r, c - 1]) / (2.0 * sx)

                if r == 0:
                    dzdy = (zmap[r + 1, c] - zmap[r, c]) / sy
                elif r == rows - 1:
                    dzdy = (zmap[r, c] - zmap[r - 1, c]) / sy
                else:
                    dzdy = (zmap[r + 1, c] - zmap[r - 1, c]) / (2.0 * sy)

                # Normal = cross(up, tangent) = (-dzdx, -dzdy, 1)
                nx = -dzdx
                ny = -dzdy
                nz = 1.0

                # Normalize
                length = np.sqrt(nx * nx + ny * ny + nz * nz)
                if length > 1e-8:
                    nx /= length
                    ny /= length
                    nz /= length

                idx = r * cols + c
                normals[idx, 0] = nx
                normals[idx, 1] = ny
                normals[idx, 2] = nz

        return normals

    # ------------------------------------------------------------------
    # GL lifecycle
    # ------------------------------------------------------------------
    def upload_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Upload CPU data to GPU. Must be called on main thread with valid GL context."""
        if not self._needs_upload:
            return
        if self._vertices is None or self._indices is None:
            return

        renderer = ViewportRenderer()

        # Delete old resources if they exist
        if self._vao is not None:
            renderer.safe_delete_vertex_array(gl, self._vao)
        if self._vbo is not None:
            renderer.safe_delete_buffers(gl, self._vbo)
        if self._ibo is not None:
            renderer.safe_delete_buffers(gl, self._ibo)

        # Create new buffers
        self._vbo = renderer.create_vbo(gl, self._vertices)
        self._ibo = renderer.create_ibo(gl, self._indices)

        if self._vbo is not None and self._ibo is not None:
            self._vao = renderer.create_vao(
                gl,
                self._vbo,
                VERTEX_STRIDE,
                [
                    (0, 3, POSITION_OFFSET),  # a_position
                    (1, 3, NORMAL_OFFSET),     # a_normal
                ],
                ibo=self._ibo,
            )

        self._gl_initialized = (
            self._vao is not None
            and self._vbo is not None
            and self._ibo is not None
        )
        self._needs_upload = False

        if self._gl_initialized:
            logger.info(
                "Stock GL upload complete: VAO=%d, VBO=%d, IBO=%d, indices=%d",
                self._vao, self._vbo, self._ibo, self._index_count,
            )
        else:
            logger.error("Stock GL upload failed")

    def draw(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        renderer: ViewportRenderer,
    ) -> None:
        """Draw the stock surface. None-guarded on all GL resources.

        Args:
            gl: OpenGL functions handle.
            renderer: ViewportRenderer for shader programs/uniforms.
        """
        # Lazy upload
        if self._needs_upload:
            self.upload_gl(gl)

        # None-guards on all GL resources
        if self._vao is None or self._vao == 0:
            return
        if self._index_count == 0:
            return

        program = renderer.use_lit_program(gl)
        if program is None:
            return

        renderer.set_lit_uniforms(
            gl, program, self._model, STOCK_DEFAULT_COLOR
        )

        gl.glBindVertexArray(self._vao)
        gl.glDrawElements(
            gl.GL_TRIANGLES,
            self._index_count,
            gl.GL_UNSIGNED_INT,
            0,
        )
        gl.glBindVertexArray(0)

    def cleanup_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Release GL resources."""
        renderer = ViewportRenderer()
        if self._vao is not None:
            renderer.safe_delete_vertex_array(gl, self._vao)
        if self._vbo is not None:
            renderer.safe_delete_buffers(gl, self._vbo)
        if self._ibo is not None:
            renderer.safe_delete_buffers(gl, self._ibo)

        self._vao = None
        self._vbo = None
        self._ibo = None
        self._gl_initialized = False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @property
    def has_data(self) -> bool:
        """True if zmap data has been loaded."""
        return self._vertices is not None and self._index_count > 0

    @property
    def vertex_count(self) -> int:
        """Number of vertices in the stock mesh."""
        return self._vertices.shape[0] if self._vertices is not None else 0

    @property
    def triangle_count(self) -> int:
        """Number of triangles in the stock mesh."""
        return self._index_count // 3 if self._index_count > 0 else 0
