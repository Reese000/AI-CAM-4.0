"""
Unit tests for feature F2 - waterline (Z-level contour) + constant-scallop
finishing (``Fusion 360 RE/docs/p5-execution-plan.md`` section 4, row P5/4).

The reference these were written against is read-only and lives in the
umbrella repo: ``impl/waterline/{waterline,scallop,section}.py`` plus the
raster primitive in ``impl/const_engagement/geometry.py``.  Where an
expectation is a number lifted from that reference (the 1.5-cell deviation
budget, the 1-cell collision budget, ``CELL_MM = 0.05``) the docstring says
which reference row it mirrors, so a future reader can tell a ported
specification from a fitted one.

Every fixture here is built in-process: no cross-repo import, no absolute
path, no fixture file.  The cross-repo fidelity measurement (this port vs
``impl/waterline`` on the pinned EXP-004 fixture) is an evidence artifact,
not a test - see ``Fusion 360 RE/tests/p5_evidence/``.
"""

from __future__ import annotations

import math

import pytest

from kernel.strategies import get_strategy, list_strategies, register_strategy
from kernel.strategies import waterline_finishing as wlf
from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, MoveType, ToolDef, Vec3

# The reference's frozen raster pitch (impl/waterline/parity.py:78) and the
# EXP-004 tool (parity.py:79).
CELL = 0.05
R = 1.5875

# Reference budgets (parity.py:95-109): analytic/ring deviation 1.5 cell,
# collision penetration 1 cell.
ANALYTIC_DEV = 0.075
COLLISION_DEV = 0.050

