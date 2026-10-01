"""
Unit tests for feature F3 - the canned-cycle drilling strategy
(``Fusion 360 RE/docs/p5-execution-plan.md`` section 4, row P5/5).

The reference these were written against is read-only and lives in the
umbrella repo: ``impl/drilling/{model,cycles,emitter}.py``.  Where an
expectation is a number lifted from that reference - ``PECK_ANCHOR_MM = 5``'s
measured 6/7/8 mm first pecks, the ``333.333344`` post feed, the 10-peck
chip-break trigger - the docstring says which reference row it mirrors, so a
future reader can tell a ported specification from a fitted one.

Every fixture here is built in-process: no cross-repo import, no absolute
path, no fixture file.  The cross-repo fidelity measurement (this port vs
``impl/drilling`` on the pinned EXP-013 fixture) is an evidence artifact, not
a test - see ``Fusion 360 RE/tests/p5_evidence/``.
"""

from __future__ import annotations

import math

import pytest

from kernel.strategies import get_strategy, list_strategies
from kernel.strategies import drilling as dr
from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, MoveType, ToolDef, Vec3

# Reference vocabulary (impl/drilling/model.py:23-54) and the EXP-013 tool.
MEASURED = ("drilling", "counter-boring", "chip-breaking", "deep-drilling")
UNMEASURED = ("break-through-drilling", "gun-drilling", "tapping", "reaming",
              "boring", "thread-milling", "probe")
# export_jsonl.cps jnum(round6(float32(1000/3))) - drilling.md R13.
FEED_POST = 333.333344


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stock(z0=-10.0, z1=0.0, x0=-20.0, y0=-20.0, x1=20.0, y1=20.0) -> BBox:
    return BBox(min=Vec3(x0, y0, z0), max=Vec3(x1, y1, z1))


def tool(diameter=3.175) -> ToolDef:
    return ToolDef(tool_id="T01", name="3.175mm End Mill", diameter=diameter)


def holes(*specs):
    """``holes((x, y, top, bottom, diameter), ...)`` -> list of dicts."""
    out = []
    for i, (x, y, top, bottom, diameter) in enumerate(specs):
        out.append({"index": i, "x": x, "y": y, "top_z": top,
                    "bottom_z": bottom, "diameter": diameter})
    return out


def normalise(*specs):
    """``normalise(...)`` -> the typed Hole list the library functions take."""
    hs, errors = dr._normalise_holes(holes(*specs))
    assert not errors, errors
    return hs


def operation(holes_list=None, stock_box=None, tool_def=None, **extra):
    args = dict(extra)
    if holes_list is not None:
        args["holes"] = holes_list
    return OperationParams(
        strategy="drilling",
        stock=stock_box or stock(),
        tool=tool_def or tool(),
        feed_rate=1000.0,
        spindle_speed=9000.0,
        extra_args=args,
    )


def emit(hole_list, cfg=None, stock_top=0.0):
    """Library-level emission - the path that raises UngroundedCycleError."""
    hs, errors = dr._normalise_holes(hole_list)
    assert not errors, errors
    return dr.emit_moves(hs, cfg or dr.CycleConfig(), stock_top)


def signature(moves):
    """Comparable form: (kind, x, y, z, feed) with rapid feed normalized."""
    out = []
    for m in moves:
        kind = "rapid" if m.move_type is MoveType.RAPID else "linear"
        feed = None if m.move_type is MoveType.RAPID else m.feed
        out.append((kind, m.end.x, m.end.y, m.end.z, feed))
    return out


# ---------------------------------------------------------------------------
# Serializers (export_jsonl.cps:94, jnum)
# ---------------------------------------------------------------------------


