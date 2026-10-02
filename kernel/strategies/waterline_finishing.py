"""
Waterline (Z-level contour) + constant-scallop finishing - feature F2
(``Fusion 360 RE/docs/p5-execution-plan.md`` section 4, row P5/4).

This module is a PORT of two planners that already ship in the umbrella repo
and are gated there by ``impl/waterline/run_parity.py`` (**gated: 35 pass /
0 FAIL**):

* ``impl/waterline/waterline.py``  - raster distance field + marching-squares
  Z-level contour extraction;
* ``impl/waterline/scallop.py``    - the S3.2 constant-scallop iso-offset
  plan (flat-surface forms only, the curved-surface ``Rw`` branch is declared
  ``[unverified]`` there and is NOT ported);
* ``impl/const_engagement/geometry.py`` - the raster primitive and its exact
  Euclidean EDT, which the reference *imports* rather than copies; this
  module re-implements it locally so the prototype has no cross-repo import.

Mechanism: how the reference's parity structures map onto the strategy
interface
--------------------------------------------------------------------------------
===============================  ==================================================
reference (read-only)            here
===============================  ==================================================
``section.section_bounds``       :func:`section_bounds` (same proof: material
                                   must sit ``2*level + 4*cell`` from the grid
                                   border, so :data:`MARGIN_CELLS` stays 4)
``section.section_from_polygon`` :func:`section_from_boundaries` /
                                   :func:`section_from_polygon` (even-odd
                                   scanline + exact point-to-segment erosion,
                                   generalised to N closed boundaries so a
                                   mesh cross-section can carry a hole)
``section.disc/rect_section``    :func:`section_rect` and the polygon path
``const_engagement.geometry.Grid``  :class:`Raster` (``data`` is a
                                   ``bytearray`` of 0/1 cells, cell centres)
``geometry.distance_to_empty``   :meth:`Raster.distance_to_empty` -
                                   Felzenszwalb & Huttenlocher 1D pass,
                                   column then row
``waterline.row_distance_to_solid`` /
``squares_distance`` / ``snap_to_squares`` /
``distance_to_material``         same names, same two-stage rule: the
                                   cell-centre EDT is snapped to the distance
                                   to the UNION OF THE CELLS' SQUARES inside
                                   ``SNAP_BAND_CELLS`` around every level
``waterline.iso_loops`` /
``_chain`` / ``_cross``          same names, same saddle rule
``waterline.waterline``          :func:`waterline` - one level set, one rule
                                   for boss and pocket alike
``waterline.offset_loops``       :func:`offset_loops` - ONE field, every ring
``waterline.collision_report``   :func:`collision_report` - independent
                                   brute-force re-measure of every point
``scallop.cusp_height`` /
``stepover_for_cusp`` /
``small_step_cusp`` / ``ring_plan``  same names, same formulas:
                                   ``H = R - sqrt(R^2 - (p/2)^2)`` and
                                   ``p = 2*sqrt(2*R*H - H^2)``
``PrismSolid.waterlines``        :func:`_finish_levels` + per-level sections
``BaseStrategy`` (this repo)     :class:`WaterlineFinishingStrategy`
===============================  ==================================================

Geometry input (the strategy interface only carries a ``BBox``), in priority
order:

1. ``profile`` - one closed XY polygon in ``extra_args``: the material
   boundary of a prismatic boss. Single boundary, so a pocket/through-hole
   cannot be described from a bare polygon (declared limitation; use 2).
2. ``mesh`` - the dict ``kernel.stl.parse_stl`` returns: the material at
   height ``z`` is the cross-section of the triangle mesh, so holes and
   multi-level shapes come out of the model itself.
3. neither - the stock footprint rectangle (the ``STL -> stock bbox ->
   strategy`` happy path).

Honest limits (declared, not hidden)
------------------------------------
* Entry is a straight vertical plunge at the first point of each loop, priced
  at ``tool_feedPlunge = tool_feedCutting / 3`` (``docs/ideal-cam-architecture.md``
  E-S6, ``par:45-46``).  No ramp, no lead-in arc.  The approach retracts to
  ``clearance_height``, moves in XY at that height, then comes down at the
  loop's start point - which is ``R`` outside the section **at the cutting
  level**.  For prismatic geometry (``profile``, stock footprint) and for any
  mesh whose cross-section does not GROW with height that descent is through
  air; for a mesh with an overhang or positive draft it can pass through
  material above the entry level.  That descent IS now checked
  (:func:`blocked_column`, review finding m6 / card ``t_3b02b4a3``): before
  the rapid from ``clearance_height`` to ``z_prev`` and before the plunge
  from ``z_prev`` to the cutting level, the XY column is verified clear over
  both spans, and a violation returns an ERROR ``ToolpathData`` naming the
  offending move instead of emitting it - retracting first is NOT a fix,
  because the obstruction sits in the very column the tool has to descend:
  every height it could retract to is above the obstruction and the descent
  still has to cross it.  Picking a different entry point on the loop could
  avoid it (for a closed contour that is only a rotation of the start
  index), and is deliberately NOT done here: the strategy refuses rather
  than silently relocating the plunge.
* The XY TRAVERSAL between two loop start points - which happens AT
  ``clearance_height``, and is also the program's very first move, from the
  machine start position - IS now checked (:func:`blocked_chord`, card
  ``t_6020987d``): before the rapid that brings the tool to a start point is
  emitted, the straight segment from where the tool WAS to that point is
  sliced against the mesh's section AT ``clearance_height``, and a chord
  that crosses material refuses the toolpath with an error ``ToolpathData``
  naming the traverse.  Same response, and the same argument, as the entry
  column above: re-routing the chord would mean either inventing a traverse
  plane ABOVE the user's own ``clearance_height`` (this module cannot bound
  the machine's Z limit, and silently overriding a user-declared safety
  plane is not a guard's job) or planning a free path around the part in XY
  (a path-planning problem, not a clearance check).  The chord is not part
  of the cut, so the fix that belongs to the caller is the actionable one:
  raise the clearance plane above what the traverse crosses - which is
  exactly what F1's export-time guard
  (``tools.export_f1_realpart.find_rapid_clearance_violations``) tells the
  same user about a clearance plane below the stock top.  Declared about
  this check:

  (a) PRISMATIC sources (``profile``, stock footprint) are NOT chord-checked
      - a fast path, and here is why: their section does not change with
      height, so a traverse at ``clearance_height`` can only meet material
      if that plane lies inside the material's z range.  That is a FLAT
      question - one plane, no geometry - and it is F1's question exactly;
      it is exact for a prism and only insufficient for a mesh, whose
      material top is not a plane, which is why the mesh needs both guards
      above.  This module does not re-run the flat test itself because
      NEITHER prismatic source carries a z extent in this module's model -
      ``_material_boundaries`` returns the profile polygon and the stock
      rectangle at EVERY height - and no rule ties ``clearance_height`` to
      ``top_of_stock``, so there is no declared material top here to
      measure against.  The residual - a clearance plane below a prismatic
      part's top, with a chord crossing it - is declared, not silently
      skipped;
  (b) the program's FIRST rapid is measured from ``(0, 0)``: the start
      ``post/ir.py`` assumes for move 0 and the one the simulation replays
      from.  The machine's real park position is not knowable here;
  (c) it is measured at ``clearance_height`` - the plane the rapid ENDS on.
      A ``G0`` carrying X, Y and Z in one block actually travels a diagonal
      from wherever the machine started, and how the controller
      interpolates a simultaneous-axis rapid is not this module's to model;
      the column guard covers the vertical half at the destination;
  (d) cost: one O(faces) slice per traverse plus one column ray per interval
      that slice produces (~10 ms / ~37 ms per ray at 41 k / 161 k faces,
      measured for the entry guard), and NOTHING when the chord leaves the
      mesh's XY box or the XY does not change at all (a loop that starts
      where the previous one ended travels nowhere).
* What the clearance checks do NOT cover, declared: LATERAL clearance: the
  checks test the tool AXIS, the point the path actually descends through.
  Material that reaches within ``R`` of the axis without containing it is
  not reported.  Up to the flute's reach at the cutting level that is a
  property of the LEVEL, not of the entry - the cut puts the flute in the
  same place anyway, so no entry could have been safe there - but material
  sitting HIGHER than the flute reaches at ``fp.z`` (still below
  ``clearance_height``) is swept by the entry descent and never touched by
  the cut: an entry-only hazard this check cannot see without the tool's
  stick-out, which this module does not know.  Declared, not patched.
* A `finish_mode` of ``scallop`` cuts rings on the FLOOR only (``scallop_z``,
  default the deepest level); it is a horizontal iso-offset, not a 3D
  constant-scallop surface finishing.
* The scallop rings walk OUTWARD from the boundary on the floor
  (``first = R``), i.e. they finish the floor around a boss; they are clipped
  by the grid extent, not by the stock outline, so a ring that reaches past
  the stock edge is still emitted (the simulation simply removes nothing
  there).
* Levels do NOT snap to mesh feature heights: ``_finish_levels`` walks a
  uniform ``stepdown`` ladder, and a mesh wall is a boundary of the section
  only at heights where material STARTS.  A wall whose base sits between two
  levels is first traced at the first level ABOVE its base, so the band
  ``[wall base, that level)`` - up to one ladder step, i.e. the ``stepdown``
  for generated levels or, when the caller supplies ``finish_levels``
  itself, the gap between its entries - can be left uncut at its foot.
  Cutting the section of the material in ``[z, z + stepdown)``
  instead would put the entry plunge through the floor below a boss (the
  overhang hazard declared above), so this is DECLARED, not patched: it is
  the standard waterline step-plane limitation, and the reference's
  ``PrismSolid`` has the same gap at heights that do not land on its ladder.
* Curved-surface scallop (``Rw``) is not implemented - the reference forbids
  shipping it without a visual check of p.5 of the source PDF, and its
  formulas are marked ``[unverified]`` (``impl/waterline/scallop.py``).
* ``stockToLeave`` (E-S4) is ported as ``stock_to_leave_mm`` and implemented
  as a **level shift**: every contour is extracted at ``R + allowance``
  instead of ``R``.  That is orientation-independent - it leaves ``allowance``
  standing on an outside boss *and* on a pocket wall.  The alternative,
  eroding the material by the allowance and cutting at ``R`` (the shape
  ``section_from_polygon``'s ``radius`` argument has), is the WRONG sign for
  an outside boss: eroding shrinks the boss, so ``R`` from the shrunken wall
  puts the tool edge ``allowance`` INSIDE the nominal wall, i.e. an overcut.
  The erosion argument is still ported and unit-tested - the reference needs
  it to rebuild a part from a tool path, ``interior(path) ⊖ R = part``
  (``impl/waterline/parity.py`` gate B) - but the strategy passes ``0``.

End-to-end path exercised by ``tests/integration/test_waterline_finishing.py``:
STL -> :meth:`WaterlineFinishingStrategy.run` -> ``ToolpathData`` ->
``simulation.SimulationEngine`` -> ``post.ir`` -> Fanuc G-code.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, Move, MoveType, ToolpathData, ToolDef, Vec3

# ---------------------------------------------------------------------------
# Frozen raster / policy constants
# ---------------------------------------------------------------------------

#: Raster resolution, mm.  Bit-identical to ``impl/waterline/parity.py:78``
#: (``CELL_MM``) so the port and the reference rasterise at the same pitch;
#: ``tests/test_waterline.py::test_cell_and_radius_are_frozen`` pins it there.
CELL_MM = 0.05

#: ``impl/waterline/section.py:27`` - the border margin is
#: ``2 * level + MARGIN_CELLS * cell`` (README S3 proof).
MARGIN_CELLS = 4.0

#: ``impl/waterline/waterline.py:53`` - half-width of the band around each
#: extracted level that is snapped to the exact solid distance.
SNAP_BAND_CELLS = 2.0

#: ``tool_feedPlunge = tool_feedCutting / 3`` - ``docs/ideal-cam-
#: architecture.md`` E-S6 (``par:45-46``, the same expression ``Fusion 360
#: RE/docs/behavior/adaptive.md`` R8 measures as ``{feed/3, ...}``).
PLUNGE_FEED_DIVISOR = 3.0

#: Default scallop target height, mm - the value reference gate A2 measures
#: (``impl/waterline/parity.py:258``).
DEFAULT_CUSP_HEIGHT_MM = 0.02

#: Hard ceiling on one section raster, in cells.  The border-margin proof
#: (``section_bounds``) forces the grid to grow as ``part + 2 * largest
#: level``, so a big stock finished at a fine ``cell`` can ask for a grid
#: that would take minutes and gigabytes: that is a configuration error and
#: it must surface as a message, not as a hang or a MemoryError.  The cost
#: model at the ceiling, measured on this module: the EDT phase alone holds
#: four O(cells) float lists (~100 bytes per cell peak) plus the field, the
#: row transform and the section mask, and one ``waterline()`` sweep of
#: 2.08 M cells takes ~11.7 s - so 4 M cells is roughly 400 MB transient and
#: ~25 s per distinct level.  The reference has the same list-per-cell
#: profile and no ceiling at all; this guard only turns the tail into an
#: actionable message.
MAX_RASTER_CELLS = 4_000_000

#: ``scallop_rings`` bound.  ``None`` derives the count from the stock
#: footprint (capped here); an explicit value is validated against the same
#: ceiling, because ``offset_loops`` runs one marching-squares sweep per
#: ring and 100 000 rings would be a hang.
MAX_SCALLOP_RINGS = 256

#: ``finish_mode`` vocabulary.
FINISH_MODES = ("waterline", "scallop", "both")

#: Float slack when comparing two z levels (same magnitude F1 uses).
Z_TOLERANCE_MM = 1e-9

#: Distances above this are "no material anywhere in range" in the field.
INF = 1e300


# ---------------------------------------------------------------------------
# Raster primitive + exact EDT (port of impl/const_engagement/geometry.py)
# ---------------------------------------------------------------------------

def raster_shape(bounds, cell: float) -> tuple[int, int]:
    """``(w, h)`` a :class:`Raster` built from ``bounds`` would have.

    Rounded the same way the reference ``Grid`` rounds, so the shape is
    identical for identical inputs; kept in one place because the
    ``MAX_RASTER_CELLS`` guard has to ask the question BEFORE the ``bytearray``
    exists.
    """
    w = max(1, int(math.ceil(round((bounds[2] - bounds[0]) / cell, 9))))
    h = max(1, int(math.ceil(round((bounds[3] - bounds[1]) / cell, 9))))
    return w, h


class Raster:
    """Uniform raster of square cells; ``data[iy * w + ix]`` is 0/1.

    ``data`` is a ``bytearray`` exactly like the reference ``Grid``, and
    distances from :meth:`distance_to_empty` come back in CELL units.
    """

    __slots__ = ("xmin", "ymin", "cell", "w", "h", "data")

    def __init__(self, xmin: float, ymin: float, xmax: float, ymax: float,
                 cell: float) -> None:
        if not math.isfinite(cell) or cell <= 0:
            raise ValueError(f"cell must be a positive finite number, got {cell!r}")
        if not (math.isfinite(xmin) and math.isfinite(ymin)
                and math.isfinite(xmax) and math.isfinite(ymax)):
            raise ValueError("raster bounds must be finite")
        if xmax < xmin or ymax < ymin:
            raise ValueError("empty bounds")
        self.xmin = float(xmin)
        self.ymin = float(ymin)
        self.cell = float(cell)
        self.w, self.h = raster_shape((xmin, ymin, xmax, ymax), cell)
        self.data = bytearray(self.w * self.h)

    # -- coordinate helpers -------------------------------------------------
    def ix(self, x: float) -> int:
        return int(math.floor((x - self.xmin) / self.cell))

    def iy(self, y: float) -> int:
        return int(math.floor((y - self.ymin) / self.cell))

    def cx(self, ix: int) -> float:
        return self.xmin + (ix + 0.5) * self.cell

    def cy(self, iy: int) -> float:
        return self.ymin + (iy + 0.5) * self.cell

    def inside(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.w and 0 <= iy < self.h

    def index(self, ix: int, iy: int) -> int:
        return iy * self.w + ix

    def count(self) -> int:
        return sum(self.data)

    def get(self, x: float, y: float) -> bool:
        """True when the cell CONTAINING ``(x, y)`` is solid."""
        ix, iy = self.ix(x), self.iy(y)
        return self.inside(ix, iy) and self.data[self.index(ix, iy)] == 1

    # -- distance field -----------------------------------------------------
    def distance_to_empty(self) -> list[float]:
        """EXACT Euclidean distance (in cell units) to the nearest empty cell.

        Felzenszwalb & Huttenlocher's squared-distance transform run column
        then row wise, then a ``min`` against the distance to the virtual
        empty cells just outside the grid border (outside == not material).
        Port of ``impl/const_engagement/geometry.py:152`` - the reference
        documents why the earlier 5-7 chamfer version was wrong (7 % error on
        diagonals let the tool centre sit inside the radius), so this stays an
        exact transform.
        """
        w, h, data = self.w, self.h, self.data
        n = w * h
        big = 1e12
        f = [0.0 if data[i] == 0 else big for i in range(n)]
        col = list(f)
        for ix in range(w):
            line = _edt1d([col[iy * w + ix] for iy in range(h)])
            for iy in range(h):
                col[iy * w + ix] = line[iy]
        out = [0.0] * n
        for iy in range(h):
            base = iy * w
            line = _edt1d(col[base:base + w])
            for ix in range(w):
                out[base + ix] = line[ix]
        d: list[float] = []
        for iy in range(h):
            border_y = min(iy + 1, h - iy)
            base = iy * w
            for ix in range(w):
                v = out[base + ix]
                v = math.sqrt(v) if v < big else big
                b = min(ix + 1, w - ix, border_y)
                d.append(b if b < v else v)
        return d


def _edt1d(f: list[float]) -> list[float]:
    """1D squared distance transform (Felzenszwalb & Huttenlocher).

    ``f`` holds 0.0 at seeds and a large finite value elsewhere; the result is
    the squared distance to the nearest seed along the line, in cell units^2.
    Port of ``impl/const_engagement/geometry.py:210``.
    """
    n = len(f)
    d = [0.0] * n
    if n == 0:
        return d
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    v[0] = 0
    z[0] = -1e300
    z[1] = 1e300
    for q in range(1, n):
        s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2 * v[k])
        while s <= z[k]:
            k -= 1
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2 * v[k])
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = 1e300
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        dx = q - v[k]
        d[q] = dx * dx + f[v[k]]
    return d


# ---------------------------------------------------------------------------
# Section construction (port of impl/waterline/section.py)
# ---------------------------------------------------------------------------

def margin(radius: float, cell: float) -> float:
    """Border margin (mm) required around the material."""
    return 2.0 * radius + MARGIN_CELLS * cell


def whole_cells(length: float, cell: float) -> float:
    """``length`` rounded UP to a whole number of cells (float-noise safe).

    Rounding outward keeps :func:`margin` while putting the lattice on the
    material boundary, so an axis-aligned mask is exact instead of half a cell
    off (``impl/waterline/section.py:35``).
    """
    return cell * int(math.ceil(round(length / cell, 9) - 1e-9))


def section_bounds(xmin: float, ymin: float, xmax: float, ymax: float,
                   radius: float, cell: float) -> tuple[float, float, float, float]:
    """Grid bounds padded by :func:`margin` around the material bbox.

    Two properties, both needed by the distance field: ``pad >= margin`` (the
    border-mask proof in :func:`distance_to_material`) and the material bbox
    landing on cell BOUNDARIES so an axis-aligned rasterisation is exact.
    """
    if radius < 0:
        raise ValueError(f"radius must be >= 0, got {radius!r}")
    pad = whole_cells(margin(radius, cell), cell)
    return (xmin - pad, ymin - pad, xmax + pad, ymax + pad)


def point_segment_distance(px: float, py: float, ax: float, ay: float,
                           bx: float, by: float) -> float:
    """Euclidean distance from point P to segment AB (2D)."""
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def inside_polygon(poly: list[tuple[float, float]], x: float, y: float) -> bool:
    """Even-odd ray cast (half-open crossing rule on the +y ray)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            t = (y - yi) / (yj - yi)
            if x < xi + t * (xj - xi):
                inside = not inside
        j = i
    return inside