RECT = [(-8.0, -4.0), (8.0, -4.0), (8.0, 4.0), (-8.0, 4.0)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rect_stock(x0=-12.0, y0=-7.0, x1=12.0, y1=7.0, z0=0.0, z1=0.0) -> BBox:
    return BBox(min=Vec3(x0, y0, z0), max=Vec3(x1, y1, z1))


def make_tool(diameter=3.175) -> ToolDef:
    return ToolDef(tool_id="T01", name="3.175mm End Mill", diameter=diameter)


def operation(**extra) -> OperationParams:
    """A valid one-level finishing operation; ``extra`` overrides extra_args.

    ``_stock`` / ``_tool_diameter`` / ``_top`` / ``_bottom`` set the
    ``OperationParams`` fields instead of ``extra_args``.
    """
    args = {
        "finish_mode": "waterline",
        "profile": RECT,
        "cell_mm": CELL,
    }
    args.update(extra)
    stock = args.pop("_stock", None) or rect_stock()
    diameter = args.pop("_tool_diameter", 3.175)
    top = args.pop("_top", 0.0)
    bottom = args.pop("_bottom", 0.0)
    return OperationParams(
        strategy="waterline_finishing",
        stock=stock,
        tool=make_tool(diameter),
        stepover=0.4,
        stepdown=1.0,
        feed_rate=1000.0,
        spindle_speed=9000.0,
        clearance_height=5.0,
        top_of_stock=top,
        bottom_of_stock=bottom,
        extra_args=args,
    )


def signed_dist_rect(x, y, x0, y0, x1, y1) -> float:
    """Signed distance to an axis-aligned rectangle (negative inside)."""
    dx = max(x0 - x, 0.0, x - x1)
    dy = max(y0 - y, 0.0, y - y1)
    if dx == 0.0 and dy == 0.0:
        return -min(x - x0, x1 - x, y - y0, y1 - y)
    return math.hypot(dx, dy)


def flat(loops):
    return [p for lp in loops for p in lp]


def box_mesh(p0, p1):
    """An axis-aligned box as the dict ``kernel.stl.parse_stl`` returns."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    quads = [
        (0, 1, 2, 3),  # bottom
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4),  # -Y
        (2, 3, 7, 6),  # +Y
        (1, 2, 6, 5),  # +X
        (3, 0, 4, 7),  # -X
    ]
    faces = []
    for a, b, c, d in quads:
        faces.append((a, b, c))
        faces.append((a, c, d))
    return {"vertices": verts, "faces": faces}


def quad(a, b, c, d):
    return [(a, b, c), (a, c, d)]


def merge_meshes(*meshes):
    """Concatenate triangle soups into the dict shape parse_stl returns."""
    verts: list = []
    faces: list = []
    for mesh in meshes:
        offset = len(verts)
        verts.extend(tuple(v) for v in mesh["vertices"])
        faces.extend((a + offset, b + offset, c + offset)
                     for a, b, c in mesh["faces"])
    return {"vertices": verts, "faces": faces}


def frame_section(x0, y0, x1, y1, radius, cell):
    """Solid EVERYWHERE except an axis-aligned rectangular void.

    The reference's ``impl.waterline.section.frame_section``, reproduced here
    so the pocket / narrow-slot cases are built the same way it builds them:
    the grid is sized around the void, the material runs to the grid border,
    and there is no outer boss boundary inside the grid at all.
    """
    grid = wlf.Raster(*wlf.section_bounds(x0, y0, x1, y1, radius, cell), cell)
    for iy in range(grid.h):
        y = grid.cy(iy)
        base = iy * grid.w
        for ix in range(grid.w):
            x = grid.cx(ix)
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                grid.data[base + ix] = 1
    return grid


def tube_mesh(outer, inner, z0, z1):
    """Rectangular tube: outer walls, inner (hole) walls, framed caps.

    ``outer`` / ``inner`` are ``(x0, y0, x1, y1)``.  Watertight, so the
    cross-section between the caps is outer rect XOR inner rect.
    """
    ox0, oy0, ox1, oy1 = outer
    ix0, iy0, ix1, iy1 = inner
    ob = [(ox0, oy0, z0), (ox1, oy0, z0), (ox1, oy1, z0), (ox0, oy1, z0)]
    ot = [(ox0, oy0, z1), (ox1, oy0, z1), (ox1, oy1, z1), (ox0, oy1, z1)]
    ib = [(ix0, iy0, z0), (ix1, iy0, z0), (ix1, iy1, z0), (ix0, iy1, z0)]
    it = [(ix0, iy0, z1), (ix1, iy0, z1), (ix1, iy1, z1), (ix0, iy1, z1)]
    verts = ob + ot + ib + it
    faces = []
    # Outer walls (0..3 bottom, 4..7 top) and inner walls (8..11, 12..15).
    for k in range(4):
        faces += quad(k, (k + 1) % 4, 4 + (k + 1) % 4, 4 + k)
        faces += quad(8 + k, 8 + (k + 1) % 4, 12 + (k + 1) % 4, 12 + k)
    # Caps: the ring between outer edge k..k+1 and inner edge k..k+1.
    for k in range(4):
        j = (k + 1) % 4
        faces += quad(k, j, 8 + j, 8 + k)              # bottom ring
        faces += quad(4 + k, 12 + k, 12 + j, 4 + j)    # top ring
    return {"vertices": verts, "faces": faces}


# ---------------------------------------------------------------------------
# Registration / interface contract
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_registered_under_its_own_name(self):
        assert "waterline_finishing" in list_strategies()

    def test_get_strategy_returns_the_f2_strategy(self):
        strategy = get_strategy("waterline_finishing")
        assert isinstance(strategy, wlf.WaterlineFinishingStrategy)
        assert isinstance(strategy, BaseStrategy)
        assert strategy.name == "waterline_finishing"

    def test_description_names_both_planners(self):
        description = get_strategy("waterline_finishing").description
        assert "waterline" in description.lower()
        assert "scallop" in description.lower()

    def test_registration_rejects_a_non_strategy_class(self):
        with pytest.raises(TypeError):
            register_strategy("not_a_strategy", dict)

    def test_unknown_name_still_reports_the_available_set(self):
        with pytest.raises(KeyError) as exc:
            get_strategy("nope")
        assert "waterline_finishing" in str(exc.value)


# ---------------------------------------------------------------------------
# Frozen constants / section bounds
# ---------------------------------------------------------------------------

class TestFrozenConstants:
    def test_cell_matches_the_reference_frozen_cell(self):
        # impl/waterline/parity.py:78 CELL_MM, pinned there by
        # tests/test_waterline.py::test_cell_and_radius_are_frozen.
        assert wlf.CELL_MM == 0.05

    def test_default_cusp_height_matches_reference_gate_a2(self):
        # impl/waterline/parity.py:258 target = 0.02
        assert wlf.DEFAULT_CUSP_HEIGHT_MM == 0.02

    def test_margin_is_two_radius_plus_four_cells(self):
        # impl/waterline/section.py:30 (README S3 proof)
        assert wlf.margin(R, CELL) == pytest.approx(2 * R + 4 * CELL)

    def test_snap_band_is_the_reference_band(self):
        # impl/waterline/waterline.py:53
        assert wlf.SNAP_BAND_CELLS == 2.0

    def test_plunge_divisor_is_the_measured_third(self):
        # docs/ideal-cam-architecture.md E-S6: tool_feedPlunge = cut / 3
        assert wlf.PLUNGE_FEED_DIVISOR == 3.0


class TestSectionBounds:
    def test_pad_is_at_least_the_margin(self):
        pad_needed = wlf.margin(R, CELL)
        x0, y0, x1, y1 = wlf.section_bounds(0.0, 0.0, 10.0, 6.0, R, CELL)
        assert -x0 == pytest.approx(pad_needed, abs=CELL)
        assert x1 - 10.0 == pytest.approx(pad_needed, abs=CELL)

    def test_material_bbox_lands_on_cell_boundaries(self):
        # Rounding the pad out to whole cells keeps the lattice on the
        # material, so an axis-aligned mask is exact rather than half a cell
        # off (impl/waterline/section.py whole_cells).
        x0, y0, _, _ = wlf.section_bounds(1.0, 2.0, 9.0, 7.0, R, CELL)
        assert abs((1.0 - x0) / CELL - round((1.0 - x0) / CELL)) < 1e-6
        assert abs((2.0 - y0) / CELL - round((2.0 - y0) / CELL)) < 1e-6

    def test_negative_radius_is_rejected(self):
        with pytest.raises(ValueError):
            wlf.section_bounds(0.0, 0.0, 1.0, 1.0, -0.1, CELL)

    def test_raster_rejects_a_non_positive_cell(self):
        with pytest.raises(ValueError):
            wlf.Raster(0.0, 0.0, 1.0, 1.0, 0.0)
        with pytest.raises(ValueError):
            wlf.Raster(0.0, 0.0, 1.0, 1.0, float("nan"))

    def test_raster_rejects_inverted_bounds(self):
        with pytest.raises(ValueError):
            wlf.Raster(5.0, 0.0, 1.0, 1.0, CELL)


# ---------------------------------------------------------------------------
# Exact EDT
# ---------------------------------------------------------------------------

class TestExactEDT:
    def test_empty_cells_read_zero_and_solid_cells_read_the_neighbour(self):
        grid = wlf.section_rect(0.0, 0.0, 1.0, 1.0, 0.0, 0.1)
        dt = grid.distance_to_empty()
        # A solid cell's distance to the nearest EMPTY cell is >= 1 cell.
        solid_dt = [v for i, v in enumerate(dt) if grid.data[i]]
        empty_dt = [v for i, v in enumerate(dt) if not grid.data[i]]
        assert min(solid_dt) >= 1.0
        assert max(empty_dt) == 0.0

    def test_edt_matches_a_brute_force_reimplementation(self):
        """Independent check: direct min over the seeds, no transform."""
        grid = wlf.Raster(0.0, 0.0, 0.5, 0.4, 0.1)
        # A deterministic pseudo-random mask (no RNG dependency).
        for iy in range(grid.h):
            for ix in range(grid.w):
                grid.data[grid.index(ix, iy)] = 1 if (ix * 7 + iy * 13) % 5 < 2 else 0
        dt = grid.distance_to_empty()
        cell = grid.cell
        # distance_to_empty seeds the EMPTY cells, so the brute force has to
        # measure to the empty cells too.
        seeds = [(grid.cx(i % grid.w), grid.cy(i // grid.w))
                 for i in range(len(grid.data)) if grid.data[i] == 0]
        assert seeds, "the mask must contain empty cells"
        for idx in range(0, len(grid.data), 37):
            x, y = grid.cx(idx % grid.w), grid.cy(idx // grid.w)
            best = min(math.hypot(x - sx, y - sy) for sx, sy in seeds)
            ix, iy = grid.ix(x), grid.iy(y)
            border = min(ix + 1, grid.w - ix, iy + 1, grid.h - iy) * cell
            assert dt[idx] * cell == pytest.approx(min(best, border), abs=1e-9)

    def test_border_cells_clamp_to_the_border_distance(self):
        grid = wlf.Raster(0.0, 0.0, 1.0, 1.0, 0.1)
        for i in range(len(grid.data)):
            grid.data[i] = 1
        dt = grid.distance_to_empty()
        corner = dt[0]
        assert corner == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Section construction
# ---------------------------------------------------------------------------

class TestSections:
    def test_axis_aligned_mask_is_exact(self):
        grid = wlf.section_rect(-8.0, -4.0, 8.0, 4.0, 0.0, CELL)
        inside = 0
        outside = 0
        for iy in range(grid.h):
            for ix in range(grid.w):
                x, y = grid.cx(ix), grid.cy(iy)
                if -8.0 <= x <= 8.0 and -4.0 <= y <= 4.0:
                    assert grid.data[grid.index(ix, iy)] == 1, (x, y)
                    inside += 1
                elif x < -8.0 - CELL or x > 8.0 + CELL or y < -4.0 - CELL \
                        or y > 4.0 + CELL:
                    assert grid.data[grid.index(ix, iy)] == 0, (x, y)
                    outside += 1
        assert inside > 1000 and outside > 1000

    def test_section_needs_at_least_three_points(self):
        with pytest.raises(ValueError):
            wlf.section_from_polygon([(0.0, 0.0), (1.0, 1.0)], 0.0, CELL)

    def test_erosion_insets_the_material(self):
        # stock_to_leave: material = interior eroded by the allowance.
        solid = wlf.section_from_polygon(RECT, 0.0, CELL, R)
        left = wlf.section_from_polygon(RECT, 1.0, CELL, R)
        assert left.count() < solid.count()
        # Raster.get answers for the cell CONTAINING the point; 7.9 sits in
        # the cell [7.90, 7.95) whose centre (7.925) is inside the +/-8 rect
        # but outside the +/-7 eroded one.
        assert solid.get(7.9, 0.0) is True
        assert left.get(7.9, 0.0) is False
        assert left.get(6.0, 0.0) is True

    def test_even_odd_fill_carries_a_hole(self):
        outer = [(-6.0, -4.0), (6.0, -4.0), (6.0, 4.0), (-6.0, 4.0)]
        inner = [(-2.0, -1.5), (2.0, -1.5), (2.0, 1.5), (-2.0, 1.5)]
        grid = wlf.section_from_boundaries([outer, inner], 0.0, CELL, R)
        assert grid.get(0.0, 0.0) is False          # inside the hole
        assert grid.get(4.0, 0.0) is True           # in the wall
        assert grid.get(7.0, 0.0) is False          # outside the boss

    def test_inside_polygon_is_even_odd(self):
        square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
        assert wlf.inside_polygon(square, 2.0, 2.0) is True
        assert wlf.inside_polygon(square, 5.0, 2.0) is False
        assert wlf.inside_polygon(square, -1.0, -1.0) is False
        assert wlf.inside_polygon(square[:2], 1.0, 1.0) is False

    def test_uneroded_fill_is_exactly_inside_polygon(self):
        """``radius = 0`` must be cell-for-cell exact against the reference
        even-odd rule, on a polygon whose edges do NOT land on cell
        boundaries.

        The index-arithmetic span the reference's ``section_from_polygon``
        uses (``ix(lo) + 1 .. ix(hi)``, i.e. ``(lo, hi]``) is only equivalent
        to that rule on cell boundaries: off them it admits one cell outside
        the material at ``hi`` and drops one cell inside at ``lo``.  At gate
        B's ``radius = R`` the erosion test rejects both slivers, so the
        reference never sees it; an un-eroded finishing section does, and the
        sliver shows up as a full-cell error on the finished contour.
        """
        poly = [(0.0, 0.0), (7.3, 0.9), (9.1, 5.4), (3.2, 8.7), (-1.7, 4.1)]
        grid = wlf.section_from_polygon(poly, 0.0, CELL, 2.0)
        mismatches = 0
        for iy in range(grid.h):
            y = grid.cy(iy)
            base = iy * grid.w
            for ix in range(grid.w):
                inside = wlf.inside_polygon(poly, grid.cx(ix), y)
                if inside != (grid.data[base + ix] == 1):
                    mismatches += 1
        assert grid.count() > 1000
        assert mismatches == 0

    @pytest.mark.parametrize("x0,width", [
        (0.0, 1.0),      # no edge on a centre
        (0.0, 1.125),    # the RIGHT edge lands exactly on a cell centre
        (0.125, 1.0),    # both vertical edges on cell boundaries
        (0.125, 1.125),  # right edge on a centre, left on a boundary
    ])
    def test_fill_is_exact_when_an_edge_lands_on_a_cell_centre(self, x0, width):
        """The half-open tie rule, pinned directly.

        ``inside_polygon`` toggles on crossings STRICTLY RIGHT of x, so a
        centre exactly on the left edge is INSIDE and one exactly on the
        right edge is OUTSIDE: the span is ``[lo, hi)``.  Selecting
        ``(lo, hi]`` instead (or the reference's index arithmetic) flips
        both of those cells - one column gained, one column lost.
        """
        cell = 0.25
        poly = [(x0, 0.0), (x0 + width, 0.0), (x0 + width, 0.9), (x0, 0.9)]
        grid = wlf.section_from_polygon(poly, 0.0, cell, 1.0)
        mismatches = []
        for iy in range(grid.h):
            y = grid.cy(iy)
            base = iy * grid.w
            for ix in range(grid.w):
                inside = wlf.inside_polygon(poly, grid.cx(ix), y)
                if inside != (grid.data[base + ix] == 1):
                    mismatches.append((grid.cx(ix), y, inside))
        assert mismatches == []

    def test_the_tie_case_really_has_a_centre_on_the_material_edge(self):
        """Prove the tie exists - otherwise the case above proves nothing.

        ``section_bounds`` rounds the PAD out to whole cells, so the material
        bbox MIN always lands on a cell BOUNDARY; a tie can only come from a
        material size that is a half-cell multiple, which pushes the far edge
        onto the next centre.  1.125 mm = 4.5 cells at cell 0.25 does that.
        """
        cell = 0.25
        poly = [(0.0, 0.0), (1.125, 0.0), (1.125, 0.9), (0.0, 0.9)]
        grid = wlf.section_from_polygon(poly, 0.0, cell, 1.0)
        on_edge = [ix for ix in range(grid.w)
                   if abs(grid.cx(ix) - 1.125) < 1e-12]
        assert on_edge, "the right edge should sit on a cell centre"
        # The centre exactly on the right edge is OUTSIDE (half-open rule).
        assert wlf.inside_polygon(poly, grid.cx(on_edge[0]), 0.5) is False
        assert grid.data[grid.index(on_edge[0], grid.iy(0.5))] == 0

    def test_scanline_pairs_crossings_in_order(self):
        square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
        xs = wlf.scanline([square], 2.0)
        assert xs == pytest.approx([0.0, 4.0])

    def test_boundary_edges_covers_every_segment(self):
        square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
        assert len(wlf._boundary_edges([square])) == 4
        assert len(wlf._boundary_edges([square, square])) == 8


# ---------------------------------------------------------------------------
# Distance field vs the independent collision measure
# ---------------------------------------------------------------------------

class TestFieldAgreesWithCollision:
    def test_distance_field_matches_the_collision_measure(self):
        """The row transform and the brute-force window must agree.

        Two different algorithms for one quantity, which is what lets the
        collision report be a real check of the field instead of a restatement
        of it (``impl/waterline/waterline.py:118-121``).

        Only the SNAPPED band is comparable: outside it the field still holds
        the cell-centre EDT, which legitimately sits up to ``cell*sqrt(2)/2``
        away from the union-of-squares distance the collision check measures.
        """
        # Pad the grid for the level being extracted (the reference builds
        # every analytic section with section_bounds(..., radius, cell)).
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, R, CELL)
        level = R
        field = wlf.distance_to_material(grid, level)
        search = level + 2 * CELL
        band = wlf.SNAP_BAND_CELLS * CELL
        checked = 0
        for idx, value in enumerate(field):
            if not (level - band <= value <= level + band):
                continue
            x, y = grid.cx(idx % grid.w), grid.cy(idx // grid.w)
            measured = wlf.clearance_to_solid(grid, x, y, search)
            assert value == pytest.approx(measured, abs=1e-6)
            checked += 1
        assert checked > 500

    def test_border_cells_are_masked_to_infinity(self):
        grid = wlf.section_rect(0.0, 0.0, 1.0, 1.0, R, CELL)
        field = wlf.distance_to_material(grid, R)
        assert field[0] == wlf.INF

    def test_snap_moves_the_field_onto_the_union_of_squares(self):
        """Unsnapped (cell-centre) values sit up to cell*sqrt(2)/2 inside the
        union of the cells' squares; snapping must remove that gap - it is
        exactly what produced the reference's 0.0354 mm collision reading."""
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, R, CELL)
        level = R
        raw = wlf.distance_to_material(grid, level)
        # Recompute the unsnapped field by re-running stage 1 only.
        inv = wlf.Raster(grid.xmin, grid.ymin, grid.xmin + grid.w * grid.cell,
                         grid.ymin + grid.h * grid.cell, grid.cell)
        for i in range(len(inv.data)):
            inv.data[i] = 0 if grid.data[i] else 1
        dt = inv.distance_to_empty()
        band = wlf.SNAP_BAND_CELLS * CELL
        gap = 0.0
        snapped = 0
        for idx, value in enumerate(raw):
            if not (level - band <= value <= level + band):
                continue
            ix, iy = idx % grid.w, idx // grid.w
            x, y = grid.cx(ix), grid.cy(iy)
            exact = wlf.clearance_to_solid(grid, x, y, level + 2 * CELL)
            # A cell whose border is closer than the material is CLAMPED by
            # distance_to_empty; comparing that reading would measure the
            # clamp, not the cell-centre bias this test is about.
            border = min(ix + 1, grid.w - ix, iy + 1, grid.h - iy) * CELL
            if border < exact:
                continue
            gap = max(gap, abs(dt[idx] * grid.cell - exact))
            assert abs(value - exact) <= 1e-6      # the snap landed
            snapped += 1
        # The EDT-to-centres reading differs from the exact union distance by
        # up to cell*sqrt(2)/2 = 0.0354 mm, i.e. the snap has work to do.
        assert snapped > 100
        assert gap > 0.01
        assert gap <= CELL * math.sqrt(2) / 2 + 1e-9

    def test_snap_matches_a_naive_per_level_sweep(self):
        """The bisect sweep must write exactly what the reference's
        one-sweep-per-level loop writes (same cells, same values)."""
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, R + 1.0, CELL)
        levels = [R, R + 0.5, R + 1.0]
        base = wlf.distance_to_material(grid, levels[-1], levels=[])
        rowdist = wlf.row_distance_to_solid(grid)
        band = wlf.SNAP_BAND_CELLS * CELL

        fast = list(base)
        wlf.snap_to_squares(fast, grid, levels, rowdist)

        naive = list(base)
        for level in levels:
            lo, hi = level - band, level + band
            for i, value in enumerate(naive):
                if lo <= value <= hi:
                    naive[i] = wlf.squares_distance(grid, rowdist,
                                                    i % grid.w, i // grid.w, hi)

        assert fast == naive
        assert any(a != b for a, b in zip(base, fast))

    def test_collision_report_flags_a_planted_gouge(self):
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, 0.0, CELL)
        good = [[(0.0, 3.0 + R)]]
        bad = [[(0.0, 3.0 + 0.2)]]
        assert wlf.collision_report(grid, R, good)["max_penetration_mm"] <= COLLISION_DEV
        assert wlf.collision_report(grid, R, bad)["max_penetration_mm"] > 1.0

    def test_clearance_inside_the_solid_is_zero(self):
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, 0.0, CELL)
        assert wlf.clearance_to_solid(grid, 0.0, 0.0, R) == 0.0


