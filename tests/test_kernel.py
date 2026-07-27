"""
Comprehensive test suite for AI CAM 4.0 kernel.

Tests cover: Vec3, BBox, Transform, ToolpathData, STL parsing,
G-code parsing, SDF, and machining strategies.

Run: cd "C:/Users/reese/Projects/AI CAM 4.0" && python -m pytest tests/test_kernel.py -v
"""

import math
import os
import struct
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Ensure the project root is on the path
import sys
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kernel.types import Vec3, BBox, Transform, ToolpathData, ToolDef, Material
from kernel.stl import parse_stl, get_mesh_info
from kernel.gcode import (
    parse_gcode, GCodeCommand, is_rapid_move, is_linear_move,
    is_arc_move, is_spindle_on, is_tool_change, get_position, get_feed,
    summary,
)
from kernel.sdf import SDFGrid, create_from_mesh
from kernel.strategies import get_strategy, list_strategies, register_strategy
from kernel.strategies.base import BaseStrategy, OperationParams


# ===========================================================================
# Vec3 Tests
# ===========================================================================

class TestVec3:
    """Test suite for Vec3 operations."""

    def test_construction(self):
        v = Vec3(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0

    def test_default_values(self):
        v = Vec3()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_addition(self):
        a = Vec3(1, 2, 3)
        b = Vec3(4, 5, 6)
        result = a + b
        assert result == Vec3(5, 7, 9)

    def test_subtraction(self):
        a = Vec3(5, 7, 9)
        b = Vec3(1, 2, 3)
        result = a - b
        assert result == Vec3(4, 5, 6)

    def test_scalar_multiply(self):
        v = Vec3(1, 2, 3)
        result = v * 2.0
        assert result == Vec3(2, 4, 6)

    def test_rmul(self):
        v = Vec3(1, 2, 3)
        result = 3.0 * v
        assert result == Vec3(3, 6, 9)

    def test_division(self):
        v = Vec3(4, 6, 8)
        result = v / 2.0
        assert result == Vec3(2, 3, 4)

    def test_division_by_zero(self):
        v = Vec3(1, 2, 3)
        with pytest.raises(ZeroDivisionError):
            v / 0.0

    def test_negation(self):
        v = Vec3(1, -2, 3)
        result = -v
        assert result == Vec3(-1, 2, -3)

    def test_length(self):
        v = Vec3(3, 4, 0)
        assert v.length() == pytest.approx(5.0)

    def test_length_squared(self):
        v = Vec3(3, 4, 0)
        assert v.length_squared() == pytest.approx(25.0)

    def test_normalized(self):
        v = Vec3(0, 0, 5)
        n = v.normalized()
        assert n.length() == pytest.approx(1.0)
        assert n == Vec3(0, 0, 1)

    def test_normalized_zero_vector(self):
        v = Vec3(0, 0, 0)
        n = v.normalized()
        assert n == Vec3(0, 0, 0)

    def test_dot_product(self):
        a = Vec3(1, 0, 0)
        b = Vec3(0, 1, 0)
        assert a.dot(b) == pytest.approx(0.0)

    def test_dot_product_parallel(self):
        a = Vec3(1, 2, 3)
        b = Vec3(2, 4, 6)
        assert a.dot(b) == pytest.approx(28.0)

    def test_cross_product(self):
        a = Vec3(1, 0, 0)
        b = Vec3(0, 1, 0)
        c = a.cross(b)
        assert c == Vec3(0, 0, 1)

    def test_distance_to(self):
        a = Vec3(0, 0, 0)
        b = Vec3(3, 4, 0)
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_lerp(self):
        a = Vec3(0, 0, 0)
        b = Vec3(10, 10, 10)
        mid = a.lerp(b, 0.5)
        assert mid == Vec3(5, 5, 5)

    def test_to_array(self):
        v = Vec3(1, 2, 3)
        arr = v.to_array()
        assert isinstance(arr, np.ndarray)
        np.testing.assert_array_almost_equal(arr, [1, 2, 3])

    def test_from_array(self):
        arr = np.array([4, 5, 6])
        v = Vec3.from_array(arr)
        assert v == Vec3(4, 5, 6)

    def test_from_list(self):
        v = Vec3.from_array([7, 8, 9])
        assert v == Vec3(7, 8, 9)

    def test_iter(self):
        v = Vec3(1, 2, 3)
        coords = list(v)
        assert coords == [1.0, 2.0, 3.0]

    def test_getitem(self):
        v = Vec3(10, 20, 30)
        assert v[0] == 10
        assert v[1] == 20
        assert v[2] == 30

    def test_immutability(self):
        v = Vec3(1, 2, 3)
        with pytest.raises(AttributeError):
            v.x = 5  # type: ignore


# ===========================================================================
# BBox Tests
# ===========================================================================

class TestBBox:
    """Test suite for BBox operations."""

    def test_from_points(self):
        points = [Vec3(0, 0, 0), Vec3(10, 20, 30)]
        bb = BBox.from_points(points)
        assert bb.min_point == Vec3(0, 0, 0)
        assert bb.max_point == Vec3(10, 20, 30)

    def test_from_numpy_array(self):
        arr = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        bb = BBox.from_points(arr)
        assert bb.min_point == Vec3(1, 2, 3)
        assert bb.max_point == Vec3(7, 8, 9)

    def test_from_empty(self):
        bb = BBox.from_points([])
        # Empty BBox has inf min / -inf max → volume is -inf
        assert bb.min_point.x == float("inf")
        assert bb.max_point.x == float("-inf")

    def test_expand(self):
        bb = BBox.from_points([Vec3(0, 0, 0), Vec3(10, 10, 10)])
        bb2 = bb.expand(Vec3(20, -5, 15))
        assert bb2.min_point == Vec3(0, -5, 0)
        assert bb2.max_point == Vec3(20, 10, 15)

    def test_union(self):
        bb1 = BBox.from_points([Vec3(0, 0, 0), Vec3(5, 5, 5)])
        bb2 = BBox.from_points([Vec3(3, 3, 3), Vec3(10, 10, 10)])
        bb3 = bb1.union(bb2)
        assert bb3.min_point == Vec3(0, 0, 0)
        assert bb3.max_point == Vec3(10, 10, 10)

    def test_contains(self):
        bb = BBox.from_points([Vec3(0, 0, 0), Vec3(10, 10, 10)])
        assert bb.contains(Vec3(5, 5, 5))
        assert not bb.contains(Vec3(15, 5, 5))
        assert bb.contains(Vec3(0, 0, 0))  # On boundary

    def test_center(self):
        bb = BBox.from_points([Vec3(0, 0, 0), Vec3(10, 20, 30)])
        c = bb.center
        assert c == Vec3(5, 10, 15)

    def test_size(self):
        bb = BBox.from_points([Vec3(0, 0, 0), Vec3(10, 20, 30)])
        s = bb.size
        assert s == Vec3(10, 20, 30)

    def test_volume(self):
        bb = BBox.from_points([Vec3(0, 0, 0), Vec3(2, 3, 4)])
        assert bb.volume == pytest.approx(24.0)


# ===========================================================================
# Transform Tests
# ===========================================================================

class TestTransform:
    """Test suite for Transform operations."""

    def test_identity(self):
        t = Transform.identity()
        p = t.apply_to_point(Vec3(1, 2, 3))
        assert p == Vec3(1, 2, 3)

    def test_translation(self):
        t = Transform(translation=Vec3(10, 20, 30))
        p = t.apply_to_point(Vec3(1, 2, 3))
        assert p == Vec3(11, 22, 33)

    def test_rotation_90_z(self):
        # 90° rotation around Z axis: (1,0,0) → (0,1,0)
        t = Transform.from_euler(0, 0, math.pi / 2)
        p = t.apply_to_point(Vec3(1, 0, 0))
        assert p.x == pytest.approx(0.0, abs=1e-10)
        assert p.y == pytest.approx(1.0, abs=1e-10)
        assert p.z == pytest.approx(0.0, abs=1e-10)

    def test_compose(self):
        t1 = Transform(translation=Vec3(1, 0, 0))
        t2 = Transform(translation=Vec3(0, 1, 0))
        t3 = t1.compose(t2)
        p = t3.apply_to_point(Vec3(0, 0, 0))
        assert p == Vec3(1, 1, 0)

    def test_inverse(self):
        t = Transform(translation=Vec3(5, 10, 15))
        t_inv = t.inverse()
        p = t.apply_to_point(Vec3(1, 2, 3))
        p_back = t_inv.apply_to_point(p)
        assert p_back.x == pytest.approx(1.0)
        assert p_back.y == pytest.approx(2.0)
        assert p_back.z == pytest.approx(3.0)

    def test_apply_to_vector(self):
        t = Transform(translation=Vec3(100, 200, 300))
        v = t.apply_to_vector(Vec3(1, 0, 0))
        # Vectors should not be translated
        assert v == Vec3(1, 0, 0)

    def test_from_axis_angle(self):
        # 90° around Z
        t = Transform.from_axis_angle(Vec3(0, 0, 1), math.pi / 2)
        p = t.apply_to_point(Vec3(1, 0, 0))
        assert p.x == pytest.approx(0.0, abs=1e-10)
        assert p.y == pytest.approx(1.0, abs=1e-10)


# ===========================================================================
# ToolpathData Tests
# ===========================================================================

class TestToolpathData:
    """Test suite for ToolpathData."""

    def test_empty_toolpath(self):
        tp = ToolpathData()
        assert len(tp) == 0
        assert tp.total_distance == 0.0

    def test_append_and_len(self):
        tp = ToolpathData()
        tp.append(Vec3(0, 0, 0))
        tp.append(Vec3(10, 0, 0))
        assert len(tp) == 2

    def test_validate(self):
        tp = ToolpathData()
        tp.append(Vec3(0, 0, 0))
        tp.append(Vec3(1, 0, 0))
        assert tp.validate()

    def test_total_distance(self):
        tp = ToolpathData()
        tp.append(Vec3(0, 0, 0))
        tp.append(Vec3(3, 4, 0))
        assert tp.total_distance == pytest.approx(5.0)

    def test_rapid_distance(self):
        tp = ToolpathData()
        tp.append(Vec3(0, 0, 0), rapid=True)
        tp.append(Vec3(3, 4, 0), rapid=True)
        tp.append(Vec3(6, 8, 0), rapid=False)
        # rapid_distance counts segments where EITHER endpoint is rapid
        # Seg 0→1: both rapid ✓, Seg 1→2: point 1 is rapid ✓
        assert tp.rapid_distance == pytest.approx(10.0)
        assert tp.cutting_distance == pytest.approx(0.0)

    def test_metadata(self):
        tp = ToolpathData(metadata={"strategy": "face_milling"})
        assert tp.metadata["strategy"] == "face_milling"


# ===========================================================================
# ToolDef and Material Tests
# ===========================================================================

class TestToolDef:
    def test_basic(self):
        tool = ToolDef(diameter=10.0)
        assert tool.effective_radius == 5.0
        assert tool.flute_count == 4

    def test_ball_nose(self):
        tool = ToolDef(diameter=6.0, tool_type="ball", radius=3.0)
        assert tool.radius == 3.0
        assert tool.tool_type == "ball"


class TestMaterial:
    def test_rpm_calculation(self):
        mat = Material(sfm=300.0)
        rpm = mat.calculate_rpm(tool_diameter=10.0)
        assert rpm == pytest.approx(114.6)  # 300 * 3.82 / 10

    def test_feed_rate(self):
        mat = Material(sfm=300.0, chip_load=0.05)
        feed = mat.calculate_feed_rate(tool_diameter=10.0, flute_count=4)
        expected = (300.0 * 3.82 / 10.0) * 4 * 0.05
        assert feed == pytest.approx(expected)

    def test_invalid_diameter(self):
        mat = Material()
        with pytest.raises(ValueError):
            mat.calculate_rpm(tool_diameter=0.0)


# ===========================================================================
# STL Parser Tests
# ===========================================================================

class TestSTLParser:
    """Test suite for STL import."""

    def _make_ascii_stl(self, tmp_path: Path) -> Path:
        """Create a minimal ASCII STL file (single triangle)."""
        stl_content = """solid test
  facet normal 0.0 0.0 1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 0.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 0.0 1.0 0.0
      vertex 1.0 0.0 0.0
    endloop
  endfacet
endsolid test
"""
        stl_path = tmp_path / "test.stl"
        stl_path.write_text(stl_content)
        return stl_path

    def _make_binary_stl(self, tmp_path: Path, num_triangles: int = 2) -> Path:
        """Create a minimal binary STL file."""
        stl_path = tmp_path / "test_binary.stl"

        with open(stl_path, "wb") as f:
            # 80-byte header
            f.write(b"\x00" * 80)
            # Number of triangles
            f.write(struct.pack("<I", num_triangles))

            for i in range(num_triangles):
                # Normal
                f.write(struct.pack("<fff", 0.0, 0.0, 1.0))
                # Three vertices
                f.write(struct.pack("<fff", float(i), 0.0, 0.0))
                f.write(struct.pack("<fff", float(i + 1), 0.0, 0.0))
                f.write(struct.pack("<fff", float(i), 1.0, 0.0))
                # Attribute byte count
                f.write(struct.pack("<H", 0))

        return stl_path

    def test_parse_ascii_stl(self, tmp_path):
        stl_path = self._make_ascii_stl(tmp_path)
        mesh = parse_stl(stl_path)

        assert "vertices" in mesh
        assert "normals" in mesh
        assert "faces" in mesh
        assert len(mesh["faces"]) == 2
        assert mesh["vertices"].shape[1] == 3
        assert mesh["normals"].shape[1] == 3

    def test_parse_binary_stl(self, tmp_path):
        stl_path = self._make_binary_stl(tmp_path)
        mesh = parse_stl(stl_path)

        assert len(mesh["faces"]) == 2
        assert mesh["vertices"].shape[1] == 3

    def test_stl_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_stl("/nonexistent/path.stl")

    def test_empty_stl(self, tmp_path):
        stl_path = tmp_path / "empty.stl"
        stl_path.write_text("solid empty\nendsolid empty")
        with pytest.raises(ValueError):
            parse_stl(stl_path)

    def test_mesh_info(self, tmp_path):
        stl_path = self._make_ascii_stl(tmp_path)
        mesh = parse_stl(stl_path)
        info = get_mesh_info(mesh)
        assert "Vertices:" in info
        assert "Faces:" in info
        assert "Bounding Box:" in info

    def test_normals_fixed(self, tmp_path):
        """Test that inverted normals get fixed."""
        stl_content = """solid test
  facet normal 0.0 0.0 -1.0
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 0.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
endsolid test
"""
        stl_path = tmp_path / "inverted.stl"
        stl_path.write_text(stl_content)
        mesh = parse_stl(stl_path)

        # The normal should be fixed to point outward (positive Z)
        normal = mesh["normals"][0]
        assert normal[2] > 0, f"Normal Z should be positive after fix, got {normal[2]}"


# ===========================================================================
# G-code Parser Tests
# ===========================================================================

class TestGCodeParser:
    """Test suite for G-code parser."""

    def test_simple_g0_g1(self):
        gcode = "G0 X10 Y20\nG1 X30 Y40 F1000"
        commands = parse_gcode(gcode)

        assert len(commands) == 2
        assert commands[0].command == "G0"
        assert commands[0].params["X"] == 10.0
        assert commands[0].params["Y"] == 20.0
        assert commands[1].command == "G1"
        assert commands[1].params["F"] == 1000.0

    def test_line_numbers(self):
        gcode = "N10 G0 X0 Y0\nN20 G1 X10 Y10"
        commands = parse_gcode(gcode)

        assert commands[0].line_number == 1
        assert commands[1].line_number == 2

    def test_comments(self):
        gcode = "G0 X10 (rapid move)\n; This is a comment\nG1 X20"
        commands = parse_gcode(gcode)

        # Comment line should be skipped, but inline comment captured
        assert len(commands) == 2
        assert commands[0].comment == "rapid move"

    def test_m_codes(self):
        gcode = "M03 S10000\nM06 T1\nM08\nM30"
        commands = parse_gcode(gcode)

        assert len(commands) == 4
        # Parser normalizes: M03→M3, M06→M6, M08→M8, M30 stays M30
        assert commands[0].command == "M3"
        assert commands[0].params["S"] == 10000.0
        assert commands[1].command == "M6"
        assert commands[2].command == "M8"
        assert commands[3].command == "M30"

    def test_g28(self):
        gcode = "G28"
        commands = parse_gcode(gcode)
        assert len(commands) == 1
        assert commands[0].command == "G28"

    def test_g90_g91(self):
        gcode = "G90\nG91"
        commands = parse_gcode(gcode)
        assert commands[0].command == "G90"
        assert commands[1].command == "G91"

    def test_empty_input(self):
        commands = parse_gcode("")
        assert len(commands) == 0

    def test_empty_lines(self):
        gcode = "\n\nG0 X0\n\nG1 X10\n\n"
        commands = parse_gcode(gcode)
        assert len(commands) == 2

    def test_helper_functions(self):
        gcode = "G0 X10 Y20\nG1 X30 Y40 F500\nG2 I5 J0\nM03 S8000\nM06 T2\nM30"
        commands = parse_gcode(gcode)

        assert is_rapid_move(commands[0])
        assert not is_rapid_move(commands[1])
        assert is_linear_move(commands[1])
        assert is_arc_move(commands[2])
        # M03 normalizes to M3, M06 to M6
        assert is_spindle_on(commands[3])
        assert is_tool_change(commands[4])
        assert commands[5].command == "M30"

    def test_get_position(self):
        gcode = "G1 X10 Y20 Z-5 F1000"
        commands = parse_gcode(gcode)
        pos = get_position(commands[0])
        assert pos is not None
        assert pos["X"] == 10.0
        assert pos["Y"] == 20.0
        assert pos["Z"] == -5.0

    def test_get_feed(self):
        gcode = "G1 X10 F1500"
        commands = parse_gcode(gcode)
        assert get_feed(commands[0]) == 1500.0

    def test_summary(self):
        gcode = "G0 X0\nG1 X10\nG1 X20\nM30"
        commands = parse_gcode(gcode)
        s = summary(commands)
        assert "4 commands" in s
        assert "G0" in s
        assert "G1" in s

    def test_negative_values(self):
        gcode = "G1 X-10.5 Y-20.3 Z-5.0"
        commands = parse_gcode(gcode)
        assert commands[0].params["X"] == -10.5
        assert commands[0].params["Y"] == -20.3
        assert commands[0].params["Z"] == -5.0


# ===========================================================================
# SDF Tests
# ===========================================================================

class TestSDF:
    """Test suite for signed distance fields."""

    def test_create_from_mesh(self):
        # Simple flat triangle at z=0
        vertices = np.array([
            [0, 0, 0],
            [10, 0, 0],
            [5, 10, 0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2]], dtype=np.int32)

        sdf = create_from_mesh(vertices, faces, resolution=1.0)

        assert sdf.shape[0] > 0
        assert sdf.shape[1] > 0
        assert sdf.z_min <= 0.0

    def test_query_above_surface(self):
        vertices = np.array([
            [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)

        sdf = create_from_mesh(vertices, faces, resolution=1.0)

        # Point above the flat surface
        d = sdf.query(Vec3(5.0, 5.0, 5.0))
        assert d > 0, f"Point above surface should have positive distance, got {d}"

    def test_query_below_surface(self):
        vertices = np.array([
            [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)

        sdf = create_from_mesh(vertices, faces, resolution=1.0)

        d = sdf.query(Vec3(5.0, 5.0, -5.0))
        assert d < 0, f"Point below surface should have negative distance, got {d}"

    def test_query_height(self):
        vertices = np.array([
            [0, 0, 0], [10, 0, 5], [5, 10, 0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2]], dtype=np.int32)

        sdf = create_from_mesh(vertices, faces, resolution=1.0)
        h = sdf.query_height(5.0, 3.0)
        assert isinstance(h, float)

    def test_empty_mesh_raises(self):
        with pytest.raises(ValueError):
            create_from_mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))

    def test_bounds(self):
        vertices = np.array([[0, 0, -5], [10, 10, 5]], dtype=np.float64)
        faces = np.array([[0, 0, 1]], dtype=np.int32)

        sdf = create_from_mesh(vertices, faces, resolution=2.0)
        mn, mx = sdf.get_bounds()
        assert mn.x <= 0.0
        assert mx.x >= 10.0


# ===========================================================================
# Strategy Tests
# ===========================================================================

class TestStrategies:
    """Test suite for machining strategies."""

    def _make_operation(self, strategy_name: str = "face_milling") -> OperationParams:
        """Create a valid test operation."""
        return OperationParams(
            strategy=strategy_name,
            stock=BBox.from_points([Vec3(0, 0, 0), Vec3(50, 50, 10)]),
            tool=ToolDef(diameter=10.0),
            stepover=0.5,
            stepdown=2.0,
            feed_rate=1000.0,
            spindle_speed=10000.0,
            clearance_height=5.0,
            top_of_stock=10.0,
            bottom_of_stock=0.0,
        )

    def test_list_strategies(self):
        strategies = list_strategies()
        assert "face_milling" in strategies
        assert "adaptive_clearing" in strategies
        assert "pocketing" in strategies

    def test_get_strategy(self):
        s = get_strategy("face_milling")
        assert s.name == "face_milling"
        assert isinstance(s, BaseStrategy)

    def test_get_unknown_strategy(self):
        with pytest.raises(KeyError):
            get_strategy("nonexistent_strategy")

    def test_face_milling_validates(self):
        strategy = get_strategy("face_milling")
        op = self._make_operation("face_milling")
        errors = strategy.validate_params(op)
        assert len(errors) == 0, f"Unexpected validation errors: {errors}"

    def test_face_milling_generates_toolpath(self):
        strategy = get_strategy("face_milling")
        op = self._make_operation()
        tp = strategy.run(op)

        assert isinstance(tp, ToolpathData)
        assert len(tp) > 0
        assert tp.validate()
        assert tp.metadata.get("strategy") == "face_milling"

    def test_adaptive_clearing_validates(self):
        strategy = get_strategy("adaptive_clearing")
        op = self._make_operation("adaptive_clearing")
        op.stepover = 0.1  # Small stepover for adaptive
        errors = strategy.validate_params(op)
        assert len(errors) == 0

    def test_adaptive_clearing_generates_toolpath(self):
        strategy = get_strategy("adaptive_clearing")
        op = self._make_operation("adaptive_clearing")
        op.stepover = 0.1
        tp = strategy.run(op)

        assert isinstance(tp, ToolpathData)
        assert len(tp) > 0
        assert tp.validate()

    def test_pocketing_generates_toolpath(self):
        strategy = get_strategy("pocketing")
        op = self._make_operation("pocketing")
        tp = strategy.run(op)

        assert isinstance(tp, ToolpathData)
        assert len(tp) > 0
        assert tp.validate()
        assert tp.metadata.get("strategy") == "pocketing"

    def test_validation_catches_bad_params(self):
        strategy = get_strategy("face_milling")
        op = OperationParams(
            tool=ToolDef(diameter=10.0),
            stock=BBox.from_points([Vec3(0, 0, 0), Vec3(50, 50, 10)]),
            stepover=-0.1,  # Invalid
            stepdown=-1.0,  # Invalid
            feed_rate=-100,  # Invalid
            top_of_stock=0.0,
            bottom_of_stock=10.0,  # Inverted
        )
        errors = strategy.validate_params(op)
        assert len(errors) >= 3, f"Expected multiple errors, got {errors}"

    def test_run_catches_validation_errors(self):
        strategy = get_strategy("face_milling")
        op = OperationParams(
            tool=ToolDef(diameter=10.0),
            stock=BBox.from_points([Vec3(0, 0, 0), Vec3(50, 50, 10)]),
            stepover=-0.1,
        )
        with pytest.raises(ValueError, match="Validation failed"):
            strategy.run(op)

    def test_register_custom_strategy(self):
        class CustomStrategy(BaseStrategy):
            @property
            def name(self) -> str:
                return "custom_test"

            def validate_params(self, operation):
                return []

            def generate_toolpath(self, stock, tool, **kwargs):
                return ToolpathData(metadata={"strategy": "custom_test"})

        register_strategy("custom_test", CustomStrategy)
        assert "custom_test" in list_strategies()

        s = get_strategy("custom_test")
        tp = s.generate_toolpath(
            BBox.from_points([Vec3(0, 0, 0), Vec3(10, 10, 10)]),
            ToolDef(diameter=5.0),
        )
        assert tp.metadata["strategy"] == "custom_test"


# ===========================================================================
# Integration Test
# ===========================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self):
        """Test STL → SDF → Strategy → ToolpathData workflow."""
        # Create a simple mesh (flat plate)
        vertices = np.array([
            [0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0],
        ], dtype=np.float64)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)

        # Create SDF
        sdf = create_from_mesh(vertices, faces, resolution=2.0)
        assert sdf.query_height(50.0, 50.0) == pytest.approx(0.0, abs=0.5)

        # Create toolpath
        strategy = get_strategy("face_milling")
        op = OperationParams(
            stock=BBox.from_points([Vec3(0, 0, 0), Vec3(100, 100, 20)]),
            tool=ToolDef(diameter=10.0),
            stepover=0.5,
            stepdown=5.0,
            feed_rate=2000.0,
            spindle_speed=12000.0,
            top_of_stock=20.0,
            bottom_of_stock=0.0,
        )
        tp = strategy.run(op)

        assert len(tp) > 0
        assert tp.validate()
        assert tp.total_distance > 0
        assert tp.metadata["strategy"] == "face_milling"

    def test_gcode_round_trip(self):
        """Test that G-code can be parsed and helpers work correctly."""
        gcode = """G28
G90
M03 S12000
M06 T1
M08
G0 X0 Y0 Z5
G1 X50 Y0 Z-2 F2000
G1 X50 Y50 Z-2
G1 X0 Y50 Z-2
G1 X0 Y0 Z-2
G0 Z5
M05
M09
M30
"""
        commands = parse_gcode(gcode)

        # Count different command types
        rapids = [c for c in commands if is_rapid_move(c)]
        cuts = [c for c in commands if is_linear_move(c)]
        m_codes = [c for c in commands if c.command.startswith("M")]

        assert len(rapids) >= 2  # G0 at start and end
        assert len(cuts) >= 4    # G1 cutting moves
        assert len(m_codes) >= 6  # M03, M06, M08, M05, M09, M30

        # Verify summary
        s = summary(commands)
        assert "G0" in s
        assert "G1" in s
        assert "M" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
