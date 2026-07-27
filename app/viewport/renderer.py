"""
AI CAM 4.0 — Main Renderer
============================

Central GL state machine: shader programs, VBO/IBO management,
and the primary draw dispatch. Each sub-renderer (stock, mesh,
overlays) handles its own buffers; this module owns the shared
programs and coordinates the draw order.

Key constraints (from v3):
- ALL GL calls happen on the main thread
- Every VAO/VBO/IBO has a None-guard before use
- Shader errors are logged, never silently swallowed
- samples=0 set in the QSurfaceFormat for NVIDIA compatibility
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core

from app.viewport.camera import OrbitCamera
from app.viewport.gl_constants import (
    COLOR_BACKGROUND,
    DEFAULT_AMBIENT,
    DEFAULT_LIGHT_COLOR,
    DEFAULT_LIGHT_DIR,
    FRAGMENT_SHADER_LIT,
    FRAGMENT_SHADER_SOLID,
    FRAGMENT_SHADER_TOOLPATH,
    VERTEX_SHADER_LIT,
    VERTEX_SHADER_SOLID,
    VERTEX_SHADER_TOOLPATH,
)
from app.viewport.renderer_utils import (
    compile_program,
    safe_delete_buffers,
    safe_delete_program,
    safe_delete_vertex_array,
    set_uniform_float,
    set_uniform_mat3,
    set_uniform_mat4,
    set_uniform_vec3,
    set_uniform_vec4,
    compute_normal_matrix,
)

logger = logging.getLogger(__name__)


class ViewportRenderer:
    """Manages GL shader programs and shared renderer state.

    This is NOT responsible for mesh/stock data — those live in
    specialized renderers (StockRenderer, MeshRenderer, Overlays).
    This class owns the shader programs and provides the GL context
    used by all sub-renderers.
    """

    def __init__(self) -> None:
        """Initialize renderer state. No GL calls until init_gl()."""
        # Shader programs
        self.program_lit: Optional[int] = None
        self.program_solid: Optional[int] = None
        self.program_toolpath: Optional[int] = None

        # GL state
        self._initialized: bool = False
        self._width: int = 0
        self._height: int = 0

        # Viewport clear color
        self.clear_color: NDArray[np.float32] = COLOR_BACKGROUND.copy()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init_gl(self, gl: QOpenGLFunctions_3_3_Core) -> bool:
        """Compile shaders and set initial GL state. Call from initializeGL().

        Args:
            gl: OpenGL functions handle (must be current context).

        Returns:
            True if initialization succeeded, False on shader failure.
        """
        if self._initialized:
            logger.warning("Renderer already initialized, skipping")
            return True

        logger.info("Initializing viewport renderer (GL 3.3 Core)...")

        # Compile all shader programs
        self.program_lit = compile_program(
            gl, VERTEX_SHADER_LIT, FRAGMENT_SHADER_LIT, "lit"
        )
        self.program_solid = compile_program(
            gl, VERTEX_SHADER_SOLID, FRAGMENT_SHADER_SOLID, "solid"
        )
        self.program_toolpath = compile_program(
            gl, VERTEX_SHADER_TOOLPATH, FRAGMENT_SHADER_TOOLPATH, "toolpath"
        )

        # Check all programs compiled
        if any(p is None for p in [
            self.program_lit, self.program_solid, self.program_toolpath
        ]):
            logger.error("One or more shader programs failed to compile")
            return False

        # GL state defaults
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LESS)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glEnable(gl.GL_MULTISAMPLE)  # Enable even if samples=0 (no harm)
        gl.glClearColor(
            self.clear_color[0],
            self.clear_color[1],
            self.clear_color[2],
            self.clear_color[3],
        )

        self._initialized = True
        logger.info(
            "Viewport renderer initialized: lit=%d, solid=%d, toolpath=%d",
            self.program_lit,
            self.program_solid,
            self.program_toolpath,
        )
        return True

    def cleanup_gl(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Release all GL resources. Call from destructor or context destroy.

        Args:
            gl: OpenGL functions handle (must be current context).
        """
        if not self._initialized:
            return

        logger.info("Cleaning up viewport renderer...")

        safe_delete_program(gl, self.program_lit)
        safe_delete_program(gl, self.program_solid)
        safe_delete_program(gl, self.program_toolpath)

        self.program_lit = None
        self.program_solid = None
        self.program_toolpath = None
        self._initialized = False

    def resize(self, width: int, height: int) -> None:
        """Update viewport dimensions. Call from resizeGL()."""
        self._width = width
        self._height = height

    # ------------------------------------------------------------------
    # Draw dispatch
    # ------------------------------------------------------------------
    def begin_frame(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        camera: OrbitCamera,
    ) -> None:
        """Set up per-frame GL state and common uniforms.

        Must be called before any sub-renderer draw() calls.
        """
        gl.glClear(
            gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT
        )

        aspect = self._width / max(self._height, 1)
        self._aspect = aspect
        self._view = camera.get_view_matrix()
        self._projection = camera.get_projection_matrix(aspect)
        self._camera_pos = camera.get_camera_position()

    def end_frame(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Cleanup per-frame state. Called after all sub-renderers."""
        # Unbind any bound VAO to prevent accidental state leakage
        gl.glBindVertexArray(0)
        gl.glUseProgram(0)

    # ------------------------------------------------------------------
    # Program accessors (for sub-renderers)
    # ------------------------------------------------------------------
    def use_lit_program(
        self, gl: QOpenGLFunctions_3_3_Core
    ) -> Optional[int]:
        """Bind the lit shader and set common uniforms. Returns program id."""
        if self.program_lit is None:
            return None
        gl.glUseProgram(self.program_lit)
        return self.program_lit

    def use_solid_program(
        self, gl: QOpenGLFunctions_3_3_Core
    ) -> Optional[int]:
        """Bind the solid-color shader. Returns program id."""
        if self.program_solid is None:
            return None
        gl.glUseProgram(self.program_solid)
        return self.program_solid

    def use_toolpath_program(
        self, gl: QOpenGLFunctions_3_3_Core
    ) -> Optional[int]:
        """Bind the toolpath shader. Returns program id."""
        if self.program_toolpath is None:
            return None
        gl.glUseProgram(self.program_toolpath)
        return self.program_toolpath

    def set_lit_uniforms(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        program: int,
        model: NDArray[np.float32],
        color: NDArray[np.float32],
        alpha: float = 1.0,
    ) -> None:
        """Set all uniforms for the lit shader program.

        Args:
            gl: OpenGL functions handle.
            program: Lit shader program handle.
            model: 4x4 model matrix.
            color: RGB or RGBA color.
            alpha: Override alpha (used for transparency).
        """
        set_uniform_mat4(gl, program, "u_model", model)
        set_uniform_mat4(gl, program, "u_view", self._view)
        set_uniform_mat4(gl, program, "u_projection", self._projection)
        normal_mat = compute_normal_matrix(model)
        set_uniform_mat3(gl, program, "u_normal_matrix", normal_mat)
        set_uniform_vec3(gl, program, "u_light_dir", DEFAULT_LIGHT_DIR)
        set_uniform_vec3(gl, program, "u_light_color", DEFAULT_LIGHT_COLOR)
        set_uniform_vec3(gl, program, "u_ambient", DEFAULT_AMBIENT)
        set_uniform_vec3(gl, program, "u_color", color[:3])
        set_uniform_float(gl, program, "u_alpha", alpha)

    def set_solid_mvp(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        program: int,
        model: NDArray[np.float32],
        color: NDArray[np.float32],
    ) -> None:
        """Set MVP and color for the solid-color shader.

        Args:
            gl: OpenGL functions handle.
            program: Solid shader program handle.
            model: 4x4 model matrix.
            color: RGBA color.
        """
        mvp = self._projection @ self._view @ model
        set_uniform_mat4(gl, program, "u_mvp", mvp)
        set_uniform_vec4(gl, program, "u_color", color)

    def set_toolpath_uniforms(
        self,
        gl: QOpenGLFunctions_3_3_Core,
        program: int,
        model: NDArray[np.float32],
        color: NDArray[np.float32],
    ) -> None:
        """Set uniforms for the toolpath shader."""
        set_uniform_mat4(gl, program, "u_model", model)
        set_uniform_mat4(gl, program, "u_view", self._view)
        set_uniform_mat4(gl, program, "u_projection", self._projection)
        set_uniform_vec4(gl, program, "u_color", color)

    # ------------------------------------------------------------------
    # Shared VBO/IBO management helpers
    # ------------------------------------------------------------------
    @staticmethod
    def create_vbo(
        gl: QOpenGLFunctions_3_3_Core,
        data: NDArray[np.float32],
        usage: int = 0x8884,  # GL_STATIC_DRAW
    ) -> Optional[int]:
        """Create and populate a VBO with float32 data.

        Args:
            gl: OpenGL functions handle.
            data: numpy float32 array to upload.
            usage: GL usage hint (default: STATIC_DRAW).

        Returns:
            VBO handle, or None if data is empty.
        """
        if data is None or data.size == 0:
            logger.warning("create_vbo: empty data, skipping")
            return None

        buf = [0]
        gl.glGenBuffers(1, buf)
        if buf[0] == 0:
            logger.error("glGenBuffers returned 0 for VBO")
            return None

        vbo = buf[0]
        flat = np.ascontiguousarray(data, dtype=np.float32).ravel()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
        gl.glBufferData(
            gl.GL_ARRAY_BUFFER,
            flat.nbytes,
            flat,
            usage,
        )
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

        logger.debug("Created VBO %d (%d bytes)", vbo, flat.nbytes)
        return vbo

    @staticmethod
    def create_ibo(
        gl: QOpenGLFunctions_3_3_Core,
        data: NDArray[np.uint32],
        usage: int = 0x8884,  # GL_STATIC_DRAW
    ) -> Optional[int]:
        """Create and populate an IBO (element buffer) with uint32 data.

        Args:
            gl: OpenGL functions handle.
            data: numpy uint32 index array to upload.
            usage: GL usage hint.

        Returns:
            IBO handle, or None if data is empty.
        """
        if data is None or data.size == 0:
            logger.warning("create_ibo: empty data, skipping")
            return None

        buf = [0]
        gl.glGenBuffers(1, buf)
        if buf[0] == 0:
            logger.error("glGenBuffers returned 0 for IBO")
            return None

        ibo = buf[0]
        flat = np.ascontiguousarray(data, dtype=np.uint32).ravel()
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, ibo)
        gl.glBufferData(
            gl.GL_ELEMENT_ARRAY_BUFFER,
            flat.nbytes,
            flat,
            usage,
        )
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)

        logger.debug("Created IBO %d (%d bytes)", ibo, flat.nbytes)
        return ibo

    @staticmethod
    def create_vao(
        gl: QOpenGLFunctions_3_3_Core,
        vbo: Optional[int],
        stride: int,
        attributes: list[Tuple[int, int, int]],
        ibo: Optional[int] = None,
    ) -> Optional[int]:
        """Create a VAO and configure vertex attribute pointers.

        Args:
            gl: OpenGL functions handle.
            vbo: Vertex buffer handle (None-guarded).
            stride: Byte stride between vertices.
            attributes: List of (location, size, offset) tuples.
            ibo: Optional element buffer handle.

        Returns:
            VAO handle, or None if vbo is None/0 or creation fails.
        """
        if vbo is None or vbo == 0:
            logger.warning("create_vao: vbo is None or 0, skipping")
            return None

        vao = [0]
        gl.glGenVertexArrays(1, vao)
        if vao[0] == 0:
            logger.error("glGenVertexArrays returned 0")
            return None

        gl.glBindVertexArray(vao[0])
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)

        for location, size, offset in attributes:
            gl.glEnableVertexAttribArray(location)
            gl.glVertexAttribPointer(
                location,
                size,
                gl.GL_FLOAT,
                gl.GL_FALSE,
                stride,
                offset,
            )

        if ibo is not None and ibo != 0:
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, ibo)

        gl.glBindVertexArray(0)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

        logger.debug("Created VAO %d (vbo=%d, ibo=%s)", vao[0], vbo, ibo)
        return vao[0]

    @staticmethod
    def update_vbo(
        gl: QOpenGLFunctions_3_3_Core,
        vbo: Optional[int],
        data: NDArray[np.float32],
    ) -> bool:
        """Update an existing VBO with new data (re-upload).

        Args:
            gl: OpenGL functions handle.
            vbo: Existing VBO handle (None-guarded).
            data: New float32 data.

        Returns:
            True on success, False on failure.
        """
        if vbo is None or vbo == 0:
            return False
        if data is None or data.size == 0:
            return False

        flat = np.ascontiguousarray(data, dtype=np.float32).ravel()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
        gl.glBufferData(
            gl.GL_ARRAY_BUFFER,
            flat.nbytes,
            flat,
            0x88E8,  # GL_DYNAMIC_DRAW
        )
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        return True