# ---------------------------------------------------------------------------
# Waterline (Z-level contour)
# ---------------------------------------------------------------------------

class TestWaterline:
    def test_rect_boss_yields_one_closed_loop(self):
        grid = wlf.section_rect(-10.0, -4.0, 10.0, 4.0, R, CELL)
        loops = wlf.waterline(grid, R)
        assert len(loops) == 1
        assert len(loops[0]) >= 4

    def test_rect_boss_deviation_is_inside_one_and_a_half_cells(self):
        # Reference gate A2 row "A2 rect boss |sd - R|" <= analytic_dev_mm.
        grid = wlf.section_rect(-10.0, -4.0, 10.0, 4.0, R, CELL)
        loops = wlf.waterline(grid, R)
        worst = max(abs(signed_dist_rect(x, y, -10, -4, 10, 4) - R)
                    for (x, y) in flat(loops))
        assert worst <= ANALYTIC_DEV

    def test_pocket_loop_sits_radius_inside_the_wall(self):
        # Reference gate A3: material everywhere except a rectangular void,
        # sd == -R for the loop inside it.
        grid = frame_section(-6.0, -3.0, 6.0, 3.0, R, CELL)
        loops = wlf.waterline(grid, R)
        assert len(loops) == 1
        worst = max(abs(signed_dist_rect(x, y, -6, -3, 6, 3) + R)
                    for (x, y) in flat(loops))
        assert worst <= ANALYTIC_DEV

    def test_boss_with_a_hole_yields_two_independent_loops(self):
        # Reference gate A4: island loop count == 2.
        outer = [(-10.0, -7.0), (10.0, -7.0), (10.0, 7.0), (-10.0, 7.0)]
        inner = [(-3.0, -2.0), (3.0, -2.0), (3.0, 2.0), (-3.0, 2.0)]
        grid = wlf.section_from_boundaries([outer, inner], 0.0, CELL, R)
        loops = wlf.waterline(grid, R)
        assert len(loops) == 2
        areas = sorted(len(lp) for lp in loops)
        assert areas[0] > 4

    def test_slot_narrower_than_the_tool_yields_no_path(self):
        # Reference gate A5: a 2.0 mm slot cannot take a 3.175 mm cutter.
        grid = frame_section(-10.0, -1.0, 10.0, 1.0, R, CELL)
        assert wlf.waterline(grid, R) == []

    def test_disc_boss_deviation_is_inside_one_and_a_half_cells(self):
        # Reference gate A1: |dist - (5 + R)| <= analytic_dev_mm.
        circle = [(5.0 * math.cos(i * math.pi / 180.0),
                   5.0 * math.sin(i * math.pi / 180.0)) for i in range(360)]
        grid = wlf.section_from_polygon(circle, 0.0, CELL, R)
        loops = wlf.waterline(grid, R)
        assert len(loops) == 1
        worst = max(abs(math.hypot(x, y) - (5.0 + R)) for (x, y) in flat(loops))
        assert worst <= ANALYTIC_DEV

    def test_emitted_loops_never_penetrate_more_than_one_cell(self):
        # Reference gate A1/A3 collision rows <= collision_penetration_mm.
        grid = wlf.section_rect(-10.0, -4.0, 10.0, 4.0, R, CELL)
        loops = wlf.waterline(grid, R)
        report = wlf.collision_report(grid, R, loops)
        assert report["max_penetration_mm"] <= COLLISION_DEV
        assert report["points"] == sum(len(lp) for lp in loops)

    def test_loop_endpoints_chain_exactly(self):
        grid = wlf.section_rect(-10.0, -4.0, 10.0, 4.0, R, CELL)
        for loop in wlf.waterline(grid, R):
            # A chained marching-squares loop returns to its start.
            assert math.hypot(loop[0][0] - loop[-1][0],
                              loop[0][1] - loop[-1][1]) < 1e-9


