"""
Canned-cycle drilling - feature **F3** (``Fusion 360 RE/docs/p5-execution-plan.md``
section 4, row P5/5).

This module is a *port*, not a re-derivation.  The reference is the read-only
clean-room implementation in the umbrella repo, ``impl/drilling`` (model, cycles,
emitter), which was itself rebuilt from the EXP-013 capture corpus and is gated
by ``impl/drilling/run_parity.py``.  What is ported here is the *behaviour*, so
the two implementations can be measured against each other on the same pinned
fixture; what is NOT ported is any corpus or cross-repo import - every fixture
used by this repository's tests is built in-process.

Reference -> port mapping
----------------=========
===============================  =============================================
``impl/drilling/model.py``       :class:`Hole`, :class:`CycleConfig`,
                                  ``round6``, ``select_holes``, ``order_holes``,
                                  ``check_order_mode``, ``resolve_cycle_type``,
                                  :class:`UngroundedCycleError`
``impl/drilling/cycles.py``      ``hole_bottom``, ``cycle_body`` and the three
                                  measured constants
``impl/drilling/emitter.py``     :func:`emit_moves` (the move grammar) and
                                  ``to_float32`` / ``post_feed``
``impl/drilling/parity.py``      not ported - the oracle stays on the reference
                                  side (gate 3 measures this module against it)
===============================  =============================================

Geometry inputs
---------------
* The strategy takes a **hole table** (``holes``): ``(x, y, top_z, bottom_z,
  diameter)`` per hole, as dicts or 5-tuples.  It performs no feature
  recognition - the plan rules that out (``docs/p5-execution-plan.md``
  section 3.3, "needs feature recognition"), and the reference takes its hole
  table from the capture's posted body for the same reason.  The measured
  feature inventory of the S1 real part is evidence, not an input: see
  ``Fusion 360 RE/tests/p5_evidence/p5_5_s1_hole_inventory_final.txt``.
* Machining planes follow the reference's measured modes (drilling.md R9):
  ``retract_z = stock_top + retract_height_offset`` and
  ``clearance_z = retract_z + clearance_height_offset``, both rounded with
  ``round6``.  ``stock_top`` / ``stock_bottom`` come from the ``stock`` BBox, or
  from the explicit ``stock_top_z`` / ``stock_bottom_z`` keywords when a caller
  carries them elsewhere.  ``OperationParams.top_of_stock`` /
  ``bottom_of_stock`` / ``clearance_height`` are NOT read - see "Honest limits".

Feeds
-----
``resolved_feed_plunge`` reproduces the measured creation-snapshot expression
``(tool_type == 'drill' or 'reamer' or depositing) ? 1000 : tool_feedCutting/3``
(drilling.md R13), and every feed that reaches a move is serialized exactly as
the Fusion post writes it - IEEE-754 binary32 then ``round6`` - so a
``flat end mill`` at ``tool_feedCutting = 1000`` carries **333.333344** and not
333.333333.  ``tool_diameter`` defaults to the tool passed in and
``tool_feed_cutting`` defaults to ``OperationParams.feed_rate``; both may be
overridden in ``cycle``.

Vocabulary (measured, build 2705.1.25)
--------------------------------------
* cycle types written by EXP-013: ``drilling``, ``counter-boring``,
  ``chip-breaking``, ``deep-drilling``; the other seven legal Choice values
  raise :class:`UngroundedCycleError` instead of guessing a body.
* ``holeToolpathOrder``: ``order-selected``, ``optimize-order``,
  ``order-inside-out``, ``order-by-x``, ``order-by-y`` - with
  ``order-inside-out`` never swept, so it raises as well.

Honest limits (carried from the reference's DECLARED GAPS; none fixed here)
--------------------------------------------------------------------------
1. **``order-by-x`` does not sort by X on this build.**  The capture visits
   ``[h2, h3, h1]``; the rebuild ships the literal parameter-name reading
   (X-ascending) and reports the mismatch.  This is the campaign's **declared
   ``order/ord_x`` fail**: gate 1 stays ``overall: fail (29/30 rows pass)`` and
   this port reproduces the reference's behaviour *unchanged*, so the port
   fails that row against the capture for exactly the same reason.  Fixing it
   is out of scope for P5/5.
2. **``PECK_ANCHOR_MM = 5.0`` and ``DEEP_REENTRY_OVERLAP_MM = 2.0``** are
   measured values whose *attribution* is unknown (two 5 mm creation
   parameters; ``incrementalDepth = 2mm`` schema-only).  Values are not
   invented; the attribution stays open.
3. **The chip-break full-clear trigger is one observation** (``cyc_chip``
   holes 2/3 at peck 10); "remaining depth < 0.4 mm" and "peck index >= 10"
   fit it equally.
4. **Break-through x peck is unobserved** - the sweep applied
   ``breakThroughDepth`` only to plain ``drilling``.
5. **``topHeight_offset`` / ``bottomHeight_offset`` arithmetic is an
   extrapolation**: both are 0 mm in the creation snapshot, but the emitter
   applies them because that is what the parameters mean.
6. **Dead at this capture boundary** (implemented, no observed effect on the
   fixture): ``retractionPolicy``, ``tolerance``, ``startingDepthOffset``,
   ``peckingDepthReduction``, ``dwellingPeriod``, ``dwellBeforeRetract``,
   ``feedHeightOffset``, ``reverseOrder`` is measured, ``numberOfHoles``.
7. **No canned G81/G83 is emitted.**  The reference posts an *expanded* move
   body (that is what ``export_jsonl.cps`` writes and what the parity gate
   compares), so this strategy returns expanded ``RAPID``/``LINEAR`` moves;
   ``MoveType.DRILL`` and the Fanuc ``G81`` branch in ``post/fanuc.py`` stay
   unused by F3.  Canned-word output would be a different, unmeasured claim.
8. **Planes ignore ``OperationParams.clearance_height``** (limit above): the
   clearance plane is ``retract + 10 mm`` as measured, so a UI clearance knob
   cannot silently change measured behaviour.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, Move, MoveType, ToolpathData, ToolDef, Vec3

# ---------------------------------------------------------------------------
# vocabulary (legal values measured on build 2705.1.25 - drilling.md R5/R10)
# ---------------------------------------------------------------------------

#: cycle types EXP-013 actually captured a posted body for.
MEASURED_CYCLE_TYPES = (
    "drilling",
    "counter-boring",
    "chip-breaking",
    "deep-drilling",
)

#: cycle types the Choice parameter exposes but EXP-013 never wrote (R5, Q4).
UNMEASURED_CYCLE_TYPES = (
    "break-through-drilling",
    "gun-drilling",
    "tapping",
    "reaming",
    "boring",
    "thread-milling",
    "probe",
)

#: legal ``holeToolpathOrder`` values (drilling.md R10).
ORDER_MODES = (
    "order-selected",
    "optimize-order",
    "order-inside-out",
    "order-by-x",
    "order-by-y",
)

#: ``order-inside-out`` was never swept by EXP-013 - no capture decides it.
UNMEASURED_ORDER_MODES = ("order-inside-out",)

#: move-type vocabulary of the expanded posted body (export_jsonl.cps).
MOVE_RAPID = "rapid"
MOVE_LINEAR = "linear"


class UngroundedCycleError(ValueError):
    """Raised when a configuration asks for semantics no capture supports.

    The honest response to an ungrounded cycle is to refuse to invent it, so
    this is an error and not a plausible-looking fallback.  The strategy-level
    API (:meth:`DrillingStrategy.generate_toolpath`) converts it into a
    ``ToolpathData`` carrying ``params["error"]`` - the repository convention -
    while direct callers of the library functions below get the exception.
    """


# ---------------------------------------------------------------------------
# serializer primitives (export_jsonl.cps:94 and jnum)
# ---------------------------------------------------------------------------


def round6(value: float) -> float:
    """``Math.round(value * 1e6) / 1e6`` - the post's serializer.

    JS ``Math.round`` rounds half UP (toward +Infinity) for both signs, i.e.
    ``floor(x + 0.5)`` - not Python's banker's rounding.
    """
    return float(math.floor(value * 1e6 + 0.5)) / 1e6


def to_float32(value: float) -> float:
    """Round-trip through IEEE-754 binary32, the width Fusion stores feeds in."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def post_feed(value: float) -> float:
    """Feed exactly as ``jnum(feed)`` serializes it: round6(float32(v))."""
    return round6(to_float32(value))


