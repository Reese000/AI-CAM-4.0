"""
AI CAM 4.0 Background Workers — QThread-based frame generation.

FrameWorker generates simulation frames off the main thread.
NO GL calls from any worker — only data processing.

Signals carry the data back to the main thread for safe GL updates.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from PySide6.QtCore import QThread, Signal, Slot

from kernel.types import ToolpathData
from simulation.engine import SimulationEngine, SimulationFrame, StockModel

logger = logging.getLogger(__name__)


class FrameWorker(QThread):
    """
    Background worker that generates simulation frames.

    Runs the SimulationEngine on a worker thread and emits frames
    via signals. The main thread receives frames and updates the
    viewport — NO GL calls happen on this thread.

    Signals:
        frame_ready(SimulationFrame)  — Emitted for each generated frame
        progress(float)               — 0.0 – 1.0 progress
        finished_ok(int)              — Total frames generated
        error(str)                     — Error message if simulation fails
    """

    frame_ready = Signal(object)   # SimulationFrame
    progress = Signal(float)
    finished_ok = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        toolpath: ToolpathData,
        stock: StockModel | None = None,
        cutter_diameter: float = 10.0,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._toolpath = toolpath
        self._stock = stock or StockModel()
        self._cutter_diameter = cutter_diameter
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. The worker checks this between frames."""
        self._cancelled = True

    def run(self) -> None:
        """
        Execute simulation on the worker thread.

        Generates ALL frames and stores them internally.
        Emits frame_ready for each frame so the main thread can
        update the viewport progressively.
        """
        try:
            engine = SimulationEngine(
                stock=self._stock,
                cutter_diameter=self._cutter_diameter,
            )

            total_moves = len(self._toolpath.moves)
            if total_moves == 0:
                self.error.emit("No moves in toolpath")
                return

            logger.info(
                "FrameWorker: Starting simulation — %d moves", total_moves
            )

            # Generate frames one by one
            frames: list[SimulationFrame] = []

            for i, move in enumerate(self._toolpath.moves):
                if self._cancelled:
                    logger.info("FrameWorker: Cancelled at move %d", i)
                    break

                # Create a single-move toolpath for incremental simulation
                single_move_tp = ToolpathData(
                    name="single",
                    tool=self._toolpath.tool,
                    material=self._toolpath.material,
                    moves=[move],
                    strategy=self._toolpath.strategy,
                )

                # This isn't truly incremental — it simulates the move
                # on the current stock state. For simplicity we simulate
                # the full toolpath but emit frames progressively.
                pass

            # Full simulation — generate all frames at once
            frames = engine.simulate_to_frames(self._toolpath)

            # Emit frames for viewport updates
            for i, frame in enumerate(frames):
                if self._cancelled:
                    break

                self.frame_ready.emit(frame)
                progress = (i + 1) / max(1, len(frames))
                self.progress.emit(progress)

            if not self._cancelled:
                self.finished_ok.emit(len(frames))
                logger.info(
                    "FrameWorker: Finished — %d frames generated", len(frames)
                )

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("FrameWorker error: %s\n%s", e, tb)
            self.error.emit(f"{e}\n{tb}")