class TestSerializers:
    def test_round6_rounds_half_up_toward_plus_infinity(self):
        """floor(v * 1e6 + 0.5) / 1e6 - JS Math.round, not banker's rounding.

        The expectations are the documented rule evaluated directly in double
        arithmetic (``impl/drilling/model.py:66`` states it as
        ``Math.round(value * 1e6) / 1e6``), not a run of this implementation:
        exact halves round toward +Infinity for BOTH signs - ``-5e-7`` and
        ``-1.5e-6`` land exactly on ``-0.5`` / ``-1.5`` and come back ``0.0`` /
        ``-1e-6``, while ``-1.0000005`` multiplies to ``-1000000.5000000001``
        and therefore floors to ``-1.000001``.
        """
        assert dr.round6(0.0000005) == 0.000001
        assert dr.round6(-0.0000005) == 0.0
        assert dr.round6(0.0000015) == 0.000002
        assert dr.round6(-0.0000015) == -0.000001
        assert dr.round6(1.2345674) == 1.234567
        assert dr.round6(1.2345676) == 1.234568
        assert dr.round6(-1.2345674) == -1.234567
        assert dr.round6(-1.2345676) == -1.234568

    def test_round6_cleans_up_binary_floating_point_noise(self):
        assert dr.round6(0.1 + 0.2) == 0.3
        assert dr.round6(-0.1 - 0.2) == -0.3
        assert dr.round6(2.675) == 2.675       # 2.675 * 1e6 is 2674999.9999999995
        assert dr.round6(1 / 3) == 0.333333
        assert dr.round6(-1 / 3) == -0.333333

    def test_round6_is_idempotent_on_its_own_output(self):
        for value in (0.1, -0.1, 1 / 3, 12.3456789, -98.7654321):
            once = dr.round6(value)
            assert dr.round6(once) == once

    def test_to_float32_matches_the_posted_1000_over_3(self):
        # 1000/3 in binary32 is 333.333343505859375, printed as 333.333344.
        assert dr.to_float32(1000.0 / 3.0) == 333.3333435058594
        assert dr.post_feed(1000.0 / 3.0) == FEED_POST

    def test_post_feed_leaves_whole_numbers_alone(self):
        assert dr.post_feed(1000.0) == 1000.0
        assert dr.post_feed(500.0) == 500.0
        assert dr.post_feed(1500.0) == 1500.0


# ---------------------------------------------------------------------------
# Vocabulary - the honest blockers
# ---------------------------------------------------------------------------


class TestVocabulary:
    @pytest.mark.parametrize("cycle_type", MEASURED)
    def test_measured_cycle_types_resolve(self, cycle_type):
        assert dr.resolve_cycle_type(cycle_type) == cycle_type

    @pytest.mark.parametrize("cycle_type", UNMEASURED)
    def test_unmeasured_cycle_types_refuse_with_a_resolving_capture(
            self, cycle_type):
        with pytest.raises(dr.UngroundedCycleError) as exc:
            dr.resolve_cycle_type(cycle_type)
        # The refusal must name the capture that would resolve it, not just fail.
        assert "never wrote it" in str(exc.value)
        assert f"cycleType='{cycle_type}'" in str(exc.value)

    def test_an_illegal_cycle_type_is_refused_as_illegal(self):
        with pytest.raises(dr.UngroundedCycleError) as exc:
            dr.resolve_cycle_type("helical-interpolation")
        assert "not a legal value" in str(exc.value)

    def test_unmeasured_order_mode_refuses(self):
        with pytest.raises(dr.UngroundedCycleError) as exc:
            dr.check_order_mode("order-inside-out")
        assert "order/ord_inside" in str(exc.value)

    def test_illegal_order_mode_refuses(self):
        with pytest.raises(dr.UngroundedCycleError):
            dr.check_order_mode("sort-by-chaos")

    @pytest.mark.parametrize("mode", [m for m in dr.ORDER_MODES
                                      if m not in dr.UNMEASURED_ORDER_MODES])
    def test_every_legal_order_mode_is_accepted(self, mode):
        dr.check_order_mode(mode)          # order-inside-out is refused below

    def test_the_legal_but_unmeasured_order_mode_is_refused(self):
        assert "order-inside-out" in dr.ORDER_MODES
        with pytest.raises(dr.UngroundedCycleError):
            dr.check_order_mode("order-inside-out")

    def test_the_ungrounded_check_runs_before_the_empty_selection(self):
        """An empty selection may NOT smuggle an unmeasured cycle past R11.

        The reference checks cycle type and order mode before selecting
        (impl/drilling/emitter.py:45-51); this pins the same order.
        """
        empty_range = dr.CycleConfig(hole_diameter_minimum=50.0,
                                     hole_diameter_maximum=60.0,
                                     cycle_type="tapping")
        with pytest.raises(dr.UngroundedCycleError):
            dr.emit_moves(normalise((0, 0, 0, -5, 6.0)), empty_range, 0.0)
        # ...while a VALID operation with an empty selection is silent.
        valid = dr.CycleConfig(hole_diameter_minimum=50.0,
                               hole_diameter_maximum=60.0)
        assert dr.emit_moves(normalise((0, 0, 0, -5, 6.0)), valid, 0.0) == []


# ---------------------------------------------------------------------------
# Selection and ordering (R4/R11, R10)
# ---------------------------------------------------------------------------