# ---------------------------------------------------------------------------
# geometry + configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hole:
    """One hole feature.

    ``top_z`` / ``bottom_z`` are the *feature* planes: the cut starts at the
    hole top and ends at the hole bottom (``topHeight_mode`` /
    ``bottomHeight_mode`` with 0 mm offsets in the EXP-013 creation snapshot).
    ``diameter`` is only consumed by the range selection (R4/R11).
    """

    index: int
    x: float
    y: float
    top_z: float
    bottom_z: float
    diameter: float

    @property
    def key(self) -> tuple[float, float]:
        return (self.x, self.y)


#: ``CycleConfig`` field names, in declaration order.  Also the accepted key
#: set of the ``cycle`` keyword - anything else is a validation error, so a
#: typo can never be silently ignored.
CYCLE_FIELDS: tuple[str, ...] = (
    "hole_diameter_minimum",
    "hole_diameter_maximum",
    "cycle_type",
    "pecking_depth",
    "pecking_depth_reduction",
    "dwelling_period_s",
    "dwell_before_retract",
    "break_through_depth",
    "drill_tip_through_bottom",
    "starting_depth_offset",
    "top_height_offset",
    "bottom_height_offset",
    "retract_height_offset",
    "clearance_height_offset",
    "feed_height_offset",
    "retraction_policy",
    "hole_toolpath_order",
    "reverse_order",
    "tool_feed_plunge",
    "tool_feed_cutting",
    "tolerance",
    "tool_diameter",
    "tool_type",
    "tool_is_depositing",
)

