"""
Unit tests: Simulation engine (StockModel, SimulationEngine, frames).
"""

import math

import numpy as np
import pytest

from kernel.types import Move, MoveType, ToolDef, ToolpathData, Vec3
from simulation.engine import SimulationEngine, SimulationFrame, StockModel


# ---------------------------------------------------------------------------
# StockModel tests
# ---------------------------------------------------------------------------

class TestStockModel:
    """StockModel Z-map heightfield tests."""

    def test_default_stock(self):
        """Default stock creates a 100x100mm block at 0.5mm resolution."""
        stock = StockModel()
        assert stock.rows == 200
        assert stock.cols == 200
        assert stock.top_z == 20.0
        assert stock.resolution == 0.5

    def test_custom_stock(self):
        """Custom dimensions create the right grid size."""
        stock = StockModel(
            origin_x=-25, origin_y=-25,
            width_x=50, width_y=50,
            top_z=10, resolution=1.0,
        )
        assert stock.rows == 50
        assert stock.cols == 50
        assert stock.zmap.shape == (50, 50)

    def test_initial_height(self):
        """All cells start at top_z."""
        stock = StockModel(top_z=15.0)
        assert np.allclose(stock.zmap, 15.0)

    def test_world_to_grid(self):
        """World coordinates map to correct grid indices."""
        stock = StockModel(
            origin_x=0, origin_y=0,
            width_x=10, width_y=10,
            resolution=1.0,
        )
        row, col = stock.world_to_grid(3.5, 7.2)
        assert col == 3
        assert row == 7

    def test_grid_to_world(self):
        """Grid indices map to correct world coordinates."""
        stock = StockModel(
            origin_x=0, origin_y=0,
            width_x=10, width_y=10,
            resolution=1.0,
        )
        x, y = stock.grid_to_world(5, 3)
        assert abs(x - 3.5) < 0.01
        assert abs(y - 5.5) < 0.01

    def test_cut_at_reduces_height(self):
        """Cutting reduces Z height within the cutter radius."""
        stock = StockModel(top_z=10.0, resolution=1.0)
        stock.cut_at(5.0, 5.0, z=5.0, radius=3.0)
        # Center should be at z=5.0
        row, col = stock.world_to_grid(5.0, 5.0)
        assert stock.zmap[row, col] == 5.0
        # Far away should still be at 10.0
        row2, col2 = stock.world_to_grid(0.0, 0.0)
        assert stock.zmap[row2, col2] == 10.0

    def test_cut_never_raises(self):
        """Cutting never raises material above current surface."""
        stock = StockModel(top_z=10.0, resolution=1.0)
        # First cut to 5.0
        stock.cut_at(5.0, 5.0, z=5.0, radius=3.0)
        # Second cut to 7.0 should not raise it
        stock.cut_at(5.0, 5.0, z=7.0, radius=3.0)
        row, col = stock.world_to_grid(5.0, 5.0)
        assert stock.zmap[row, col] == 5.0

    def test_snapshot_returns_copy(self):
        """Snapshot returns an independent copy."""
        stock = StockModel()
        snap = stock.snapshot()
        stock.cut_at(0, 0, z=0, radius=1.0)
        # Original changed, snapshot should not
        assert snap[stock.rows // 2, stock.cols // 2] == stock.top_z

    def test_bounding_box(self):
        """Bounding box returns correct world extent."""
        stock = StockModel(
            origin_x=-10, origin_y=-10,
            width_x=20, width_y=20,
        )
        bbox = stock.bounding_box_world()
        assert bbox == (-10, -10, 10, 10)


# ---------------------------------------------------------------------------
# SimulationEngine tests
# ---------------------------------------------------------------------------

class TestSimulationEngine:
    """SimulationEngine toolpath replay tests."""

    def _make_linear_toolpath(self) -> ToolpathData:
        """Create a simple toolpath with rapid → cut → retract."""
        return ToolpathData(
            name="test",
            tool=ToolDef(diameter=2.0),
            moves=[
                Move(move_type=MoveType.RAPID, end=Vec3(-5, 0, 10)),
                Move(move_type=MoveType.LINEAR, end=Vec3(5, 0, 5), feed=500),
                Move(move_type=MoveType.RETRACT, end=Vec3(5, 0, 10)),
            ],
        )

    def test_simulate_returns_frames(self):
        """Simulation produces one frame per move."""
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)
        assert len(frames) == len(tp.moves)

    def test_frame_is_frozen(self):
        """SimulationFrame is a frozen dataclass."""
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)
        frame = frames[0]
        with pytest.raises(AttributeError):
            frame.move_index = 999  # type: ignore

    def test_frame_has_zmap(self):
        """Each frame contains a Z-map heightfield."""
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)
        for frame in frames:
            assert isinstance(frame.zmap, np.ndarray)
            assert frame.zmap.ndim == 2

    def test_frame_tool_position(self):
        """Each frame tracks tool position."""
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)
        for frame in frames:
            assert len(frame.tool_position) == 3
            assert all(isinstance(v, (int, float)) for v in frame.tool_position)

    def test_cutting_reduces_stock(self):
        """After a cutting move, stock Z is lower than initial."""
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)

        initial_z = StockModel().top_z
        final_z = frames[-1].zmap.mean()
        assert final_z < initial_z

    def test_stock_model_used(self):
        """Simulation uses the provided stock model."""
        stock = StockModel(top_z=15.0, resolution=0.5)
        tp = self._make_linear_toolpath()
        engine = SimulationEngine(stock=stock, cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)

        assert len(frames) > 0
        # Stock dimensions should match
        assert frames[0].zmap.shape == (stock.rows, stock.cols)

    def test_empty_toolpath(self):
        """Empty toolpath produces zero frames."""
        tp = ToolpathData(name="empty")
        engine = SimulationEngine()
        frames = engine.simulate_to_frames(tp)
        assert len(frames) == 0

    def test_rapid_does_not_cut(self):
        """Rapid moves don't remove material."""
        tp = ToolpathData(
            name="rapid only",
            tool=ToolDef(diameter=2.0),
            moves=[
                Move(move_type=MoveType.RAPID, end=Vec3(0, 0, 10)),
                Move(move_type=MoveType.RAPID, end=Vec3(5, 5, 10)),
            ],
        )
        engine = SimulationEngine(cutter_diameter=2.0)
        frames = engine.simulate_to_frames(tp)
        # Both frames should have uncut stock
        for frame in frames:
            assert np.allclose(frame.zmap, StockModel().top_z)
