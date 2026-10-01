"""
Integration test: feature F3 end-to-end (``Fusion 360 RE/docs/p5-execution-plan.md``
section 4, row P5/5).

The full user path, no stubs and no mocks:

    hole table  ->  kernel.strategies.drilling.DrillingStrategy.run
                 ->  ToolpathData (expanded canned-cycle body)
                 ->  simulation.SimulationEngine   (the plunges cut the stock)
                 ->  post.ir.segments_to_ir
                 ->  post.fanuc.FanucRenderer      (the plunge feed reaches the bytes)
                 ->  kernel.gcode.parse_gcode      (the written program re-parses)

The hole table is a *declared input*, not a discovered one: feature recognition
is out of scope for P5 (plan section 3.3), and the reference implementation
takes its holes from the capture's posted body for the same reason.  The plate
is written as an ASCII STL in-process so the stock really is parsed geometry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kernel.gcode import parse_gcode
from kernel.stl import parse_stl
from kernel.strategies import get_strategy
from kernel.strategies.base import OperationParams
from kernel.types import BBox, MoveType, ToolDef, Vec3
from post.fanuc import FanucRenderer
from post.ir import segments_to_ir
from simulation.engine import SimulationEngine, StockModel

TOOL_DIAMETER = 3.175
FEED = 1000.0
SPINDLE = 9000.0
#: round6(float32(FEED / 3)) - drilling.md R13's flat-end-mill arm, as posted.
PLUNGE_POST = 333.333344

#: (x0, y0, z0) -> (x1, y1, z1) of the plate the STL describes.
PLATE = (0.0, 0.0, 0.0, 60.0, 40.0, 8.0)
#: hole table: (x, y, top_z, bottom_z, diameter) - two blind holes + one
#: through-hole, at z = 8 (the plate's top face).
HOLES = (
    (10.0, 10.0, 8.0, 2.0, 6.0),
    (30.0, 20.0, 8.0, 4.0, 3.0),
    (50.0, 30.0, 8.0, -1.0, 6.0),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _box_triangles(p0, p1):
    """Six faces of an axis-aligned box as outward-wound corner quads."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    p000, p100, p110, p010 = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)
    )
    p001, p101, p111, p011 = (
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)
    )
    quads = [
        ((0.0, 0.0, 1.0), [p001, p101, p111, p011]),  # +Z
        ((0.0, 0.0, -1.0), [p000, p010, p110, p100]),  # -Z
        ((1.0, 0.0, 0.0), [p100, p110, p111, p101]),   # +X
        ((-1.0, 0.0, 0.0), [p000, p001, p011, p010]),  # -X
        ((0.0, 1.0, 0.0), [p010, p011, p111, p110]),   # +Y
        ((0.0, -1.0, 0.0), [p000, p100, p101, p001]),  # -Y
    ]
    triangles = []
    for normal, corners in quads:
        triangles.append((normal, [corners[0], corners[1], corners[2]]))
        triangles.append((normal, [corners[0], corners[2], corners[3]]))
    return triangles


def write_plate_stl(path: Path) -> Path:
    """Write the test plate as an ASCII STL the kernel can parse."""
    p0, p1 = PLATE[:3], PLATE[3:]
    lines = ["solid plate"]
    for normal, corners in _box_triangles(p0, p1):
        lines.append(f"  facet normal {normal[0]:g} {normal[1]:g} {normal[2]:g}")
        lines.append("    outer loop")
        for corner in corners:
            lines.append(f"      vertex {corner[0]:g} {corner[1]:g} {corner[2]:g}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid plate")
    path.write_text("\n".join(lines) + "\n")
    return path


def stock_from_mesh(mesh) -> BBox:
    import numpy as np
    vertices = np.asarray(mesh["vertices"], dtype=float)
    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    return BBox(min=Vec3(float(lo[0]), float(lo[1]), float(lo[2])),
                max=Vec3(float(hi[0]), float(hi[1]), float(hi[2])))


def operation(stock: BBox, **extra) -> OperationParams:
    args = {"holes": [dict(zip(("x", "y", "top_z", "bottom_z", "diameter"), h))
                      for h in HOLES]}
    args.update(extra)
    return OperationParams(
        strategy="drilling",
        stock=stock,
        tool=ToolDef(tool_id="T01", name="3.175mm End Mill",
                     diameter=TOOL_DIAMETER),
        feed_rate=FEED,
        spindle_speed=SPINDLE,
        extra_args=args,
    )