#: fields that must be a finite number (``None`` is legal for the optional ones).
NUMERIC_FIELDS = frozenset({
    "hole_diameter_minimum", "hole_diameter_maximum", "pecking_depth",
    "pecking_depth_reduction", "dwelling_period_s", "break_through_depth",
    "starting_depth_offset", "top_height_offset", "bottom_height_offset",
    "retract_height_offset", "clearance_height_offset", "feed_height_offset",
    "tool_feed_plunge", "tool_feed_cutting", "tolerance", "tool_diameter",
})
#: numeric fields where ``None`` means "evaluate the stored expression".
OPTIONAL_NUMERIC_FIELDS = frozenset({
    "pecking_depth", "starting_depth_offset", "tool_feed_plunge", "tolerance",
})
BOOL_FIELDS = frozenset({
    "dwell_before_retract", "drill_tip_through_bottom", "reverse_order",
    "tool_is_depositing",
})
STRING_FIELDS = frozenset({
    "cycle_type", "retraction_policy", "hole_toolpath_order", "tool_type",
})


@dataclass(frozen=True)
class CycleConfig:
    """The swept + stored state of one drill operation.

    Defaults are the *evaluated* creation-snapshot values of the EXP-013
    control capture (``created_params.json``); the reference pins the verbatim
    expressions in ``impl/drilling/fixture.py`` and asserts them against the
    corpus.  They are transcribed here so a caller that passes nothing gets the
    measured baseline rather than an invented one.
    """

    # -- selection (R4, R11)
    hole_diameter_minimum: float = 0.0
    hole_diameter_maximum: float = 100.0

    # -- cycle control (R5, R6, R7, R8)
    cycle_type: str = "drilling"
    pecking_depth: float | None = None       # None -> stored expr tool_diameter * 0.25
    pecking_depth_reduction: float = 0.0      # measured DEAD (R6)
    dwelling_period_s: float = 0.0            # measured DEAD at this boundary (R7)
    dwell_before_retract: bool = False        # measured DEAD at this boundary (R7)
    break_through_depth: float = 0.0
    drill_tip_through_bottom: bool = False
    starting_depth_offset: float | None = None  # measured DEAD (R8)
    top_height_offset: float = 0.0
    bottom_height_offset: float = 0.0

    # -- linking / retract (R9)
    retract_height_offset: float = 5.0
    clearance_height_offset: float = 10.0
    feed_height_offset: float = 5.0           # recorded; never observed as a move
    retraction_policy: str = "minimum"        # measured DEAD for this fixture (R9)

    # -- ordering (R10)
    hole_toolpath_order: str = "optimize-order"
    reverse_order: bool = False

    # -- output (R13)
    tool_feed_plunge: float | None = None     # None -> evaluate the stored conditional
    tool_feed_cutting: float = 1000.0
    tolerance: float | None = None            # measured DEAD (R12)

    # -- tool geometry (creation snapshot)
    tool_diameter: float = 3.175
    tool_type: str = "flat end mill"
    tool_is_depositing: bool = False

    # ------------------------------------------------------------------
    # derived quantities
    # ------------------------------------------------------------------
    @property
    def peck_gate_open(self) -> bool:
        """``peckingDepth`` is live only behind these two cycle types (R5/R6)."""
        return self.cycle_type in ("deep-drilling", "chip-breaking")

    @property
    def resolved_pecking_depth(self) -> float:
        if self.pecking_depth is not None:
            return self.pecking_depth
        return self.tool_diameter * 0.25  # creation expr, C:4154

    @property
    def chip_break_distance(self) -> float:
        """``Math.max(tool_diameter * 0.02; 0.1mm)`` - creation expr, measured 0.1."""
        return max(self.tool_diameter * 0.02, 0.1)

    @property
    def accumulated_pecking_depth(self) -> float:
        """``Math.max(tool_diameter * 2.5; peckingDepth)`` - creation expr."""
        return max(self.tool_diameter * 2.5, self.resolved_pecking_depth)

    @property
    def resolved_feed_plunge(self) -> float:
        """``(tool_type=='drill' || 'reamer' || isDepositing) ? 1000 : feedCutting/3``.

        The EXP-013 tool is a ``flat end mill``, so the measured branch is the
        ``else`` arm: 1000/3 = 333.333333... which the post serialises as
        333.333344 (float32 then round6).
        """
        if self.tool_feed_plunge is not None:
            return self.tool_feed_plunge
        if self.tool_type in ("drill", "reamer") or self.tool_is_depositing:
            return 1000.0
        return self.tool_feed_cutting / 3.0

    def with_(self, **kw: Any) -> "CycleConfig":
        return replace(self, **kw)


# ---------------------------------------------------------------------------
# selection (R4, R11) and ordering (R10)
# ---------------------------------------------------------------------------


def select_holes(holes: Sequence[Hole], cfg: CycleConfig) -> list[Hole]:
    """Keep holes whose diameter lies inside [minimum, maximum]; inclusive.

    An empty result is a *silent* no-toolpath state, not an error (R11), so
    this returns ``[]`` rather than raising.
    """
    return [h for h in holes
            if cfg.hole_diameter_minimum <= h.diameter <= cfg.hole_diameter_maximum]


