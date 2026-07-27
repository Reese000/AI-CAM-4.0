"""
AI CAM 4.0 — Viewport Shell
============================

The main QOpenGLWidget subclass that owns the GL context and
orchestrates all rendering. This is the entry point for the
viewport — MainWindow creates one of these and adds it to a layout.

Architecture:
- GLViewportWidget inherits QOpenGLWidget
- initializeGL() → sets up renderer, sub-renderers
- paintGL() → frame loop: begin → grid → stock → mesh → toolpath → overlays → end
- resizeGL() → updates viewport + projection
- Mouse/key events → InputHandler → camera

Key NVIDIA RTX 4070 Ti workarounds:
- setSamples(0) in format constructor
- setSwapInterval(0) to prevent driver hangs
- os._exit(0) on unrecoverable GL errors

All GL operations happen on the main thread (Qt requirement).
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QPainter
from PySide6.QtOpenGL import (
    QOpenGLFunctions_3_3_Core,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from app.viewport.camera import OrbitCamera
from app.viewport.gl_constants import (
    CAMERA_DEFAULT_DISTANCE,
    COLOR_BACKGROUND,
    SAMPLES,
    SWAP_INTERVAL,
)
from app.viewport.input_handler import InputHandler, InputAction, ActionType
from app.viewport.mesh_renderer import MeshRenderer
from app.viewport.overlays import GridRenderer, OrientationCube, StatusOverlay
from app.viewport.renderer import ViewportRenderer
from app.viewport.stock_renderer import StockRenderer

logger = logging.getLogger(__name__)


class GLViewportWidget(QOpenGLWidget, QOpenGLFunctions_3_3_Core):
    """Main OpenGL viewport widget.

    Signals:
        camera_changed: Emitted when camera position/orientation changes.
        fps_updated: Emitted with current FPS value.
        status_message: Emitted with status text for the status bar.
    """

    camera_changed = Signal()
    fps_updated = Signal(float)
    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        """Initialize viewport widget with OpenGL 3.3 Core Profile.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Set up OpenGL format with NVIDIA workarounds
        from PySide6.QtGui import QSurfaceFormat
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setSamples(SAMPLES)  # NVIDIA: samples=0 avoids driver crashes
        fmt.setSwapInterval(SWAP_INTERVAL)  # VSync off to prevent hangs
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        self.setFormat(fmt)

        # Core components
        self._camera = OrbitCamera()
        self._input_handler = InputHandler(camera=self._camera)
        self._renderer = ViewportRenderer()
        self._stock_renderer = StockRenderer()
        self._mesh_renderer = MeshRenderer()
        self._grid_renderer = GridRenderer()
        self._orientation_cube = OrientationCube()
        self._status_overlay = StatusOverlay()

        # State
        self._gl_initialized: bool = False
        self._frame_count: int = 0

        # Enable mouse tracking for continuous mouse move events
        self.setMouseTracking(True)

        # Focus policy for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        logger.info("GLViewportWidget created (samples=%d, swap=%d)",
                     SAMPLES, SWAP_INTERVAL)

    # ------------------------------------------------------------------
    # OpenGL lifecycle
    # ------------------------------------------------------------------
    def initializeGL(self) -> None:
        """Called once when GL context is first created.

        Initializes all GL resources. Must call initializeOpenGLFunctions()
        before any GL calls.
        """
        logger.info("initializeGL() called")
        self.initializeOpenGLFunctions()

        # Print GL info for debugging
        gl = self
        vendor = gl.glGetString(gl.GL_VENDOR)
        renderer_str = gl.glGetString(gl.GL_RENDERER)
        version = gl.glGetString(gl.GL_VERSION)
        logger.info("GL Vendor: %s", vendor)
        logger.info("GL Renderer: %s", renderer_str)
        logger.info("GL Version: %s", version)

        # Initialize main renderer (compiles shaders)
        success = self._renderer.init_gl(gl)
        if not success:
            logger.error("Renderer initialization FAILED — viewport will be blank")
            return

        # Grid uploads immediately (small geometry)
        self._grid_renderer.upload_gl(gl)

        self._gl_initialized = True
        logger.info("initializeGL() complete")

    def paintGL(self) -> None:
        """Called every frame. Orchestrates the draw order.

        Draw order:
        1. Clear buffers
        2. Set per-frame uniforms
        3. Grid (world space)
        4. Stock surface (world space)
        5. Mesh (world space)
        6. Toolpath lines (world space)
        7. Orientation cube (screen space overlay)
        8. Status text (2D QPainter overlay)
        """
        if not self._gl_initialized:
            return

        gl = self
        self._frame_count += 1

        # Update FPS
        self._status_overlay.update()
        if self._frame_count % 30 == 0:
            self.fps_updated.emit(self._status_overlay.fps)

        # Set up per-frame state
        self._renderer.begin_frame(gl, self._camera)

        # Draw order: grid → stock → mesh → toolpath → orientation
        self._draw_grid(gl)
        self._draw_stock(gl)
        self._draw_mesh_and_toolpath(gl)
        self._draw_orientation(gl)

        # End frame
        self._renderer.end_frame(gl)

        # Draw 2D overlay (QPainter — after GL)
        self._draw_2d_overlay()

    def resizeGL(self, width: int, height: int) -> None:
        """Called when widget is resized.

        Args:
            width: New width in pixels.
            height: New height in pixels.
        """
        if not self._gl_initialized:
            return

        gl = self
        gl.glViewport(0, 0, width, height)
        self._renderer.resize(width, height)
        logger.debug("resizeGL: %dx%d", width, height)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def _draw_grid(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Draw the ground-plane grid."""
        try:
            self._grid_renderer.draw(gl, self._renderer)
        except Exception:
            logger.exception("Error drawing grid")

    def _draw_stock(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Draw the stock surface."""
        if not self._stock_renderer.has_data:
            return
        try:
            self._stock_renderer.draw(gl, self._renderer)
        except Exception:
            logger.exception("Error drawing stock")

    def _draw_mesh_and_toolpath(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Draw meshes and toolpath lines."""
        if not self._mesh_renderer.has_mesh and not self._mesh_renderer.has_toolpath:
            return
        try:
            self._mesh_renderer.draw(gl, self._renderer)
        except Exception:
            logger.exception("Error drawing mesh/toolpath")

    def _draw_orientation(self, gl: QOpenGLFunctions_3_3_Core) -> None:
        """Draw the orientation cube indicator."""
        w, h = self.width(), self.height()
        try:
            self._orientation_cube.draw(
                gl, self._renderer, self._camera, w, h
            )
        except Exception:
            logger.exception("Error drawing orientation cube")

    def _draw_2d_overlay(self) -> None:
        """Draw 2D text overlay using QPainter (after GL rendering)."""
        if not self._status_overlay.visible:
            return

        text = self._status_overlay.get_status_text(self._camera)
        if not text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.GlobalColor.white)

        # Draw status text in top-left corner
        font = painter.font()
        font.setPointSize(10)
        font.setFamily("Consolas")
        painter.setFont(font)

        x, y = 10, 20
        for line in text.split("\n"):
            painter.drawText(x, y, line)
            y += 18

        painter.end()

    # ------------------------------------------------------------------
    # Public API — data loading
    # ------------------------------------------------------------------
    def set_stock_zmap(
        self,
        zmap: NDArray[np.float64 | np.float32],
        spacing_x: float = 1.0,
        spacing_y: float = 1.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
    ) -> None:
        """Load stock data from a Z-map heightfield.

        Args:
            zmap: 2D array of Z heights.
            spacing_x: World units per grid column.
            spacing_y: World units per grid row.
            origin_x: World X of zmap[0,0].
            origin_y: World Y of zmap[0,0].
        """
        self._stock_renderer.update_from_zmap(
            zmap, spacing_x, spacing_y, origin_x, origin_y
        )
        self.update()  # Trigger repaint

    def set_mesh(
        self,
        vertices: NDArray[np.float32],
        normals: NDArray[np.float32],
        faces: NDArray[np.uint32],
        color: NDArray[np.float32] | None = None,
    ) -> None:
        """Load an STL mesh for visualization.

        Args:
            vertices: Position array, shape (N, 3).
            normals: Normal array, shape (N, 3).
            faces: Triangle index array, shape (M, 3) or flat.
            color: Optional RGBA color override.
        """
        self._mesh_renderer.upload_mesh(vertices, normals, faces, color)
        self.update()

    def set_toolpath(
        self,
        positions: NDArray[np.float32],
        color: NDArray[np.float32] | None = None,
        is_rapid: bool = False,
    ) -> None:
        """Load toolpath data for visualization.

        Args:
            positions: Flat position array [x,y,z, x,y,z, ...].
            color: Optional RGBA color.
            is_rapid: True for rapid (retract) moves.
        """
        self._mesh_renderer.upload_toolpath(positions, color, is_rapid=is_rapid)
        self.update()

    def clear_scene(self) -> None:
        """Clear all loaded data (stock, mesh, toolpath)."""
        self._stock_renderer = StockRenderer()
        self._mesh_renderer = MeshRenderer()
        self.update()
        logger.info("Scene cleared")

    def frame_all(self) -> None:
        """Frame the camera to fit all loaded geometry."""
        # Find bounding box of all loaded data
        bounds = self._compute_bounds()
        if bounds is not None:
            center = (bounds[0] + bounds[1]) / 2.0
            radius = float(np.linalg.norm(bounds[1] - bounds[0])) / 2.0
            self._camera.focus_on(center, max(radius, 1.0))
            self.camera_changed.emit()
            self.update()

    def _compute_bounds(self) -> Optional[tuple[NDArray, NDArray]]:
        """Compute bounding box of all loaded geometry."""
        all_min = None
        all_max = None

        # Stock bounds
        if self._stock_renderer._vertices is not None:
            verts = self._stock_renderer._vertices[:, :3]
            v_min = verts.min(axis=0)
            v_max = verts.max(axis=0)
            all_min = v_min if all_min is None else np.minimum(all_min, v_min)
            all_max = v_max if all_max is None else np.maximum(all_max, v_max)

        # Mesh bounds
        if self._mesh_renderer._mesh_data is not None:
            verts = self._mesh_renderer._mesh_data.vertices[:, :3]
            v_min = verts.min(axis=0)
            v_max = verts.max(axis=0)
            all_min = v_min if all_min is None else np.minimum(all_min, v_min)
            all_max = v_max if all_max is None else np.maximum(all_max, v_max)

        if all_min is not None and all_max is not None:
            return (all_min, all_max)
        return None

    # ------------------------------------------------------------------
    # Mouse events → InputHandler
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Route mouse press to input handler."""
        button = self._qt_button_to_int(event.button())
        self._input_handler.handle_mouse_press(
            button, event.position().x(), event.position().y()
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Route mouse release to input handler."""
        button = self._qt_button_to_int(event.button())
        self._input_handler.handle_mouse_release(
            button, event.position().x(), event.position().y()
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Route mouse move to input handler. Triggers repaint if camera changed."""
        action = self._input_handler.handle_mouse_move(
            event.position().x(), event.position().y()
        )
        if action.action_type in (ActionType.ORBIT, ActionType.PAN):
            self.camera_changed.emit()
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Route scroll wheel to input handler for zoom."""
        angle = event.angleDelta()
        delta_x = angle.x() / 120.0
        delta_y = angle.y() / 120.0
        action = self._input_handler.handle_wheel(delta_x, delta_y)
        if action.action_type == ActionType.ZOOM:
            self.camera_changed.emit()
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Route keyboard input to input handler."""
        key = event.text()
        if not key:
            key = event.key()

        action = self._input_handler.handle_key_press(key)

        if action.action_type == ActionType.FRAME:
            self.frame_all()
        elif action.action_type == ActionType.RESET:
            self.camera_changed.emit()
            self.update()
        elif action.action_type in (
            ActionType.VIEW_FRONT,
            ActionType.VIEW_RIGHT,
            ActionType.VIEW_TOP,
            ActionType.VIEW_ISO,
        ):
            self.camera_changed.emit()
            self.update()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _qt_button_to_int(button: Qt.MouseButton) -> int:
        """Convert Qt mouse button enum to simple int (1/2/4)."""
        if button == Qt.MouseButton.LeftButton:
            return 1
        elif button == Qt.MouseButton.RightButton:
            return 2
        elif button == Qt.MouseButton.MiddleButton:
            return 4
        return 0

    # ------------------------------------------------------------------
    # Property accessors
    # ------------------------------------------------------------------
    @property
    def camera(self) -> OrbitCamera:
        """The orbit camera instance."""
        return self._camera

    @property
    def stock_renderer(self) -> StockRenderer:
        """The stock renderer instance."""
        return self._stock_renderer

    @property
    def mesh_renderer(self) -> MeshRenderer:
        """The mesh renderer instance."""
        return self._mesh_renderer

    @property
    def status_overlay(self) -> StatusOverlay:
        """The status overlay instance."""
        return self._status_overlay

    @property
    def fps(self) -> float:
        """Current FPS."""
        return self._status_overlay.fps

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        """Release all GL resources. Call before widget destruction.

        Note: This MUST be called while the GL context is still valid.
        Typically called from the parent window's closeEvent.
        """
        if not self._gl_initialized:
            return

        gl = self
        logger.info("Cleaning up viewport GL resources...")

        self._stock_renderer.cleanup_gl(gl)
        self._mesh_renderer.cleanup_gl(gl)
        self._grid_renderer.cleanup_gl(gl)
        self._orientation_cube.cleanup_gl(gl)
        self._renderer.cleanup_gl(gl)

        self._gl_initialized = False
        logger.info("Viewport cleanup complete")

    def paintEvent(self, event) -> None:
        """Override to ensure QPainter overlay works correctly."""
        super().paintEvent(event)