def scanline(boundaries: list[list[tuple[float, float]]], y: float) -> list[float]:
    """x-crossings of the horizontal line ``y`` with every boundary, sorted.

    Pairing the sorted crossings 0-1, 2-3, ... is the even-odd rule over the
    UNION of the boundaries, so an outer wall plus a hole yields the material
    between them.
    """
    xs: list[float] = []
    for poly in boundaries:
        n = len(poly)
        if n < 3:
            continue
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    xs.sort()
    return xs


def _boundary_edges(boundaries: list[list[tuple[float, float]]]) -> list[tuple]:
    edges: list[tuple] = []
    for poly in boundaries:
        n = len(poly)
        for i in range(n):
            edges.append((poly[i][0], poly[i][1],
                          poly[(i + 1) % n][0], poly[(i + 1) % n][1]))
    return edges


def _edge_index(g: Raster, edges: list[tuple], radius: float) -> dict[int, list]:
    """cell index -> edges whose ``radius + cell``-grown bbox holds the centre.

    Absence proves the cell is more than ``radius`` from every edge, which is
    what lets the fill loop skip the distance test for deep interior cells.
    """
    cand: dict[int, list] = {}
    pad = radius + g.cell
    for e in edges:
        ax, ay, bx, by = e
        ix0 = max(0, g.ix(min(ax, bx) - pad))
        ix1 = min(g.w - 1, g.ix(max(ax, bx) + pad))
        iy0 = max(0, g.iy(min(ay, by) - pad))
        iy1 = min(g.h - 1, g.iy(max(ay, by) + pad))
        for iy in range(iy0, iy1 + 1):
            base = iy * g.w
            for ix in range(ix0, ix1 + 1):
                cand.setdefault(base + ix, []).append(e)
    return cand


def section_from_boundaries(
    boundaries: list[list[tuple[float, float]]],
    radius: float,
    cell: float,
    pad_radius: float | None = None,
) -> Raster:
    """Material mask of ``interior(boundaries)`` eroded by ``radius``.

    Exact geometry only, like ``impl.waterline.section.section_from_polygon``:
    even-odd scanline for "inside" plus a brute-force point-to-segment
    minimum for "at least ``radius`` from the boundary".  Deliberately NOT the
    distance transform :func:`distance_to_material` uses, so a port test that
    compares the two is not a self-inverse.

    ``pad_radius`` defaults to ``radius`` (the reference couples the erosion
    and the border margin through one argument).  They are separated here
    because a finishing contour has to be extracted ``level`` mm out of a
    material that was eroded by a *stock allowance*: the margin must cover the
    level, not the allowance.
    """
    if radius < 0:
        raise ValueError(f"radius must be >= 0, got {radius!r}")
    if pad_radius is None:
        pad_radius = radius
    if pad_radius < 0:
        raise ValueError(f"pad_radius must be >= 0, got {pad_radius!r}")
    clean = [b for b in boundaries if len(b) >= 3]
    if not clean:
        raise ValueError("section needs at least one closed boundary of >= 3 points")
    xs = [p[0] for poly in clean for p in poly]
    ys = [p[1] for poly in clean for p in poly]
    bounds = section_bounds(min(xs), min(ys), max(xs), max(ys),
                            pad_radius, cell)
    w, h = raster_shape(bounds, cell)
    if w * h > MAX_RASTER_CELLS:
        # The grid grows as (part + 2 * largest level) because of the border
        # proof, so a fine cell over a large span is a configuration error.
        raise ValueError(
            f"section raster would be {w} x {h} = {w * h} cells at "
            f"cell_mm = {cell} (limit {MAX_RASTER_CELLS}) for a contour "
            f"offset of {pad_radius:g} mm: raise cell_mm, lower "
            "scallop_rings, or shrink the stock")
    g = Raster(*bounds, cell)
    edges = _boundary_edges(clean)
    cand = _edge_index(g, edges, radius)
    # Cell centres in ascending order: the inside test below is then exactly
    # ``inside_polygon``'s rule.  That function toggles on every crossing
    # STRICTLY RIGHT of x (``if x < xi + t * (xj - xi)``), so a centre lies
    # in the span as ``lo <= centre < hi`` - which is what two
    # ``bisect_left`` calls select.  Index arithmetic
    # (``ix(lo) + 1 .. ix(hi)``, i.e. ``(lo, hi]``) - what the reference's
    # ``section_from_polygon`` does - is only equivalent when the polygon
    # edges land on cell boundaries; otherwise it slips one cell outside the
    # material at ``hi``, drops one cell inside at ``lo``, and disagrees with
    # ``inside_polygon`` on both edges when a crossing lands exactly on a
    # centre.  That is invisible at gate B's ``radius = R`` (the erosion test
    # rejects both slivers anyway) but wrong for ``radius = 0``, which is how
    # this port builds an un-eroded finishing section.
    centres = [g.xmin + (i + 0.5) * cell for i in range(g.w)]
    for iy in range(g.h):
        y = g.cy(iy)
        row = scanline(clean, y)
        base = iy * g.w
        for k in range(0, len(row) - 1, 2):
            lo, hi = row[k], row[k + 1]
            for ix in range(bisect_left(centres, lo),
                            bisect_left(centres, hi)):
                idx = base + ix
                found = cand.get(idx)
                if not found:
                    # Provably > radius from the whole boundary.
                    g.data[idx] = 1
                    continue
                x = g.cx(ix)
                best = radius + cell
                for e in found:
                    d = point_segment_distance(x, y, e[0], e[1], e[2], e[3])
                    if d < best:
                        best = d
                        if best < radius:
                            break
                if best >= radius:
                    g.data[idx] = 1
    return g


def section_from_polygon(poly: list[tuple[float, float]], radius: float,
                         cell: float,
                         pad_radius: float | None = None) -> Raster:
    """Single-boundary form of :func:`section_from_boundaries`."""
    return section_from_boundaries([poly], radius, cell, pad_radius)