class TestMarchingSquares:
    def test_cross_is_none_on_one_side(self):
        assert wlf._cross((0.0, 0.0), (1.0, 0.0), 1.0, 2.0, 0.5, True) is None
        assert wlf._cross((0.0, 0.0), (1.0, 0.0), -1.0, -2.0, 0.5, True) is None

    def test_cross_interpolates_horizontally_and_vertically(self):
        p = wlf._cross((0.0, 0.0), (4.0, 0.0), 0.0, 8.0, 4.0, True)
        assert p == pytest.approx((2.0, 0.0))
        p = wlf._cross((0.0, 0.0), (0.0, 4.0), 0.0, 8.0, 4.0, False)
        assert p == pytest.approx((0.0, 2.0))

    def test_chain_links_segments_through_shared_endpoints(self):
        a, b, c = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))
        loops = wlf._chain([(a, b), (b, c)])
        assert len(loops) == 1
        assert loops[0] == [a, b, c]


# ---------------------------------------------------------------------------
# Constant-scallop maths
# ---------------------------------------------------------------------------

class TestScallopMaths:
    def test_forward_and_inverse_round_trip_over_a_sweep(self):
        for h in (0.001, 0.005, 0.02, 0.05, 0.2):
            p = wlf.stepover_for_cusp(h, R)
            assert wlf.cusp_height(p, R) == pytest.approx(h, rel=1e-9)

    def test_inverse_round_trip_over_a_stepover_sweep(self):
        for p in (0.05, 0.2, 0.5023942674832188, 1.5, 3.0):
            h = wlf.cusp_height(p, R)
            assert wlf.stepover_for_cusp(h, R) == pytest.approx(p, rel=1e-9)

    def test_small_step_is_first_order_and_under_shoots(self):
        p = wlf.stepover_for_cusp(0.02, R)
        approx = wlf.small_step_cusp(p, R)
        assert approx < 0.02
        assert approx == pytest.approx(0.02, rel=1e-2)

    def test_stepover_for_cusp_matches_the_closed_form(self):
        h = 0.02
        expected = 2.0 * math.sqrt(2.0 * R * h - h * h)
        assert wlf.stepover_for_cusp(h, R) == pytest.approx(expected)

    def test_cusp_height_domain_errors(self):
        with pytest.raises(ValueError):
            wlf.cusp_height(-0.1, R)
        with pytest.raises(ValueError):
            wlf.cusp_height(2.0 * R + 0.1, R)
        with pytest.raises(ValueError):
            wlf.stepover_for_cusp(-0.001, R)
        with pytest.raises(ValueError):
            wlf.stepover_for_cusp(R + 0.001, R)

    def test_ring_plan_steps_by_the_cusp_stepover(self):
        p, ds = wlf.ring_plan(R, 0.02, R, 4)
        assert ds[0] == pytest.approx(R)
        assert ds[1] - ds[0] == pytest.approx(p)
        assert ds[3] - ds[2] == pytest.approx(p)
        assert len(ds) == 4

    def test_ring_plan_validates_its_inputs(self):
        with pytest.raises(ValueError):
            wlf.ring_plan(R, 0.02, R - 0.01, 4)
        with pytest.raises(ValueError):
            wlf.ring_plan(R, 0.02, R, 0)

    def test_offset_loops_returns_every_requested_distance(self):
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, 0.0, R + 1.0)
        p, ds = wlf.ring_plan(R, 0.02, R, 3)
        out = wlf.offset_loops(grid, ds)
        assert [d for d, _ in out] == pytest.approx(ds)
        assert all(loops for _, loops in out)

    def test_offset_loops_needs_at_least_one_distance(self):
        grid = wlf.section_rect(-6.0, -3.0, 6.0, 3.0, 0.0, R)
        with pytest.raises(ValueError):
            wlf.offset_loops(grid, [])

    def test_ring_loops_sit_at_their_declared_offset(self):
        p, ds = wlf.ring_plan(R, 0.02, R, 3)
        # Pad for the FARTHEST ring, exactly like scallop_program does.
        grid = wlf.section_rect(-8.0, -5.0, 8.0, 5.0, ds[-1], CELL)
        for d, loops in wlf.offset_loops(grid, ds):
            assert loops, d
            worst = max(abs(signed_dist_rect(x, y, -8, -5, 8, 5) - d)
                        for (x, y) in flat(loops))
            assert worst <= ANALYTIC_DEV, (d, worst)


