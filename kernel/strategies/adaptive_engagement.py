"""
Adaptive roughing with an engagement-gated feed - feature F1
(``Fusion 360 RE/docs/p5-execution-plan.md`` section 4, row P5/3).

The module has two halves, and the split between them is deliberate.

**1. Adaptive roughing (geometry).**  The stock footprint is cleared level by
level with concentric offset rings, inside-out (contour-parallel clearing):

* the deepest ring degenerates to a line down the LONG axis of the footprint
  and cuts a fresh slot - the cutter is fully surrounded there, so its radial
  engagement is the full tool diameter ``D``;
* every following ring is offset radially by one stepover from the band the
  previous ring already cleared, so it opens a fresh band exactly
  ``spacing = stepover * D`` wide and its radial engagement is
  ``min(D, spacing)`` - engagement is constant by construction.  This is the
  same identity ``Fusion 360 RE/impl/const_engagement`` is built on (H9: the
  offset distance between two offset rings IS the stepover).

**2. Engagement-gated feed (the F1 gate).**  Every cutting move is priced by
:func:`select_feed` from ONE of exactly three feed values.  The *vocabulary*
is measured; the *gate* is this prototype's own policy.

Vocabulary source - ``Fusion 360 RE/docs/behavior/adaptive.md`` (sibling
checkout, read-only):

* **R8** - every capture carries exactly three distinct feed values,
  ``{feed/3, 0.9*feed, feed}``: observed ``{333.333344, 900, 1000}`` at
  ``feed = 1000``, ``{166.666672, 450, 500}`` at 500, ``{500, 1350, 1500}``
  at 1500, and cycle time scales exactly as ``1/feed``;
* the three arms of that set are the expression graph - ``tool_feedPlunge =
  tool_feedCutting / 3`` (``SCH:31720``), ``tool_feedCutting`` (``SCH:31624``)
  and the 0.9 arm, which **R10/R11** identify as ``reducedFeedrate``
  (``SCH:35352`` aliasing ``otherWayFeedrate`` ``SCH:34760`` in the adaptive
  operation), carried exclusively by the ``MOVEMENT_REDUCED`` class in
  333/333 captures;
* **R12** - the feed-optimisation group *selects* ``reducedFeedrate``; it
  never scales it, so "a fourth value is impossible by construction".  This
  module therefore also only ever *selects*.

What is NOT claimed: ``docs/behavior/adaptive.md`` records that
"engagement-driven feed optimization is not observable in our captures"
(section *Contradictions* item 2) and that Fusion's own reduced-feed trigger
is a corner/direction change (``reducedFeedChange = 25deg``), with "no
engagement quantity appears anywhere in it" (**R14**).  The engagement gate
below is therefore this prototype's policy over the measured vocabulary, not
a reconstruction of Fusion's feed logic.  Continuous engagement ->
chip-thickness feed was explicitly rejected for P5
(``docs/p5-execution-plan.md`` section 3.3) and is out of scope here too:
the gate *selects*, it does not modulate.

End-to-end path exercised by ``tests/integration/test_adaptive_engagement.py``:
STL -> :meth:`AdaptiveEngagementStrategy.run` -> ``ToolpathData`` ->
``simulation.SimulationEngine`` -> ``post.ir`` -> Fanuc G-code.
"""

from __future__ import annotations

from typing import Any

from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, Move, MoveType, ToolpathData, ToolDef, Vec3

# ---------------------------------------------------------------------------
# The measured three-value feed vocabulary
# ---------------------------------------------------------------------------

#: ``tool_feedPlunge = tool_feedCutting / 3`` (adaptive.md R8, SCH:31720).
FEED_PLUNGE_DIVISOR = 3.0

#: ``reducedFeedrate = tool_feedCutting * 0.9`` (adaptive.md R10, SCH:35352
#: aliasing SCH:34760); the ``MOVEMENT_REDUCED`` arm.
FEED_REDUCED_FACTOR = 0.9