def section_from_regions(regions, radius: float, cell: float,
                         pad_radius: float | None = None) -> Raster:
    """Material = the UNION of independent regions (each a list of loops).

    General union builder: several disjoint/nested closed regions rasterised
    into one grid, even-odd INSIDE each region and OR across regions.  The
    strategy's own paths all return ONE region - ``profile``, ``stock`` and
    (since the round-3 step-plane rule) ``mesh``, which returns the section
    just above ``z`` (falling back to the section just below when nothing
    starts there) - so they take the exact single-region branch above.
    The union branch is what a caller gets when it assembles independent
    regions by hand (see ``test_multi_region_section_rejects_an_erosion`` and
    ``test_a_step_plane_union_swallows_the_feature``).

    It is NOT the step-plane rule any more, and the history is worth keeping
    straight: round 1 fed the exact-plane even-odd set, which XOR-s a plate
    and the boss standing on it into a FRAME (a hole under the boss) and the
    contour cut through the boss; round 2 fed both limits as two regions and
    unioned them, which is the SUPERSET - the plate outline covers the boss
    wall's base band and a full block covers its pocket's wall, so the
    feature vanished from the pass.  Round 3 keeps ONE limit: the material
    that starts at ``z`` (see
    :meth:`WaterlineFinishingStrategy._material_boundaries`).

    ``radius`` erodes only a SINGLE region exactly: the erosion of a union
    needs the union's own boundary, which is not what "distance to every
    region's edges" computes (a boss standing on a plate contributes an edge
    that is interior to the union).  Multi-region therefore accepts
    ``radius = 0`` only, which is exactly what the strategy passes - it takes
    its allowance as a level shift instead of an erosion.
    """
    if len(regions) == 1:
        return section_from_boundaries(regions[0], radius, cell, pad_radius)
    if radius != 0:
        raise ValueError(
            "a union of regions supports only radius = 0 (erosion of a union "
            "needs the union's own boundary); got %r" % (radius,))
    # A degenerate loop is dropped rather than treated as fatal for the whole
    # region - the policy section_from_boundaries already uses - so one 2-point
    # loop cannot silently discard an entire region's geometry.
    clean = [[list(loop) for loop in region if len(loop) >= 3]
             for region in regions]
    clean = [region for region in clean if region]
    if not clean:
        raise ValueError("section needs at least one closed boundary of >= 3 points")
    xs = [p[0] for region in clean for loop in region for p in loop]
    ys = [p[1] for region in clean for loop in region for p in loop]
    pad = pad_radius if pad_radius is not None else 0.0
    bounds = section_bounds(min(xs), min(ys), max(xs), max(ys), pad, cell)
    w, h = raster_shape(bounds, cell)
    if w * h > MAX_RASTER_CELLS:
        raise ValueError(
            f"section raster would be {w} x {h} = {w * h} cells at "
            f"cell_mm = {cell} (limit {MAX_RASTER_CELLS}) for a contour "
            f"offset of {pad:g} mm: raise cell_mm, lower "
            "scallop_rings, or shrink the stock")
    g = Raster(*bounds, cell)
    centres = [g.xmin + (i + 0.5) * cell for i in range(g.w)]
    for iy in range(g.h):
        y = g.cy(iy)
        base = iy * g.w
        for region in clean:
            for lo, hi in _spans(region, y):
                for ix in range(bisect_left(centres, lo),
                                bisect_left(centres, hi)):
                    g.data[base + ix] = 1
    return g


def _spans(polys: list, y: float):
    """``[(lo, hi), ...]`` - the even-odd spans of one region at height y."""
    row = scanline(polys, y)
    return [(row[k], row[k + 1]) for k in range(0, len(row) - 1, 2)]


def section_rect(x0: float, y0: float, x1: float, y1: float, radius: float,
                 cell: float) -> Raster:
    """Solid axis-aligned rectangle (a boss / post cross-section).

    ``radius`` is the border-margin basis only - no erosion - which is what
    ``impl.waterline.section.rect_section`` does.
    """
    rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return section_from_boundaries([rect], 0.0, cell, radius)


# ---------------------------------------------------------------------------
# Distance field (port of impl/waterline/waterline.py)
# ---------------------------------------------------------------------------

def row_distance_to_solid(grid: Raster) -> list[int]:
    """For every cell: distance in CELLS to the nearest solid cell in the
    SAME ROW (0 when this cell is solid).

    Two linear passes per row; this is the x-half of an exact distance to the
    union of the solid cells' squares.
    """
    w, h, data = grid.w, grid.h, grid.data
    out = [0] * (w * h)
    big = 1 << 30
    for iy in range(h):
        base = iy * w
        d = big
        for ix in range(w):
            if data[base + ix]:
                d = 0
            elif d < big:
                d += 1
            out[base + ix] = d
        d = big
        for ix in range(w - 1, -1, -1):
            if data[base + ix]:
                d = 0
            elif d < big:
                d += 1
            if d < out[base + ix]:
                out[base + ix] = d
    return out


def squares_distance(grid: Raster, rowdist: list[int], ix: int, iy: int,
                     upper: float) -> float:
    """EXACT distance (mm) from the centre of cell ``(ix, iy)`` to the union
    of the solid cells' squares.

    See ``impl/waterline/waterline.py:88`` for the derivation: within a row
    the squares differ only in x, so the row-wise minimum of
    ``max(|dx| - cell/2, 0)^2`` is attained at that row's nearest solid cell.
    ``upper`` is both an upper bound on the answer and the reach of the row
    scan, so skipped rows cannot beat it.
    """
    half = 0.5 * grid.cell
    y = grid.cy(iy)
    w = grid.w
    reach = int((upper + half) / grid.cell) + 2
    best2 = upper * upper
    for jy in range(max(0, iy - reach), min(grid.h, iy + reach + 1)):
        dy = y - grid.cy(jy)
        fy = dy - half if dy > half else (dy + half if dy < -half else 0.0)
        fy2 = fy * fy
        if fy2 >= best2:
            continue
        dx = rowdist[jy * w + ix] * grid.cell
        fx = dx - half if dx > half else 0.0
        v = fx * fx + fy2
        if v < best2:
            best2 = v
    return math.sqrt(best2)


def snap_to_squares(field: list[float], grid: Raster, levels,
                    rowdist: list[int] | None = None) -> int:
    """Replace the cell-centre estimate by the exact solid distance in the
    band around every level.  Returns the number of cells corrected.

    Snapping only the band is what keeps this cheap and exact at once: by
    ``SNAP_BAND_CELLS``' argument a cell outside ``level +/- band`` can never
    take part in a marching-squares crossing of that level.

    Implementation note (the ONE place this port diverges structurally from
    ``impl/waterline/waterline.py:142``): the reference sweeps the whole
    field once per level, this sweeps it ONCE with a ``bisect`` per cell to
    find the band, if any, that contains the value.  For sorted levels -
    which is what :func:`distance_to_material` passes - both visit exactly
    the same cells and write the same ``squares_distance(..., level + band)``
    value (asserted by ``test_snap_matches_a_naive_per_level_sweep``); the
    difference is ``O(cells)`` instead of ``O(cells * levels)``, which is
    what makes a many-ring constant-scallop plan affordable.
    """
    if rowdist is None:
        rowdist = row_distance_to_solid(grid)
    w = grid.w
    band = SNAP_BAND_CELLS * grid.cell
    ordered = sorted(set(float(v) for v in levels))
    if not ordered:
        return 0
    lows = [v - band for v in ordered]
    highs = [v + band for v in ordered]
    n = 0
    for i, v in enumerate(field):
        stop = bisect_right(lows, v)     # first low strictly above v
        start = bisect_left(highs, v)    # first high at or above v
        for j in range(start, stop):
            field[i] = squares_distance(grid, rowdist, i % w, i // w, highs[j])
            n += 1
    return n


def distance_to_material(grid: Raster, radius: float,
                         levels=None) -> list[float]:
    """Distance (mm) from every cell centre to the rasterised solid, snapped
    exact around ``levels`` (default: ``[radius]``).

    Stage 1 is the cell-centre EDT on the INVERTED mask, corrected for the
    border clamp: a cell closer to the border than ``radius + cell`` becomes
    +inf, which is sound because :func:`section_bounds` guarantees the
    material sits ``2*radius + 4*cell`` from the border.  Stage 2 is
    :func:`snap_to_squares`: the EDT measures to cell CENTRES while the solid
    is the union of the cells' SQUARES, which reach ``cell/2`` further out -
    left uncorrected every emitted point sits ``0.025 .. 0.0354 mm`` inside
    the material at CELL = 0.05 (that gap was 100 % of the reference's
    collision reading before its card t_cbdaf03f).
    """
    w, h, cell = grid.w, grid.h, grid.cell
    inv = Raster(grid.xmin, grid.ymin, grid.xmin + w * cell,
                 grid.ymin + h * cell, cell)
    src, dst = grid.data, inv.data
    for i in range(len(dst)):
        dst[i] = 0 if src[i] else 1
    dt = inv.distance_to_empty()
    cut = radius + cell
    out = [0.0] * len(dt)
    for iy in range(h):
        by = min(iy + 1, h - iy)
        base = iy * w
        for ix in range(w):
            b = min(ix + 1, w - ix, by) * cell
            v = dt[base + ix]
            out[base + ix] = INF if (b <= cut and v * cell > 0.0) else v * cell
    lvls = (radius,) if levels is None else tuple(
        sorted(set(float(v) for v in levels)))
    snap_to_squares(out, grid, lvls)
    return out


def clearance_to_solid(grid: Raster, x: float, y: float, search: float) -> float:
    """Exact distance (mm) from ``(x, y)`` to the rasterised solid, or
    ``search`` when the true minimum is farther away.

    Brute force over a window of radius ``search`` - deliberately a different
    algorithm from the row transform behind :func:`distance_to_material`, so
    the two can check each other.
    """
    cell = grid.cell
    k = int(math.ceil(search / cell)) + 1
    ix, iy = grid.ix(x), grid.iy(y)
    best = search
    w = grid.w
    for jy in range(iy - k, iy + k + 1):
        if jy < 0 or jy >= grid.h:
            continue
        base = jy * w
        cy0 = grid.ymin + jy * cell
        dy = max(cy0 - y, 0.0, y - (cy0 + cell))
        if dy >= best:
            continue
        for jx in range(ix - k, ix + k + 1):
            if jx < 0 or jx >= w or grid.data[base + jx] == 0:
                continue
            cx0 = grid.xmin + jx * cell
            dx = max(cx0 - x, 0.0, x - (cx0 + cell))
            if dx >= best:
                continue
            d = math.hypot(dx, dy)
            if d < best:
                best = d
                if best == 0.0:
                    return 0.0
    return best


def collision_report(grid: Raster, radius: float, loops) -> dict:
    """Independent collision check of every emitted point.

    ``min_clearance_mm`` is the smallest exact tool-centre-to-solid distance
    over all loop points; below ``radius`` the cutter reaches into the solid.
    """
    search = radius + 2.0 * grid.cell
    worst = search
    n = 0
    for loop in loops:
        for (x, y) in loop:
            d = clearance_to_solid(grid, x, y, search)
            n += 1
            if d < worst:
                worst = d
    return {"points": n, "min_clearance_mm": worst,
            "max_penetration_mm": max(0.0, radius - worst),
            "clearance_margin_mm": worst - radius}


# ---------------------------------------------------------------------------
# Marching squares (port of impl/waterline/waterline.py)
# ---------------------------------------------------------------------------

def _cross(p0, p1, v0, v1, level: float, horiz: bool):
    """Point where the edge ``p0 -> p1`` crosses ``level`` (or ``None``)."""
    if (v0 < level) == (v1 < level):
        return None
    t = (level - v0) / (v1 - v0)
    if horiz:
        return (p0[0] + t * (p1[0] - p0[0]), p0[1])
    return (p0[0], p0[1] + t * (p1[1] - p0[1]))


def _chain(segs):
    """Link segments into polylines through shared endpoints."""
    adj: dict = defaultdict(list)
    for i, (a, b) in enumerate(segs):
        adj[a].append(i)
        adj[b].append(i)
    used = [False] * len(segs)
    loops = []
    for i in range(len(segs)):
        if used[i]:
            continue
        a, b = segs[i]
        used[i] = True
        pts = [a, b]
        while True:
            nxt = None
            for j in adj[pts[-1]]:
                if not used[j]:
                    nxt = j
                    break
            if nxt is None:
                break
            used[nxt] = True
            s, e = segs[nxt]
            pts.append(e if s == pts[-1] else s)
        loops.append(pts)
    return loops


def iso_loops(field: list[float], grid: Raster, level: float) -> list:
    """Marching-squares extraction of ``field == level`` as closed loops.

    Crossing points are pre-computed once per grid edge and shared by the two
    cells on either side, so chained endpoints match bit-for-bit.  Saddle
    cells (all four corners straddling) are resolved by the cell-centre
    average of the four corner values.
    """
    w, h, cell = grid.w, grid.h, grid.cell
    ox, oy = grid.xmin + 0.5 * cell, grid.ymin + 0.5 * cell

    def hx(ix, iy, v0, v1):
        return _cross((ox + ix * cell, oy + iy * cell),
                      (ox + (ix + 1) * cell, oy + iy * cell),
                      v0, v1, level, True)

    def vx(ix, iy, v0, v1):
        return _cross((ox + ix * cell, oy + iy * cell),
                      (ox + ix * cell, oy + (iy + 1) * cell),
                      v0, v1, level, False)

    h_edge: list = [None] * (w * h)
    v_edge: list = [None] * (w * h)
    for iy in range(h):
        base = iy * w
        for ix in range(w - 1):
            h_edge[base + ix] = hx(ix, iy, field[base + ix], field[base + ix + 1])
    for iy in range(h - 1):
        base = iy * w
        nxt = base + w
        for ix in range(w):
            v_edge[base + ix] = vx(ix, iy, field[base + ix], field[nxt + ix])

    segs = []
    for iy in range(h - 1):
        b0, b1 = iy * w, (iy + 1) * w
        for ix in range(w - 1):
            v00, v10 = field[b0 + ix], field[b0 + ix + 1]
            v01, v11 = field[b1 + ix], field[b1 + ix + 1]
            e0, e1 = h_edge[b0 + ix], v_edge[b0 + ix + 1]
            e2, e3 = h_edge[b1 + ix], v_edge[b0 + ix]
            n = sum(1 for e in (e0, e1, e2, e3) if e is not None)
            if n == 2:
                pts = [e for e in (e0, e1, e2, e3) if e is not None]
                segs.append((pts[0], pts[1]))
            elif n == 4:
                low00 = v00 < level
                centre = 0.25 * (v00 + v10 + v01 + v11)
                if (centre < level) == low00:
                    segs.append((e0, e1))
                    segs.append((e2, e3))
                else:
                    segs.append((e0, e3))
                    segs.append((e1, e2))
    return [p for p in _chain(segs) if len(p) >= 4]


def waterline(grid: Raster, radius: float) -> list:
    """Closed tool-centre loops lying exactly ``radius`` from the solid.

    One rule covers both cases: the outside of a boss and the inside of a
    pocket are both "void cells whose distance to solid == radius".
    """
    return iso_loops(distance_to_material(grid, radius), grid, radius)


def offset_loops(grid: Raster, distances) -> list[tuple[float, list]]:
    """``[(distance, loops)]`` for each distance, from ONE distance field.

    The section must have been built with a margin for ``max(distances)`` -
    that is what makes the border correction in :func:`distance_to_material`
    sound for every level extracted here.
    """
    levels = sorted(set(float(d) for d in distances))
    if not levels:
        raise ValueError("offset_loops needs at least one distance")
    field = distance_to_material(grid, levels[-1], levels=levels)
    return [(d, iso_loops(field, grid, d)) for d in levels]


# ---------------------------------------------------------------------------
# Constant-scallop maths (port of impl/waterline/scallop.py, S3.2 formulas)
# ---------------------------------------------------------------------------

def cusp_height(stepover: float, radius: float) -> float:
    """Scallop height ``H`` left by two ball passes ``stepover`` apart:
    ``H = R - sqrt(R^2 - (p/2)^2)`` (Soori et al. 2024 eq. (6))."""
    if stepover < 0.0:
        raise ValueError("stepover must be >= 0")
    if stepover > 2.0 * radius:
        raise ValueError("stepover > 2R: the sqrt domain is exhausted "
                         "(algorithm_impls L606)")
    return radius - math.sqrt(radius * radius - (0.5 * stepover) ** 2)


def stepover_for_cusp(height: float, radius: float) -> float:
    """Stepover ``p`` that leaves a scallop of exactly ``height``:
    ``p = 2 * sqrt(2*R*H - H^2)`` (algorithm_impls L605)."""
    if not 0.0 <= height <= radius:
        raise ValueError("cusp height must lie in [0, R] (algorithm_impls L610)")
    return 2.0 * math.sqrt(2.0 * radius * height - height * height)


def small_step_cusp(stepover: float, radius: float) -> float:
    """First-order approximation ``H ~ p^2 / (8R)`` (the reference's own
    Taylor expansion, not a quoted source)."""
    return stepover * stepover / (8.0 * radius)


def ring_plan(radius: float, height: float, first: float, count: int):
    """Iso-offset plan ``(stepover, [first, first + p, ...])``.

    ``first`` is the offset of the first ring from the solid (>= radius);
    every following ring sits one ``p`` farther out so the ridge on the flat
    between adjacent rings equals ``height`` exactly.
    """
    p = stepover_for_cusp(height, radius)
    if first < radius:
        raise ValueError("first ring must be at least the tool radius")
    if count < 1:
        raise ValueError("count must be >= 1")
    return p, [first + k * p for k in range(count)]


# ---------------------------------------------------------------------------
# Mesh cross-section: STL -> material mask at one height
# ---------------------------------------------------------------------------

def _plane_point(pa, pb, za: float, zb: float, ia: int, ib: int,
                 z: float) -> tuple[float, float]:
    """Point where edge ``pa -> pb`` crosses the plane ``z``.

    The edge is canonicalised by vertex INDEX first, so the two triangles that
    share it evaluate the identical expression and the chained endpoints are
    bit-for-bit equal (without that, ``A + t*(B - A)`` and
    ``B + (1 - t)*(A - B)`` can differ in the last ULP and the loop breaks).
    """
    if ia > ib:
        pa, pb, za, zb, ia, ib = pb, pa, zb, za, ib, ia
    t = (z - za) / (zb - za)
    return (pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]))