def _xy_dist(a: Hole, b: Hole) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _nearest_neighbour(holes: Sequence[Hole]) -> list[Hole]:
    """Greedy open path anchored at the first hole, then 2-opt."""
    remaining = list(holes)
    path = [remaining.pop(0)]
    while remaining:
        cur = path[-1]
        best = min(range(len(remaining)), key=lambda i: (_xy_dist(cur, remaining[i]),
                                                         remaining[i].index))
        path.append(remaining.pop(best))
    improved = True
    while improved:
        improved = False
        for i in range(1, len(path) - 1):
            for j in range(i + 1, len(path)):
                a = path[i - 1]
                b, c = path[i], path[j]
                d = path[j + 1] if j + 1 < len(path) else None
                before = _xy_dist(a, b) + (_xy_dist(c, d) if d else 0.0)
                alt = _xy_dist(a, c) + (_xy_dist(b, d) if d else 0.0)
                if alt < before - 1e-12:
                    path[i:j + 1] = reversed(path[i:j + 1])
                    improved = True
    return path


def check_order_mode(mode: str) -> None:
    """Validate ``holeToolpathOrder`` against this build (R10) - no geometry.

    Split out of :func:`order_holes` so the emitter can refuse an illegal or
    unmeasured order mode even when the diameter selection comes back empty
    (otherwise an empty selection would bypass the honest-blocker check).
    """
    if mode not in ORDER_MODES:
        raise UngroundedCycleError(
            f"holeToolpathOrder {mode!r} is not a legal value on build 2705.1.25 "
            f"(legal: {', '.join(ORDER_MODES)})")
    if mode in UNMEASURED_ORDER_MODES:
        raise UngroundedCycleError(
            f"holeToolpathOrder={mode!r} was never written by EXP-013; no capture "
            f"decides its geometry. Resolving capture: a `order/ord_inside` sweep "
            f"point on the EXP-013 fixture (write holeToolpathOrder='order-inside-out').")


def order_holes(holes: Sequence[Hole], mode: str, reverse: bool = False) -> list[Hole]:
    """Apply ``holeToolpathOrder`` then ``reverseOrder`` (R10).

    ``optimize-order`` is an open-path optimizer anchored at the first hole;
    ``order-by-x`` / ``order-by-y`` are literal sorts of the parameter name -
    and the literal reading of ``order-by-x`` is the campaign's declared
    ``order/ord_x`` fail (see the module docstring, Honest limits #1).
    """
    check_order_mode(mode)
    seq = list(holes)
    if mode == "optimize-order":
        seq = _nearest_neighbour(seq)
    elif mode == "order-by-x":
        seq = sorted(seq, key=lambda h: h.x)
    elif mode == "order-by-y":
        seq = sorted(seq, key=lambda h: h.y)
    # 'order-selected' -> fixture order
    if reverse:
        seq = seq[::-1]
    return seq


def resolve_cycle_type(cycle_type: str) -> str:
    """Validate a cycle type against what this build has been measured on."""
    if cycle_type in MEASURED_CYCLE_TYPES:
        return cycle_type
    if cycle_type in UNMEASURED_CYCLE_TYPES:
        raise UngroundedCycleError(
            f"cycleType={cycle_type!r} is a legal Choice value but EXP-013 never "
            f"wrote it (drilling.md R5/Q4), so no posted body exists to rebuild "
            f"from. Resolving capture: one sweep point writing "
            f"cycleType='{cycle_type}' on the EXP-013 fixture.")
    raise UngroundedCycleError(
        f"cycleType={cycle_type!r} is not a legal value on build 2705.1.25 "
        f"(measured: {', '.join(MEASURED_CYCLE_TYPES)})")


# ---------------------------------------------------------------------------
# cycle expansion (impl/drilling/cycles.py)
# ---------------------------------------------------------------------------

#: First peck ends ``PECK_ANCHOR_MM`` below the hole top *plus* one peck:
#: ``E_k = top - (k * pecking_depth + PECK_ANCHOR_MM)``.  Measured on 6
#: (cycle x peck) combinations x 3 holes x 3 runs; the value 5.000 mm is
#: measured, its attribution is a declared gap (Honest limits #2).
PECK_ANCHOR_MM = 5.0

#: Re-entry depth after a full-retract peck: the tool plunges to
#: ``previous_end + DEEP_REENTRY_OVERLAP_MM``.  Measured = 2.000 mm; the
#: attribution (``incrementalDepth = 2mm``, schema-only) is a declared gap.
DEEP_REENTRY_OVERLAP_MM = 2.0

#: The chip-breaking full-retract trigger label; see Honest limits #3.
ACCUMULATED_TRIGGER = "accumulated_pecking_depth"