# ---------------------------------------------------------------------------
# Mesh cross-sections
# ---------------------------------------------------------------------------

class TestMeshSections:
    def test_box_section_is_the_footprint(self):
        mesh = box_mesh((0.0, 0.0, 0.0), (10.0, 6.0, 4.0))
        loops = wlf.mesh_section_loops(mesh, 2.0)
        assert len(loops) == 1
        xs = [p[0] for p in loops[0]]
        ys = [p[1] for p in loops[0]]
        assert min(xs) == pytest.approx(0.0, abs=1e-9)
        assert max(xs) == pytest.approx(10.0, abs=1e-9)
        assert min(ys) == pytest.approx(0.0, abs=1e-9)
        assert max(ys) == pytest.approx(6.0, abs=1e-9)

    def test_box_section_at_its_own_top_and_bottom_faces(self):
        """The degenerate cases: coplanar faces are skipped, the walls'
        in-plane edges carry the rectangle."""
        mesh = box_mesh((0.0, 0.0, 0.0), (10.0, 6.0, 4.0))
        for z in (0.0, 4.0):
            loops = wlf.mesh_section_loops(mesh, z)
            assert len(loops) == 1, z
            xs = [p[0] for p in loops[0]]
            assert max(xs) - min(xs) == pytest.approx(10.0, abs=1e-9)

    def test_section_above_the_part_is_empty(self):
        mesh = box_mesh((0.0, 0.0, 0.0), (10.0, 6.0, 4.0))
        assert wlf.mesh_section_loops(mesh, 5.0) == []
        assert wlf.mesh_section_loops(mesh, -1.0) == []

    def test_stepped_part_has_different_sections_per_level(self):
        mesh = box_mesh((0.0, 0.0, 0.0), (20.0, 12.0, 4.0))
        boss = box_mesh((5.0, 3.0, 4.0), (15.0, 9.0, 10.0))
        # Merge the two boxes into one vertex/face soup.
        verts = list(mesh["vertices"]) + list(boss["vertices"])
        offset = len(mesh["vertices"])
        faces = list(mesh["faces"]) + [(a + offset, b + offset, c + offset)
                                       for a, b, c in boss["faces"]]
        stepped = {"vertices": verts, "faces": faces}
        low = wlf.mesh_section_loops(stepped, 2.0)
        high = wlf.mesh_section_loops(stepped, 7.0)
        assert len(low) == 1 and len(high) == 1
        assert max(p[0] for p in low[0]) - min(p[0] for p in low[0]) == pytest.approx(20.0)
        assert max(p[0] for p in high[0]) - min(p[0] for p in high[0]) == pytest.approx(10.0)

    def test_tube_section_carries_the_hole(self):
        mesh = tube_mesh((0.0, 0.0, 10.0, 10.0), (3.0, 3.0, 7.0, 7.0), 0.0, 5.0)
        loops = wlf.mesh_section_loops(mesh, 2.5)
        assert len(loops) == 2
        grid = wlf.section_from_boundaries(loops, 0.0, CELL, R)
        assert grid.get(0.0 + 1.0, 5.0) is True      # in the wall
        assert grid.get(5.0, 5.0) is False           # inside the hole

    def test_tube_waterline_has_a_loop_in_the_hole(self):
        mesh = tube_mesh((0.0, 0.0, 12.0, 12.0), (3.0, 3.0, 9.0, 9.0), 0.0, 5.0)
        loops = wlf.mesh_section_loops(mesh, 2.5)
        grid = wlf.section_from_boundaries(loops, 0.0, CELL, R)
        water = wlf.waterline(grid, R)
        assert len(water) == 2
        # One loop hugs the outside of the boss, one sits R inside the hole;
        # measure the inner one only.
        inner = [lp for lp in water
                 if all(3.0 <= x <= 9.0 and 3.0 <= y <= 9.0 for (x, y) in lp)]
        assert len(inner) == 1
        worst = max(abs(signed_dist_rect(x, y, 3, 3, 9, 9) + R)
                    for (x, y) in inner[0])
        assert worst <= ANALYTIC_DEV

    def test_mesh_without_the_required_keys_raises(self):
        with pytest.raises(ValueError):
            wlf.mesh_section_loops({"vertices": []}, 0.0)

    def test_a_step_plane_section_is_the_union_not_a_frame(self):
        """The step-plane trap, pinned at the section level.

        Plate ``0..60 x 0..40 z 0..4`` with a boss ``20..40 x 15..25 z 4..8``:
        at exactly ``z = 4`` the plane carries the plate's outline AND the
        boss's outline.  Even-odd over both is a FRAME - it declares the
        boss's footprint to be a void, which is the opposite of the truth
        (the plate is under it).  The material is the UNION of the section
        just below and the section just above, so the boss footprint stays
        solid and the waterline stays ONE loop.
        """
        mesh = merge_meshes(box_mesh((0.0, 0.0, 0.0), (60.0, 40.0, 4.0)),
                            box_mesh((20.0, 15.0, 4.0), (40.0, 25.0, 8.0)))
        stock = rect_stock(0.0, 0.0, 60.0, 40.0, 0.0, 8.0)
        regions, source = wlf.WaterlineFinishingStrategy._material_boundaries(
            {"mesh": mesh}, stock, 4.0)
        assert source == "mesh"
        assert len(regions) == 2          # one limit from each side of z
        grid = wlf.section_from_regions(regions, 0.0, CELL, R)
        assert grid.get(30.0, 20.0) is True    # boss footprint: material
        assert grid.get(5.0, 5.0) is True      # plate around it: material
        assert grid.get(62.0, 20.0) is False    # pad, outside the plate
        assert len(wlf.waterline(grid, R)) == 1

    def test_a_step_plane_does_not_gouge_through_the_strategy(self):
        """End-to-end form of the same trap: no cut may enter the boss."""
        mesh = merge_meshes(box_mesh((0.0, 0.0, 0.0), (60.0, 40.0, 4.0)),
                            box_mesh((20.0, 15.0, 4.0), (40.0, 25.0, 8.0)))
        op = operation(mesh=mesh, finish_levels=[4.0], finish_mode="waterline",
                       _top=8.0, _bottom=0.0,
                       _stock=rect_stock(0.0, 0.0, 60.0, 40.0, 0.0, 8.0))
        op.extra_args.pop("profile")
        tp = get_strategy("waterline_finishing").run(op)
        assert "error" not in tp.params
        assert tp.params["waterline_loops"] == 1
        cuts = [(m.end.x, m.end.y) for m in tp.moves
                if m.move_type is MoveType.LINEAR]
        inside_boss = [p for p in cuts if 20.0 < p[0] < 40.0
                       and 15.0 < p[1] < 25.0]
        assert inside_boss == [], f"contour ran through the boss: {inside_boss[:3]}"

    def test_multi_region_section_rejects_an_erosion(self):
        """Union erosion would need the union's own boundary - declared."""
        outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        inner = [(3.0, 3.0), (7.0, 3.0), (7.0, 7.0), (3.0, 7.0)]
        with pytest.raises(ValueError) as exc:
            wlf.section_from_regions([[outer], [inner]], R, CELL, R)
        assert "radius = 0" in str(exc.value)
        # ...and the single-region path still erodes exactly.
        assert wlf.section_from_regions([[outer]], R, CELL, R).count() < \
            wlf.section_from_regions([[outer]], 0.0, CELL, R).count()

    def test_plane_point_is_canonicalised_by_vertex_index(self):
        a, b = (0.0, 0.0, 0.0), (4.0, 0.0, 8.0)
        forward = wlf._plane_point(a, b, 0.0, 8.0, 1, 2, 4.0)
        backward = wlf._plane_point(b, a, 8.0, 0.0, 2, 1, 4.0)
        assert forward == backward


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