def mesh_section_loops(mesh: dict, z: float) -> list[list[tuple[float, float]]]:
    """Closed XY loops where the triangle mesh meets the horizontal plane ``z``.

    Rules, and why:

    * a face lying entirely IN the plane is skipped - its boundary is carried
      by its non-coplanar neighbours, and emitting it too would duplicate
      every edge and make the chain branch (a box sampled at its own top
      face still yields its full rectangle, from the wall faces' in-plane
      top edges);
    * an edge lying in the plane is emitted whole, an edge with one endpoint
      on the plane yields that endpoint, a straddling edge is interpolated
      through :func:`_plane_point`;
    * a triangle that contributes fewer than two distinct points contributes
      no segment (it only touches the plane at a point).

    ``mesh`` is what ``kernel.stl.parse_stl`` returns: ``vertices`` (N, 3) and
    ``faces`` (M, 3) of vertex indices.
    """
    verts = mesh.get("vertices")
    faces = mesh.get("faces")
    if verts is None or faces is None:
        raise ValueError("mesh must carry 'vertices' and 'faces'")
    segs: list[tuple] = []
    for tri in faces:
        idx = (int(tri[0]), int(tri[1]), int(tri[2]))
        pts = [verts[i] for i in idx]
        zs = [float(p[2]) for p in pts]
        if zs[0] == z and zs[1] == z and zs[2] == z:
            continue  # coplanar face
        found: list[tuple[float, float]] = []
        for k in range(3):
            a, b = k, (k + 1) % 3
            ia, ib = idx[a], idx[b]
            pa, pb = pts[a], pts[b]
            za, zb = zs[a], zs[b]
            if za == z and zb == z:
                found.append((float(pa[0]), float(pa[1])))
                found.append((float(pb[0]), float(pb[1])))
            elif za == z:
                found.append((float(pa[0]), float(pa[1])))
            elif zb == z:
                found.append((float(pb[0]), float(pb[1])))
            elif (za < z) != (zb < z):
                found.append(_plane_point(pa, pb, za, zb, ia, ib, z))
        uniq: list[tuple[float, float]] = []
        for p in found:
            if p not in uniq:
                uniq.append(p)
        if len(uniq) < 2:
            continue
        if len(uniq) == 2:
            segs.append((uniq[0], uniq[1]))
            continue
        # Three collinear points: keep the pair that spans the intersection.
        best = (uniq[0], uniq[1])
        best_d = -1.0
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                d = math.hypot(uniq[i][0] - uniq[j][0], uniq[i][1] - uniq[j][1])
                if d > best_d:
                    best_d, best = d, (uniq[i], uniq[j])
        segs.append(best)
    return [p for p in _chain(segs) if len(p) >= 4]


# ---------------------------------------------------------------------------
# Rapid / plunge clearance - the 3D column check (round-1 review finding m6)
# ---------------------------------------------------------------------------

#: XY nudge, mm, applied to a clearance query before it is tested against the
#: triangle soup.  A mesh is a TRIANGLE SOUP: one flat face is two triangles
#: sharing a diagonal, and a query that lands exactly on that shared edge is
#: contained in both, so the vertical line would pierce the face TWICE and the
#: even-odd parity would report solid as air (or the reverse) - a clearance
#: check that flips on a tie is worse than none.  ``1e-7`` mm sits SIX orders
#: above float64 round-off at part scale (a few ulps at 1000 mm is ~1e-13 mm)
#: and about six orders below the smallest thing this module can resolve
#: (``CELL_MM = 0.05``, i.e. 5e5 times the nudge), so it moves a query off an
#: edge but can never move it across a real feature.
CLEARANCE_NUDGE_MM = 1e-7

#: Y-component factor of the nudge.  The nudge direction is
#: ``(d, d * (sqrt(5)-1)/2)`` - an IRRATIONAL slope - so no mesh edge (every
#: edge of a float64 mesh has a rational-ish slope, and an axis-aligned or 45
#: degree edge is the common case) can be parallel to it: a query sitting
#: exactly on an edge always leaves it.  A diagonal nudge ``(d, d)`` would
#: stay ON a 45 degree edge and miss the point of the nudge entirely.
NUDGE_SLOPE = (math.sqrt(5.0) - 1.0) / 2.0


def mesh_xy_bounds(mesh: dict) -> tuple[float, float, float, float] | None:
    """``(min_x, min_y, max_x, max_y)`` over the mesh's vertices, or ``None``.

    A triangle's XY projection lies inside the XY box of its own vertices, so
    the XY extent of a whole mesh IS the extent of its vertices: a query
    outside this box is outside every face's projection, the column is
    provably empty, and the O(faces) scan can be skipped.  That is the
    common case for a finishing contour, which sits ``R`` outside the part
    and is often outside its bounding box altogether (every prismatic fixture
    in the tests is).  Computed once per ``generate_toolpath``.
    """
    verts = mesh.get("vertices")
    if verts is None or len(verts) == 0:
        return None
    lo_x = lo_y = math.inf
    hi_x = hi_y = -math.inf
    for v in verts:
        vx = float(v[0])
        vy = float(v[1])
        if vx < lo_x:
            lo_x = vx
        if vx > hi_x:
            hi_x = vx
        if vy < lo_y:
            lo_y = vy
        if vy > hi_y:
            hi_y = vy
    return (lo_x, lo_y, hi_x, hi_y)


def column_crossings(mesh: dict, x: float, y: float) -> list[float]:
    """Every height at which the vertical line through ``(x, y)`` pierces ``mesh``.

    Sorted ascending, one entry per pierce, counted with the even-odd rule the
    rest of this module uses for cross-sections, so a point at height ``z`` is
    INSIDE the solid exactly when the number of crossings STRICTLY above ``z``
    is odd (the line is outside above the topmost crossing).

    Why a ray cast and not a stack of cross-sections: the membership of one
    fixed ``(x, y)`` can change at any height where a triangle's plane passes
    through the line - for a sloped face that is NOT a mesh vertex height, so
    sampling sections at vertex heights can miss an obstruction entirely.

    Rules, and why:

    * the query is nudged by :data:`CLEARANCE_NUDGE_MM` along
      :data:`NUDGE_SLOPE` first, so a query that lands exactly on a face's
      shared diagonal (or on a wall) is attributed to exactly one triangle
      and the parity cannot flip on a tie;
    * a triangle whose XY projection does not contain the query is skipped
      (bounding-box reject first, so the scan stays O(faces) with a cheap
      constant);
    * a triangle degenerate in XY - a vertical wall, or a zero-area sliver -
      projects to a LINE, not an area, and cannot be pierced transversally;
      it is skipped.  Its boundary is carried by the horizontal faces it
      meets, exactly as :func:`mesh_section_loops` skips a face lying in the
      plane and takes the boundary from its neighbours;
    * two boxes stacked face to face contribute two coincident crossings at
      the step plane and the pair CANCELS - the union has no surface there,
      so one continuous solid reads as one band and the parity below stays
      correct (``test_two_boxes_touching_face_to_face_keep_one_surface``);
    * like every other geometric rule in this module it assumes a CLOSED
      mesh, and here also that the shells do not INTERPENETRATE: two closed
      shells that overlap XOR through one another under this even-odd rule,
      so a union solid can read as air where they meet.  That is the same
      rule ``mesh_section_loops`` rasterises sections with, and
      ``kernel.stl.parse_stl`` returns one shell per solid - an
      interpenetrating multi-body STL is out of contract here exactly as it
      is for the section machinery it serves.

    F1's ``tools.export_f1_realpart.find_rapid_clearance_violations`` is the
    flat cousin of this function: it answers "does an XY-traversing rapid sit
    below ONE horizontal plane (the stock top)?" over posted G-code text.  The
    F2 entry hazard is a Z-descent at a fixed XY through geometry that GROWS
    with height, so a flat threshold cannot see it - this is its 3D
    counterpart, run on the mesh BEFORE the move is emitted.

    Cost, measured here on a synthetic heightfield: ~10 ms per ray at 41 k
    faces and ~37 ms at 161 k faces (pure Python, bounding-box rejected per
    face).  One ray per loop, and none at all for a start point outside
    :func:`mesh_xy_bounds`; the raster sweep the plan already pays per level
    (up to ~11.7 s at :data:`MAX_RASTER_CELLS`, see that constant) is the
    term that dominates a fine-cell job.
    """
    verts = mesh.get("vertices")
    faces = mesh.get("faces")
    if verts is None or faces is None:
        raise ValueError("mesh must carry 'vertices' and 'faces'")
    px = float(x) + CLEARANCE_NUDGE_MM
    py = float(y) + CLEARANCE_NUDGE_MM * NUDGE_SLOPE
    hits: list[float] = []
    for tri in faces:
        a = verts[int(tri[0])]
        b = verts[int(tri[1])]
        c = verts[int(tri[2])]
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
        if (min(ax, bx, cx) > px or max(ax, bx, cx) < px
                or min(ay, by, cy) > py or max(ay, by, cy) < py):
            continue
        e1x, e1y = bx - ax, by - ay
        e2x, e2y = cx - ax, cy - ay
        denom = e1x * e2y - e2x * e1y
        if denom == 0.0:
            continue                      # degenerate in XY (vertical wall)
        dx, dy = px - ax, py - ay
        u = (dx * e2y - e2x * dy) / denom
        v = (e1x * dy - dx * e1y) / denom
        if u < 0.0 or v < 0.0 or u + v > 1.0:
            continue
        if az == bz == cz:
            # Horizontal face: the pierce height is that exact plane.  The
            # barycentric blend below is mathematically the same number but
            # can come back 4.0000000000000007 for a face at z = 4 - which
            # would stand a hair ABOVE a band that starts at 4 and invent a
            # picometre of "material" out of round-off (seen on the plate +
            # boss fixture, whose plate top and boss bottom both sit at z=4).
            hits.append(az)
        else:
            hits.append((1.0 - u - v) * az + u * bz + v * cz)
    hits.sort()
    return hits