#: Hard ceiling on the peck schedule of one hole.  A sweep record can carry an
#: absurd ``peckingDepth``; measured maxima through this guard are 18 pecks
#: (control) / 15 pecks (1 mm sweep), so a ceiling 555x that can never hide a
#: value EXP-013 wrote - anything past it is refused rather than expanded.
MAX_PECK_STEPS = 10_000


def hole_bottom(hole_bottom_z: float, cfg: CycleConfig) -> float:
    """``breakThroughDepth`` only bites when ``drillTipThroughBottom`` is on (R8).

    Measured: both switches -> -12.3 becomes -13.3 (exactly 1 mm deeper);
    either alone -> unchanged.
    """
    if cfg.drill_tip_through_bottom and cfg.break_through_depth:
        return hole_bottom_z - cfg.break_through_depth
    return hole_bottom_z


def cycle_body(top_z: float, bottom_z: float, cfg: CycleConfig,
               retract_z: float) -> list[tuple[str, float]]:
    """Return the ``(kind, z)`` body for ONE hole, entry rapid included.

    ``kind`` is ``"rapid"`` (no feed) or ``"linear"`` (plunge feed).
    """
    cfg = cfg.with_(cycle_type=resolve_cycle_type(cfg.cycle_type))
    out: list[tuple[str, float]] = [("rapid", round6(top_z))]

    if not cfg.peck_gate_open:
        # 'drilling' and 'counter-boring': one plunge.  Counter-boring adds no
        # move at this capture boundary (R5: identical body, header only).
        out.append(("linear", round6(bottom_z)))
        return out

    peck = cfg.resolved_pecking_depth
    if peck <= 0.0:
        raise UngroundedCycleError(
            f"peckingDepth={peck} with cycleType={cfg.cycle_type!r} produces an "
            f"empty peck schedule; EXP-013 never wrote a non-positive peck")
    steps = int((top_z - bottom_z) // peck) + 2
    if steps > MAX_PECK_STEPS:
        raise UngroundedCycleError(
            f"peckingDepth={peck} over {top_z - bottom_z:.6f} mm would expand to "
            f"at most {steps} pecks (ceiling {MAX_PECK_STEPS}); EXP-013 never wrote "
            f"a peck below {(top_z - bottom_z) / MAX_PECK_STEPS:.9f} mm, so the "
            f"schedule is refused instead of expanded.")
    chip = cfg.cycle_type == "chip-breaking"
    accumulated = 0.0
    k = 0
    while True:
        k += 1
        accumulated += peck
        raw = top_z - (k * peck + PECK_ANCHOR_MM)
        if raw <= bottom_z:
            end = bottom_z          # final peck is clipped by the hole bottom
        else:
            end = raw
        out.append(("linear", round6(end)))
        if raw <= bottom_z:
            return out
        if chip:
            if accumulated + 1e-9 >= cfg.accumulated_pecking_depth:
                # full retract to the RETRACT PLANE (not the hole top), then
                # re-enter at the same +2 mm overlap deep-drilling uses.
                out.append(("rapid", round6(retract_z)))
                out.append(("rapid", round6(end + DEEP_REENTRY_OVERLAP_MM)))
                accumulated = 0.0
            else:
                out.append(("rapid", round6(end + cfg.chip_break_distance)))
        else:
            out.append(("rapid", round6(top_z)))   # full retract to the hole top
            out.append(("rapid", round6(end + DEEP_REENTRY_OVERLAP_MM)))


# ---------------------------------------------------------------------------
# the emitter (impl/drilling/emitter.py)
# ---------------------------------------------------------------------------


def planes(stock_top_z: float, cfg: CycleConfig) -> tuple[float, float]:
    """``(retract_z, clearance_z)`` - drilling.md R9 modes, both round6'd."""
    retract_z = round6(stock_top_z + cfg.retract_height_offset)
    return retract_z, round6(retract_z + cfg.clearance_height_offset)


def emit_moves(holes: Sequence[Hole], cfg: CycleConfig, stock_top_z: float,
               spindle_speed: float = 0.0) -> list[Move]:
    """Build the expanded posted body for one operation as kernel moves.

    Move grammar per hole (after the two positioning rapids):

        rapid  -> hole top                 entry
        <cycle body>                       one or more (rapid | linear) pairs
        rapid  -> retract plane            end-of-hole retract

    Program approach is home -> first hole on the clearance plane; program exit
    is last hole -> clearance plane.  Rapids carry ``feed = 0.0`` (kernel
    convention) where the reference records ``feed: null`` - the two encode the
    same "no feed word" and the fidelity measurement maps one onto the other.

    Returns ``[]`` when the diameter range selects nothing: an empty selection
    is a silent no-toolpath state (R11), not an error.  The ungrounded-cycle
    and order-mode checks run BEFORE that short-circuit, so an empty selection
    can never smuggle an unmeasured ``cycleType`` past the honest-blocker check.

    Raises:
        UngroundedCycleError: unmeasured cycle type / order mode, or a peck
            schedule that cannot be grounded.
    """
    resolve_cycle_type(cfg.cycle_type)
    check_order_mode(cfg.hole_toolpath_order)
    selected = select_holes(holes, cfg)
    if not selected:
        return []
    seq = order_holes(selected, cfg.hole_toolpath_order, cfg.reverse_order)

    retract_z, clearance_z = planes(stock_top_z, cfg)
    feed = post_feed(cfg.resolved_feed_plunge)

    moves: list[Move] = []

    def add(kind: str, x: float, y: float, z: float,
            move_feed: float | None = None) -> None:
        moves.append(Move(
            move_type=MoveType.RAPID if kind == MOVE_RAPID else MoveType.LINEAR,
            end=Vec3(round6(x), round6(y), round6(z)),
            feed=0.0 if move_feed is None else move_feed,
            spindle_speed=spindle_speed,
        ))

    # program approach: home -> first hole on the clearance plane
    first = seq[0]
    add(MOVE_RAPID, first.x, first.y, clearance_z)
    plane = clearance_z

    for hole in seq:
        # travel to this hole at whatever plane the tool currently sits on
        # (clearance for the first hole, retract for every later one), then
        # move to the retract plane - a no-op on later holes, exactly as posted.
        add(MOVE_RAPID, hole.x, hole.y, plane)
        add(MOVE_RAPID, hole.x, hole.y, retract_z)
        plane = retract_z

        top = round6(hole.top_z + cfg.top_height_offset)
        bottom = round6(hole_bottom(hole.bottom_z, cfg) - cfg.bottom_height_offset)
        for kind, z in cycle_body(top, bottom, cfg, retract_z):
            if kind == MOVE_LINEAR:
                add(MOVE_LINEAR, hole.x, hole.y, z, feed)
            else:
                add(MOVE_RAPID, hole.x, hole.y, z)
        add(MOVE_RAPID, hole.x, hole.y, retract_z)

    last = seq[-1]
    add(MOVE_RAPID, last.x, last.y, clearance_z)
    return moves


# ---------------------------------------------------------------------------
# configuration plumbing (validation mirrors the generation path exactly)
# ---------------------------------------------------------------------------


def _normalise_holes(raw: Any) -> tuple[list[Hole], list[str]]:
    """Accept dicts or ``(x, y, top_z, bottom_z, diameter)`` tuples."""
    errors: list[str] = []
    holes: list[Hole] = []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
        return [], ["holes must be a list of dicts or 5-tuples "
                    "(x, y, top_z, bottom_z, diameter)"]
    for i, item in enumerate(raw):
        if isinstance(item, Hole):
            if not all(math.isfinite(v) for v in
                       (item.x, item.y, item.top_z, item.bottom_z,
                        item.diameter)):
                errors.append(f"holes[{i}]: coordinates must be finite numbers")
                continue
            holes.append(item)
            continue
        if isinstance(item, dict):
            missing = [k for k in ("x", "y", "top_z", "bottom_z", "diameter")
                       if k not in item]
            if missing:
                errors.append(f"holes[{i}]: missing key(s) {', '.join(missing)}")
                continue
            try:
                values = [float(item[k]) for k in
                          ("x", "y", "top_z", "bottom_z", "diameter")]
            except (TypeError, ValueError):
                errors.append(f"holes[{i}]: non-numeric coordinate or diameter")
                continue
            index = int(item.get("index", i))
        elif isinstance(item, (tuple, list)) and len(item) == 5:
            try:
                values = [float(v) for v in item]
            except (TypeError, ValueError):
                errors.append(f"holes[{i}]: non-numeric coordinate or diameter")
                continue
            index = i
        else:
            errors.append(f"holes[{i}]: expected a dict or a 5-tuple "
                          f"(x, y, top_z, bottom_z, diameter)")
            continue
        if not all(math.isfinite(v) for v in values):
            errors.append(f"holes[{i}]: coordinates must be finite numbers")
            continue
        holes.append(Hole(index=index, x=values[0], y=values[1],
                          top_z=values[2], bottom_z=values[3],
                          diameter=values[4]))
    return holes, errors


def _build_config(effective: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Split the strategy keywords into a resolved config plus error strings."""
    cfg: dict[str, Any] = {}
    errors: list[str] = []

    raw_cycle = effective.get("cycle", {})
    if raw_cycle is None:
        raw_cycle = {}
    if not isinstance(raw_cycle, dict):
        errors.append("cycle must be a dict of CycleConfig fields")
        raw_cycle = {}
    unknown = sorted(set(raw_cycle) - set(CYCLE_FIELDS))
    if unknown:
        errors.append("cycle: unknown field(s) "
                      + ", ".join(unknown)
                      + " (accepted: " + ", ".join(CYCLE_FIELDS) + ")")
    for name, value in raw_cycle.items():
        if name not in CYCLE_FIELDS:
            continue
        if name in STRING_FIELDS:
            if not isinstance(value, str):
                errors.append(f"cycle.{name}: expected a string, got "
                              f"{type(value).__name__}")
                continue
        elif name in BOOL_FIELDS:
            if not isinstance(value, bool):
                errors.append(f"cycle.{name}: expected a bool, got "
                              f"{type(value).__name__}")
                continue
        elif name in NUMERIC_FIELDS:
            if value is None and name in OPTIONAL_NUMERIC_FIELDS:
                pass
            elif isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                errors.append(f"cycle.{name}: expected a finite number, got "
                              f"{value!r}")
                continue
        cfg[name] = value

    if "holes" in effective and effective["holes"] is not None:
        holes, hole_errors = _normalise_holes(effective["holes"])
        cfg["holes"] = holes
        errors.extend(hole_errors)
    elif "holes" not in effective:
        errors.append("holes is required: the strategy machines a hole table "
                      "(no feature recognition - see the module docstring)")

    for key in ("stock_top_z", "stock_bottom_z"):
        if key in effective and effective[key] is not None:
            try:
                value = float(effective[key])
            except (TypeError, ValueError):
                errors.append(f"{key}: expected a number, got "
                              f"{effective[key]!r}")
                continue
            if not math.isfinite(value):
                errors.append(f"{key}: must be finite")
                continue
            cfg[key] = value

    if "feed_rate" in effective:
        try:
            cfg["feed_rate"] = float(effective["feed_rate"])
        except (TypeError, ValueError):
            errors.append(f"feed_rate: expected a number, got "
                          f"{effective['feed_rate']!r}")
    return cfg, errors


def resolve_config(cfg: dict[str, Any], tool: ToolDef | None = None) -> CycleConfig:
    """Build the frozen ``CycleConfig`` from a validated config dict.

    ``tool_diameter`` falls back to the tool's diameter and ``tool_feed_cutting``
    to ``feed_rate`` - both are the numbers a caller already has, and the
    reference's own defaults (3.175 mm / 1000 mm/min) apply when neither is
    given.
    """
    kw = {name: cfg[name] for name in CYCLE_FIELDS if name in cfg}
    if "tool_diameter" not in kw and tool is not None:
        kw["tool_diameter"] = float(tool.diameter)
    if "tool_feed_cutting" not in kw and cfg.get("feed_rate") is not None:
        kw["tool_feed_cutting"] = float(cfg["feed_rate"])
    return CycleConfig(**kw)


def validate_config(cfg: dict[str, Any], stock: BBox | None,
                    tool: ToolDef | None) -> list[str]:
    """Checks that need the resolved values - the ones generation will use."""
    errors: list[str] = []
    if tool is None:
        errors.append("a tool is required")
    if stock is None:
        errors.append("a stock BBox is required")
    if "holes" not in cfg:
        return errors
    if len(cfg["holes"]) == 0 and cfg.get("hole_diameter_minimum") is None:
        pass  # an empty table is legal: selection may empty it later (R11)

    try:
        cycle = resolve_config(cfg, tool)
    except TypeError as exc:                     # pragma: no cover - guarded above
        return errors + [f"cycle: {exc}"]

    try:
        resolve_cycle_type(cycle.cycle_type)
    except UngroundedCycleError as exc:
        errors.append(str(exc))
    try:
        check_order_mode(cycle.hole_toolpath_order)
    except UngroundedCycleError as exc:
        errors.append(str(exc))

    if cycle.peck_gate_open:
        peck = cycle.resolved_pecking_depth
        if peck <= 0.0:
            errors.append(f"cycle.pecking_depth must be > 0 for "
                          f"{cycle.cycle_type!r}, got {peck}")
        else:
            for hole in select_holes(cfg["holes"], cycle):
                top = round6(hole.top_z + cycle.top_height_offset)
                bottom = round6(hole_bottom(hole.bottom_z, cycle)
                                - cycle.bottom_height_offset)
                steps = int((top - bottom) // peck) + 2
                if steps > MAX_PECK_STEPS:
                    errors.append(
                        f"cycle.pecking_depth={peck} over {top - bottom:.6f} mm "
                        f"would expand to at most {steps} pecks "
                        f"(ceiling {MAX_PECK_STEPS}); the schedule is refused "
                        f"rather than expanded")
                    break
    if cycle.hole_diameter_minimum > cycle.hole_diameter_maximum:
        errors.append("cycle.hole_diameter_minimum must not exceed "
                      "cycle.hole_diameter_maximum")
    if "stock_top_z" in cfg and "stock_bottom_z" in cfg \
            and cfg["stock_top_z"] < cfg["stock_bottom_z"]:
        errors.append("stock_top_z must not be below stock_bottom_z")
    return errors


# ---------------------------------------------------------------------------
# the strategy
# ---------------------------------------------------------------------------


class DrillingStrategy(BaseStrategy):
    """Canned-cycle drilling - feature F3.

    See the module docstring for the reference mapping, the geometry inputs
    and the declared limits.
    """

    @property
    def name(self) -> str:
        return "drilling"

    @property
    def description(self) -> str:
        return ("Canned-cycle drilling: drilling / counter-boring / "
                "deep-drilling / chip-breaking (F3)")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate the operation before an F3 toolpath is generated.

        The numbers checked are the numbers :meth:`BaseStrategy.run` hands to
        :meth:`generate_toolpath`: ``extra_args`` first, then the
        ``OperationParams`` fields that merge fills in.
        """
        effective: dict[str, Any] = dict(operation.extra_args)
        effective.setdefault("feed_rate", operation.feed_rate)
        effective.setdefault("spindle_speed", operation.spindle_speed)
        cfg, errors = _build_config(effective)
        errors.extend(validate_config(cfg, operation.stock, operation.tool))
        return errors

    # ------------------------------------------------------------------
    # Toolpath generation
    # ------------------------------------------------------------------
    def generate_toolpath(self, stock: BBox, tool: ToolDef,
                          **kwargs: Any) -> ToolpathData:
        """Generate the expanded canned-cycle toolpath.

        Args:
            stock: stock bounding box; ``min.z`` / ``max.z`` are the stock
                planes the retract and clearance heights are measured from
                unless ``stock_top_z`` / ``stock_bottom_z`` are passed.
            tool: cutter definition; ``diameter`` feeds ``tool_diameter``.
            **kwargs: ``holes`` (required), ``cycle`` (dict of
                :class:`CycleConfig` fields), ``stock_top_z``,
                ``stock_bottom_z``, plus ``feed_rate`` / ``spindle_speed`` from
                the operation merge.

        Returns:
            ``ToolpathData`` whose rapids carry ``feed = 0.0`` and whose linear
            moves carry the post-serialized plunge feed (333.333344 for the
            measured fixture).  Invalid parameters return an error
            ``ToolpathData`` instead of raising; an empty selection returns an
            empty toolpath with ``holes_selected = 0`` (R11).
        """
        cfg, errors = _build_config(kwargs)
        errors.extend(validate_config(cfg, stock, tool))
        if errors:
            return ToolpathData(
                name="Drilling",
                tool=tool,
                strategy=self.name,
                params={"error": "; ".join(errors)},
            )

        cycle = resolve_config(cfg, tool)
        stock_top = cfg.get("stock_top_z", stock.max.z)
        stock_bottom = cfg.get("stock_bottom_z", stock.min.z)
        holes: list[Hole] = cfg.get("holes", [])
        speed = float(kwargs.get("spindle_speed", 0.0) or 0.0)

        try:
            moves = emit_moves(holes, cycle, stock_top, spindle_speed=speed)
        except UngroundedCycleError as exc:
            return ToolpathData(
                name="Drilling",
                tool=tool,
                strategy=self.name,
                params={"error": str(exc)},
            )

        retract_z, clearance_z = planes(stock_top, cycle)
        selected = select_holes(holes, cycle)
        # An empty selection is a silent no-toolpath state (R11): there is no
        # sequence to optimise, and _nearest_neighbour([]) would raise.
        ordered = (order_holes(selected, cycle.hole_toolpath_order,
                               cycle.reverse_order) if selected else [])
        feed_counts: dict[float, int] = {}
        for move in moves:
            if move.move_type is MoveType.LINEAR:
                feed_counts[move.feed] = feed_counts.get(move.feed, 0) + 1

        params: dict[str, Any] = {
            "cycle_type": cycle.cycle_type,
            "hole_toolpath_order": cycle.hole_toolpath_order,
            "reverse_order": cycle.reverse_order,
            "holes_total": len(holes),
            "holes_selected": len(selected),
            "holes_machined": len(ordered),
            "hole_xy": [[h.x, h.y] for h in ordered],
            "retract_z": retract_z,
            "clearance_z": clearance_z,
            "retract_height_offset": cycle.retract_height_offset,
            "clearance_height_offset": cycle.clearance_height_offset,
            "tool_diameter": cycle.tool_diameter,
            "pecking_depth_mm": (cycle.resolved_pecking_depth
                                 if cycle.peck_gate_open else None),
            "feed_vocabulary": {
                "plunge": round(cycle.resolved_feed_plunge, 6),
                "cutting": round(cycle.tool_feed_cutting, 6),
            },
            "feed_histogram": {
                f"{value:.6f}": count
                for value, count in sorted(feed_counts.items())
            },
            "moves": len(moves),
        }
        return ToolpathData(
            name="Drilling",
            tool=tool,
            moves=moves,
            strategy=self.name,
            params=params,
        )


__all__ = [
    "DrillingStrategy", "CycleConfig", "Hole", "UngroundedCycleError",
    "MEASURED_CYCLE_TYPES", "UNMEASURED_CYCLE_TYPES", "ORDER_MODES",
    "UNMEASURED_ORDER_MODES", "CYCLE_FIELDS", "MOVE_RAPID", "MOVE_LINEAR",
    "PECK_ANCHOR_MM", "DEEP_REENTRY_OVERLAP_MM", "ACCUMULATED_TRIGGER",
    "MAX_PECK_STEPS", "round6", "to_float32", "post_feed", "hole_bottom",
    "cycle_body", "select_holes", "order_holes", "check_order_mode",
    "resolve_cycle_type", "planes", "emit_moves", "resolve_config",
    "validate_config",
]