class TestSelection:
    BASE = normalise((0, 0, 0, -5, 6.0), (10, 0, 0, -8, 3.0),
                     (20, 0, 0, -8, 4.0))

    def test_bounds_are_inclusive(self):
        cfg = dr.CycleConfig(hole_diameter_minimum=3.0,
                             hole_diameter_maximum=6.0)
        assert len(dr.select_holes(self.BASE, cfg)) == 3

    def test_minimum_drops_the_smaller_holes(self):
        cfg = dr.CycleConfig(hole_diameter_minimum=5.0,
                             hole_diameter_maximum=100.0)
        assert [h.diameter for h in dr.select_holes(self.BASE, cfg)] == [6.0]

    def test_maximum_drops_the_bigger_holes(self):
        cfg = dr.CycleConfig(hole_diameter_minimum=0.0,
                             hole_diameter_maximum=4.0)
        assert [h.diameter for h in dr.select_holes(self.BASE, cfg)] == [3.0, 4.0]

    def test_empty_selection_is_silent_at_the_strategy_level(self):
        cfg = dr.CycleConfig(hole_diameter_minimum=50.0)
        result = get_strategy("drilling").run(operation(self.BASE, cycle=cfg.__dict__))
        assert "error" not in result.params
        assert result.moves == []
        assert result.params["holes_selected"] == 0
        assert result.bounding_box is None


class TestOrdering:
    BASE = holes((0, 0, 0, -5, 6.0), (10, 0, 0, -8, 3.0), (-10, 0, 0, -8, 4.0))

    def order(self, mode, reverse=False):
        hs = dr._normalise_holes(self.BASE)[0]
        return [(h.x, h.y) for h in dr.order_holes(hs, mode, reverse)]

    def test_order_selected_keeps_the_table_order(self):
        assert self.order("order-selected") == [(0, 0), (10, 0), (-10, 0)]

    def test_order_by_x_is_the_literal_parameter_name_reading(self):
        # The literal reading - and the campaign's declared order/ord_x fail
        # against the capture (Honest limits #1), carried unchanged.
        assert self.order("order-by-x") == [(-10, 0), (0, 0), (10, 0)]

    def test_order_by_y_sorts_ascending(self):
        assert self.order("order-by-y") == [(0, 0), (10, 0), (-10, 0)]

    def test_reverse_order_reverses_the_resolved_sequence(self):
        assert self.order("order-by-x", reverse=True) == [(10, 0), (0, 0), (-10, 0)]

    def test_optimize_order_is_an_open_path_from_the_first_hole(self):
        # From (0, 0): nearest is (10, 0) at 10 mm vs (-10, 0) at 10 mm - a
        # tie broken by index, then 2-opt has nothing to improve.
        assert self.order("optimize-order") == [(0, 0), (10, 0), (-10, 0)]

    def test_optimize_order_improves_a_crossing_path(self):
        # Anchored at A, greedy goes to the far point first; 2-opt flips the
        # tail when that shortens the open path.
        hs = dr._normalise_holes(holes(
            (0, 0, 0, -5, 6.0), (1.0, 0, 0, -5, 6.0),
            (10.0, 0, 0, -5, 6.0)))[0]
        ordered = [(h.x, h.y) for h in dr.order_holes(hs, "optimize-order")]
        assert ordered == [(0, 0), (1.0, 0), (10.0, 0)]

    def test_order_inside_out_raises(self):
        hs = dr._normalise_holes(self.BASE)[0]
        with pytest.raises(dr.UngroundedCycleError):
            dr.order_holes(hs, "order-inside-out")


# ---------------------------------------------------------------------------
# Planes (drilling.md R9)
# ---------------------------------------------------------------------------


class TestPlanes:
    def test_retract_is_stock_plus_5_and_clearance_is_retract_plus_10(self):
        # measured modes: 'from stock top' +5mm, 'from retract height' +10mm
        cfg = dr.CycleConfig()
        assert dr.planes(0.0, cfg) == (5.0, 15.0)
        assert dr.planes(-12.7, cfg) == (-7.7, 2.3)

    def test_the_offsets_are_the_measured_creation_defaults(self):
        assert dr.CycleConfig().retract_height_offset == 5.0
        assert dr.CycleConfig().clearance_height_offset == 10.0

    def test_sweeping_the_retract_offset_moves_both_planes(self):
        cfg = dr.CycleConfig(retract_height_offset=2.0)
        assert dr.planes(0.0, cfg) == (2.0, 12.0)

    def test_the_planes_round_to_the_post_quantum(self):
        cfg = dr.CycleConfig(retract_height_offset=0.0000005)
        assert dr.planes(0.0, cfg) == (0.000001, 10.000001)