def blocked_span(crossings: list[float], z_from: float, z_to: float,
                 ) -> list[tuple[float, float]]:
    """Solid sub-spans of a vertical move from ``z_from`` to ``z_to``.

    ``crossings`` is the sorted pierce list :func:`column_crossings` returned
    for that column.  Returns ``[(z_lo, z_hi), ...]``, lowest first: touching
    bands merge into one run (two boxes stacked face to face leave one
    continuous solid), disjoint runs stay separate so a message can show
    exactly which heights are solid, and an empty list means the column is
    clear over the whole move.  The span is order-independent (a rapid from
    ``clearance_height`` to ``z_prev`` and the plunge below it travel the
    same set of points), and a zero-length span is trivially clear.
    """
    lo, hi = (z_from, z_to) if z_from <= z_to else (z_to, z_from)
    if hi - lo <= 0.0:
        return []
    # Crossings at or below `lo` cannot change the parity inside the span;
    # neither can one standing within Z_TOLERANCE_MM of `lo`.  That slack only
    # ever decides the answer for heights in (lo, lo + slack) - a band 1e-9 mm
    # thick - because a crossing at `c` contributes to the count of a height
    # `z` only while ``z < c``, so nothing above ``lo + slack`` is affected.
    # It is needed because a face that ENDS exactly at `lo` can come back a
    # few ulps ABOVE it, and a clearance check that reports round-off as
    # material refuses the part (the plate + boss fixture: plate top and boss
    # bottom both at z = 4, band starting at z = 4).
    crossings = [z for z in crossings if z > lo + Z_TOLERANCE_MM]
    edges = [lo] + [z for z in crossings if lo < z < hi] + [hi]
    solid: list[tuple[float, float]] = []
    for a, b in zip(edges, edges[1:]):
        if b <= a:
            # A duplicate crossing - two boxes stacked face to face pierce
            # the column twice AT the step plane - leaves a zero-height
            # interval, and reporting it would print "Z4..Z4".  Skipping it
            # cannot hide material: the parity of the intervals around it is
            # counted from `crossings` directly, and the two solid runs it
            # separates are merged below.
            continue
        mid = 0.5 * (a + b)
        if sum(1 for z in crossings if z > mid) % 2:
            if solid and a <= solid[-1][1]:
                solid[-1] = (solid[-1][0], b)   # touching runs: one solid
            else:
                solid.append((a, b))
    return solid


def blocked_column(mesh: dict, x: float, y: float,
                   z_from: float, z_to: float) -> list[tuple[float, float]]:
    """Solid sub-spans of a vertical move at ``(x, y)``: :func:`blocked_span`.

    One ray cast of :func:`column_crossings` plus one span slice.  Callers
    that measure two spans of the SAME column (the entry does) should cast
    once and call :func:`blocked_span` twice instead.
    """
    return blocked_span(column_crossings(mesh, x, y), z_from, z_to)


def point_in_mesh(mesh: dict, x: float, y: float, z: float) -> bool:
    """Is the point ``(x, y, z)`` inside ``mesh``?

    Casts :func:`column_crossings` and counts the pierces STRICTLY above
    ``z`` - the even-odd rule :func:`column_crossings` documents - with the
    same :data:`Z_TOLERANCE_MM` slack :func:`blocked_span` gives a span's
    lower edge: a face that ENDS at ``z`` can come back a few ulps above it,
    and a clearance check that reports round-off as material refuses a clean
    part (the plate + boss fixture is the case that produced the slack).
    The query inherits the nudge :func:`column_crossings` applies, so a point
    on a shared face diagonal is attributed to exactly one triangle.
    """
    return sum(1 for c in column_crossings(mesh, x, y)
               if c > z + Z_TOLERANCE_MM) % 2 == 1


def chord_crossings(mesh: dict, x0: float, y0: float, x1: float, y1: float,
                    z: float,
                    bounds: tuple[float, float, float, float] | None = None,
                    ) -> list[float]:
    """Every distance along the chord ``(x0, y0) -> (x1, y1)`` at the height
    ``z`` where that horizontal chord pierces ``mesh``'s cross-section.

    The horizontal dual of :func:`column_crossings`: casting a VERTICAL line
    through the triangle soup returns pierce heights, casting a HORIZONTAL
    chord through it returns pierce distances in mm along the chord.  Each
    triangle is cut by the plane ``z`` into a segment, and that segment is
    intersected with the chord - a triangle/plane then segment/segment test.

    Why a slice of the soup and not ``mesh_section_loops(mesh, z)``: the
    section machinery is a rasterised, chained, level-aware answer tuned for
    cutting, and this question is a pure "where does the boundary cross this
    line" one - it needs the raw pierces, not a contour.

    Rules, and why:

    * a triangle that only touches the plane (all three vertices on one
      side, or a single vertex exactly on it) contributes no segment and is
      skipped;
    * a triangle lying IN the plane - a horizontal face - would intersect it
      in an AREA, not a segment: it cannot be pierced transversally, so it is
      skipped exactly as :func:`column_crossings` skips a triangle degenerate
      in XY.  Its boundary is carried by the faces meeting it, so the
      section's outline still comes out complete;
    * a section segment COLLINEAR with the chord - the chord running along a
      wall - reports both ends of the overlap, so the intervals either side
      of it are still separated.  What the overlap ITSELF reads as is then
      decided by :func:`point_in_mesh` at the interval midpoint, i.e. by
      which side of the wall the column query's nudge lands on: an
      asymmetry worth naming, because it means "riding a wall" has no one
      answer here (measured: on an axis-aligned box the chord along
      ``y = 0`` reads SOLID and the same chord along ``x = 4`` reads
      clear).  It is measure-zero, the axis is on the surface either way,
      and LATERAL clearance is declared out of contract below - but it is
      not a guarantee, so it is documented rather than smoothed over;
    * unlike the column query this one is deliberately NOT nudged: the pierce
      list only SPLITS the chord, it never decides membership (see
      :func:`blocked_chord`).  A chord that passes exactly through the point
      where two triangles of one flat face meet therefore reports that pierce
      TWICE, and a duplicate merely leaves a zero-length interval, which
      :func:`blocked_chord` skips - the even-odd answer can never flip on a
      tie.  The column query has no such luck: there the pierce list IS the
      answer, which is why it needs :data:`CLEARANCE_NUDGE_MM`;
    * a whole chord outside :func:`mesh_xy_bounds` cannot be pierced at all
      and returns immediately (the same argument the column fast path uses),
      and every triangle is bounding-box rejected first, so the scan stays
      O(faces) with a cheap constant;
    * like every other geometric rule in this module it assumes a CLOSED,
      non-overlapping mesh: interpenetrating shells XOR through one another
      under the even-odd rule (declared out of contract everywhere here).

    ``bounds`` is the caller's precomputed :func:`mesh_xy_bounds` result;
    ``None`` means "not computed yet" and is computed here.
    """
    verts = mesh.get("vertices")
    faces = mesh.get("faces")
    if verts is None or faces is None:
        raise ValueError("mesh must carry 'vertices' and 'faces'")
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length == 0.0:
        return []
    if bounds is None:
        bounds = mesh_xy_bounds(mesh)
    if bounds is None:
        return []                       # no vertices: nothing to pierce
    lo_x, lo_y, hi_x, hi_y = bounds
    c_lo_x, c_hi_x = (x0, x1) if x0 <= x1 else (x1, x0)
    c_lo_y, c_hi_y = (y0, y1) if y0 <= y1 else (y1, y0)
    if (c_hi_x < lo_x or c_lo_x > hi_x
            or c_hi_y < lo_y or c_lo_y > hi_y):
        return []                       # the chord never enters the box
    hits: list[float] = []
    for tri in faces:
        a = verts[int(tri[0])]
        b = verts[int(tri[1])]
        c = verts[int(tri[2])]
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
        if (min(ax, bx, cx) > c_hi_x or max(ax, bx, cx) < c_lo_x
                or min(ay, by, cy) > c_hi_y or max(ay, by, cy) < c_lo_y):
            continue
        z_lo, z_hi = min(az, bz, cz), max(az, bz, cz)
        if z_lo > z or z_hi < z:
            continue                    # the plane misses this triangle
        if z_lo == z_hi:
            continue                    # in the plane: an area, not a pierce
        # Triangle ∩ plane z -> the segment (p, q): one point per crossing of
        # an edge, plus a vertex sitting exactly on the plane.  Exactly two
        # points come out of every reachable sign pattern (0/0/+ gives both
        # on-plane vertices, 0/+/- gives the vertex and the crossing, ...
        da, db, dc = az - z, bz - z, cz - z
        pts: list[tuple[float, float]] = []
        for d0, d1, px, py, qx, qy in (
                (da, db, ax, ay, bx, by),
                (db, dc, bx, by, cx, cy),
                (dc, da, cx, cy, ax, ay)):
            if d0 == 0.0:
                pts.append((px, py))
            if d0 * d1 < 0.0:
                t = d0 / (d0 - d1)
                pts.append((px + t * (qx - px), py + t * (qy - py)))
        if len(pts) < 2:
            continue                    # a vertex-only touch: no segment
        p, q = pts[0], pts[-1]
        ex, ey = q[0] - p[0], q[1] - p[1]
        wx, wy = p[0] - x0, p[1] - y0
        den = dx * ey - dy * ex
        if den != 0.0:
            t = (wx * ey - wy * ex) / den      # along the chord,  0..1
            u = (wx * dy - wy * dx) / den      # along the section segment
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                hits.append(t * length)
        elif wx * dy - wy * dx == 0.0:
            # Parallel AND on the same line: the chord runs along the
            # boundary.  Both ends of the overlap are boundary points, so
            # they split the chord; the membership of what lies between them
            # is still decided per interval by point_in_mesh.
            dot = dx * dx + dy * dy
            t0 = (wx * dx + wy * dy) / dot
            t1 = ((p[0] + ex - x0) * dx + (p[1] + ey - y0) * dy) / dot
            lo, hi = (t0, t1) if t0 <= t1 else (t1, t0)
            lo, hi = max(lo, 0.0), min(hi, 1.0)
            if hi > lo:
                hits.append(lo * length)
                hits.append(hi * length)
    hits.sort()
    return hits


def blocked_chord(mesh: dict, x0: float, y0: float, x1: float, y1: float,
                  z: float,
                  bounds: tuple[float, float, float, float] | None = None,
                  ) -> list[tuple[float, float]]:
    """Solid sub-spans of the horizontal segment ``(x0, y0) -> (x1, y1)``
    measured at the height ``z``.

    Returns ``[(d_lo, d_hi), ...]`` - distances in MILLIMETRES along the
    chord, lowest first - and an empty list means the segment crosses no
    material at that height.  Touching spans merge into one run, disjoint
    spans stay separate (a chord across both legs of a C crosses material
    twice with air between), and a zero-length chord is trivially clear.

    The pierce list from :func:`chord_crossings` only decides WHERE the
    answer can change; membership of each interval is decided by
    :func:`point_in_mesh` at its midpoint - the nudged, epsilon'd, heavily
    tested column cast.  That split is what makes this primitive safe on the
    ties the column query needs a nudge for: a pierce reported twice (a chord
    through the shared edge of one flat face) leaves a zero-length interval,
    which is skipped, and a pierce missed entirely would only matter if the
    midpoint of the interval it should have split disagreed with the answer
    on the other side - the column cast is the independent witness either
    way.

    ``bounds`` is the caller's precomputed :func:`mesh_xy_bounds`; ``None``
    is computed here.  Two things are skipped without a single ray cast:
    a chord whose XY box misses the mesh's vertex box (no projection reaches
    it, so neither its pierces nor its midpoints can be inside) and an
    interval whose MIDPOINT lands outside that box (same argument, applied
    per interval - the column there is provably empty).  A loop whose start
    point repeats travels nowhere and never reaches this function.
    """
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0.0:
        return []
    if bounds is None:
        bounds = mesh_xy_bounds(mesh)
    if bounds is None:
        return []
    lo_x, lo_y, hi_x, hi_y = bounds
    if ((x0 < lo_x and x1 < lo_x) or (x0 > hi_x and x1 > hi_x)
            or (y0 < lo_y and y1 < lo_y) or (y0 > hi_y and y1 > hi_y)):
        return []
    spans: list[tuple[float, float]] = []
    ts = [t for t in chord_crossings(mesh, x0, y0, x1, y1, z, bounds)
          if 0.0 < t < length]
    edges = [0.0] + sorted(ts) + [length]
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    for a, b in zip(edges, edges[1:]):
        if b <= a:
            # A duplicate pierce (the chord passing exactly through the
            # point where two triangles of one face meet) leaves a
            # zero-length interval here.  Skipping it cannot hide material:
            # the intervals on either side are measured on their own
            # midpoints below, and touching solid runs merge.
            continue
        mid = 0.5 * (a + b)
        xm, ym = x0 + ux * mid, y0 + uy * mid
        if not (lo_x <= xm <= hi_x and lo_y <= ym <= hi_y):
            continue                # over air by construction: no ray cast
        if point_in_mesh(mesh, xm, ym, z):
            if spans and a <= spans[-1][1]:
                spans[-1] = (spans[-1][0], b)   # touching runs: one solid
            else:
                spans.append((a, b))
    return spans