#: Gate as a FRACTION OF THE TOOL DIAMETER: a move whose radial engagement
#: ``ae >= gate * D`` is priced at the reduced feed, everything else at the
#: full cutting feed.  0.5 puts the fresh full-diameter slot on the reduced
#: arm while every constant-engagement ring (``0.4 * D`` at the measured
#: ``optimalLoad = tool_diameter * 0.4``) stays on the cutting arm.
DEFAULT_ENGAGEMENT_GATE = 0.5


def feed_vocabulary(feed_cutting: float) -> dict[str, float]:
    """The measured three-value feed vocabulary for a base cutting feed.

    Returns ``{"plunge": f/3, "reduced": 0.9*f, "cutting": f}`` - exactly the
    set ``docs/behavior/adaptive.md`` R8 measured in every capture.  No fourth
    value can be produced from here (R12: the group selects, never modulates).
    """
    if feed_cutting <= 0:
        raise ValueError(f"feed_cutting must be positive, got {feed_cutting}")
    return {
        "plunge": feed_cutting / FEED_PLUNGE_DIVISOR,
        "reduced": feed_cutting * FEED_REDUCED_FACTOR,
        "cutting": feed_cutting,
    }


def select_feed(
    ae: float,
    tool_diameter: float,
    feed_cutting: float,
    engagement_gate: float = DEFAULT_ENGAGEMENT_GATE,
    is_plunge: bool = False,
) -> float:
    """Select ONE value of the measured vocabulary for a move.

    Args:
        ae: radial engagement of the move in mm (ignored for a plunge).
        tool_diameter: cutter diameter ``D`` in mm, the gate's scale.
        feed_cutting: base ``tool_feedCutting`` in mm/min.
        engagement_gate: threshold as a fraction of ``D`` in ``(0, 1]``.
        is_plunge: True for a vertical entry move, which is priced at
            ``tool_feedPlunge`` regardless of its radial engagement.

    Returns one of ``{feed/3, 0.9*feed, feed}`` and never anything else.
    """
    vocabulary = feed_vocabulary(feed_cutting)
    if is_plunge:
        return vocabulary["plunge"]
    # THE GUARDED SELECTION LINE: engagement picks the value, it never scales it.
    return (
        vocabulary["reduced"]
        if ae >= engagement_gate * tool_diameter
        else vocabulary["cutting"]
    )


def ring_engagement(
    is_first_ring: bool,
    band_mm: float,
    tool_diameter: float,
    slot_half_width_mm: float,
) -> float:
    """Radial engagement ``ae`` (mm) opened by one offset ring.

    * First ring: the cutter is fully surrounded in fresh material (a slot
      across the footprint), so ``ae`` is the full diameter, bounded by the
      material actually present on both sides of the slot line -
      ``min(D, 2 * slot_half_width)``.
    * Any later ring: it opens the band between the previously cleared reach
      and its own reach, i.e. ``band_mm`` (the ring spacing), bounded by the
      cutter - ``min(D, max(0, band_mm))``.
    """
    if is_first_ring:
        return min(tool_diameter, 2.0 * slot_half_width_mm)
    return min(tool_diameter, max(0.0, band_mm))