# ---------------------------------------------------------------------------
# Move grammar (impl/drilling/emitter.py)
# ---------------------------------------------------------------------------


class TestMoveGrammar:
    TWO = holes((0, 0, 0, -5, 6.0), (10, 0, 0, -8, 3.0))

    def test_program_approach_and_exit_use_the_clearance_plane(self):
        moves = emit(self.TWO)
        assert signature(moves)[0] == ("rapid", 0.0, 0.0, 15.0, None)
        assert signature(moves)[-1] == ("rapid", 10.0, 0.0, 15.0, None)

    def test_a_plain_drilling_hole_is_entry_rapid_plunge_retract(self):
        moves = emit(self.TWO[:1])
        assert signature(moves) == [
            ("rapid", 0.0, 0.0, 15.0, None),   # program approach
            ("rapid", 0.0, 0.0, 15.0, None),   # travel at the current plane
            ("rapid", 0.0, 0.0, 5.0, None),    # to the retract plane
            ("rapid", 0.0, 0.0, 0.0, None),    # entry -> hole top
            ("linear", 0.0, 0.0, -5.0, FEED_POST),   # the plunge
            ("rapid", 0.0, 0.0, 5.0, None),    # end-of-hole retract
            ("rapid", 0.0, 0.0, 15.0, None),   # program exit
        ]

    def test_later_holes_travel_at_the_retract_plane_not_the_clearance(self):
        moves = signature(emit(self.TWO))
        # second hole's first travel is at z = 5 (retract), not 15 (clearance)
        assert moves[6] == ("rapid", 10.0, 0.0, 5.0, None)
        assert moves[7] == ("rapid", 10.0, 0.0, 5.0, None)

    def test_rapids_never_carry_a_feed_and_linears_always_do(self):
        for m in emit(self.TWO):
            if m.move_type is MoveType.RAPID:
                assert m.feed == 0.0
            else:
                assert m.feed == FEED_POST

    def test_every_move_carries_the_operation_spindle_speed(self):
        moves = dr.emit_moves(dr._normalise_holes(self.TWO)[0],
                              dr.CycleConfig(), 0.0, spindle_speed=9000.0)
        assert {m.spindle_speed for m in moves} == {9000.0}

    def test_counter_boring_has_the_same_body_as_drilling(self):
        """R5: at this capture boundary counter-boring adds no move (no dwell)."""
        a = dr.CycleConfig(cycle_type="drilling")
        b = dr.CycleConfig(cycle_type="counter-boring")
        assert signature(emit(self.TWO, a)) == signature(emit(self.TWO, b))


# ---------------------------------------------------------------------------
# Peck schedules (drilling.md R5/R6) - the measured numbers
# ---------------------------------------------------------------------------