# ---------------------------------------------------------------------------
# Pass planning
# ---------------------------------------------------------------------------

@dataclass
class FinishPass:
    """One finished level: a waterline contour or one constant-scallop ring."""

    kind: str                      # "waterline" | "scallop"
    z: float                       # cutting height, mm
    level: float                   # offset distance from the material, mm
    loops: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def points(self) -> int:
        return sum(len(loop) for loop in self.loops)


def _finish_levels(top_z: float, bottom_z: float, stepdown: float) -> list[float]:
    """Cutting levels ``top_z, top_z - stepdown, ... , bottom_z``.

    A finishing pass starts AT the stock top (the wall's top edge is real
    geometry to be cut), unlike a rougher whose first level sits one stepdown
    down so the first cut removes material.  ``bottom_z`` is always a level of
    its own.
    """
    levels: list[float] = []
    z = top_z
    while z > bottom_z + Z_TOLERANCE_MM:
        levels.append(z)
        z -= stepdown
    levels.append(bottom_z)
    return levels


def _max_ring_extent(regions, stock: BBox, samples: int = 33) -> float:
    """Largest distance from the material to any point of the stock (bound).

    The rings must reach far enough to cover the whole floor inside the stock,
    i.e. ``max over p in stock of distance(p, material)``.  That maximum is
    NOT attained at a stock corner in general: it is a convex function only
    for convex material (a corner rule is therefore wrong for a pocket - the
    maximum sits at the bottom of the void - and for a non-convex boss, where
    it sits on the medial axis).  Instead this samples the stock on a
    ``samples x samples`` grid (corners included) and adds HALF the sample
    diagonal: ``distance(., material)`` is 1-Lipschitz, every stock point
    lies within half a sample diagonal of a sample, so

        true max <= sampled max + hypot(dx, dy) / 2

    is a proven upper bound - the derived ring count can over-cover by at
    most half a sample cell and can never under-cover.  Points inside the
    material contribute 0 (a ring must not start inside the solid).
    """
    flat = [loop for region in regions for loop in region]
    if not flat:
        raise ValueError("ring extent needs a material boundary")
    edges = _boundary_edges(flat)
    x0, y0 = stock.min.x, stock.min.y
    x1, y1 = stock.max.x, stock.max.y
    dx = (x1 - x0) / max(1, samples - 1)
    dy = (y1 - y0) / max(1, samples - 1)
    worst = 0.0
    for i in range(samples):
        x = x0 + i * dx
        for j in range(samples):
            y = y0 + j * dy
            if _inside_regions(regions, x, y):
                continue                    # inside the material: distance 0
            near = min(point_segment_distance(x, y, e[0], e[1], e[2], e[3])
                       for e in edges)
            if near > worst:
                worst = near
    return worst + 0.5 * math.hypot(dx, dy)


def _inside_regions(regions, x: float, y: float) -> bool:
    """Even-odd inside ANY region (the union the section builder rasterises)."""
    for region in regions:
        parity = 0
        for loop in region:
            if inside_polygon(loop, x, y):
                parity ^= 1
        if parity:
            return True
    return False


def _scallop_plane(z_levels: list[float], scallop_z: float | None) -> float:
    """Height the constant-scallop rings are cut at.

    The DEEPEST level, unless the caller pins ``scallop_z``.  One helper for
    both the ring-COUNT measurement and the ring SECTION, so the floor that
    is measured and the floor that is cut can never disagree (review round-2
    MINOR: the count was read at ``min(z_levels)`` while the rings were cut
    at ``scallop_z`` - two different materials on a mesh as soon as a feature
    starts between the two heights).  Both call sites sit inside the scallop
    guard of :func:`plan_finishes`, so a waterline-only plan evaluates
    neither ``min(z_levels)`` nor ``scallop_z``.
    """
    return (min(float(v) for v in z_levels) if scallop_z is None
            else float(scallop_z))