def toolpath(tmp_path: Path, **extra):
    mesh = parse_stl(write_plate_stl(tmp_path / "plate.stl"))
    stock = stock_from_mesh(mesh)
    return mesh, stock, get_strategy("drilling").run(operation(stock, **extra))


def stock_model(stock: BBox) -> StockModel:
    return StockModel(
        origin_x=stock.min.x,
        origin_y=stock.min.y,
        width_x=stock.size.x,
        width_y=stock.size.y,
        top_z=stock.max.z,
    )


def f_words(gcode: str) -> set[float]:
    out = set()
    for line in gcode.splitlines():
        for token in line.split():
            if token.startswith("F") and token[1:].replace(".", "", 1) \
                    .replace("-", "", 1).isdigit():
                out.add(float(token[1:]))
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestF3EndToEnd:
    """Hole table -> strategy -> simulation -> IR -> Fanuc G-code -> re-parse."""

    def test_the_plate_parses_to_the_declared_geometry(self, tmp_path):
        mesh, stock, _ = toolpath(tmp_path)
        assert len(mesh["faces"]) == 12
        assert stock.size.x == pytest.approx(PLATE[3] - PLATE[0])
        assert stock.size.y == pytest.approx(PLATE[4] - PLATE[1])
        assert stock.size.z == pytest.approx(PLATE[5] - PLATE[2])

    def test_the_strategy_returns_the_expanded_canned_cycle_body(self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        assert tp.strategy == "drilling"
        assert "error" not in tp.params
        assert tp.params["holes_total"] == 3
        assert tp.params["holes_selected"] == 3
        assert tp.params["cycle_type"] == "drilling"
        assert len(tp.moves) == tp.params["moves"]
        # one linear plunge per hole for a plain drilling cycle
        plunges = [m for m in tp.moves if m.move_type is MoveType.LINEAR]
        assert len(plunges) == 3
        assert sorted(m.end.z for m in plunges) == [-1.0, 2.0, 4.0]

    def test_the_planes_are_the_measured_ones(self, tmp_path):
        # stock top 8 -> retract 13, clearance 23 (R9: +5 then +10)
        _, _, tp = toolpath(tmp_path)
        assert tp.params["retract_z"] == 13.0
        assert tp.params["clearance_z"] == 23.0
        assert max(m.end.z for m in tp.moves) == pytest.approx(23.0)

    def test_the_only_feed_that_reaches_the_body_is_the_plunge(self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        feeds = {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}
        assert feeds == {PLUNGE_POST}
        assert tp.params["feed_vocabulary"]["plunge"] == pytest.approx(
            round(FEED / 3.0, 6))
        for m in tp.moves:
            if m.move_type is MoveType.RAPID:
                assert m.feed == 0.0

    def test_simulation_cuts_the_declared_depths(self, tmp_path):
        _, stock, tp = toolpath(tmp_path)
        engine = SimulationEngine(stock=stock_model(stock),
                                  cutter_diameter=TOOL_DIAMETER)
        frames = engine.simulate_to_frames(tp)
        assert len(frames) == len(tp.moves)
        assert frames[-1].zmap.mean() < stock.max.z
        # the deepest hole bottoms out at z = -1 (below the plate floor)
        assert frames[-1].zmap.min() <= 0.0

    def test_the_posted_program_carries_the_mandatory_words(self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        gcode = FanucRenderer().render(segments_to_ir(tp))
        for mandatory in ("O0001", "M06", "M03", "M30", "G21", "G90"):
            assert mandatory in gcode, f"missing {mandatory} in posted program"

    def test_exactly_one_f_word_reaches_the_program(self, tmp_path):
        """Drilling cuts with the plunge feed only - one value, at the post's
        0.1 mm/min precision (post/fanuc.py: ``F{seg.feed:.1f}``)."""
        _, _, tp = toolpath(tmp_path)
        gcode = FanucRenderer().render(segments_to_ir(tp))
        assert f_words(gcode) == {333.3}

    def test_rapids_are_posted_without_a_feed_word(self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        gcode = FanucRenderer().render(segments_to_ir(tp))
        rapid_lines = [ln for ln in gcode.splitlines() if ln.startswith("G00")]
        feed_lines = [ln for ln in gcode.splitlines() if ln.startswith("G01")]
        assert rapid_lines and feed_lines
        assert len(feed_lines) == sum(1 for m in tp.moves
                                      if m.move_type is MoveType.LINEAR)
        assert len(rapid_lines) >= sum(1 for m in tp.moves
                                       if m.move_type is MoveType.RAPID)
        for line in rapid_lines:
            assert not f_words(line), f"rapid block has a feed: {line}"

    def test_the_plunges_appear_in_the_posted_program_at_their_depths(
            self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        gcode = FanucRenderer().render(segments_to_ir(tp))
        for z in (-1.0, 2.0, 4.0):
            assert any(ln.startswith("G01") and f"Z{z:.3f}" in ln
                       for ln in gcode.splitlines()), f"missing plunge to {z}"

    def test_the_exported_program_re_parses(self, tmp_path):
        _, _, tp = toolpath(tmp_path)
        gcode = FanucRenderer().render(segments_to_ir(tp))
        commands = parse_gcode(gcode)
        assert len(commands) > 0
        # kernel.gcode normalizes G00 -> G0 and G01 -> G1; every motion block
        # (plus the post's own program-end rapids) survived the round trip.
        motion = sum(1 for c in commands if c.command in ("G0", "G1"))
        assert motion >= len(tp.moves)
        # Nothing the parser emitted is malformed, and every motion block of
        # the toolpath is present.  Two declared gaps in kernel/gcode.py are
        # observed here and NOT fixed by this card (it is out of P5/5 scope):
        # the post writes ``T01 M06`` and ``S9000 M03`` - lines that start with
        # a T/S word - which the parser skips because it anchors on a G/M at
        # line start (the raw-text assertions in
        # test_the_posted_program_carries_the_mandatory_words cover them), and
        # ``SUPPORTED_GCODES``/``SUPPORTED_MCODES`` list the zero-padded
        # ``M03``/``M05`` forms that the parser's own normalization never
        # produces, and omit ``G21``/``G94``/``M05``.
        assert all(c.command.startswith(("G", "M")) for c in commands)
        assert {c.command for c in commands} >= {"G0", "G1", "G90", "M30"}

    def test_the_hole_order_follows_the_declared_order_mode(self, tmp_path):
        mesh = parse_stl(write_plate_stl(tmp_path / "plate.stl"))
        stock = stock_from_mesh(mesh)
        op = operation(stock, cycle={"hole_toolpath_order": "order-by-x"})
        tp = get_strategy("drilling").run(op)
        visited = [(m.end.x, m.end.y) for m in tp.moves
                   if m.move_type is MoveType.LINEAR]
        assert visited == [(10.0, 10.0), (30.0, 20.0), (50.0, 30.0)]
        assert tp.params["hole_xy"] == [[10.0, 10.0], [30.0, 20.0],
                                        [50.0, 30.0]]

    def test_a_diameter_range_selects_a_subset_end_to_end(self, tmp_path):
        # only the two 6 mm holes survive a [5, 10] mm window
        mesh = parse_stl(write_plate_stl(tmp_path / "plate.stl"))
        stock = stock_from_mesh(mesh)
        op = operation(stock, cycle={"hole_diameter_minimum": 5.0,
                                     "hole_diameter_maximum": 10.0})
        tp = get_strategy("drilling").run(op)
        assert tp.params["holes_selected"] == 2
        assert sum(1 for m in tp.moves
                   if m.move_type is MoveType.LINEAR) == 2

    def test_an_empty_selection_is_a_silent_no_toolpath_not_an_error(
            self, tmp_path):
        mesh = parse_stl(write_plate_stl(tmp_path / "plate.stl"))
        stock = stock_from_mesh(mesh)
        op = operation(stock, cycle={"hole_diameter_minimum": 50.0,
                                     "hole_diameter_maximum": 60.0})
        tp = get_strategy("drilling").run(op)
        assert "error" not in tp.params
        assert tp.moves == []
        assert tp.params["holes_selected"] == 0
