"""
Integration test: feature F2 end-to-end.

`Fusion 360 RE/docs/p5-execution-plan.md` section 4, row P5/4.

The full user path, no stubs and no mocks:

    STL  ->  kernel.stl.parse_stl
         ->  WaterlineFinishingStrategy.run   (Z-level contour + scallop)
         ->  ToolpathData
         ->  simulation.SimulationEngine      (the rim stock actually gets cut)
         ->  post.ir.segments_to_ir
         ->  post.fanuc.FanucRenderer         (both F words reach the bytes)

The material is read from the MODEL: the strategy cross-sections the parsed
triangle mesh at each cutting level, so ``profile_source == "mesh"`` - not
from the stock box, and not from a hand-written polygon.

Feeds asserted in the posted program are ``docs/ideal-cam-architecture.md``
E-S6: ``{tool_feedCutting, tool_feedPlunge}`` with
``tool_feedPlunge = tool_feedCutting / 3``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from kernel.stl import parse_stl
from kernel.strategies import get_strategy
from kernel.strategies.base import OperationParams
from kernel.types import BBox, MoveType, ToolDef, Vec3
from post.fanuc import FanucRenderer
from post.ir import segments_to_ir
from simulation.engine import SimulationEngine, StockModel

FEED = 1000.0
TOOL_DIAMETER = 6.35
STEPDOWN = 4.0
#: Raster pitch for the integration run: the pipeline test does not need the
#: reference's 0.05 mm (that is the fidelity evidence artifact's job), and the
#: grid area - hence the runtime - scales as 1 / cell^2.
CELL_MM = 0.25
#: How much bigger the stock is than the part in X/Y.  A finishing contour
#: sits TOOL_RADIUS outside the part, so the stock has to be wider than that
#: or the pass would cut air.
STOCK_MARGIN = 6.0
#: (x0, y0, z0) -> (x1, y1, z1) of the plate the STL describes.
PLATE = (0.0, 0.0, 0.0, 60.0, 40.0, 8.0)


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
        a, b, c, d = corners
        triangles.append((normal, [a, b, c]))
        triangles.append((normal, [a, c, d]))
    return triangles


def write_plate_stl(path: Path) -> Path:
    """Write the test plate as an ASCII STL the kernel can parse."""
    p0, p1 = PLATE[:3], PLATE[3:]
    lines = ["solid plate"]
    for normal, corners in _box_triangles(p0, p1):
        lines.append(
            "  facet normal {} {} {}".format(*[f"{v:g}" for v in normal])
        )
        lines.append("    outer loop")
        for corner in corners:
            lines.append("      vertex {} {} {}".format(*[f"{v:g}" for v in corner]))
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid plate")
    path.write_text("\n".join(lines) + "\n")
    return path


def write_overhang_stl(path: Path) -> Path:
    """A narrow plate under a WIDER one: the cross-section grows with height.

    The two boxes only touch at ``z = 4``, so the parsed mesh stays a valid
    triangle soup for the even-odd rules (and for the entry-column ray cast,
    which is what this fixture is for: the descent at the lower level's loop
    start point passes through material above it).
    """
    boxes = [((20.0, 15.0, 0.0), (40.0, 25.0, 4.0)),
             ((10.0, 5.0, 4.0), (50.0, 35.0, 8.0))]
    lines = ["solid overhang"]
    for p0, p1 in boxes:
        for normal, corners in _box_triangles(p0, p1):
            lines.append(
                "  facet normal {} {} {}".format(*[f"{v:g}" for v in normal])
            )
            lines.append("    outer loop")
            for corner in corners:
                lines.append(
                    "      vertex {} {} {}".format(*[f"{v:g}" for v in corner])
                )
            lines.append("    endloop")
            lines.append("  endfacet")
    lines.append("endsolid overhang")
    path.write_text("\n".join(lines) + "\n")
    return path


def stock_from_mesh(mesh, margin: float = 0.0) -> BBox:
    """Bounding box of the parsed mesh, optionally grown in X/Y only.

    Real CAM leaves clearance stock around the part: the finishing contour is
    TOOL_RADIUS outside the part boundary, so a stock equal to the part would
    put the whole pass in air.
    """
    vertices = np.asarray(mesh["vertices"], dtype=float)
    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    return BBox(
        min=Vec3(float(lo[0]) - margin, float(lo[1]) - margin, float(lo[2])),
        max=Vec3(float(hi[0]) + margin, float(hi[1]) + margin, float(hi[2])),
    )


def toolpath_from_stl(tmp_path: Path, writer=write_plate_stl, **extra):
    """Parse ``writer``'s STL and run the whole strategy on it (plate by
    default); ``mesh`` in ``extra`` would override the parsed geometry."""
    stl_path = writer(tmp_path / "part.stl")
    mesh = parse_stl(stl_path)
    stock = stock_from_mesh(mesh, STOCK_MARGIN)
    args = {
        "finish_mode": "both",
        "cell_mm": CELL_MM,
        "scallop_rings": 3,
        "cusp_height_mm": 0.02,
        # The material comes from the MODEL: the strategy cross-sections
        # this mesh at every cutting level.
        "mesh": mesh,
    }
    args.update(extra)
    operation = OperationParams(
        strategy="waterline_finishing",
        stock=stock,
        tool=ToolDef(tool_id="T01", name="6.35mm End Mill",
                     diameter=TOOL_DIAMETER),
        stepover=0.4,
        stepdown=STEPDOWN,
        feed_rate=FEED,
        spindle_speed=8000.0,
        clearance_height=5.0,
        top_of_stock=stock.max.z,
        bottom_of_stock=stock.min.z,
        extra_args=args,
    )
    toolpath = get_strategy("waterline_finishing").run(operation)
    return mesh, stock, toolpath


def stock_model(stock: BBox) -> StockModel:
    return StockModel(
        origin_x=stock.min.x,
        origin_y=stock.min.y,
        width_x=stock.size.x,
        width_y=stock.size.y,
        top_z=stock.max.z,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestF2EndToEnd:
    """STL -> strategy -> simulation -> IR -> Fanuc G-code."""

    def test_stl_parses_to_the_declared_plate(self, tmp_path):
        mesh, stock, _ = toolpath_from_stl(tmp_path)
        assert len(mesh["faces"]) == 12
        assert stock.size.x == pytest.approx(PLATE[3] - PLATE[0] + 2 * STOCK_MARGIN)
        assert stock.size.y == pytest.approx(PLATE[4] - PLATE[1] + 2 * STOCK_MARGIN)
        assert stock.size.z == pytest.approx(PLATE[5] - PLATE[2])

    def test_strategy_reads_its_geometry_from_the_mesh(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        assert tp.strategy == "waterline_finishing"
        assert len(tp.moves) > 0
        assert tp.params["profile_source"] == "mesh"
        # Three cutting levels (8 / 4 / 0) plus three scallop rings.
        assert tp.params["levels"] == 3
        assert tp.params["waterline_loops"] == 3
        assert tp.params["scallop_rings"] == 3
        assert tp.params["passes"] == 6

    def test_the_contour_sits_tool_radius_outside_the_part(self, tmp_path):
        """The waterline is the level set ``distance == R`` of the part."""
        _, _, tp = toolpath_from_stl(tmp_path, finish_mode="waterline")
        # 1.5 cells is the declared analytic budget (parity.py analytic_dev_mm).
        tolerance = 1.5 * CELL_MM
        xs = [m.end.x for m in tp.moves if m.move_type is MoveType.LINEAR]
        ys = [m.end.y for m in tp.moves if m.move_type is MoveType.LINEAR]
        assert min(xs) == pytest.approx(-TOOL_DIAMETER / 2.0, abs=tolerance)
        assert max(xs) == pytest.approx(PLATE[3] + TOOL_DIAMETER / 2.0,
                                        abs=tolerance)
        assert min(ys) == pytest.approx(-TOOL_DIAMETER / 2.0, abs=tolerance)
        assert max(ys) == pytest.approx(PLATE[4] + TOOL_DIAMETER / 2.0,
                                        abs=tolerance)

    def test_only_the_two_e_s6_feeds_reach_the_toolpath(self, tmp_path):
        """``{feed, feed/3}`` - no third value, no engagement modulation."""
        _, _, tp = toolpath_from_stl(tmp_path)
        feeds = {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}
        assert feeds == {FEED, FEED / 3.0}
        assert tp.params["feed_vocabulary"] == {
            "plunge": round(FEED / 3.0, 6),
            "cutting": FEED,
        }

    def test_the_realised_scallop_is_the_requested_height(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        assert tp.params["cusp_height_target_mm"] == 0.02
        assert tp.params["cusp_height_mm"] == pytest.approx(0.02, rel=1e-9)
        # p = 2*sqrt(2*R*H - H^2) with R = 3.175, H = 0.02.
        radius = TOOL_DIAMETER / 2.0
        expected = 2.0 * math.sqrt(2.0 * radius * 0.02 - 0.02 ** 2)
        assert tp.params["ring_stepover_mm"] == pytest.approx(expected)

    def test_simulation_cuts_the_stock(self, tmp_path):
        _, stock, tp = toolpath_from_stl(tmp_path)
        model = stock_model(stock)
        engine = SimulationEngine(stock=model, cutter_diameter=TOOL_DIAMETER)
        frames = engine.simulate_to_frames(tp)

        assert len(frames) == len(tp.moves)
        # Material was removed below the untouched stock top...
        assert frames[-1].zmap.mean() < model.top_z
        # ...and at least one spot was cut all the way down: each level
        # plunges at its first loop point, the deepest one reaching the
        # stock floor.
        assert frames[-1].zmap.min() <= 1.0

    def test_posted_gcode_carries_exactly_the_two_e_s6_f_words(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        segments = segments_to_ir(tp)
        gcode = FanucRenderer().render(segments)

        for mandatory in ("O0001", "M06", "M03", "M30", "G21", "G90"):
            assert mandatory in gcode, f"missing {mandatory} in posted program"

        f_words = {
            float(token[1:])
            for line in gcode.splitlines()
            for token in line.split()
            if token.startswith("F")
            and token[1:].replace(".", "", 1).replace("-", "", 1).isdigit()
        }
        # post/fanuc.py renders F with %.1f.
        assert f_words == {333.3, 1000.0}
        assert len(f_words) == 2

    def test_rapids_are_posted_without_a_feed_word(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        assert any(m.move_type is MoveType.RAPID for m in tp.moves)
        gcode = FanucRenderer().render(segments_to_ir(tp))

        rapid_lines = [ln for ln in gcode.splitlines() if ln.startswith("G00")]
        feed_lines = [ln for ln in gcode.splitlines() if ln.startswith("G01")]
        assert rapid_lines and feed_lines

        def carries_feed_word(line: str) -> bool:
            return any(
                token.startswith("F")
                and token[1:].replace(".", "", 1).replace("-", "", 1).isdigit()
                for token in line.split()
            )

        for line in rapid_lines:
            assert not carries_feed_word(line), f"rapid block has a feed: {line}"
        assert any(carries_feed_word(line) for line in feed_lines)

    def test_waterline_only_mode_drops_the_rings(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path, finish_mode="waterline")
        assert tp.params["finish_mode"] == "waterline"
        assert tp.params["scallop_rings"] == 0
        assert tp.params["waterline_loops"] == 3

    def test_every_cutting_move_ends_at_a_cutting_level(self, tmp_path):
        """No stray z: every G01 endpoint sits on a declared level."""
        _, stock, tp = toolpath_from_stl(tmp_path)
        levels = {round(stock.max.z - k * STEPDOWN, 6) for k in range(3)}
        levels.add(round(stock.min.z, 6))
        for move in tp.moves:
            if move.move_type is MoveType.LINEAR:
                assert round(move.end.z, 6) in levels

    def test_an_overhanging_stl_is_refused_before_any_move(self, tmp_path):
        """A section that grows with height is not descended through.

        Same pipeline as every other test here - ``parse_stl`` (numpy
        vertices, the real input shape), ``run`` - but the part is a narrow
        plate under a wider one, so the loop start point of the lowest level
        sits under material.  The strategy must return an error ToolpathData
        naming the offending move and emit NOTHING, rather than post a rapid
        through solid; the plate fixture above must still be unaffected
        (every other test in this file proves that one).
        """
        _, _, tp = toolpath_from_stl(tmp_path, writer=write_overhang_stl)
        assert tp.params["profile_source"] == "mesh"
        assert "error" in tp.params, "the descent through material was emitted"
        assert "rapid clearance" in tp.params["error"]
        assert tp.params["clearance_violations"]
        assert tp.moves == [], f"moves were emitted: {len(tp.moves)}"