def plan_finishes(
    boundaries_at,
    z_levels: list[float],
    tool_radius: float,
    cell: float,
    mode: str = "both",
    cusp_height_mm: float | None = DEFAULT_CUSP_HEIGHT_MM,
    ring_count: int | None = None,
    ring_stepover: float | None = None,
    first_ring: float | None = None,
    stock: BBox | None = None,
    stock_to_leave_mm: float = 0.0,
    scallop_z: float | None = None,
) -> tuple[list[FinishPass], dict[str, Any]]:
    """Compute every finishing pass for one material description.

    Args:
        boundaries_at: ``z -> [region, ...]`` where a region is
            ``[closed XY loop, ...]``.  Material = UNION of the regions,
            even-odd inside each (so a hole is a second loop).  A prismatic
            part ignores ``z`` and returns one region; a mesh part returns
            ONE region too - the cross-section just ABOVE ``z`` (the material
            that starts at ``z``, which is what the tip at ``z`` finishes),
            falling back to the section just below when nothing starts there
            - see :meth:`WaterlineFinishingStrategy._material_boundaries`.
        z_levels: cutting heights, descending.
        tool_radius: ``R``; the waterline is the level set
            ``distance == R + stock_to_leave_mm`` of the material (the
            allowance is a LEVEL SHIFT, not an erosion - see the module
            docstring: eroding would overcut an outside boss).
        cell: raster pitch, mm.
        mode: ``waterline`` | ``scallop`` | ``both``.
        cusp_height_mm: target scallop height.  ``None`` means "take the ring
            spacing from ``ring_stepover`` instead" (the realised height is
            still reported).
        ring_count: ``None`` derives it from the stock footprint; ``0`` is
            rejected by validation.
        ring_stepover: explicit ring spacing, mm (only consulted when
            ``cusp_height_mm`` is ``None``).
        first_ring: offset of the first ring, default ``R``.
        stock: used to derive the ring count.
        scallop_z: height of the scallop rings, default the deepest level.

    Returns:
        ``(passes, info)`` - ``passes`` sorted deepest-first is NOT
        guaranteed; callers must not assume an order, :meth:`generate_toolpath`
        sorts by ``z`` descending itself.  ``info`` carries the scallop
        numbers for the toolpath report.
    """
    if mode not in FINISH_MODES:
        raise ValueError(f"finish_mode must be one of {FINISH_MODES}, got {mode!r}")
    if cell <= 0:
        raise ValueError("cell must be > 0")

    info: dict[str, Any] = {
        "mode": mode,
        "cell_mm": cell,
        "tool_radius_mm": tool_radius,
        "stock_to_leave_mm": stock_to_leave_mm,
        "ring_stepover_mm": None,
        "cusp_height_mm": None,
        "cusp_height_target_mm": None,
        "rings": 0,
    }

    ring_distances: list[float] = []
    p: float | None = None
    if mode in ("scallop", "both"):
        # Where the scallop rings are CUT: the deepest level unless the caller
        # pins ``scallop_z``.  ``_scallop_plane`` is called here AND for the
        # ring SECTION at the end, so the count and the cut always read the
        # same height - and both calls sit inside the scallop guard, so a
        # waterline-only plan evaluates neither ``min(z_levels)`` nor
        # ``scallop_z``, exactly as before this fix.  On a mesh the two
        # heights are two different materials as soon as a feature starts
        # between them (same defect class as review round-2 finding n5, where
        # ``z_levels[-1]`` was read for ``min(z_levels)``: measuring the floor
        # at the deepest level while cutting at ``scallop_z`` repeats it one
        # level up).
        scallop_plane = _scallop_plane(z_levels, scallop_z)
        if cusp_height_mm is not None:
            p = stepover_for_cusp(cusp_height_mm, tool_radius)
            info["cusp_height_target_mm"] = cusp_height_mm
        else:
            if ring_stepover is None or ring_stepover <= 0:
                raise ValueError(
                    "ring_stepover must be positive when cusp_height_mm is None")
            p = float(ring_stepover)
            if p > 2.0 * tool_radius:
                raise ValueError(
                    f"ring_stepover {p} > 2R {2.0 * tool_radius}: the cusp "
                    "domain is exhausted (algorithm_impls L606)")
        first = tool_radius if first_ring is None else float(first_ring)
        if first < tool_radius:
            raise ValueError("first ring must be at least the tool radius")
        if ring_count is None:
            if stock is None:
                raise ValueError("deriving the ring count needs a stock footprint")
            # The floor the rings have to cover is measured at the height
            # they are actually CUT (``scallop_plane``), not at the deepest
            # level: with an explicit ``scallop_z`` the two sections differ
            # on a mesh.
            extent = _max_ring_extent(boundaries_at(scallop_plane), stock)
            count = int((extent - first) // p) + 1 if extent > first else 1
            count = max(1, min(MAX_SCALLOP_RINGS, count))
        else:
            count = int(ring_count)
        # ``ring_plan`` validates the domain and the ordering; the spacing is
        # recomputed from ``p`` so an explicit ``ring_stepover`` and a
        # cusp-derived spacing take exactly the same code path.
        ring_plan(tool_radius,
                  info["cusp_height_target_mm"]
                  if info["cusp_height_target_mm"] is not None
                  else _cusp_of_step(p, tool_radius), first, count)
        # Stock allowance: every cut stands ``stock_to_leave_mm`` off the
        # nominal wall, for a boss and for a pocket alike.
        ring_distances = [first + k * p + stock_to_leave_mm
                          for k in range(count)]
        info["ring_stepover_mm"] = p
        info["cusp_height_mm"] = cusp_height(p, tool_radius)
        info["rings"] = count

    waterline_level = tool_radius + stock_to_leave_mm
    max_level = waterline_level
    if ring_distances:
        max_level = max(max_level, max(ring_distances))
    pad_radius = max_level

    section_cache: dict[tuple, Raster] = {}
    # The distance field is the expensive part (EDT + snap + marching
    # squares), and for a prismatic part every level yields the same section
    # AND the same level -> the same loops, so the result is cached too.
    waterline_cache: dict[tuple, list] = {}

    def section_and_key(z: float) -> tuple[tuple, Raster]:
        # Keyed by the BOUNDARIES, not by z: a prismatic part has the same
        # cross-section at every level, and rasterising it once per level is
        # pure waste (the mesh path still recomputes its section per z).
        regions = boundaries_at(z)
        key = tuple(tuple(tuple(loop) for loop in region) for region in regions)
        hit = section_cache.get(key)
        if hit is None:
            hit = section_from_regions(regions, 0.0, cell, pad_radius)
            section_cache[key] = hit
        return key, hit

    passes: list[FinishPass] = []
    if mode in ("waterline", "both"):
        for z in z_levels:
            key, grid = section_and_key(z)
            cache_key = (key, waterline_level)
            loops = waterline_cache.get(cache_key)
            if loops is None:
                loops = waterline(grid, waterline_level)
                waterline_cache[cache_key] = loops
            passes.append(FinishPass("waterline", float(z), waterline_level,
                                     loops))
    if mode in ("scallop", "both"):
        # Same helper as the ring count above, so the cut height and the
        # measured floor always agree; the call sits inside this guard, so a
        # waterline-only plan still evaluates neither value.
        plane = _scallop_plane(z_levels, scallop_z)
        _, grid = section_and_key(plane)
        for d, loops in offset_loops(grid, ring_distances):
            passes.append(FinishPass("scallop", plane, d, loops))

    # Deepest last: z descending, so the entry height never has to climb.
    passes.sort(key=lambda fp: -fp.z)
    info["sections"] = len(section_cache)
    info["waterline_fields"] = len(waterline_cache)
    info["passes"] = len(passes)
    info["loops"] = sum(len(fp.loops) for fp in passes)
    info["loop_points"] = sum(fp.points for fp in passes)
    return passes, info


def _cusp_of_step(stepover: float, radius: float) -> float:
    """Realised cusp height for an explicit ring spacing (never raises for
    ``stepover <= 2R``; callers validate that first)."""
    return radius - math.sqrt(max(0.0, radius * radius - (0.5 * stepover) ** 2))


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

#: Every key :func:`_build_config` coerces, in one place so ``validate_params``
#: and ``generate_toolpath`` can never disagree about what a parameter is.
_NUMERIC_KEYS = (
    "cell_mm", "cusp_height_mm", "stepover", "stepdown", "feed_rate",
    "spindle_speed", "clearance_height", "top_of_stock", "bottom_of_stock",
    "stock_to_leave_mm", "ring_stepover", "first_ring", "scallop_z",
)


def _build_config(values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge defaults onto ``values`` and float-coerce the numeric keys.

    Returns ``(config, errors)``.  Every coercion failure becomes a string
    here rather than a ``ValueError`` escaping out of the strategy, so a bad
    ``generate_toolpath`` call yields an error ``ToolpathData`` and a bad
    ``run`` yields the same messages from ``validate_params``.
    """
    cfg: dict[str, Any] = dict(values)
    errors: list[str] = []

    cfg.setdefault("finish_mode", "both")
    cfg.setdefault("cell_mm", CELL_MM)
    cfg.setdefault("cusp_height_mm", DEFAULT_CUSP_HEIGHT_MM)
    cfg.setdefault("scallop_rings", None)
    cfg.setdefault("stock_to_leave_mm", 0.0)
    cfg.setdefault("finish_levels", None)
    cfg.setdefault("profile", None)
    cfg.setdefault("mesh", None)
    cfg.setdefault("stepover", 0.4)
    cfg.setdefault("stepdown", 1.0)
    cfg.setdefault("feed_rate", 1000.0)
    cfg.setdefault("spindle_speed", 10000.0)
    cfg.setdefault("clearance_height", 5.0)
    cfg.setdefault("top_of_stock", 0.0)
    cfg.setdefault("bottom_of_stock", -10.0)

    for key in _NUMERIC_KEYS:
        raw = cfg.get(key)
        if raw is None:
            continue
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{key} must be a number, got {raw!r}")
            cfg[key] = None      # already reported; skip the range checks
            continue
        if not math.isfinite(parsed):
            # nan/inf slip past every <= / < comparison, so they would reach
            # the geometry as NaN coordinates.
            errors.append(f"{key} must be a finite number, got {raw!r}")
            cfg[key] = None      # already reported; skip the range checks
            continue
        cfg[key] = parsed

    raw_rings = cfg.get("scallop_rings")
    if raw_rings is not None:
        try:
            rings_int = int(raw_rings)
        except (TypeError, ValueError):
            errors.append(f"scallop_rings must be an integer, got {raw_rings!r}")
        else:
            if float(raw_rings) != float(rings_int):
                errors.append(f"scallop_rings must be an integer, got {raw_rings!r}")
            cfg["scallop_rings"] = rings_int

    raw_levels = cfg.get("finish_levels")
    if raw_levels is not None:
        if isinstance(raw_levels, (str, bytes)) or not hasattr(raw_levels, "__iter__"):
            errors.append(f"finish_levels must be a sequence of z values, "
                          f"got {raw_levels!r}")
            cfg["finish_levels"] = None
        else:
            levels: list[float] = []
            for item in raw_levels:
                try:
                    z = float(item)
                except (TypeError, ValueError):
                    errors.append(f"finish_levels entries must be numbers, "
                                  f"got {item!r}")
                    continue
                if not math.isfinite(z):
                    errors.append(f"finish_levels entries must be finite, "
                                  f"got {item!r}")
                    continue
                levels.append(z)
            cfg["finish_levels"] = levels

    raw_profile = cfg.get("profile")
    if raw_profile is not None:
        poly = _coerce_profile(raw_profile)
        if poly is None:
            errors.append(
                "profile must be a sequence of at least 3 [x, y] pairs, "
                f"got {type(raw_profile).__name__}"
            )
        else:
            cfg["profile"] = poly

    return cfg, errors


def _coerce_profile(raw: Any) -> list[tuple[float, float]] | None:
    """``[[x, y], ...]`` -> ``[(x, y), ...]``, dropping a repeated closing
    point.  ``None`` means "not a usable polygon"."""
    if isinstance(raw, (str, bytes, dict)):
        return None
    try:
        pts = list(raw)
    except TypeError:
        return None
    out: list[tuple[float, float]] = []
    for item in pts:
        try:
            x, y = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        out.append((x, y))
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if len(out) < 3:
        return None
    return out


def _validate_config(cfg: dict[str, Any], stock: BBox | None,
                     tool: ToolDef | None) -> list[str]:
    """Shared validation body for ``validate_params`` and ``generate_toolpath``."""
    errors: list[str] = []

    if tool is None:
        errors.append("Tool definition is required")
    elif not (math.isfinite(tool.diameter) and tool.diameter > 0):
        errors.append(f"Tool diameter must be a positive finite number, "
                      f"got {tool.diameter!r}")

    if stock is None:
        errors.append("Stock definition is required")

    mode = cfg.get("finish_mode")
    if not isinstance(mode, str) or mode not in FINISH_MODES:
        errors.append(f"finish_mode must be one of {list(FINISH_MODES)}, "
                      f"got {mode!r}")

    # ``_build_config`` sets a numeric key to None when its coercion already
    # failed, so "reported, skip" is just ``None`` here.
    if cfg.get("cell_mm") is not None and cfg["cell_mm"] <= 0:
        errors.append(f"cell_mm must be > 0, got {cfg['cell_mm']!r}")

    if cfg.get("stepover") is not None and not 0.0 < cfg["stepover"] <= 1.0:
        errors.append(f"stepover must be a fraction of the tool diameter in "
                      f"(0, 1], got {cfg['stepover']!r}")
    if cfg.get("stepdown") is not None and cfg["stepdown"] <= 0:
        errors.append(f"stepdown must be positive, got {cfg['stepdown']!r}")
    if cfg.get("feed_rate") is not None and cfg["feed_rate"] <= 0:
        errors.append(f"feed_rate must be positive, got {cfg['feed_rate']!r}")
    if cfg.get("clearance_height") is not None and cfg["clearance_height"] < 0:
        errors.append(f"clearance_height must be >= 0, got {cfg['clearance_height']!r}")
    if cfg.get("stock_to_leave_mm") is not None and cfg["stock_to_leave_mm"] < 0:
        errors.append(f"stock_to_leave_mm must be >= 0, "
                      f"got {cfg['stock_to_leave_mm']!r}")

    top = cfg.get("top_of_stock")
    bottom = cfg.get("bottom_of_stock")
    if top is not None and bottom is not None and top < bottom:
        errors.append(f"top_of_stock {top} must not be below "
                      f"bottom_of_stock {bottom}")

    if tool is not None and math.isfinite(tool.diameter) and tool.diameter > 0:
        radius = tool.diameter / 2.0
        if stock is not None:
            half = min(stock.size.x, stock.size.y) / 2.0
            if half < radius:
                errors.append(
                    f"Stock footprint {stock.size.x:.3f} x "
                    f"{stock.size.y:.3f} mm is narrower than the "
                    f"tool radius {radius:.3f} mm"
                )
        cusp = cfg.get("cusp_height_mm")
        if cusp is not None and not 0.0 < cusp <= radius:
            errors.append(f"cusp_height_mm must lie in (0, R] where "
                          f"R = {radius}, got {cusp!r}")
        step = cfg.get("ring_stepover")
        if step is not None and not 0.0 < step <= 2.0 * radius:
            errors.append(f"ring_stepover must lie in (0, 2R] where "
                          f"R = {radius}, got {step!r}")
        first = cfg.get("first_ring")
        if first is not None and first < radius:
            errors.append(f"first_ring must be at least the tool radius "
                          f"{radius}, got {first!r}")

    rings = cfg.get("scallop_rings")
    if rings is not None and not 1 <= rings <= MAX_SCALLOP_RINGS:
        errors.append(
            f"scallop_rings must be in [1, {MAX_SCALLOP_RINGS}] (or null to "
            f"derive it from the stock footprint), got {rings!r}")

    scallop_z = cfg.get("scallop_z")
    if scallop_z is not None and top is not None and bottom is not None \
            and not bottom <= scallop_z <= top:
        errors.append(f"scallop_z {scallop_z} must lie in "
                      f"[{bottom}, {top}]")

    for z in cfg.get("finish_levels") or []:
        if top is not None and bottom is not None and not bottom <= z <= top:
            errors.append(f"finish_levels entry {z} must lie in "
                          f"[{bottom}, {top}]")

    if mode in ("scallop", "both") and cfg.get("cusp_height_mm") is None \
            and cfg.get("ring_stepover") is None:
        errors.append("either cusp_height_mm or ring_stepover is required "
                      "for constant-scallop finishing")

    return errors


class WaterlineFinishingStrategy(BaseStrategy):
    """Waterline (Z-level contour) + constant-scallop finishing, feature F2.

    See the module docstring for the mapping from the reference parity
    structures, the geometry inputs and the declared limitations.
    """

    @property
    def name(self) -> str:
        return "waterline_finishing"

    @property
    def description(self) -> str:
        return "Waterline (Z-level) + constant-scallop finishing (F2)"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate the operation before an F2 toolpath is generated.

        The numbers checked are the numbers :meth:`BaseStrategy.run` will hand
        to :meth:`generate_toolpath`: that merge puts ``extra_args`` first and
        falls back to the ``OperationParams`` fields, so this mirrors it
        exactly and then runs the SAME ``_build_config`` +
        ``_validate_config`` pair the generator uses.
        """
        effective: dict[str, Any] = dict(operation.extra_args)
        effective.setdefault("stepover", operation.stepover)
        effective.setdefault("stepdown", operation.stepdown)
        effective.setdefault("feed_rate", operation.feed_rate)
        effective.setdefault("spindle_speed", operation.spindle_speed)
        effective.setdefault("clearance_height", operation.clearance_height)
        effective.setdefault("top_of_stock", operation.top_of_stock)
        effective.setdefault("bottom_of_stock", operation.bottom_of_stock)

        cfg, errors = _build_config(effective)
        errors.extend(_validate_config(cfg, operation.stock, operation.tool))
        errors.extend(self._validate_geometry(cfg))
        return errors

    @staticmethod
    def _validate_geometry(cfg: dict[str, Any]) -> list[str]:
        """Checks that need the resolved config (mesh shape, level ordering)."""
        errors: list[str] = []
        mesh = cfg.get("mesh")
        if mesh is not None:
            if not isinstance(mesh, dict) or "vertices" not in mesh \
                    or "faces" not in mesh:
                errors.append("mesh must be the dict kernel.stl.parse_stl "
                              "returns (keys 'vertices' and 'faces')")
        profile = cfg.get("profile")
        if profile is not None and mesh is not None:
            errors.append("pass either 'profile' or 'mesh', not both")
        levels = cfg.get("finish_levels")
        if levels is not None and len(levels) == 0:
            errors.append("finish_levels must not be empty")
        return errors

    # ------------------------------------------------------------------
    # Toolpath generation
    # ------------------------------------------------------------------
    def generate_toolpath(self, stock: BBox, tool: ToolDef,
                          **kwargs: Any) -> ToolpathData:
        """Generate the finishing toolpath.

        Args:
            stock: bounding box of the stock (the machining envelope).
            tool: cutter definition; ``diameter`` sets ``R``.
            **kwargs: ``finish_mode`` (``waterline`` | ``scallop`` |
                ``both``), ``cell_mm``, ``cusp_height_mm``,
                ``scallop_rings``, ``ring_stepover``, ``first_ring``,
                ``stock_to_leave_mm``, ``finish_levels``, ``scallop_z``,
                ``profile``, ``mesh``, plus the standard ``stepover`` /
                ``stepdown`` / ``feed_rate`` / ``spindle_speed`` /
                ``clearance_height`` / ``top_of_stock`` / ``bottom_of_stock``.

        Returns:
            ToolpathData whose cutting moves carry exactly two feed values -
            ``feed`` and ``feed / 3`` (E-S6) - and whose rapids carry
            ``feed = 0``.  Invalid parameters return an error ToolpathData
            instead of raising.
        """
        cfg, errors = _build_config(kwargs)
        errors.extend(_validate_config(cfg, stock, tool))
        errors.extend(self._validate_geometry(cfg))
        if errors:
            return ToolpathData(
                name="Waterline Finishing",
                tool=tool,
                strategy=self.name,
                params={"error": "; ".join(errors)},
            )

        cell = float(cfg["cell_mm"])
        mode = cfg["finish_mode"]
        leave = float(cfg["stock_to_leave_mm"])
        feed_cutting = float(cfg["feed_rate"])
        feed_plunge = feed_cutting / PLUNGE_FEED_DIVISOR
        speed = float(cfg["spindle_speed"])
        clearance = float(cfg["clearance_height"])
        top_z = float(cfg["top_of_stock"])
        bottom_z = float(cfg["bottom_of_stock"])
        stepdown = float(cfg["stepdown"])
        radius = tool.diameter / 2.0

        if cfg.get("finish_levels") is not None:
            z_levels = [float(z) for z in cfg["finish_levels"]]
        else:
            z_levels = _finish_levels(top_z, bottom_z, stepdown)

        source_seen: dict[str, str] = {}

        def boundaries_at(z: float) -> list:
            resolved, label = self._material_boundaries(cfg, stock, z)
            source_seen["v"] = label
            return resolved

        cusp = cfg.get("cusp_height_mm")
        ring_step = cfg.get("ring_stepover")
        try:
            passes, info = plan_finishes(
                boundaries_at=boundaries_at,
                z_levels=z_levels,
                tool_radius=radius,
                cell=cell,
                mode=mode,
                cusp_height_mm=cusp,
                ring_count=cfg.get("scallop_rings"),
                ring_stepover=ring_step,
                first_ring=cfg.get("first_ring"),
                stock=stock,
                stock_to_leave_mm=leave,
                scallop_z=cfg.get("scallop_z"),
            )
        except ValueError as exc:
            return ToolpathData(
                name="Waterline Finishing",
                tool=tool,
                strategy=self.name,
                params={"error": str(exc)},
            )

        if info["loops"] == 0:
            return ToolpathData(
                name="Waterline Finishing",
                tool=tool,
                strategy=self.name,
                params={"error": "no reachable level set: the tool cannot "
                                 "enter this geometry at cell_mm = %g" % cell},
            )

        moves: list[Move] = []
        feed_counts: dict[float, int] = {}
        # The triangle mesh the clearance column is measured against; a
        # ``profile``/stock source is prismatic in z, so its column at a loop
        # start point is clear by construction (the point is R outside the
        # section at the cutting level, and the section does not change with
        # height) and is not ray-cast at all.  ``clearance_checks`` reports
        # how many spans were actually measured, so a test can tell the fast
        # path from a check that never ran.
        mesh = cfg.get("mesh")
        # XY box of the mesh, computed once: a loop start point outside it
        # sits over air by construction and the ray cast is skipped.
        mesh_bounds = mesh_xy_bounds(mesh) if mesh is not None else None
        clearance_checks = 0
        clearance_violations: list[str] = []
        # The XY TRAVERSE at ``clearance_height`` - the one rapid the entry
        # column guard cannot see, because it travels sideways at that plane
        # instead of down it (card t_6020987d, declared limitation (1) of
        # t_3b02b4a3).  ``prev_xy`` is where the tool was before the rapid:
        # for the program's first move that is (0, 0), the start post/ir.py
        # assumes for move 0 (``prev_x = ... if idx > 0 else 0.0``) and the
        # one the simulation replays from (``current_x = 0.0``).
        # ``traverse_checks`` counts the traversals actually measured, so a
        # test can tell a passing check from one that never ran - and a
        # prismatic source, which is never chord-checked, reports 0.
        traverse_checks = 0
        traverse_violations: list[str] = []
        prev_x, prev_y = 0.0, 0.0
        prev_is_start = True

        def _rapid(end: Vec3) -> None:
            moves.append(Move(move_type=MoveType.RAPID, end=end, feed=0.0,
                              spindle_speed=speed))

        def _cut(end: Vec3, feed: float) -> None:
            moves.append(Move(move_type=MoveType.LINEAR, end=end, feed=feed,
                              spindle_speed=speed))
            feed_counts[feed] = feed_counts.get(feed, 0) + 1

        z_prev = top_z
        for fp in passes:
            for index, loop in enumerate(fp.loops, start=1):
                if len(loop) < 2:
                    continue
                x0, y0 = loop[0]
                if mesh is not None and (x0, y0) != (prev_x, prev_y):
                    # The XY traverse at ``clearance_height`` that brings the
                    # tool to this start point: the program's first rapid
                    # travels it from the machine start position, every later
                    # one from the previous loop's exit retract (both sit at
                    # ``clearance_height``).  Checked BEFORE it is emitted,
                    # for the same reason as the entry column - a refusal has
                    # to happen before the tool moves.  A zero-length
                    # traverse is no travel at all and is not counted.
                    #
                    # The chord is only measured when the source is a mesh:
                    # a ``profile``/stock source is prismatic, and for a
                    # prism the question is not a geometry question at all -
                    # see "Honest limits" in the module docstring.
                    traverse_checks += 1
                    bands = blocked_chord(mesh, prev_x, prev_y, x0, y0,
                                          clearance, mesh_bounds)
                    if bands:
                        run = math.hypot(x0 - prev_x, y0 - prev_y)
                        ux, uy = ((x0 - prev_x) / run,
                                  (y0 - prev_y) / run)
                        where = ", ".join(
                            f"(x{prev_x + ux * a:g}, y{prev_y + uy * a:g})"
                            f"..(x{prev_x + ux * b:g}, "
                            f"y{prev_y + uy * b:g})"
                            for a, b in bands)
                        src = (f"the program start (x{prev_x:g}, "
                               f"y{prev_y:g})" if prev_is_start
                               else f"(x{prev_x:g}, y{prev_y:g})")
                        traverse_violations.append(
                            f"XY traverse at Z{clearance:g} from {src} to "
                            f"(x{x0:g}, y{y0:g}) passes through material in "
                            f"{where} (pass z={fp.z:g}, "
                            f"loop {index} of {len(fp.loops)})")
                if mesh is not None:
                    # Both vertical spans the entry travels at (x0, y0): the
                    # rapid from ``clearance_height`` to ``z_prev`` and the
                    # plunge from ``z_prev`` to the cutting level.  Checked
                    # BEFORE either move is emitted - a refusal has to happen
                    # before the tool moves, not after (review finding m6).
                    # The column is ray-cast ONCE per loop and both spans are
                    # slices of it, so the O(faces) scan runs once, not twice.
                    # Their union is [fp.z, clearance_height], which is also
                    # the span the loop's EXIT retract travels: every loop
                    # leaves from ``loop[0]`` again (a closed contour, or cut
                    # back to its start), so the same two measurements cover
                    # the way out as well.
                    within = (mesh_bounds is None
                              or (mesh_bounds[0] <= x0 <= mesh_bounds[2]
                                  and mesh_bounds[1] <= y0 <= mesh_bounds[3]))
                    crossings = (column_crossings(mesh, x0, y0) if within
                                 else [])   # outside the XY box: over air
                    for z_from, z_to, what in (
                        (clearance, z_prev, "rapid from clearance"),
                        (z_prev, fp.z, "plunge"),
                    ):
                        clearance_checks += 1
                        bands = blocked_span(crossings, z_from, z_to)
                        if bands:
                            where = ", ".join(f"Z{a:g}..Z{b:g}"
                                              for a, b in bands)
                            clearance_violations.append(
                                f"{what} at (x{x0:g}, y{y0:g}) from "
                                f"Z{z_from:g} to Z{z_to:g} passes through "
                                f"material in {where} (pass z={fp.z:g}, "
                                f"loop {index} of {len(fp.loops)})")
                start = Vec3(x0, y0, fp.z)
                _rapid(Vec3(x0, y0, clearance))
                _rapid(Vec3(x0, y0, z_prev))
                if fp.z < z_prev - Z_TOLERANCE_MM:
                    # Straight vertical entry, priced at tool_feedPlunge.
                    # (fp.z can never exceed z_prev: passes are sorted
                    # descending and every level is validated inside
                    # [bottom_of_stock, top_of_stock].)
                    _cut(Vec3(x0, y0, fp.z), feed_plunge)
                pos = start
                closed = (math.hypot(loop[-1][0] - loop[0][0],
                                     loop[-1][1] - loop[0][1]) > 1e-9)
                for (x, y) in loop[1:]:
                    if x == pos.x and y == pos.y:
                        continue
                    _cut(Vec3(x, y, fp.z), feed_cutting)
                    pos = Vec3(x, y, fp.z)
                if closed:
                    _cut(start, feed_cutting)
                    pos = start
                _rapid(Vec3(pos.x, pos.y, clearance))
                # Every loop leaves at ``clearance_height`` from where it
                # ended, so that is the far end of the NEXT traverse.
                prev_x, prev_y = pos.x, pos.y
                prev_is_start = False
                z_prev = fp.z

        if clearance_violations or traverse_violations:
            # DECISION (t_3b02b4a3, and the SAME decision for the traverse,
            # t_6020987d): refuse with a named move rather than emit.  For
            # the column there is no height to retract to - the obstruction
            # IS the column.  For the chord the alternative the card allows,
            # re-routing it, would mean either inventing a traverse plane
            # ABOVE the user's own ``clearance_height`` (this module cannot
            # bound the machine's Z limit, and silently overriding a
            # user-declared safety plane is not a guard's job) or planning a
            # free path around the part in XY (a path-planning problem, not
            # a clearance check).  The chord is not part of the cut, so the
            # actionable fix belongs to the caller: raise the clearance plane
            # above what the traverse crosses - which is exactly what F1's
            # export-time guard tells the same user about a clearance plane
            # below the stock top.
            #
            # Entry-column violations are listed FIRST so the wording and
            # the ordering t_3b02b4a3's tests pin keep their meaning: only
            # a COLUMN-ONLY refusal keeps the parent's header verbatim.
            # A refusal that also carries a traverse violation takes the
            # header below instead, which lists whichever guards fired -
            # column first - because it has to describe both.
            violations = clearance_violations + traverse_violations
            more = (f"  (+{len(violations) - 1} more)"
                    if len(violations) > 1 else "")
            if not traverse_violations:
                error = (
                    f"rapid clearance: the tool would descend through "
                    f"material at a loop start point "
                    f"({len(violations)} offending move(s), "
                    f"the XY column is not clear between "
                    f"clearance_height and the cutting level).  First: "
                    f"{violations[0]}{more}")
            else:
                kinds = []
                if clearance_violations:
                    kinds.append("the XY column at a loop start point is "
                                 "not clear between clearance_height and "
                                 "the cutting level")
                kinds.append("an XY traverse at clearance_height crosses "
                             "material")
                error = (
                    f"rapid clearance: the tool would move through material "
                    f"({len(violations)} offending move(s): "
                    f"{'; '.join(kinds)}).  First: "
                    f"{violations[0]}{more}")
            return ToolpathData(
                name="Waterline Finishing",
                tool=tool,
                strategy=self.name,
                params={
                    "error": error,
                    "clearance_violations": clearance_violations,
                    "clearance_checks": clearance_checks,
                    "traverse_violations": traverse_violations,
                    "traverse_checks": traverse_checks,
                    "profile_source": source_seen.get("v", "stock"),
                },
            )

        params: dict[str, Any] = {
            "profile_source": source_seen.get("v", "stock"),
            "finish_mode": mode,
            "tool_diameter": tool.diameter,
            "raster_cell_mm": cell,
            "stock_to_leave_mm": leave,
            "levels": len(z_levels),
            "passes": info["passes"],
            "loops": info["loops"],
            "loop_points": info["loop_points"],
            "waterline_loops": sum(len(fp.loops) for fp in passes
                                   if fp.kind == "waterline"),
            "scallop_rings": info["rings"],
            "ring_stepover_mm": info["ring_stepover_mm"],
            "cusp_height_mm": info["cusp_height_mm"],
            "cusp_height_target_mm": info["cusp_height_target_mm"],
            "feed_vocabulary": {
                "plunge": round(feed_plunge, 6),
                "cutting": round(feed_cutting, 6),
            },
            "feed_histogram": {
                f"{value:.6f}": count
                for value, count in sorted(feed_counts.items())
            },
            # Clearance observability: how many entry spans were ray-cast and
            # what they found (always empty here - a violation returns the
            # error ToolpathData above instead).
            "clearance_checks": clearance_checks,
            "clearance_violations": clearance_violations,
            # ...and the same two numbers for the XY traverses at
            # ``clearance_height`` (0 for a prismatic source, which is never
            # chord-checked).
            "traverse_checks": traverse_checks,
            "traverse_violations": traverse_violations,
            "moves": len(moves),
        }
        return ToolpathData(
            name="Waterline Finishing",
            tool=tool,
            moves=moves,
            strategy=self.name,
            params=params,
        )

    # ------------------------------------------------------------------
    # Geometry input
    # ------------------------------------------------------------------
    @staticmethod
    def _material_boundaries(cfg: dict[str, Any], stock: BBox, z: float
                             ) -> tuple[list, str]:
        """Material REGIONS at height ``z``.

        Returns ``(regions, source)`` where ``regions = [region, ...]``, a
        region is ``[loop, ...]`` and a loop is ``[(x, y), ...]``; the
        material is the UNION of the regions, even-odd inside each.

        * ``profile`` / stock footprint: one region, prismatic in z.
        * ``mesh``: the section of the material the tool can reach from ``z``
          upward - i.e. the section just ABOVE ``z``, falling back to the
          section just below when there is nothing above.  ``mesh_section_loops``
          reports the curves where the model's boundary meets a plane, and on
          a STEP plane - a boss standing on a plate - that is the plate's
          outline AND the boss's outline.  Taking the exact-plane even-odd set
          XOR-s them into a frame (a hole under the boss) and the contour then
          cut through the boss; unioning both limits is the SUPERSET and
          swallows the feature instead (the plate outline hides the boss wall's
          base band, the solid outline hides a pocket wall whose floor sits on
          the plane).  The above-limit is the feature that starts at ``z``,
          which is what the tip at ``z`` finishes.  ``math.nextafter`` moves
          the sample off the plane by one ULP, so no other feature can be
          crossed.
        """
        profile = cfg.get("profile")
        if profile is not None:
            return [[list(profile)]], "profile"
        mesh = cfg.get("mesh")
        if mesh is not None:
            # A pass at tip height z cuts UPWARD from z, so what it has to
            # finish is the material that STARTS at z.  Take the section just
            # ABOVE the plane; fall back to the section just below it only
            # when NOTHING anywhere starts at z - i.e. z at or above the top
            # of every body.  z strictly above the mesh finds both limits
            # empty and raises the declared "no cross-section" error; a wall
            # whose material ENDS at z is not re-added by the fallback (it
            # only exists where the whole section is empty), because its band
            # was already cut by the levels below.
            #
            # Two wrong rules came before this one and both are pinned by
            # tests.  Round 1 took the exact-plane even-odd set: on a step
            # plane that XOR-s the two bodies into a FRAME (a hole under the
            # boss) and the contour cut through the boss.  Round 2 unioned
            # both limits instead, which is the SUPERSET - at a boss-on-plate
            # step plane the union is the plate outline, so the boss wall's
            # base band was never traced, and for a pocket whose floor sits
            # on the plane the pocket wall contour disappeared entirely.
            # The superset swallows the feature; the above-limit is the
            # feature.
            above = mesh_section_loops(mesh, math.nextafter(z, math.inf))
            if above:
                return [above], "mesh"
            below = mesh_section_loops(mesh, math.nextafter(z, -math.inf))
            if below:
                return [below], "mesh"
            raise ValueError(f"the mesh has no cross-section at z = {z}")
        rect = [(stock.min.x, stock.min.y), (stock.max.x, stock.min.y),
                (stock.max.x, stock.max.y), (stock.min.x, stock.max.y)]
        return [[rect]], "stock"