class TestPeckSchedule:
    DEEP = holes((0, 0, 0, -10, 6.0))

    @pytest.mark.parametrize("peck,first_end", [(1.0, -6.0), (2.0, -7.0),
                                                (3.0, -8.0)])
    def test_first_peck_ends_anchor_plus_one_peck_below_the_top(
            self, peck, first_end):
        """measured: peck 1 -> 6.000, 2 -> 7.000, 3 -> 8.000 below the top."""
        cfg = dr.CycleConfig(cycle_type="deep-drilling", pecking_depth=peck)
        kinds = dr.cycle_body(0.0, -10.0, cfg, 5.0)
        assert kinds[0] == ("rapid", 0.0)
        assert kinds[1] == ("linear", first_end)

    def test_the_default_peck_is_a_quarter_of_the_tool_diameter(self):
        # creation expr peckingDepth = tool_diameter * 0.25 -> 0.79375
        cfg = dr.CycleConfig(cycle_type="deep-drilling")
        assert cfg.resolved_pecking_depth == pytest.approx(0.79375)
        kinds = dr.cycle_body(0.0, -6.23375, cfg, 5.0)
        assert kinds[1] == ("linear", -5.79375)

    def test_deep_drilling_retracts_to_the_hole_top_and_re_enters_plus_2(self):
        cfg = dr.CycleConfig(cycle_type="deep-drilling", pecking_depth=3.0)
        kinds = dr.cycle_body(0.0, -10.0, cfg, 5.0)
        # rapid top, linear -8, rapid top, rapid -6 (= end + DEEP_REENTRY 2),
        # linear -10 (clipped by the bottom)
        assert kinds == [("rapid", 0.0), ("linear", -8.0), ("rapid", 0.0),
                         ("rapid", -6.0), ("linear", -10.0)]

    def test_the_final_peck_is_clipped_by_the_hole_bottom(self):
        cfg = dr.CycleConfig(cycle_type="deep-drilling", pecking_depth=3.0)
        kinds = dr.cycle_body(0.0, -10.0, cfg, 5.0)
        assert kinds[-1] == ("linear", -10.0)

    def test_chip_breaking_partially_retracts_by_the_measured_distance(self):
        cfg = dr.CycleConfig(cycle_type="chip-breaking", pecking_depth=3.0,
                             tool_diameter=3.175)
        assert cfg.chip_break_distance == pytest.approx(0.1)   # max(0.0635, 0.1)
        kinds = dr.cycle_body(0.0, -20.0, cfg, 5.0)
        # after the first peck: rapid to end + 0.1, NOT to the top
        assert kinds[2][0] == "rapid"
        assert kinds[2][1] == pytest.approx(kinds[1][1] + 0.1, abs=1e-9)
        assert kinds[2][1] != 0.0

    def test_the_full_retract_fires_on_the_measured_tenth_peck(self):
        """accumulated = max(D*2.5, peck) = 7.9375 = 10 * 0.79375 (measured)."""
        cfg = dr.CycleConfig(cycle_type="chip-breaking", pecking_depth=0.79375,
                             tool_diameter=3.175)
        assert cfg.accumulated_pecking_depth == pytest.approx(7.9375)
        kinds = dr.cycle_body(0.0, -20.0, cfg, 5.0)
        linears = [i for i, (k, _z) in enumerate(kinds) if k == "linear"]
        assert len(linears) >= 10
        # peck 10 ends the accumulated budget: retract PLANE, then re-enter
        k = linears[9]
        assert kinds[k + 1][0] == "rapid"
        assert kinds[k + 1][1] == pytest.approx(5.0, abs=1e-12)  # full, not partial
        assert kinds[k + 2][0] == "rapid"
        assert kinds[k + 2][1] == pytest.approx(kinds[k][1] + 2.0, abs=1e-9)
        # the nine pecks before it only partial-retract
        for i in linears[:9]:
            assert kinds[i + 1][1] != pytest.approx(5.0, abs=1e-9)

    def test_chip_breaking_resets_the_accumulator_after_a_full_retract(self):
        cfg = dr.CycleConfig(cycle_type="chip-breaking", pecking_depth=0.79375,
                             tool_diameter=3.175)
        kinds = dr.cycle_body(0.0, -30.0, cfg, 5.0)
        full = [i for i, (k, z) in enumerate(kinds)
                if k == "rapid" and z == 5.0]
        assert len(full) >= 2                     # a second clear happens
        # after the first clear the next retract is partial again
        after = kinds[full[0] + 3]
        assert after[0] == "rapid"
        assert after[1] != 5.0

    def test_a_non_positive_peck_is_refused_rather_than_expanded(self):
        cfg = dr.CycleConfig(cycle_type="deep-drilling", pecking_depth=0.0)
        with pytest.raises(dr.UngroundedCycleError) as exc:
            dr.cycle_body(0.0, -10.0, cfg, 5.0)
        assert "empty peck schedule" in str(exc.value)

    def test_an_absurd_peck_is_refused_by_the_ceiling(self):
        # 1e-6 mm over a 13.3 mm hole would expand to ~13 million pecks.
        cfg = dr.CycleConfig(cycle_type="deep-drilling", pecking_depth=1e-6)
        with pytest.raises(dr.UngroundedCycleError) as exc:
            dr.cycle_body(0.0, -13.3, cfg, 5.0)
        assert "refused instead of expanded" in str(exc.value)
        assert str(dr.MAX_PECK_STEPS) in str(exc.value)

    def test_the_ceiling_itself_is_far_above_any_measured_schedule(self):
        # measured: <= 18 pecks at the control peck, <= 15 at the 1 mm sweep
        assert dr.MAX_PECK_STEPS == 10_000
        assert dr.MAX_PECK_STEPS > 555 * 18


# ---------------------------------------------------------------------------
# Depth (drilling.md R8)
# ---------------------------------------------------------------------------


