"""
Integration test: feature F1 end-to-end.

`Fusion 360 RE/docs/p5-execution-plan.md` section 4, row P5/3.

The full user path, no stubs and no mocks:

    STL  ->  kernel.stl.parse_stl
         ->  AdaptiveEngagementStrategy.run   (engagement-gated feed)
         ->  ToolpathData
         ->  simulation.SimulationEngine      (stock actually gets cut)
         ->  post.ir.segments_to_ir
         ->  post.fanuc.FanucRenderer         (three F words reach the bytes)

The three feed values asserted in the posted program are the measured
vocabulary of `Fusion 360 RE/docs/behavior/adaptive.md` R8:
``{feed/3, 0.9*feed, feed}``.
"""

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
STEPDOWN = 3.0

# (x0, y0, z0) -> (x1, y1, z1) of the plate the STL describes.
PLATE = (0.0, 0.0, 0.0, 100.0, 60.0, 12.0)


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
            lines.append(
                "      vertex {} {} {}".format(*[f"{v:g}" for v in corner])
            )
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid plate")
    path.write_text("\n".join(lines) + "\n")
    return path


def stock_from_mesh(mesh: dict) -> BBox:
    """Bounding box of the parsed mesh = the stock the strategy clears."""
    vertices = np.asarray(mesh["vertices"], dtype=float)
    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    return BBox(
        min=Vec3(float(lo[0]), float(lo[1]), float(lo[2])),
        max=Vec3(float(hi[0]), float(hi[1]), float(hi[2])),
    )


def toolpath_from_stl(tmp_path: Path):
    stl_path = write_plate_stl(tmp_path / "plate.stl")
    mesh = parse_stl(stl_path)
    stock = stock_from_mesh(mesh)
    tool = ToolDef(tool_id="T01", name="6.35mm End Mill", diameter=TOOL_DIAMETER)
    operation = OperationParams(
        strategy="adaptive_engagement",
        stock=stock,
        tool=tool,
        stepover=0.4,
        stepdown=STEPDOWN,
        feed_rate=FEED,
        spindle_speed=8000.0,
        clearance_height=5.0,
        top_of_stock=stock.max.z,
        bottom_of_stock=stock.min.z,
    )
    toolpath = get_strategy("adaptive_engagement").run(operation)
    return mesh, stock, toolpath


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestF1EndToEnd:
    """STL -> strategy -> simulation -> IR -> Fanuc G-code."""

    def test_stl_parses_to_the_declared_plate(self, tmp_path):
        mesh, stock, _ = toolpath_from_stl(tmp_path)
        assert len(mesh["faces"]) == 12
        assert stock.size.x == pytest.approx(PLATE[3] - PLATE[0])
        assert stock.size.y == pytest.approx(PLATE[4] - PLATE[1])
        assert stock.size.z == pytest.approx(PLATE[5] - PLATE[2])

    def test_strategy_generates_moves_from_the_stl_stock(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        assert tp.strategy == "adaptive_engagement"
        assert len(tp.moves) > 0
        # R8's measured triplet at feed = 1000, written as literals rather
        # than read back from the module under test.
        assert tp.params["feed_vocabulary"] == {
            "plunge": 333.333333,
            "reduced": 900.0,
            "cutting": 1000.0,
        }

    def test_only_measured_feeds_reach_the_toolpath(self, tmp_path):
        _, _, tp = toolpath_from_stl(tmp_path)
        expected = {FEED / 3.0, FEED * 0.9, FEED}
        feeds = {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}
        # All three arms are exercised on this plate, and no fourth value.
        assert feeds == expected

    def test_simulation_cuts_the_stock(self, tmp_path):
        _, stock, tp = toolpath_from_stl(tmp_path)
        model = StockModel(
            origin_x=stock.min.x,
            origin_y=stock.min.y,
            width_x=stock.size.x,
            width_y=stock.size.y,
            top_z=stock.max.z,
        )
        engine = SimulationEngine(stock=model, cutter_diameter=TOOL_DIAMETER)
        frames = engine.simulate_to_frames(tp)

        assert len(frames) == len(tp.moves)
        # Material was removed below the untouched stock top.
        assert frames[-1].zmap.mean() < model.top_z

        # ...and the rougher cleared the footprint essentially completely:
        # measured 0.998667 of the cells sit at the stock bottom (the residue
        # is the boundary/corner cells the outermost ring cannot reach).
        at_bottom = frames[-1].zmap <= stock.min.z + 1e-9
        assert at_bottom.mean() >= 0.99

    def test_posted_gcode_carries_exactly_the_three_measured_f_words(
        self, tmp_path
    ):
        _, _, tp = toolpath_from_stl(tmp_path)
        segments = segments_to_ir(tp)
        gcode = FanucRenderer().render(segments)

        # Mandatory Fanuc blocks (same contract as tests/integration).
        for mandatory in ("O0001", "M06", "M03", "M30", "G21", "G90"):
            assert mandatory in gcode, f"missing {mandatory} in posted program"

        # The posted F words are the vocabulary at the post's 0.1 mm/min
        # precision (post/fanuc.py: f" F{seg.feed:.1f}") — and only three.
        f_words = {
            float(token[1:])
            for line in gcode.splitlines()
            for token in line.split()
            if token.startswith("F")
            and token[1:].replace(".", "", 1).replace("-", "", 1).isdigit()
        }
        expected = {333.3, 900.0, 1000.0}  # R8 triplet at feed 1000, .1f post
        assert f_words == expected
        assert len(f_words) == 3

    def test_rapids_are_posted_without_a_feed_word(self, tmp_path):
        """G00 blocks carry no F word; G01 blocks do.

        post/fanuc.py emits ``f" F{seg.feed:.1f}"`` only on a LINEAR move and
        only when the feed changed, so a rapid must never carry one.
        """
        _, _, tp = toolpath_from_stl(tmp_path)
        assert any(m.move_type is MoveType.RAPID for m in tp.moves)
        gcode = FanucRenderer().render(segments_to_ir(tp))

        rapid_lines = [ln for ln in gcode.splitlines() if ln.startswith("G00")]
        feed_lines = [ln for ln in gcode.splitlines() if ln.startswith("G01")]
        assert rapid_lines and feed_lines

        def carries_feed_word(line: str) -> bool:
            return any(
                token.startswith("F")
                and token[1:].replace(".", "", 1).isdigit()
                for token in line.split()
            )

        for line in rapid_lines:
            assert not carries_feed_word(line), f"rapid block has a feed: {line}"
        assert any(carries_feed_word(line) for line in feed_lines)
