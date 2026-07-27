"""
AI CAM 4.0 MainWindow — Single MainWindow, no versions.

Every menu action does something real. No stubs.

Menus:
  File  → Import STL, Export G-code, Quit
  Edit  → Undo, Redo
  View  → Grid, Mesh, Toolpath, Stock toggles
  Help  → About

Central: GLViewportWidget
Status bar: FPS counter
Toolbar: Strategy selector + Run button
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.strategy_executor import StrategyExecutor, list_strategies
from kernel.types import BBox, Material, ToolDef, ToolpathData, Vec3
from post.fanuc import FanucRenderer
from post.heidenhain import HeidenhainRenderer
from post.ir import segments_to_ir
from simulation.controller import SimulationController
from simulation.engine import SimulationEngine, StockModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GL Viewport — minimal OpenGL widget
# ---------------------------------------------------------------------------

class GLViewportWidget(QOpenGLWidget):
    """
    Central OpenGL viewport. Renders grid, mesh, toolpath, and stock.

    Toggle visibility via MainWindow's View menu. The simulation
    controller feeds frames here for real-time display.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Rendering toggles (controlled by View menu)
        self.show_grid = True
        self.show_mesh = True
        self.show_toolpath = True
        self.show_stock = True

        # State
        self._mesh_vertices: np.ndarray | None = None
        self._mesh_normals: np.ndarray | None = None
        self._toolpath_points: list[tuple[float, float, float]] = []
        self._stock_zmap: np.ndarray | None = None
        self._tool_position: tuple[float, float, float] = (0, 0, 0)
        self._stock_origin: tuple[float, float, float] = (-50, -50, 0)
        self._stock_resolution: float = 0.5

        # FPS tracking
        self._frame_times: list[float] = []
        self._fps: float = 0.0

    @property
    def fps(self) -> float:
        return self._fps

    def set_mesh(self, vertices: np.ndarray, normals: np.ndarray) -> None:
        """Set mesh data for rendering. Called from main thread."""
        self._mesh_vertices = vertices
        self._mesh_normals = normals
        self.update()

    def set_toolpath(self, points: list[tuple[float, float, float]]) -> None:
        """Set toolpath points for rendering."""
        self._toolpath_points = points
        self.update()

    def set_toolpath_from_moves(self, toolpath: ToolpathData) -> None:
        """Extract tool positions from a ToolpathData."""
        self._toolpath_points = [
            (m.end.x, m.end.y, m.end.z) for m in toolpath.moves
        ]
        self.update()

    def update_simulation_state(
        self,
        zmap: np.ndarray,
        tool_pos: tuple[float, float, float],
        origin: tuple[float, float, float],
        resolution: float,
    ) -> None:
        """Update stock display from a simulation frame."""
        self._stock_zmap = zmap
        self._tool_position = tool_pos
        self._stock_origin = origin
        self._stock_resolution = resolution
        self.update()

    # ------------------------------------------------------------------
    # OpenGL lifecycle
    # ------------------------------------------------------------------

    def initializeGL(self) -> None:
        """Set up OpenGL state."""
        gl = self.context()
        if gl:
            gl.makeCurrent(self.surface())

        # Try importing OpenGL
        try:
            from OpenGL.GL import (
                GL_COLOR_BUFFER_BIT,
                GL_DEPTH_BUFFER_BIT,
                GL_DEPTH_TEST,
                GL_LIGHTING,
                GL_MODELVIEW,
                GL_PROJECTION,
                GL_SMOOTH,
                glClear,
                glClearColor,
                glEnable,
                glMatrixMode,
                glLoadIdentity,
                glOrtho,
                glShadeModel,
            )
            glClearColor(0.15, 0.15, 0.18, 1.0)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)
            glShadeModel(GL_SMOOTH)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(-100, 100, -100, 100, -200, 200)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
        except ImportError:
            logger.warning("OpenGL not available — viewport will be blank")

    def resizeGL(self, w: int, h: int) -> None:
        """Handle viewport resize."""
        try:
            from OpenGL.GL import glViewport
            glViewport(0, 0, w, h)
        except ImportError:
            pass

    def paintGL(self) -> None:
        """Render the scene."""
        t0 = time.perf_counter()

        try:
            from OpenGL.GL import (
                GL_COLOR_BUFFER_BIT,
                GL_DEPTH_BUFFER_BIT,
                GL_LINES,
                GL_LINE_STRIP,
                GL_POINTS,
                GL_POLYGON,
                GL_QUADS,
                GL_TRIANGLES,
                glBegin,
                glColor3f,
                glEnd,
                glLineWidth,
                glVertex3f,
                glClear,
                glLoadIdentity,
                glTranslatef,
                glRotatef,
            )

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()

            # Camera: simple orbit (can be enhanced later)
            glTranslatef(0, 0, -200)
            glRotatef(30, 1, 0, 0)
            glRotatef(-45, 0, 0, 1)

            # Grid
            if self.show_grid:
                self._draw_grid()

            # Stock (Z-map heightfield)
            if self.show_stock and self._stock_zmap is not None:
                self._draw_stock()

            # Mesh
            if self.show_mesh and self._mesh_vertices is not None:
                self._draw_mesh()

            # Toolpath
            if self.show_toolpath and self._toolpath_points:
                self._draw_toolpath()

            # Tool indicator
            if self._tool_position != (0, 0, 0):
                self._draw_tool()

        except ImportError:
            # No OpenGL — just clear to dark background
            pass

        # FPS
        dt = time.perf_counter() - t0
        self._frame_times.append(dt)
        if len(self._frame_times) > 60:
            self._frame_times = self._frame_times[-60:]
        if self._frame_times:
            avg = sum(self._frame_times) / len(self._frame_times)
            self._fps = 1.0 / avg if avg > 0 else 0

    # ------------------------------------------------------------------
    # Draw helpers (all use raw OpenGL calls — no Qt)
    # ------------------------------------------------------------------

    def _draw_grid(self) -> None:
        """Draw a reference grid on the XY plane."""
        try:
            from OpenGL.GL import GL_LINES, glBegin, glColor3f, glEnd, glVertex3f, glLineWidth

            glLineWidth(1.0)
            glBegin(GL_LINES)
            for i in range(-50, 51, 10):
                glColor3f(0.3, 0.3, 0.3)
                glVertex3f(i, -50, 0)
                glVertex3f(i, 50, 0)
                glVertex3f(-50, i, 0)
                glVertex3f(50, i, 0)
            # Axes
            glColor3f(0.8, 0.2, 0.2)
            glVertex3f(0, 0, 0)
            glVertex3f(30, 0, 0)
            glColor3f(0.2, 0.8, 0.2)
            glVertex3f(0, 0, 0)
            glVertex3f(0, 30, 0)
            glColor3f(0.2, 0.2, 0.8)
            glVertex3f(0, 0, 0)
            glVertex3f(0, 0, 30)
            glEnd()
        except ImportError:
            pass

    def _draw_mesh(self) -> None:
        """Draw the imported STL mesh."""
        if self._mesh_vertices is None:
            return
        try:
            from OpenGL.GL import GL_TRIANGLES, glBegin, glColor3f, glEnd, glNormal3f, glVertex3f

            glBegin(GL_TRIANGLES)
            verts = self._mesh_vertices
            normals = self._mesh_normals
            for i in range(0, len(verts), 3):
                if normals is not None and i < len(normals):
                    glNormal3f(normals[i][0], normals[i][1], normals[i][2])
                glColor3f(0.6, 0.7, 0.8)
                for j in range(3):
                    v = verts[i + j]
                    glVertex3f(v[0], v[1], v[2])
            glEnd()
        except ImportError:
            pass

    def _draw_toolpath(self) -> None:
        """Draw toolpath as a colored line strip."""
        if not self._toolpath_points:
            return
        try:
            from OpenGL.GL import GL_LINE_STRIP, glBegin, glColor3f, glEnd, glLineWidth, glVertex3f

            glLineWidth(2.0)
            glBegin(GL_LINE_STRIP)
            n = len(self._toolpath_points)
            for i, (x, y, z) in enumerate(self._toolpath_points):
                # Color gradient: green (start) → yellow → red (end)
                t = i / max(1, n - 1)
                glColor3f(t, 1.0 - t * 0.5, 0.2)
                glVertex3f(x, y, z)
            glEnd()
        except ImportError:
            pass

    def _draw_stock(self) -> None:
        """Draw the stock heightfield as a wireframe mesh."""
        if self._stock_zmap is None:
            return
        try:
            from OpenGL.GL import GL_LINES, glBegin, glColor3f, glEnd, glVertex3f, glLineWidth

            zmap = self._stock_zmap
            res = self._stock_resolution
            ox, oy, oz = self._stock_origin
            rows, cols = zmap.shape

            glLineWidth(1.0)

            # Draw as wireframe quads
            for r in range(0, rows - 1, 2):
                for c in range(0, cols - 1, 2):
                    x0 = ox + c * res
                    y0 = oy + r * res
                    x1 = ox + (c + 1) * res
                    y1 = oy + (r + 1) * res
                    z00 = zmap[r, c]
                    z10 = zmap[r, c + 1] if c + 1 < cols else z00
                    z01 = zmap[r + 1, c] if r + 1 < rows else z00
                    z11 = zmap[r + 1, c + 1] if r + 1 < rows and c + 1 < cols else z00

                    glBegin(GL_LINES)
                    glColor3f(0.4, 0.6, 0.4)
                    glVertex3f(x0, y0, z00)
                    glVertex3f(x1, y0, z10)
                    glVertex3f(x1, y0, z10)
                    glVertex3f(x1, y1, z11)
                    glVertex3f(x1, y1, z11)
                    glVertex3f(x0, y1, z01)
                    glVertex3f(x0, y1, z01)
                    glVertex3f(x0, y0, z00)
                    glEnd()
        except ImportError:
            pass

    def _draw_tool(self) -> None:
        """Draw a simple tool indicator at the current position."""
        if self._tool_position == (0, 0, 0):
            return
        try:
            from OpenGL.GL import GL_LINES, GL_LINE_STRIP, glBegin, glColor3f, glEnd, glVertex3f, glLineWidth

            x, y, z = self._tool_position
            glLineWidth(3.0)
            glBegin(GL_LINE_STRIP)
            glColor3f(1.0, 0.8, 0.0)
            glVertex3f(x, y, z + 15)
            glVertex3f(x, y, z)
            glEnd()

            # Small cross at tip
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glColor3f(1.0, 0.2, 0.2)
            glVertex3f(x - 2, y, z)
            glVertex3f(x + 2, y, z)
            glVertex3f(x, y - 2, z)
            glVertex3f(x, y + 2, z)
            glEnd()
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# Viewport container (sidebar + GL)
# ---------------------------------------------------------------------------