class TestDepth:
    def test_break_through_only_bites_with_both_switches(self):
        cfg = dr.CycleConfig(break_through_depth=1.0, drill_tip_through_bottom=True)
        assert dr.hole_bottom(-12.3, cfg) == -13.3
        only_tip = dr.CycleConfig(drill_tip_through_bottom=True)
        assert dr.hole_bottom(-12.3, only_tip) == -12.3
        only_brk = dr.CycleConfig(break_through_depth=1.0)
        assert dr.hole_bottom(-12.3, only_brk) == -12.3

    def test_break_through_deepens_the_emitted_body(self):
        cfg = dr.CycleConfig(break_through_depth=1.0,
                             drill_tip_through_bottom=True)
        moves = dr.emit_moves(dr._normalise_holes(
            holes((0, 0, 0, -12.3, 6.0)))[0], cfg, 0.0)
        plunges = [m.end.z for m in moves if m.move_type is MoveType.LINEAR]
        assert plunges == [-13.3]

    def test_top_and_bottom_height_offsets_shift_the_body(self):
        """Extrapolation (Honest limits #5): both are 0 mm in the capture but
        the parameters mean what they say, and this pins the arithmetic."""
        cfg = dr.CycleConfig(top_height_offset=-0.44, bottom_height_offset=-1.0)
        moves = dr.emit_moves(dr._normalise_holes(
            holes((0, 0, 0, -12.3, 6.0)))[0], cfg, 0.0)
        body = signature(moves)
        assert ("rapid", 0.0, 0.0, -0.44, None) in body      # entry at top + offset
        assert ("linear", 0.0, 0.0, -11.3, FEED_POST) in body


# ---------------------------------------------------------------------------
# Feed (drilling.md R13)
# ---------------------------------------------------------------------------


class TestFeed:
    def test_flat_end_mill_uses_a_third_of_the_cutting_feed(self):
        cfg = dr.CycleConfig(tool_feed_cutting=1000.0, tool_type="flat end mill")
        assert cfg.resolved_feed_plunge == pytest.approx(1000.0 / 3.0)
        assert dr.post_feed(cfg.resolved_feed_plunge) == FEED_POST

    @pytest.mark.parametrize("tool_type", ["drill", "reamer"])
    def test_a_drill_or_reamer_takes_the_1000_arm(self, tool_type):
        cfg = dr.CycleConfig(tool_type=tool_type, tool_feed_cutting=600.0)
        assert cfg.resolved_feed_plunge == 1000.0

    def test_a_depositing_tool_takes_the_1000_arm(self):
        cfg = dr.CycleConfig(tool_is_depositing=True, tool_feed_cutting=600.0)
        assert cfg.resolved_feed_plunge == 1000.0

    def test_an_explicit_plunge_feed_wins(self):
        cfg = dr.CycleConfig(tool_feed_plunge=250.0, tool_type="drill")
        assert cfg.resolved_feed_plunge == 250.0

    def test_the_emitted_feed_is_the_posted_float32_value(self):
        moves = dr.emit_moves(dr._normalise_holes(
            holes((0, 0, 0, -5, 6.0)))[0], dr.CycleConfig(), 0.0)
        feeds = {m.feed for m in moves if m.move_type is MoveType.LINEAR}
        assert feeds == {FEED_POST}


# ---------------------------------------------------------------------------
# Strategy wiring
# ---------------------------------------------------------------------------


class TestStrategyRegistration:
    def test_registered_under_its_own_name(self):
        assert "drilling" in list_strategies()
        strategy = get_strategy("drilling")
        assert isinstance(strategy, BaseStrategy)
        assert strategy.name == "drilling"
        assert "canned-cycle" in strategy.description.lower() \
            or "canned" in strategy.description.lower()

    def test_run_validates_before_generating(self):
        strategy = get_strategy("drilling")
        bad = operation(holes((0, 0, 0, -5, 6.0)), cycle={"cycle_type": "tapping"})
        with pytest.raises(ValueError) as exc:
            strategy.run(bad)
        assert "tapping" in str(exc.value)