class TestLevels:
    def test_levels_start_at_the_top_and_end_at_the_bottom(self):
        assert wlf._finish_levels(12.0, 0.0, 3.0) == [12.0, 9.0, 6.0, 3.0, 0.0]

    def test_stock_bottom_is_always_a_level(self):
        levels = wlf._finish_levels(10.0, 0.0, 4.0)
        assert levels[-1] == 0.0

    def test_single_level_when_top_equals_bottom(self):
        assert wlf._finish_levels(5.0, 5.0, 1.0) == [5.0]

    def test_stepdown_larger_than_the_stock_still_yields_two_levels(self):
        assert wlf._finish_levels(12.0, 0.0, 50.0) == [12.0, 0.0]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_operation_validates_clean(self):
        assert get_strategy("waterline_finishing").validate_params(operation()) == []

    def test_missing_tool_is_reported(self):
        op = operation()
        op.tool = None
        errors = get_strategy("waterline_finishing").validate_params(op)
        assert any("Tool definition" in e for e in errors)

    def test_missing_stock_is_reported(self):
        op = operation()
        op.stock = None
        errors = get_strategy("waterline_finishing").validate_params(op)
        assert any("Stock definition" in e for e in errors)

    def test_unknown_finish_mode_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="sideways"))
        assert any("finish_mode" in e for e in errors)

    def test_cusp_above_the_tool_radius_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(cusp_height_mm=R + 0.01))
        assert any("cusp_height_mm" in e for e in errors)

    def test_non_finite_feed_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(feed_rate=float("nan")))
        assert any("feed_rate" in e for e in errors)

    def test_non_numeric_cell_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(cell_mm="coarse"))
        assert any("cell_mm must be a number" in e for e in errors)

    def test_profile_and_mesh_together_are_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(mesh=box_mesh((0, 0, 0), (1, 1, 1))))
        assert any("not both" in e for e in errors)

    def test_malformed_mesh_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(mesh={"triangles": []}))
        assert any("parse_stl" in e for e in errors)

    def test_malformed_profile_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(profile=[(0.0, 0.0), (1.0, 1.0)]))
        assert any("profile" in e for e in errors)

    def test_finish_level_outside_the_stock_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_levels=[99.0]))
        assert any("finish_levels" in e for e in errors)

    def test_empty_finish_levels_are_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_levels=[]))
        assert any("finish_levels" in e for e in errors)

    def test_first_ring_below_the_radius_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="scallop", first_ring=R - 0.1))
        assert any("first_ring" in e for e in errors)

    def test_scallop_mode_without_any_spacing_is_reported(self):
        op = operation(finish_mode="scallop")
        op.extra_args["cusp_height_mm"] = None
        errors = get_strategy("waterline_finishing").validate_params(op)
        assert any("cusp_height_mm or ring_stepover" in e for e in errors)

    def test_ring_stepover_outside_the_domain_is_reported(self):
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="scallop", cusp_height_mm=None,
                      ring_stepover=2.0 * R + 0.1))
        assert any("ring_stepover" in e for e in errors)

    def test_scallop_rings_outside_the_ceiling_is_reported(self):
        # An explicit value used to bypass MAX_SCALLOP_RINGS and reach
        # offset_loops as N marching-squares sweeps - a hang, not an error.
        for bad in (0, -1, wlf.MAX_SCALLOP_RINGS + 1, 100000):
            errors = get_strategy("waterline_finishing").validate_params(
                operation(finish_mode="scallop", scallop_rings=bad))
            assert any("scallop_rings" in e for e in errors), bad
        assert get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="scallop", scallop_rings=3)) == []

    def test_scallop_z_outside_the_stock_is_reported(self):
        # scallop_z feeds a mesh section lookup and the pass sort, so an
        # unvalidated value could put a pass above the stock top.
        errors = get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="scallop", scallop_z=99.0, _top=8.0,
                     _bottom=0.0))
        assert any("scallop_z" in e for e in errors)
        assert get_strategy("waterline_finishing").validate_params(
            operation(finish_mode="scallop", scallop_z=0.0, _top=8.0,
                     _bottom=0.0)) == []

    def test_scallop_z_outside_the_stock_returns_an_error_toolpath(self):
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(), finish_mode="scallop", scallop_z=99.0,
            top_of_stock=0.0, bottom_of_stock=0.0)
        assert "scallop_z" in tp.params["error"]
        assert tp.moves == []

    def test_top_below_bottom_is_reported(self):
        op = operation()
        op.extra_args["top_of_stock"] = -5.0
        op.extra_args["bottom_of_stock"] = 0.0
        errors = get_strategy("waterline_finishing").validate_params(op)
        assert any("top_of_stock" in e for e in errors)

    def test_run_raises_on_an_invalid_operation(self):
        op = operation(finish_mode="sideways")
        with pytest.raises(ValueError):
            get_strategy("waterline_finishing").run(op)

    def test_direct_generate_returns_an_error_toolpath_for_a_nan(self):
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(), feed_rate=float("nan"))
        assert "error" in tp.params
        assert tp.moves == []

    def test_direct_generate_returns_an_error_toolpath_for_a_bad_mode(self):
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(), finish_mode="sideways")
        assert "finish_mode" in tp.params["error"]
        assert tp.moves == []

    def test_direct_generate_rejects_a_non_numeric_cell(self):
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(), cell_mm="coarse")
        assert "cell_mm" in tp.params["error"]


