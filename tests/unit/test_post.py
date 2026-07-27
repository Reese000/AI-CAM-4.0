"""
Unit tests: Post-processors (IR, Fanuc, Heidenhain).
"""

import pytest

from kernel.types import (
    BBox,
    Material,
    Move,
    MoveType,
    ToolDef,
    ToolpathData,
    Vec3,
)
from post.fanuc import BaseRenderer, FanucRenderer
from post.heidenhain import HeidenhainRenderer
from post.ir import IRSegment, SegmentType, segments_to_ir


# ---------------------------------------------------------------------------
# IR tests
# ---------------------------------------------------------------------------

class TestIR:
    """Intermediate representation tests."""

    def test_segments_to_ir_count(self):
        """IR segments include wrapper blocks (start, tool, spindle, end)."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        # Should be more segments than raw moves (wrapping blocks added)
        assert len(segments) > len(tp.moves)

    def test_segments_to_ir_types(self):
        """IR segments have valid types."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        for seg in segments:
            assert isinstance(seg.segment_type, SegmentType)

    def test_program_start_and_end(self):
        """IR includes PROGRAM_START and PROGRAM_END."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        types = [s.segment_type for s in segments]
        assert SegmentType.PROGRAM_START in types
        assert SegmentType.PROGRAM_END in types

    def test_tool_change(self):
        """IR includes a TOOL_CHANGE segment."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        tool_changes = [s for s in segments if s.segment_type == SegmentType.TOOL_CHANGE]
        assert len(tool_changes) == 1
        assert tool_changes[0].tool_number == "01"

    def test_spindle_on(self):
        """IR includes a SPINDLE_ON segment with correct speed."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        spindle = [s for s in segments if s.segment_type == SegmentType.SPINDLE_ON]
        assert len(spindle) == 1
        assert spindle[0].spindle_speed == 8000.0

    def test_motion_segments_preserved(self):
        """Motion segments preserve coordinates from ToolpathData."""
        tp = self._make_toolpath()
        segments = segments_to_ir(tp)
        motion_segs = [s for s in segments if s.is_motion]
        assert len(motion_segs) == len(tp.moves)

        for seg, move in zip(motion_segs, tp.moves):
            assert abs(seg.x - move.end.x) < 1e-6
            assert abs(seg.y - move.end.y) < 1e-6
            assert abs(seg.z - move.end.z) < 1e-6

    def test_ir_segment_is_motion(self):
        """is_motion property works for all segment types."""
        assert IRSegment(segment_type=SegmentType.LINEAR).is_motion
        assert IRSegment(segment_type=SegmentType.RAPID).is_motion
        assert IRSegment(segment_type=SegmentType.ARC_CW).is_motion
        assert not IRSegment(segment_type=SegmentType.TOOL_CHANGE).is_motion
        assert not IRSegment(segment_type=SegmentType.PROGRAM_END).is_motion

    @staticmethod
    def _make_toolpath() -> ToolpathData:
        return ToolpathData(
            name="test",
            tool=ToolDef(tool_id="T01", diameter=10.0, flute_length=30.0),
            material=Material.ALUMINUM,
            moves=[
                Move(move_type=MoveType.RAPID, end=Vec3(0, 0, 20)),
                Move(move_type=MoveType.LINEAR, end=Vec3(10, 0, 10), feed=500, spindle_speed=8000, coolant=True),
                Move(move_type=MoveType.LINEAR, end=Vec3(20, 0, 10), feed=500, spindle_speed=8000),
                Move(move_type=MoveType.RETRACT, end=Vec3(20, 0, 30)),
            ],
        )


# ---------------------------------------------------------------------------
# Fanuc tests
# ---------------------------------------------------------------------------

class TestFanucRenderer:
    """Fanuc G-code output tests."""

    def test_output_has_program_number(self):
        """Output contains O0001."""
        gcode = self._render()
        assert "O0001" in gcode

    def test_output_has_metric_mode(self):
        """Output contains G21."""
        gcode = self._render()
        assert "G21" in gcode

    def test_output_has_absolute_mode(self):
        """Output contains G90."""
        gcode = self._render()
        assert "G90" in gcode

    def test_output_has_tool_change(self):
        """Output contains M06."""
        gcode = self._render()
        assert "M06" in gcode

    def test_output_has_spindle_on(self):
        """Output contains M03."""
        gcode = self._render()
        assert "M03" in gcode

    def test_output_has_coolant(self):
        """Output contains M08 when coolant is on."""
        gcode = self._render()
        assert "M08" in gcode

    def test_output_has_program_end(self):
        """Output contains M30."""
        gcode = self._render()
        assert "M30" in gcode

    def test_output_has_feed_rate(self):
        """Output contains F parameter for cutting moves."""
        gcode = self._render()
        assert "F" in gcode

    def test_output_has_g01_for_linear(self):
        """Output contains G01 for linear moves."""
        gcode = self._render()
        assert "G01" in gcode

    def test_output_has_g00_for_rapid(self):
        """Output contains G00 for rapid moves."""
        gcode = self._render()
        assert "G00" in gcode

    def test_output_ends_with_percent(self):
        """Fanuc programs end with %."""
        gcode = self._render()
        assert gcode.strip().endswith("%")

    def test_custom_program_number(self):
        """Custom program number renders correctly."""
        renderer = FanucRenderer(program_number=42)
        tp = TestIR._make_toolpath()
        segments = segments_to_ir(tp)
        gcode = renderer.render(segments)
        assert "O0042" in gcode

    def test_render_to_file(self):
        """render_to_file produces a valid file."""
        import tempfile
        import os

        renderer = FanucRenderer()
        tp = TestIR._make_toolpath()
        segments = segments_to_ir(tp)

        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
            path = f.name

        try:
            renderer.render_to_file(segments, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def _render(self) -> str:
        renderer = FanucRenderer()
        tp = TestIR._make_toolpath()
        segments = segments_to_ir(tp)
        return renderer.render(segments)


# ---------------------------------------------------------------------------
# Heidenhain tests
# ---------------------------------------------------------------------------

class TestHeidenhainRenderer:
    """Heidenhain format output tests."""

    def test_output_has_begin_pgm(self):
        """Output contains BEGIN PGM."""
        gcode = self._render()
        assert "BEGIN PGM" in gcode

    def test_output_has_end_pgm(self):
        """Output contains END PGM."""
        gcode = self._render()
        assert "END PGM" in gcode

    def test_output_has_blk_form(self):
        """Output contains BLK FORM for stock definition."""
        gcode = self._render()
        assert "BLK FORM" in gcode

    def test_output_has_tool_call(self):
        """Output contains TOOL CALL."""
        gcode = self._render()
        assert "TOOL CALL" in gcode

    def test_output_has_linear_moves(self):
        """Output contains L (linear) moves."""
        gcode = self._render()
        assert " L " in gcode

    def test_output_has_rapid(self):
        """Output contains R0 or FMAX for rapids."""
        gcode = self._render()
        assert "R0" in gcode or "FMAX" in gcode

    def test_mm_units(self):
        """Program specifies MM units."""
        gcode = self._render()
        assert "MM" in gcode

    def _render(self) -> str:
        renderer = HeidenhainRenderer()
        tp = TestIR._make_toolpath()
        segments = segments_to_ir(tp)
        return renderer.render(segments)