class TestValidation:
    def test_missing_holes_is_reported(self):
        errors = get_strategy("drilling").validate_params(operation(None))
        assert any("holes is required" in e for e in errors)

    def test_unknown_cycle_field_is_reported_with_the_accepted_set(self):
        op = operation(holes((0, 0, 0, -5, 6.0)), cycle={"peckingDepht": 2.0})
        errors = get_strategy("drilling").validate_params(op)
        assert any("unknown field" in e and "peckingDepht" in e for e in errors)
        assert any("pecking_depth" in e for e in errors)

    @pytest.mark.parametrize("value", ["fast", None, float("nan"), True, (1,)])
    def test_a_non_numeric_cycle_field_is_reported(self, value):
        op = operation(holes((0, 0, 0, -5, 6.0)),
                       cycle={"break_through_depth": value})
        errors = get_strategy("drilling").validate_params(op)
        assert any("cycle.break_through_depth" in e for e in errors)

    @pytest.mark.parametrize("value", [3, None, True, (1,), 2.5])
    def test_a_non_string_cycle_type_is_reported(self, value):
        op = operation(holes((0, 0, 0, -5, 6.0)), cycle={"cycle_type": value})
        errors = get_strategy("drilling").validate_params(op)
        assert any("cycle.cycle_type: expected a string" in e for e in errors)

    def test_an_illegal_cycle_type_string_is_reported_by_the_vocabulary(self):
        op = operation(holes((0, 0, 0, -5, 6.0)), cycle={"cycle_type": "tapping"})
        errors = get_strategy("drilling").validate_params(op)
        assert any("cycleType='tapping'" in e for e in errors)

    @pytest.mark.parametrize("hole", [
        {"x": 0, "y": 0, "top_z": 0},                       # missing keys
        (0, 0, 0, -5),                                      # 4-tuple
        {"x": 0, "y": 0, "top_z": 0, "bottom_z": "deep", "diameter": 6},
        (0, 0, float("nan"), -5, 6.0),                      # non-finite
        "not a hole",
    ])
    def test_a_malformed_hole_is_reported(self, hole):
        errors = get_strategy("drilling").validate_params(operation([hole]))
        assert any(e.startswith("holes[0]") for e in errors), errors

    def test_a_bad_stock_override_is_reported(self):
        op = operation(holes((0, 0, 0, -5, 6.0)), stock_top_z=-20.0,
                       stock_bottom_z=0.0)
        errors = get_strategy("drilling").validate_params(op)
        assert any("stock_top_z must not be below" in e for e in errors)

    def test_a_non_finite_stock_override_is_reported(self):
        op = operation(holes((0, 0, 0, -5, 6.0)), stock_top_z=float("inf"))
        errors = get_strategy("drilling").validate_params(op)
        assert any("stock_top_z" in e for e in errors)

    def test_inverted_diameter_range_is_reported(self):
        op = operation(holes((0, 0, 0, -5, 6.0)),
                       cycle={"hole_diameter_minimum": 10.0,
                              "hole_diameter_maximum": 5.0})
        errors = get_strategy("drilling").validate_params(op)
        assert any("hole_diameter_minimum" in e for e in errors)

    def test_an_over_long_peck_schedule_is_reported_before_emission(self):
        op = operation(holes((0, 0, 0, -13.3, 6.0)),
                       cycle={"cycle_type": "deep-drilling",
                              "pecking_depth": 1e-6})
        errors = get_strategy("drilling").validate_params(op)
        assert any("refused" in e and "pecks" in e for e in errors)

    def test_generate_toolpath_returns_an_error_toolpath_instead_of_raising(self):
        result = get_strategy("drilling").generate_toolpath(
            stock(), tool(), holes=holes((0, 0, 0, -5, 6.0)),
            cycle={"cycle_type": "tapping"})
        assert result.moves == []
        assert "error" in result.params
        assert "tapping" in result.params["error"]


class TestConfigResolution:
    def test_tool_diameter_falls_back_to_the_tool(self):
        result = get_strategy("drilling").run(
            operation(holes((0, 0, 0, -5, 6.0)), tool_def=tool(8.0)))
        assert result.params["tool_diameter"] == 8.0

    def test_an_explicit_tool_diameter_wins(self):
        result = get_strategy("drilling").run(
            operation(holes((0, 0, 0, -5, 6.0)), tool_def=tool(8.0),
                      cycle={"tool_diameter": 3.175}))
        assert result.params["tool_diameter"] == 3.175

    def test_the_plunge_feed_follows_the_operation_feed_rate(self):
        result = get_strategy("drilling").run(
            operation(holes((0, 0, 0, -5, 6.0)), feed_rate=600.0))
        assert result.params["feed_vocabulary"]["plunge"] == pytest.approx(200.0)

    def test_stock_planes_come_from_the_bbox(self):
        result = get_strategy("drilling").run(
            operation(holes((0, 0, 0, -5, 6.0))))
        assert result.params["retract_z"] == 5.0
        assert result.params["clearance_z"] == 15.0

    def test_explicit_stock_planes_override_the_bbox(self):
        result = get_strategy("drilling").run(
            operation(holes((0, 0, 0, -5, 6.0)), stock_top_z=3.0,
                      stock_bottom_z=-7.0))
        assert result.params["retract_z"] == 8.0
        assert result.params["clearance_z"] == 18.0

    def test_operation_top_of_stock_is_not_read(self):
        """Declared: the stock BBox carries the planes (module docstring)."""
        op = operation(holes((0, 0, 0, -5, 6.0)), top_of_stock=42.0)
        result = get_strategy("drilling").run(op)
        assert result.params["retract_z"] == 5.0