# ---------------------------------------------------------------------------
# Pass planning
# ---------------------------------------------------------------------------

class TestPlanFinishes:
    def test_waterline_mode_plans_one_pass_per_level(self):
        passes, info = wlf.plan_finishes(
            boundaries_at=lambda z: [[RECT]],
            z_levels=[10.0, 5.0, 0.0],
            tool_radius=R,
            cell=CELL,
            mode="waterline",
        )
        assert [fp.kind for fp in passes] == ["waterline"] * 3
        assert [fp.z for fp in passes] == [10.0, 5.0, 0.0]
        assert info["rings"] == 0

    def test_scallop_mode_plans_one_pass_per_ring_at_the_floor(self):
        passes, info = wlf.plan_finishes(
            boundaries_at=lambda z: [[RECT]],
            z_levels=[10.0, 5.0, 0.0],
            tool_radius=R,
            cell=CELL,
            mode="scallop",
            cusp_height_mm=0.02,
            ring_count=4,
        )
        assert [fp.kind for fp in passes] == ["scallop"] * 4
        assert {fp.z for fp in passes} == {0.0}
        assert info["rings"] == 4
        assert info["ring_stepover_mm"] == pytest.approx(
            wlf.stepover_for_cusp(0.02, R))

    def test_both_mode_mixes_the_two_and_sorts_by_descending_z(self):
        passes, info = wlf.plan_finishes(
            boundaries_at=lambda z: [[RECT]],
            z_levels=[10.0, 0.0],
            tool_radius=R,
            cell=CELL,
            mode="both",
            cusp_height_mm=0.02,
            ring_count=2,
        )
        assert [fp.z for fp in passes] == sorted([fp.z for fp in passes],
                                                 reverse=True)
        assert {fp.kind for fp in passes} == {"waterline", "scallop"}
        assert info["loops"] > 0

    def test_explicit_ring_stepover_drives_the_plan(self):
        _, info = wlf.plan_finishes(
            boundaries_at=lambda z: [[RECT]],
            z_levels=[0.0],
            tool_radius=R,
            cell=CELL,
            mode="scallop",
            cusp_height_mm=None,
            ring_stepover=1.0,
            ring_count=3,
        )
        assert info["ring_stepover_mm"] == pytest.approx(1.0)
        assert info["cusp_height_target_mm"] is None
        # The realised height is reported even when the caller set the spacing.
        assert info["cusp_height_mm"] == pytest.approx(
            R - math.sqrt(R * R - 0.25))

    def test_ring_count_is_derived_from_the_stock_footprint(self):
        # 24 x 14 stock around the 16 x 8 profile: the floor reaches 5 mm
        # from the wall at the farthest corner (convex material, so the
        # maximum really is there), and the sampled bound adds at most half
        # a sample cell on top.
        stock = rect_stock(-12.0, -7.0, 12.0, 7.0)
        true_extent = math.hypot(4.0, 3.0)
        extent = wlf._max_ring_extent([[RECT]], stock, samples=33)
        dx, dy = 24.0 / 32, 14.0 / 32
        assert extent >= true_extent - 1e-12            # never under-cover
        assert extent <= true_extent + 0.5 * math.hypot(dx, dy) + 1e-9
        _, info = wlf.plan_finishes(
            boundaries_at=lambda z: [[RECT]],
            z_levels=[0.0],
            tool_radius=R,
            cell=CELL,
            mode="scallop",
            cusp_height_mm=0.02,
            ring_count=None,
            stock=stock,
        )
        p = wlf.stepover_for_cusp(0.02, R)
        assert info["rings"] == int((extent - R) // p) + 1
        assert 2 <= info["rings"] <= wlf.MAX_SCALLOP_RINGS

    def test_ring_extent_reaches_the_bottom_of_a_pocket(self):
        """A corner rule returns 0 here; the rings would never enter the void.

        Material = frame (outer 40 x 30 with a 10 x 6 hole); the deepest
        floor point inside the stock is the hole centre, 3 mm from the wall.
        """
        outer = [(-20.0, -15.0), (20.0, -15.0), (20.0, 15.0), (-20.0, 15.0)]
        inner = [(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]
        stock = rect_stock(-20.0, -15.0, 20.0, 15.0)
        extent = wlf._max_ring_extent([[outer, inner]], stock, samples=33)
        assert extent >= 3.0, "the pocket bottom is 3 mm from the wall"
        assert extent <= 3.0 + 0.5 * math.hypot(40 / 32, 30 / 32) + 1e-9

    def test_ring_extent_reaches_into_a_u_shaped_notch(self):
        """Every stock corner lies ON this material, so a corner rule says 0
        while the notch mouth is 1 mm from both walls."""
        u = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (6.0, 10.0),
             (6.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]
        stock = rect_stock(0.0, 0.0, 10.0, 10.0)
        extent = wlf._max_ring_extent([[u]], stock, samples=33)
        assert extent >= 1.0

    def test_a_raster_that_would_exceed_the_cell_ceiling_is_rejected(self):
        # part + 2 * (stock extent) at cell 0.05 would be a huge grid; the
        # guard turns that into a message instead of a minutes-long sweep.
        with pytest.raises(ValueError) as exc:
            wlf.section_from_boundaries([RECT], 0.0, CELL, 200.0)
        assert "cells" in str(exc.value)
        assert str(wlf.MAX_RASTER_CELLS) in str(exc.value)

    def test_the_strategy_reports_the_guard_as_an_error_toolpath(self):
        stock = rect_stock(-400.0, -400.0, 400.0, 400.0)
        tp = get_strategy("waterline_finishing").generate_toolpath(
            stock, make_tool(), finish_mode="scallop",
            cusp_height_mm=0.02, finish_levels=[0.0],
            top_of_stock=0.0, bottom_of_stock=0.0)
        assert "cells" in tp.params.get("error", "")
        assert tp.moves == []

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            wlf.plan_finishes(lambda z: [[RECT]], [0.0], R, CELL, mode="nope")

    def test_non_positive_cell_raises(self):
        with pytest.raises(ValueError):
            wlf.plan_finishes(lambda z: [[RECT]], [0.0], R, 0.0)

    def test_deriving_rings_without_a_stock_raises(self):
        with pytest.raises(ValueError):
            wlf.plan_finishes(lambda z: [[RECT]], [0.0], R, CELL,
                              mode="scallop", ring_count=None, stock=None)

    def test_a_mesh_boundaries_callable_may_vary_with_z(self):
        seen: list[float] = []

        def at(z):
            seen.append(z)
            return [[RECT]]

        wlf.plan_finishes(at, [10.0, 0.0], R, CELL, mode="waterline")
        assert sorted(set(seen)) == [0.0, 10.0]


# ---------------------------------------------------------------------------
# Toolpath emission
# ---------------------------------------------------------------------------

class TestToolpath:
    def test_waterline_mode_emits_one_pass_per_level(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_levels=[0.0]))
        assert tp.strategy == "waterline_finishing"
        assert tp.params["waterline_loops"] == 1
        assert tp.params["scallop_rings"] == 0
        assert len(tp.moves) > 0

    def test_both_modes_emit_the_waterline_and_every_ring(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_mode="both", scallop_rings=3,
                      finish_levels=[0.0]))
        assert tp.params["waterline_loops"] == 1
        assert tp.params["scallop_rings"] == 3
        assert tp.params["passes"] == 4

    def test_exactly_two_feed_values_reach_the_toolpath(self):
        # E-S6: tool_feedCutting and tool_feedPlunge = cut / 3.  A plunge
        # happens only when the first level sits below the stock top.
        tp = get_strategy("waterline_finishing").run(
            operation(finish_levels=[0.0], _top=6.0, _bottom=0.0))
        feeds = {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}
        assert feeds == {1000.0, 1000.0 / 3.0}
        assert tp.params["feed_vocabulary"] == {
            "plunge": 333.333333, "cutting": 1000.0}

    def test_no_plunge_when_the_first_level_is_the_stock_top(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_levels=[0.0]))
        feeds = {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}
        assert feeds == {1000.0}

    def test_rapids_carry_no_feed(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_levels=[0.0]))
        assert any(m.move_type is MoveType.RAPID for m in tp.moves)
        assert all(m.feed == 0.0 for m in tp.moves
                   if m.move_type is MoveType.RAPID)
        assert all(m.feed > 0.0 for m in tp.moves
                   if m.move_type is MoveType.LINEAR)

    def test_every_loop_is_retracted_to_clearance(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_mode="both", scallop_rings=2,
                      finish_levels=[0.0]))
        retracts = [m for m in tp.moves
                    if m.move_type is MoveType.RAPID and m.end.z == 5.0]
        assert len(retracts) >= 2 * tp.params["passes"]

    def test_the_reported_point_count_matches_the_emitted_cuts(self):
        tp = get_strategy("waterline_finishing").run(
            operation(finish_levels=[0.0]))
        cuts = sum(1 for m in tp.moves if m.move_type is MoveType.LINEAR)
        assert tp.params["loop_points"] >= cuts - 1
        assert tp.params["moves"] == len(tp.moves)

    def test_stock_to_leave_moves_the_contour_out(self):
        op = operation(finish_levels=[0.0], stock_to_leave_mm=0.5)
        tp = get_strategy("waterline_finishing").run(op)
        assert tp.params["stock_to_leave_mm"] == 0.5
        xs = [m.end.x for m in tp.moves if m.move_type is MoveType.LINEAR]
        # The rect is 16 mm wide; R out plus 0.5 of allowance pushes the
        # contour 0.5 mm further out than R alone.
        assert max(xs) == pytest.approx(8.0 + R + 0.5, abs=0.02)

    def test_tool_wider_than_the_stock_is_reported(self):
        op = operation(finish_levels=[0.0], _tool_diameter=60.0)
        errors = get_strategy("waterline_finishing").validate_params(op)
        assert any("narrower than the tool radius" in e for e in errors)
        # run() refuses loudly (BaseStrategy.run raises on bad params)...
        with pytest.raises(ValueError):
            get_strategy("waterline_finishing").run(op)
        # ...while a direct generate_toolpath() call reports it in-band.
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(60.0), finish_levels=[0.0])
        assert "error" in tp.params
        assert tp.moves == []

    def test_a_level_with_no_cross_section_returns_an_error_toolpath(self):
        # The mesh stops at z = 4, so there is nothing to finish at z = 6.
        mesh = box_mesh((0.0, 0.0, 0.0), (10.0, 10.0, 4.0))
        op = operation(mesh=mesh, finish_levels=[6.0], _top=8.0, _bottom=0.0)
        op.extra_args.pop("profile")
        tp = get_strategy("waterline_finishing").run(op)
        assert "error" in tp.params
        assert tp.moves == []

    def test_an_empty_plan_returns_an_error_toolpath(self, monkeypatch):
        """Defensive branch: no reachable loop at all -> in-band error."""
        info = {"passes": 0, "loops": 0, "loop_points": 0, "rings": 0,
                "ring_stepover_mm": None, "cusp_height_mm": None,
                "cusp_height_target_mm": None, "sections": 0}
        monkeypatch.setattr(wlf, "plan_finishes",
                            lambda **kwargs: ([], dict(info)))
        tp = get_strategy("waterline_finishing").generate_toolpath(
            rect_stock(), make_tool(), finish_levels=[0.0],
            top_of_stock=0.0, bottom_of_stock=0.0, profile=RECT)
        assert "no reachable level set" in tp.params["error"]
        assert tp.moves == []

    def test_stock_footprint_is_the_default_geometry(self):
        op = operation()
        op.extra_args.pop("profile")
        tp = get_strategy("waterline_finishing").run(op)
        assert tp.params["profile_source"] == "stock"
        xs = [m.end.x for m in tp.moves if m.move_type is MoveType.LINEAR]
        assert max(xs) == pytest.approx(12.0 + R, abs=0.02)

    def test_profile_geometry_is_labelled(self):
        tp = get_strategy("waterline_finishing").run(operation())
        assert tp.params["profile_source"] == "profile"

    def test_mesh_geometry_is_labelled_and_cut(self):
        mesh = box_mesh((0.0, 0.0, 0.0), (16.0, 8.0, 6.0))
        op = operation(mesh=mesh, finish_levels=[3.0], _top=6.0, _bottom=0.0,
                       _stock=rect_stock(-4.0, -2.0, 20.0, 10.0, 0.0, 6.0))
        op.extra_args.pop("profile")
        tp = get_strategy("waterline_finishing").run(op)
        assert tp.params["profile_source"] == "mesh"
        xs = [m.end.x for m in tp.moves if m.move_type is MoveType.LINEAR]
        assert max(xs) == pytest.approx(16.0 + R, abs=0.02)

    def test_raster_cell_is_reported(self):
        tp = get_strategy("waterline_finishing").run(operation(cell_mm=0.1))
        assert tp.params["raster_cell_mm"] == 0.1