class ViewportContainer(QWidget):
    """Wraps the GLViewportWidget with optional side panels."""

    def __init__(self, viewport: GLViewportWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewport = viewport
        layout.addWidget(viewport)


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """
    AI CAM 4.0 main application window.

    Single window, no versioning. Every menu action performs real work.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI CAM 4.0")
        self.resize(1280, 800)

        # ---- State ----
        self._current_stl_path: str | None = None
        self._current_toolpath: ToolpathData | None = None
        self._stock_model = StockModel()
        self._undo_stack: list[ToolpathData] = []
        self._redo_stack: list[ToolpathData] = []

        # Strategy executor (pure Python, no Qt)
        self._executor = StrategyExecutor()

        # Simulation controller
        self._sim_controller = SimulationController(self)

        # ---- Central widget ----
        self._viewport = GLViewportWidget(self)
        self._viewport_container = ViewportContainer(self._viewport, self)
        self.setCentralWidget(self._viewport_container)

        # ---- Menu bar ----
        self._create_menus()

        # ---- Toolbar ----
        self._create_toolbar()

        # ---- Status bar ----
        self._create_status_bar()

        # ---- FPS timer ----
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(500)  # Update FPS display every 500ms

        # ---- Wire up simulation controller ----
        self._sim_controller.frame_ready.connect(self._on_frame_ready)
        self._sim_controller.state_changed.connect(self._on_sim_state_changed)

        logger.info("MainWindow initialized")

    # ==================================================================
    # Menu creation
    # ==================================================================

    def _create_menus(self) -> None:
        menubar = self.menuBar()

        # ---- File menu ----
        file_menu = menubar.addMenu("&File")

        self._action_import_stl = QAction("&Import STL...", self)
        self._action_import_stl.setShortcut(QKeySequence("Ctrl+O"))
        self._action_import_stl.triggered.connect(self._on_import_stl)
        file_menu.addAction(self._action_import_stl)

        self._action_export_gcode = QAction("&Export G-code...", self)
        self._action_export_gcode.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self._action_export_gcode.triggered.connect(self._on_export_gcode)
        file_menu.addAction(self._action_export_gcode)

        file_menu.addSeparator()

        self._action_quit = QAction("&Quit", self)
        self._action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self._action_quit.triggered.connect(self.close)
        file_menu.addAction(self._action_quit)

        # ---- Edit menu ----
        edit_menu = menubar.addMenu("&Edit")

        self._action_undo = QAction("&Undo", self)
        self._action_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._action_undo.triggered.connect(self._on_undo)
        edit_menu.addAction(self._action_undo)

        self._action_redo = QAction("&Redo", self)
        self._action_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self._action_redo.triggered.connect(self._on_redo)
        edit_menu.addAction(self._action_redo)

        # ---- View menu ----
        view_menu = menubar.addMenu("&View")

        self._action_grid = QAction("Show &Grid", self)
        self._action_grid.setCheckable(True)
        self._action_grid.setChecked(True)
        self._action_grid.triggered.connect(self._on_toggle_grid)
        view_menu.addAction(self._action_grid)

        self._action_mesh = QAction("Show &Mesh", self)
        self._action_mesh.setCheckable(True)
        self._action_mesh.setChecked(True)
        self._action_mesh.triggered.connect(self._on_toggle_mesh)
        view_menu.addAction(self._action_mesh)

        self._action_toolpath = QAction("Show &Toolpath", self)
        self._action_toolpath.setCheckable(True)
        self._action_toolpath.setChecked(True)
        self._action_toolpath.triggered.connect(self._on_toggle_toolpath)
        view_menu.addAction(self._action_toolpath)

        self._action_stock = QAction("Show S&tock", self)
        self._action_stock.setCheckable(True)
        self._action_stock.setChecked(True)
        self._action_stock.triggered.connect(self._on_toggle_stock)
        view_menu.addAction(self._action_stock)

        # ---- Help menu ----
        help_menu = menubar.addMenu("&Help")

        self._action_about = QAction("&About AI CAM 4.0", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    # ==================================================================
    # Toolbar
    # ==================================================================

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Strategy selector
        toolbar.addWidget(QLabel(" Strategy: "))
        self._strategy_combo = QComboBox()
        strategies = list_strategies()
        self._strategy_combo.addItems(
            [s.replace("_", " ").title() for s in strategies]
        )
        self._strategy_combo.setMinimumWidth(180)
        self._strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        toolbar.addWidget(self._strategy_combo)

        toolbar.addSeparator()

        # Run button
        self._run_btn = QAction("▶ Run", self)
        self._run_btn.triggered.connect(self._on_run_strategy)
        toolbar.addAction(self._run_btn)

        # Simulate button
        self._sim_btn = QAction("⏯ Simulate", self)
        self._sim_btn.triggered.connect(self._on_toggle_simulation)
        toolbar.addAction(self._sim_btn)

        toolbar.addSeparator()

        # Speed control
        toolbar.addWidget(QLabel(" Speed: "))
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.1x", "0.25x", "0.5x", "1x", "2x", "5x", "10x"])
        self._speed_combo.setCurrentText("1x")
        self._speed_combo.currentTextChanged.connect(self._on_speed_changed)
        self._speed_combo.setMinimumWidth(70)
        toolbar.addWidget(self._speed_combo)

    # ==================================================================
    # Status bar
    # ==================================================================

    def _create_status_bar(self) -> None:
        status = self.statusBar()
        self._status_label = QLabel("Ready")
        self._fps_label = QLabel("FPS: --")
        self._move_label = QLabel("Moves: 0")
        status.addWidget(self._status_label, 1)
        status.addPermanentWidget(self._move_label)
        status.addPermanentWidget(self._fps_label)

    # ==================================================================
    # File actions
    # ==================================================================

    @Slot()
    def _on_import_stl(self) -> None:
        """Import an STL file and display it in the viewport."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import STL File",
            "",
            "STL Files (*.stl *.STL);;All Files (*)",
        )
        if not path:
            return

        self._status_label.setText(f"Loading {os.path.basename(path)}...")
        self.statusBar().repaint()

        try:
            vertices, normals = self._load_stl(path)
            self._current_stl_path = path
            self._viewport.set_mesh(vertices, normals)

            # Compute stock from mesh bounds
            if len(vertices) > 0:
                mins = vertices.min(axis=0)
                maxs = vertices.max(axis=0)
                bbox = BBox(
                    min=Vec3(mins[0], mins[1], mins[2]),
                    max=Vec3(maxs[0], maxs[1], maxs[2]),
                )
                # Create stock model with 2mm padding
                pad = 2.0
                self._stock_model = StockModel(
                    origin_x=bbox.min.x - pad,
                    origin_y=bbox.min.y - pad,
                    width_x=bbox.size.x + 2 * pad,
                    width_y=bbox.size.y + 2 * pad,
                    top_z=bbox.max.z + pad,
                )

            self._status_label.setText(
                f"Loaded: {os.path.basename(path)} — "
                f"{len(vertices)} vertices"
            )
            self.setWindowTitle(f"AI CAM 4.0 — {os.path.basename(path)}")
            logger.info("Imported STL: %s (%d vertices)", path, len(vertices))

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to load STL:\n{e}")
            self._status_label.setText("Import failed")
            logger.error("STL import failed: %s", e)

    @Slot()
    def _on_export_gcode(self) -> None:
        """Export the current toolpath as G-code."""
        if self._current_toolpath is None:
            QMessageBox.information(
                self,
                "Export G-code",
                "No toolpath to export. Run a strategy first.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export G-code",
            "",
            "Fanuc G-code (*.nc);;Heidenhain (*.h);;All Files (*)",
        )
        if not path:
            return

        try:
            # Determine renderer from extension
            ext = Path(path).suffix.lower()
            if ext == ".h":
                renderer = HeidenhainRenderer(
                    program_name=Path(path).stem.upper(),
                )
            else:
                renderer = FanucRenderer()

            # Convert toolpath → IR → G-code
            ir_segments = segments_to_ir(self._current_toolpath)
            gcode = renderer.render(ir_segments)

            with open(path, "w", encoding="utf-8") as f:
                f.write(gcode)

            self._status_label.setText(
                f"Exported: {os.path.basename(path)} ({len(ir_segments)} segments)"
            )
            logger.info(
                "Exported G-code to %s (%d segments)", path, len(ir_segments)
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")
            self._status_label.setText("Export failed")
            logger.error("G-code export failed: %s", e)

    # ==================================================================
    # Edit actions
    # ==================================================================

    @Slot()
    def _on_undo(self) -> None:
        """Undo the last strategy run."""
        if not self._undo_stack:
            self._status_label.setText("Nothing to undo")
            return

        # Move current to redo stack
        if self._current_toolpath:
            self._redo_stack.append(self._current_toolpath)

        # Restore previous
        self._current_toolpath = self._undo_stack.pop()

        # Update viewport
        if self._current_toolpath:
            self._viewport.set_toolpath_from_moves(self._current_toolpath)
            self._move_label.setText(
                f"Moves: {len(self._current_toolpath.moves)}"
            )
            self._status_label.setText(
                f"Undone — back to '{self._current_toolpath.name}' "
                f"({len(self._current_toolpath.moves)} moves)"
            )
        else:
            self._viewport.set_toolpath([])
            self._move_label.setText("Moves: 0")
            self._status_label.setText("Undone — toolpath cleared")

    @Slot()
    def _on_redo(self) -> None:
        """Redo the last undone strategy."""
        if not self._redo_stack:
            self._status_label.setText("Nothing to redo")
            return

        # Move current to undo stack
        if self._current_toolpath:
            self._undo_stack.append(self._current_toolpath)

        # Restore redo
        self._current_toolpath = self._redo_stack.pop()

        # Update viewport
        if self._current_toolpath:
            self._viewport.set_toolpath_from_moves(self._current_toolpath)
            self._move_label.setText(
                f"Moves: {len(self._current_toolpath.moves)}"
            )
            self._status_label.setText(
                f"Redone — '{self._current_toolpath.name}' "
                f"({len(self._current_toolpath.moves)} moves)"
            )

    # ==================================================================
    # View actions
    # ==================================================================

    @Slot(bool)
    def _on_toggle_grid(self, checked: bool) -> None:
        self._viewport.show_grid = checked
        self._viewport.update()
        self._status_label.setText(f"Grid: {'ON' if checked else 'OFF'}")

    @Slot(bool)
    def _on_toggle_mesh(self, checked: bool) -> None:
        self._viewport.show_mesh = checked
        self._viewport.update()
        self._status_label.setText(f"Mesh: {'ON' if checked else 'OFF'}")

    @Slot(bool)
    def _on_toggle_toolpath(self, checked: bool) -> None:
        self._viewport.show_toolpath = checked
        self._viewport.update()
        self._status_label.setText(f"Toolpath: {'ON' if checked else 'OFF'}")

    @Slot(bool)
    def _on_toggle_stock(self, checked: bool) -> None:
        self._viewport.show_stock = checked
        self._viewport.update()
        self._status_label.setText(f"Stock: {'ON' if checked else 'OFF'}")

    # ==================================================================
    # Help
    # ==================================================================

    @Slot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About AI CAM 4.0",
            "<h2>AI CAM 4.0</h2>"
            "<p>Minimal scope, maximum functionality CAM system.</p>"
            "<p><b>Kernel:</b> Pure Python + NumPy<br>"
            "<b>GUI:</b> PySide6 + OpenGL<br>"
            "<b>Data Flow:</b> Strategy → ToolpathData → Simulation → Viewport</p>"
            "<p>Lessons learned from AI CAM 3.0 — no stubs, one window, "
            "real handlers only.</p>",
        )

    # ==================================================================
    # Strategy execution
    # ==================================================================

    @Slot()
    def _on_run_strategy(self) -> None:
        """Run the selected strategy on the current stock/mesh."""
        # Get selected strategy
        idx = self._strategy_combo.currentIndex()
        strategies = list_strategies()
        if idx < 0 or idx >= len(strategies):
            self._status_label.setText("No strategy selected")
            return
        strategy = strategies[idx]

        # Create tool
        tool = ToolDef(
            tool_id="T01",
            name="10mm End Mill",
            diameter=10.0,
            flute_length=30.0,
        )

        # Create stock bounding box
        bbox = BBox(
            min=Vec3(
                self._stock_model.origin_x,
                self._stock_model.origin_y,
                0,
            ),
            max=Vec3(
                self._stock_model.origin_x + self._stock_model.width_x,
                self._stock_model.origin_y + self._stock_model.width_y,
                self._stock_model.top_z,
            ),
        )

        self._status_label.setText(f"Running {strategy}...")
        self.statusBar().repaint()

        try:
            # Save current toolpath to undo stack
            if self._current_toolpath:
                self._undo_stack.append(self._current_toolpath)
                self._redo_stack.clear()

            # Execute strategy
            toolpath = self._executor.execute(
                strategy=strategy,
                tool=tool,
                stock_bbox=bbox,
                material=Material.ALUMINUM,
            )

            self._current_toolpath = toolpath

            # Update viewport with toolpath
            self._viewport.set_toolpath_from_moves(toolpath)
            self._move_label.setText(f"Moves: {len(toolpath.moves)}")
            self._status_label.setText(
                f"Strategy '{strategy}' complete — {len(toolpath.moves)} moves"
            )
            logger.info(
                "Strategy '%s' completed with %d moves",
                strategy, len(toolpath.moves),
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Strategy Error", f"Strategy failed:\n{e}"
            )
            self._status_label.setText("Strategy failed")
            logger.error("Strategy execution failed: %s", e)

    # ==================================================================
    # Strategy selector callback
    # ==================================================================

    @Slot(int)
    def _on_strategy_changed(self, index: int) -> None:
        strategies = list_strategies()
        if 0 <= index < len(strategies):
            name = strategies[index]
            self._status_label.setText(
                f"Strategy: {name.replace('_', ' ').title()}"
            )

    # ==================================================================
    # Simulation
    # ==================================================================

    @Slot()
    def _on_toggle_simulation(self) -> None:
        """Toggle simulation play/pause."""
        if self._current_toolpath is None:
            self._status_label.setText("No toolpath to simulate")
            return

        state = self._sim_controller.state
        if state == "playing":
            self._sim_controller.pause()
        elif state == "paused":
            self._sim_controller.play()
        else:
            # Generate simulation frames
            self._status_label.setText("Generating simulation frames...")
            self.statusBar().repaint()

            try:
                engine = SimulationEngine(
                    stock=self._stock_model,
                    cutter_diameter=self._current_toolpath.tool.diameter,
                )
                frames = engine.simulate_to_frames(self._current_toolpath)
                self._sim_controller.load_frames(frames)
                self._sim_controller.play()
                self._status_label.setText(
                    f"Simulating — {len(frames)} frames"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Simulation Error", f"Simulation failed:\n{e}"
                )
                self._status_label.setText("Simulation failed")
                logger.error("Simulation failed: %s", e)

    @Slot(object)
    def _on_frame_ready(self, frame: Any) -> None:
        """Handle a new simulation frame from the controller."""
        self._viewport.update_simulation_state(
            zmap=frame.zmap,
            tool_pos=frame.tool_position,
            origin=frame.stock_min,
            resolution=frame.resolution,
        )

    @Slot(str)
    def _on_sim_state_changed(self, state: str) -> None:
        """Update status when simulation state changes."""
        icon = {"playing": "▶", "paused": "⏸", "stopped": "⏹", "idle": "⏹"}.get(state, "")
        self._status_label.setText(f"Simulation: {icon} {state.title()}")

    @Slot(str)
    def _on_speed_changed(self, text: str) -> None:
        """Handle speed selector change."""
        try:
            speed = float(text.replace("x", ""))
            self._sim_controller.set_speed(speed)
        except ValueError:
            pass

    # ==================================================================
    # FPS display
    # ==================================================================

    @Slot()
    def _update_fps(self) -> None:
        fps = self._viewport.fps
        self._fps_label.setText(f"FPS: {fps:.1f}")

    # ==================================================================
    # STL loader (simple binary/ASCII STL parser)
    # ==================================================================

    @staticmethod
    def _load_stl(path: str) -> tuple[np.ndarray, np.ndarray]:
        """
        Load an STL file and return (vertices, normals).

        Supports both binary and ASCII STL formats.
        Returns vertices as (N, 3) array and normals as (N, 3) array.
        """
        with open(path, "rb") as f:
            header = f.read(80)

            # Check if binary STL (starts with 'solid' but might be binary)
            is_binary = True
            try:
                text = header.decode("ascii", errors="ignore")
                if text.startswith("solid") and b"\n" in header:
                    # Could be ASCII — peek at first few lines
                    rest = f.read(200)
                    f.seek(80)
                    first_line = header.split(b"\n")[0]
                    if not first_line.strip().endswith(b"\n") or b"facet" in rest:
                        is_binary = False
            except Exception:
                pass

            if is_binary:
                return MainWindow._load_stl_binary(f)
            else:
                return MainWindow._load_stl_ascii(path)

    @staticmethod
    def _load_stl_binary(f: Any) -> tuple[np.ndarray, np.ndarray]:
        """Load binary STL."""
        # Skip header (already read 80 bytes)
        num_triangles_bytes = f.read(4)
        num_triangles = int.from_bytes(num_triangles_bytes, byteorder="little")

        vertices = []
        normals = []

        for _ in range(num_triangles):
            data = f.read(50)  # 12 + 3*12 + 2 = 50
            if len(data) < 50:
                break

            # Normal (3 floats)
            nx = np.float32.from_bytes(data[0:4], "little")
            ny = np.float32.from_bytes(data[4:8], "little")
            nz = np.float32.from_bytes(data[8:12], "little")

            for v in range(3):
                offset = 12 + v * 12
                vx = np.float32.from_bytes(data[offset:offset + 4], "little")
                vy = np.float32.from_bytes(data[offset + 4:offset + 8], "little")
                vz = np.float32.from_bytes(data[offset + 8:offset + 12], "little")
                vertices.append([vx, vy, vz])
                normals.append([nx, ny, nz])

        return (
            np.array(vertices, dtype=np.float32) if vertices else np.empty((0, 3), dtype=np.float32),
            np.array(normals, dtype=np.float32) if normals else np.empty((0, 3), dtype=np.float32),
        )

    @staticmethod
    def _load_stl_ascii(path: str) -> tuple[np.ndarray, np.ndarray]:
        """Load ASCII STL."""
        vertices = []
        normals = []
        current_normal = [0.0, 0.0, 1.0]

        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("facet normal"):
                    parts = line.split()
                    current_normal = [float(parts[2]), float(parts[3]), float(parts[4])]
                elif line.startswith("vertex"):
                    parts = line.split()
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    normals.append(current_normal[:])

        return (
            np.array(vertices, dtype=np.float32) if vertices else np.empty((0, 3), dtype=np.float32),
            np.array(normals, dtype=np.float32) if normals else np.empty((0, 3), dtype=np.float32),
        )
