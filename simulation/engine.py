"""
AI CAM 4.0 Simulation Engine — Z-map heightfield stock model.

Zero Qt imports. Pure Python + NumPy. Produces SimulationFrame frozen
dataclasses consumed by the viewport.

Resolution: 0.5mm grid cells. The stock is a 2D heightfield (X, Y) where
each cell stores the current Z height of the material surface. Cutting
reduces the Z height; rapids leave it unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from kernel.types import Move, ToolpathData


# ---------------------------------------------------------------------------
# Frozen frame — immutable snapshot for O(1) random access
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SimulationFrame:
    """
    Immutable snapshot of stock state at a given point in the toolpath.

    zmap: np.ndarray[float64]  — Z heights at each grid cell (shape: rows×cols)
    tool_position: tuple[float, float, float] — current tool tip (x, y, z)
    move_index: int — which ToolpathData move produced this frame
    stock_min: tuple[float, float, float] — world-space origin of the stock box
    resolution: float — mm per grid cell
    """
    zmap: np.ndarray
    tool_position: tuple[float, float, float]
    move_index: int
    stock_min: tuple[float, float, float]
    resolution: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.zmap.shape


# ---------------------------------------------------------------------------
# Stock model — mutable heightfield used during simulation
# ---------------------------------------------------------------------------

class StockModel:
    """
    Mutable Z-map heightfield representing the workpiece material.

    Grid cells store the current top surface Z coordinate. The stock
    occupies a rectangular region in XY defined by (origin_x, origin_y)
    with width_x × width_y mm, discretized at `resolution` mm/cell.
    """

    def __init__(
        self,
        origin_x: float = -50.0,
        origin_y: float = -50.0,
        width_x: float = 100.0,
        width_y: float = 100.0,
        top_z: float = 20.0,
        resolution: float = 0.5,
    ) -> None:
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.width_x = width_x
        self.width_y = width_y
        self.top_z = top_z
        self.resolution = resolution

        self.cols = max(1, int(math.ceil(width_x / resolution)))
        self.rows = max(1, int(math.ceil(width_y / resolution)))

        # Initialize all cells at top_z
        self.zmap: np.ndarray = np.full(
            (self.rows, self.cols), top_z, dtype=np.float64
        )

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world XY to grid (row, col) indices."""
        col = int((x - self.origin_x) / self.resolution)
        row = int((y - self.origin_y) / self.resolution)
        row = max(0, min(row, self.rows - 1))
        col = max(0, min(col, self.cols - 1))
        return row, col

    def grid_to_world(self, row: int, col: int) -> tuple[float, float]:
        """Convert grid (row, col) to world XY center of cell."""
        x = self.origin_x + (col + 0.5) * self.resolution
        y = self.origin_y + (row + 0.5) * self.resolution
        return x, y

    def cut_at(self, x: float, y: float, z: float, radius: float) -> None:
        """
        Simulate a circular cutter removing material at (x, y, z).

        All grid cells within `radius` of (x, y) have their Z reduced
        to at most `z` (but never raised above the current surface).
        """
        r_cells = int(math.ceil(radius / self.resolution)) + 1

        row_center, col_center = self.world_to_grid(x, y)

        r0 = max(0, row_center - r_cells)
        r1 = min(self.rows, row_center + r_cells + 1)
        c0 = max(0, col_center - r_cells)
        c1 = min(self.cols, col_center + r_cells + 1)

        if r0 >= r1 or c0 >= c1:
            return

        # Vectorised: compute distance from each cell to (x, y)
        rows_idx = np.arange(r0, r1)[:, np.newaxis]
        cols_idx = np.arange(c0, c1)[np.newaxis, :]
        wx = self.origin_x + (cols_idx + 0.5) * self.resolution
        wy = self.origin_y + (rows_idx + 0.5) * self.resolution
        dist = np.sqrt((wx - x) ** 2 + (wy - y) ** 2)

        # Mask: cells within the cutter radius
        mask = dist <= radius
        if not np.any(mask):
            return

        # Reduce Z: only lower, never raise
        self.zmap[r0:r1, c0:c1] = np.where(
            mask, np.minimum(self.zmap[r0:r1, c0:c1], z), self.zmap[r0:r1, c0:c1]
        )

    def snapshot(self) -> np.ndarray:
        """Return a read-only copy of the current heightfield."""
        return self.zmap.copy()

    def bounding_box_world(self) -> tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y) in world coords."""
        return (
            self.origin_x,
            self.origin_y,
            self.origin_x + self.cols * self.resolution,
            self.origin_y + self.rows * self.resolution,
        )


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------

class SimulationEngine:
    """
    Drives the simulation by replaying a ToolpathData through a StockModel.

    Each cutting move removes material; rapids are tracked for tool position
    but don't affect the stock.
    """

    def __init__(
        self,
        stock: StockModel | None = None,
        cutter_diameter: float = 10.0,
    ) -> None:
        self.stock = stock or StockModel()
        self.cutter_diameter = cutter_diameter
        self.cutter_radius = cutter_diameter / 2.0

    def simulate_to_frames(self, toolpath: ToolpathData) -> list[SimulationFrame]:
        """
        Replay a complete toolpath and return one SimulationFrame per move.

        Frames are pre-computed in memory for O(1) random access during
        playback. A simple straight-line interpolation between move end
        points simulates the continuous cut at the current resolution.
        """
        frames: list[SimulationFrame] = []
        origin = (
            self.stock.origin_x,
            self.stock.origin_y,
            self.stock.top_z,
        )

        # Track position (start at origin or first move)
        current_x = 0.0
        current_y = 0.0
        current_z = self.stock.top_z + 10.0  # start above stock

        for i, move in enumerate(toolpath.moves):
            end_x = move.end.x
            end_y = move.end.y
            end_z = move.end.z

            if move.move_type.name in ("LINEAR", "ARC_CW", "ARC_CCW"):
                # Cutting move — interpolate and remove material
                dist = math.sqrt(
                    (end_x - current_x) ** 2 + (end_y - current_y) ** 2
                )
                steps = max(1, int(dist / (self.cutter_radius * 0.5)))

                for s in range(steps + 1):
                    t = s / steps
                    ix = current_x + t * (end_x - current_x)
                    iy = current_y + t * (end_y - current_y)
                    iz = current_z + t * (end_z - current_z)
                    self.stock.cut_at(ix, iy, iz, self.cutter_radius)

                # Snap tool to end
                current_x, current_y, current_z = end_x, end_y, end_z

            elif move.move_type.name == "RAPID":
                current_x, current_y, current_z = end_x, end_y, end_z

            elif move.move_type.name == "RETRACT":
                current_z = end_z

            elif move.move_type.name == "DRILL":
                # Simple plunge — cut at final position
                self.stock.cut_at(end_x, end_y, end_z, self.cutter_radius)
                current_x, current_y, current_z = end_x, end_y, end_z

            frame = SimulationFrame(
                zmap=self.stock.snapshot(),
                tool_position=(current_x, current_y, current_z),
                move_index=i,
                stock_min=origin,
                resolution=self.stock.resolution,
            )
            frames.append(frame)

        return frames