class TestToolpathData:
    TWO = holes((0, 0, 0, -5, 6.0), (10, 0, 0, -8, 3.0))

    def run(self, **extra):
        return get_strategy("drilling").run(operation(self.TWO, **extra))

    def test_the_strategy_and_counts_are_recorded(self):
        result = self.run()
        assert result.strategy == "drilling"
        assert result.params["moves"] == len(result.moves) == 12
        assert result.params["holes_total"] == 2
        assert result.params["holes_selected"] == 2
        assert result.params["holes_machined"] == 2

    def test_the_hole_order_is_reported(self):
        result = self.run(cycle={"hole_toolpath_order": "order-by-x"})
        assert result.params["hole_xy"] == [[0.0, 0.0], [10.0, 0.0]]

    def test_the_feed_histogram_counts_plunges_only(self):
        result = self.run()
        assert result.params["feed_histogram"] == {f"{FEED_POST:.6f}": 2}

    def test_a_bounding_box_is_computed(self):
        result = self.run()
        assert result.bounding_box is not None
        assert result.bounding_box.max.z == pytest.approx(15.0)
        assert result.bounding_box.min.z == pytest.approx(-8.0)

    def test_the_toolpath_is_indexable_and_len_able(self):
        result = self.run()
        assert len(result) == 12
        assert result[0].move_type is MoveType.RAPID
        start, end = result.start_point, result.end_point
        assert start is not None and end is not None
        assert start.z == pytest.approx(15.0)
        assert end.z == pytest.approx(15.0)

    def test_a_drilled_move_counts_as_cutting(self):
        result = self.run()
        cutting = [m for m in result.moves if m.is_cutting]
        assert len(cutting) == 2
        assert {m.move_type for m in cutting} == {MoveType.LINEAR}


# ---------------------------------------------------------------------------
# Golden body: one hand-computed program, pinned move by move
# ---------------------------------------------------------------------------


class TestGoldenBody:
    def test_two_holes_plain_drilling(self):
        """Expected values derived from the emitter's grammar, not from a run.

        stock top 0 -> retract 5, clearance 15; holes (0,0,0,-5,d6) and
        (10,0,0,-8,d3); order optimize-order keeps table order; feed =
        round6(float32(1000/3)) = 333.333344.
        """
        moves = dr.emit_moves(dr._normalise_holes(
            holes((0, 0, 0, -5, 6.0), (10, 0, 0, -8, 3.0)))[0],
            dr.CycleConfig(), 0.0)
        assert signature(moves) == [
            ("rapid", 0.0, 0.0, 15.0, None),
            ("rapid", 0.0, 0.0, 15.0, None),
            ("rapid", 0.0, 0.0, 5.0, None),
            ("rapid", 0.0, 0.0, 0.0, None),
            ("linear", 0.0, 0.0, -5.0, FEED_POST),
            ("rapid", 0.0, 0.0, 5.0, None),
            ("rapid", 10.0, 0.0, 5.0, None),
            ("rapid", 10.0, 0.0, 5.0, None),
            ("rapid", 10.0, 0.0, 0.0, None),
            ("linear", 10.0, 0.0, -8.0, FEED_POST),
            ("rapid", 10.0, 0.0, 5.0, None),
            ("rapid", 10.0, 0.0, 15.0, None),
        ]

    def test_three_holes_sorted_by_x(self):
        hs = dr._normalise_holes(holes(
            (0, 0, 0, -5, 6.0), (10, 0, 0, -5, 6.0), (-10, 0, 0, -5, 6.0)))[0]
        moves = dr.emit_moves(hs, dr.CycleConfig(hole_toolpath_order="order-by-x"),
                              0.0)
        visited = [(m.end.x, m.end.y) for m in moves
                   if m.move_type is MoveType.LINEAR]
        assert visited == [(-10.0, 0.0), (0.0, 0.0), (10.0, 0.0)]
