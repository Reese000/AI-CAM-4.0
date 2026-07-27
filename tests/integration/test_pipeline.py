"""
Integration tests: STL → Strategy → Toolpath → Export pipeline.

These test the real user path — no stubs, no mocks.
"""

import os
import tempfile

import numpy as np
import pytest

from app.strategy_executor import StrategyExecutor, list_strategies
from kernel.types import BBox, Material, ToolDef, ToolpathData, Vec3
from post.fanuc import FanucRenderer
from post.heidenhain import HeidenhainRenderer
from post.ir import segments_to_ir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_toolpath() -> ToolpathData:
    """Create a minimal toolpath for testing."""
    from kernel.types import Move, MoveType

    executor = StrategyExecutor()
    tool = ToolDef(diameter=10.0, flute_length=30.0)
    bbox = BBox(min=Vec3(-50, -50, 0), max=Vec3(50, 50, 20))

    return executor.execute(
        strategy="face_milling",
        tool=tool,
        stock_bbox=bbox,
        material=Material.ALUMINUM,
    )


def make_simple_stl(path: str) -> None:
    """Write a minimal binary STL file (single triangle)."""
    with open(path, "wb") as f:
        # Header (80 bytes)
        f.write(b"\x00" * 80)
        # Triangle count
        f.write(np.uint32(1).tobytes())
        # Normal
        f.write(np.array([0.0, 0.0, 1.0], dtype=np.float32).tobytes())
        # Vertex 1
        f.write(np.array([0.0, 0.0, 0.0], dtype=np.float32).tobytes())
        # Vertex 2
        f.write(np.array([10.0, 0.0, 0.0], dtype=np.float32).tobytes())
        # Vertex 3
        f.write(np.array([0.0, 10.0, 0.0], dtype=np.float32).tobytes())
        # Attribute byte count
        f.write(np.uint16(0).tobytes())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipeline:
    """Full pipeline integration tests."""

    def test_strategy_to_toolpath(self):
        """Strategy generates a valid ToolpathData."""
        tp = make_test_toolpath()
        assert isinstance(tp, ToolpathData)
        assert len(tp.moves) > 0
        assert tp.strategy == "face_milling"
        assert tp.tool.diameter == 10.0

    def test_toolpath_has_moves(self):
        """Toolpath has at least 5 moves (rapid + cuts + retract)."""
        tp = make_test_toolpath()
        assert len(tp.moves) >= 5

    def test_toolpath_moves_are_typed(self):
        """Each move has a valid MoveType."""
        from kernel.types import MoveType
        tp = make_test_toolpath()
        for move in tp.moves:
            assert isinstance(move.move_type, MoveType)

    def test_toolpath_to_ir(self):
        """Toolpath converts to IR segments."""
        tp = make_test_toolpath()
        segments = segments_to_ir(tp)
        assert len(segments) > 0
        # Should have program start, tool change, spindle, motions, end
        types = [s.segment_type.name for s in segments]
        assert "PROGRAM_START" in types
        assert "TOOL_CHANGE" in types
        assert "PROGRAM_END" in types

    def test_ir_to_fanuc_gcode(self):
        """IR segments render to Fanuc G-code."""
        tp = make_test_toolpath()
        segments = segments_to_ir(tp)
        renderer = FanucRenderer()
        gcode = renderer.render(segments)

        assert isinstance(gcode, str)
        assert len(gcode) > 0
        # Mandatory blocks
        assert "O0001" in gcode          # Program number
        assert "M06" in gcode            # Tool change
        assert "M03" in gcode            # Spindle on
        assert "M30" in gcode            # Program end
        assert "G21" in gcode            # Metric mode
        assert "G90" in gcode            # Absolute positioning

    def test_ir_to_heidenhain(self):
        """IR segments render to Heidenhain format."""
        tp = make_test_toolpath()
        segments = segments_to_ir(tp)
        renderer = HeidenhainRenderer()
        gcode = renderer.render(segments)

        assert isinstance(gcode, str)
        assert len(gcode) > 0
        assert "BEGIN PGM" in gcode
        assert "END PGM" in gcode
        assert "BLK FORM" in gcode
        assert "TOOL CALL" in gcode

    def test_fanuc_export_to_file(self):
        """Fanuc G-code writes to a file."""
        tp = make_test_toolpath()
        segments = segments_to_ir(tp)
        renderer = FanucRenderer()

        with tempfile.NamedTemporaryFile(
            suffix=".nc", delete=False, mode="w"
        ) as f:
            path = f.name

        try:
            renderer.render_to_file(segments, path)
            assert os.path.exists(path)
            with open(path) as f:
                content = f.read()
            assert len(content) > 0
            assert "O0001" in content
        finally:
            os.unlink(path)

    def test_heidenhain_export_to_file(self):
        """Heidenhain code writes to a file."""
        tp = make_test_toolpath()
        segments = segments_to_ir(tp)
        renderer = HeidenhainRenderer()

        with tempfile.NamedTemporaryFile(
            suffix=".h", delete=False, mode="w"
        ) as f:
            path = f.name

        try:
            renderer.render_to_file(segments, path)
            assert os.path.exists(path)
            with open(path) as f:
                content = f.read()
            assert "BEGIN PGM" in content
        finally:
            os.unlink(path)

    def test_all_strategies_generate(self):
        """Every listed strategy produces a valid toolpath."""
        executor = StrategyExecutor()
        tool = ToolDef(diameter=10.0)
        bbox = BBox(min=Vec3(-50, -50, 0), max=Vec3(50, 50, 20))

        for name in list_strategies():
            tp = executor.execute(
                strategy=name,
                tool=tool,
                stock_bbox=bbox,
            )
            assert isinstance(tp, ToolpathData)
            assert len(tp.moves) > 0, f"Strategy '{name}' produced 0 moves"
            assert tp.strategy == name

    def test_stl_roundtrip(self):
        """Create an STL, verify it's a valid file."""
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            path = f.name

        try:
            make_simple_stl(path)
            assert os.path.getsize(path) > 80
        finally:
            os.unlink(path)

    def test_toolpath_bounding_box(self):
        """Toolpath computes a bounding box from its moves."""
        tp = make_test_toolpath()
        # BBox is computed in __post_init__
        assert tp.bounding_box is not None