class AdaptiveEngagementStrategy(BaseStrategy):
    """Adaptive roughing with an engagement-gated feed (feature F1).

    See the module docstring for the geometry, the gate and the citations.
    """

    @property
    def name(self) -> str:
        return "adaptive_engagement"

    @property
    def description(self) -> str:
        return "Adaptive roughing with engagement-gated feed (F1)"

    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate the operation before an F1 toolpath is generated."""
        errors: list[str] = []

        if operation.tool is None:
            errors.append("Tool definition is required")
        elif operation.tool.diameter <= 0:
            errors.append("Tool diameter must be positive")

        if operation.stock is None:
            errors.append("Stock definition is required")
        elif operation.tool is not None and operation.tool.diameter > 0:
            half = min(operation.stock.size.x, operation.stock.size.y) / 2.0
            if half < operation.tool.radius:
                errors.append(
                    f"Stock footprint {operation.stock.size.x:.3f} x "
                    f"{operation.stock.size.y:.3f} mm is narrower than the "
                    f"tool radius {operation.tool.radius:.3f} mm"
                )

        if operation.stepover <= 0 or operation.stepover > 0.5:
            errors.append(
                f"Stepover for adaptive engagement should be in (0, 0.5], "
                f"got {operation.stepover}"
            )

        if operation.stepdown <= 0:
            errors.append(f"Stepdown must be positive, got {operation.stepdown}")

        if operation.feed_rate <= 0:
            errors.append(f"Feed rate must be positive, got {operation.feed_rate}")

        if operation.top_of_stock < operation.bottom_of_stock:
            errors.append(
                f"top_of_stock {operation.top_of_stock} must not be below "
                f"bottom_of_stock {operation.bottom_of_stock}"
            )

        gate = operation.extra_args.get(
            "engagement_gate", DEFAULT_ENGAGEMENT_GATE
        )
        if not isinstance(gate, (int, float)) or not 0.0 < float(gate) <= 1.0:
            errors.append(
                f"engagement_gate must be a fraction of the tool diameter "
                f"in (0, 1], got {gate!r}"
            )

        return errors

    # ------------------------------------------------------------------
    # Toolpath generation
    # ------------------------------------------------------------------

    def generate_toolpath(
        self,
        stock: BBox,
        tool: ToolDef,
        **kwargs: Any,
    ) -> ToolpathData:
        """Clear the stock footprint level by level with gated feeds.

        Args:
            stock: bounding box of the stock (the machining footprint).
            tool: cutter definition.
            **kwargs: ``stepover`` (fraction of D), ``stepdown`` (mm),
                ``feed_rate`` (mm/min, the vocabulary's ``feed``),
                ``spindle_speed``, ``clearance_height``, ``top_of_stock``,
                ``bottom_of_stock``, ``engagement_gate`` (fraction of D).

        Returns:
            ToolpathData whose cutting moves carry only the three measured
            feed values; rapids carry ``feed = 0`` (no feed word).
        """
        stepover_frac = float(kwargs.get("stepover", 0.4))
        stepdown = float(kwargs.get("stepdown", 2.0))
        feed_cutting = float(kwargs.get("feed_rate", 1000.0))
        speed = float(kwargs.get("spindle_speed", 12000.0))
        clearance = float(kwargs.get("clearance_height", 5.0))
        top_z = float(kwargs.get("top_of_stock", stock.max.z))
        bottom_z = float(kwargs.get("bottom_of_stock", stock.min.z))
        gate = float(kwargs.get("engagement_gate", DEFAULT_ENGAGEMENT_GATE))

        diameter = tool.diameter
        radius = tool.radius
        spacing = diameter * stepover_frac

        half_x = stock.size.x / 2.0
        half_y = stock.size.y / 2.0
        cx = stock.center.x
        cy = stock.center.y
        slot_half_width = min(half_x, half_y)

        # `run()` validates first; a direct generate_toolpath() call can still
        # arrive here with a footprint the cutter cannot enter.
        if slot_half_width < radius or spacing <= 0.0 or top_z < bottom_z:
            return ToolpathData(
                name="Adaptive Engagement",
                tool=tool,
                strategy=self.name,
                params={"error": "stock too small for this tool"},
            )

        levels = _z_levels(top_z, bottom_z, stepdown)
        rings = _ring_insets(slot_half_width, radius, spacing)

        moves: list[Move] = []
        feed_counts: dict[float, int] = {}
        engagements: list[float] = []

        def _rapid(end: Vec3) -> None:
            moves.append(
                Move(
                    move_type=MoveType.RAPID,
                    end=end,
                    feed=0.0,
                    spindle_speed=speed,
                )
            )

        def _cut(end: Vec3, ae: float, is_plunge: bool = False) -> None:
            feed = select_feed(ae, diameter, feed_cutting, gate, is_plunge)
            moves.append(
                Move(
                    move_type=MoveType.LINEAR,
                    end=end,
                    feed=feed,
                    spindle_speed=speed,
                )
            )
            feed_counts[feed] = feed_counts.get(feed, 0) + 1
            engagements.append(ae)

        for level_index, z in enumerate(levels):
            z_prev = top_z if level_index == 0 else levels[level_index - 1]

            # Entry point: the far end of the deepest ring's slot line, so the
            # slot cut finishes on corner A and every later ring connects from
            # A to A of the next ring outward.
            hx0 = half_x - rings[0]
            hy0 = half_y - rings[0]
            if hy0 <= 1e-9 and hx0 > 1e-9:
                entry = Vec3(cx + hx0, cy, z)
            elif hx0 <= 1e-9 and hy0 > 1e-9:
                entry = Vec3(cx, cy + hy0, z)
            else:
                entry = Vec3(cx, cy, z)

            _rapid(Vec3(entry.x, entry.y, clearance))
            _rapid(Vec3(entry.x, entry.y, z_prev))
            if z < z_prev - 1e-9:
                # Vertical entry: priced at tool_feedPlunge = feed / 3.
                _cut(Vec3(entry.x, entry.y, z), 0.0, is_plunge=True)

            pos = entry
            prev_inset: float | None = None
            for ring_index, inset in enumerate(rings):
                hx = half_x - inset
                hy = half_y - inset

                if ring_index == 0:
                    ae = ring_engagement(True, 0.0, diameter, slot_half_width)
                    if hx <= 1e-9 and hy <= 1e-9:
                        # Square footprint: the deepest "ring" is a point and
                        # the plunge above is the fresh full-width cut.
                        prev_inset = inset
                        continue
                    target = Vec3(cx - hx, cy - hy, z)
                    if target.x != pos.x or target.y != pos.y:
                        _cut(target, ae)
                        pos = target
                else:
                    # prev_inset is always set here: ring 0 assigns it on both
                    # of its branches (slot line and degenerate point).
                    band = (prev_inset if prev_inset is not None else inset) - inset
                    ae = ring_engagement(False, band, diameter, slot_half_width)
                    corner_a = Vec3(cx - hx, cy - hy, z)
                    corner_b = Vec3(cx + hx, cy - hy, z)
                    corner_c = Vec3(cx + hx, cy + hy, z)
                    corner_d = Vec3(cx - hx, cy + hy, z)
                    # corner_a first: that is the outward step from the
                    # previous ring, opening the same fresh band.
                    for target in (corner_a, corner_b, corner_c, corner_d, corner_a):
                        _cut(target, ae)
                        pos = target
                prev_inset = inset

            _rapid(Vec3(pos.x, pos.y, clearance))

        vocabulary = feed_vocabulary(feed_cutting)
        params: dict[str, Any] = {
            "tool_diameter": diameter,
            "stepover_mm": spacing,
            "stepdown": stepdown,
            "engagement_gate": gate,
            "gate_mm": gate * diameter,
            "feed_vocabulary": {
                key: round(value, 6) for key, value in vocabulary.items()
            },
            "feed_histogram": {
                f"{value:.6f}": count
                for value, count in sorted(feed_counts.items())
            },
            "levels": len(levels),
            "rings_per_level": len(rings),
            "moves": len(moves),
        }
        if engagements:
            params["engagement_min_mm"] = min(engagements)
            params["engagement_max_mm"] = max(engagements)

        return ToolpathData(
            name="Adaptive Engagement",
            tool=tool,
            moves=moves,
            strategy=self.name,
            params=params,
        )


# ---------------------------------------------------------------------------
# helpers (module level so the tests can pin them directly)
# ---------------------------------------------------------------------------

def _z_levels(top_z: float, bottom_z: float, stepdown: float) -> list[float]:
    """Cutting levels from ``top_z - stepdown`` down to ``bottom_z``.

    The first level sits one stepdown BELOW the stock top, so the level
    actually removes material; the stock bottom is always a level of its own.
    """
    levels: list[float] = []
    z = top_z - stepdown
    while z > bottom_z + 1e-9:
        levels.append(z)
        z -= stepdown
    levels.append(bottom_z)
    return levels


def _ring_insets(d0: float, radius: float, spacing: float) -> list[float]:
    """Inset of every offset ring, deepest first (inside-out clearing).

    ``d0`` is the deepest inset where the tool-centre rectangle degenerates to
    a line; the outermost ring stops at ``radius`` so the cutter's edge lands
    exactly on the footprint boundary (no overhang, no leftover margin).
    """
    insets: list[float] = []
    inset = d0
    while True:
        insets.append(inset)
        if inset <= radius + 1e-9:
            break
        inset = max(radius, inset - spacing)
    return insets
