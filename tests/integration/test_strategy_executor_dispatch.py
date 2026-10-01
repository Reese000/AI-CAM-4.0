"""
App-layer dispatch for the three kernel-backed strategies (F1, F2, F3).

``app/strategy_executor.py`` is the layer between the UI and the kernel: it
owns the parameter schemas ``execute()`` validates against (the selector
picks names; parameters ride in on ``execute(params=...)`` from whichever
caller drives it), and it decides what each strategy is actually invoked
with.  Until t_130bcaa7 it listed only
the legacy app-local planners, so F1 (P5/3, ``adaptive_engagement``) and F2
(P5/4, ``waterline_finishing``) were reachable from the kernel and from the
kernel tests but not from the application; t_6a5f2239 then re-pointed
``drilling`` at the kernel's F3 ``DrillingStrategy``, retiring the app-local
peck planner so one name no longer hides two algorithms.

These tests pin the app-side contract for all three:

  * the strategy is listed by ``list_strategies()`` and dispatched by
    ``execute()``,
  * the app's parameter vocabulary reaches the kernel intact,
  * the translations the executor owns actually happen — ``step_over``
    in mm becomes the kernel's stepover-as-a-fraction-of-D for F1, every
    kernel-backed strategy is handed the stock's z faces (F2 would
    otherwise plan against its own ``top_of_stock = 0.0`` /
    ``bottom_of_stock = -10.0`` defaults, a different z range from the
    stock on screen; F1 already defaults to the stock faces, but passing
    them explicitly keeps the strategies on the same rule), and F3's
    seven cycle keys are nested under ``cycle=`` where DrillingStrategy
    reads them,
  * a rejected parameter set surfaces as ``ValueError`` rather than as an
    empty toolpath the GUI would report as a successful cut.

Runtime note: the default ``cell_mm`` is measured against the suite's
standard 100 mm stock below, because that is the shape
``tests/integration/test_pipeline.py::test_all_strategies_generate`` runs
every listed strategy over.
"""

from __future__ import annotations

import logging
import re

import pytest

from app import strategy_executor
from app.strategy_executor import (
    StrategyExecutor,
    get_strategy_params,
    list_strategies,
)
from kernel.strategies import list_strategies as kernel_list_strategies
from kernel.strategies.drilling import (
    MEASURED_CYCLE_TYPES,
    ORDER_MODES,
    UNMEASURED_ORDER_MODES,
)
from kernel.strategies.waterline_finishing import FINISH_MODES
from kernel.types import BBox, MoveType, ToolDef, ToolpathData, Vec3

# ---------------------------------------------------------------------------
# Fixtures (module level: constructing these is free)
# ---------------------------------------------------------------------------

EXECUTOR = StrategyExecutor()
TOOL = ToolDef(tool_id="T01", name="10mm End Mill", diameter=10.0, flute_length=30.0)
#: The bounding box ``tests/integration/test_pipeline.py`` runs every listed
#: strategy over — the app-layer default path has to work on exactly this.
STOCK = BBox(min=Vec3(-50, -50, 0), max=Vec3(50, 50, 20))
#: A 20 mm part: same code path, a fraction of the raster cost, so repeated
#: waterline runs in this file stay cheap.
SMALL = BBox(min=Vec3(0, 0, 0), max=Vec3(20, 20, 10))

#: A profile strictly inside the stock.  The kernel finishes the OUTSIDE of
#: a material region, so the contour it plans sits one tool radius BEYOND the
#: boundary it follows: 10 mm + R when handed PROFILE, 30 mm + R when it
#: falls back to the stock box.  Measuring the far side of the contour is
#: therefore what tells the two sources apart — see
#: ``test_profile_replaces_the_stock_footprint``.
PROFILE = [[-10.0, -10.0], [10.0, -10.0], [10.0, 10.0], [-10.0, 10.0]]
STOCK_AROUND_PROFILE = BBox(min=Vec3(-30, -30, 0), max=Vec3(30, 30, 10))

#: A hole table the app-layer tests drill: two 6 mm holes through a 10 mm
#: plate, both inside SMALL.  Dict rows are the kernel's own hole spelling
#: (``_normalise_holes``), so passing them through must be lossless.
HOLES = [
    {"x": 5.0, "y": 5.0, "top_z": 10.0, "bottom_z": 0.0, "diameter": 6.0},
    {"x": 15.0, "y": 15.0, "top_z": 10.0, "bottom_z": 0.0, "diameter": 6.0},
]

#: Kernel strategies ``execute()`` still answers with its own legacy
#: app-local planner of the SAME NAME rather than the kernel algorithm.
#: Two algorithms share one name here on purpose for now: ``app/`` was on
#: the P5 no-touch list, so the cards that landed the kernel algorithms
#: could not re-point the executor — t_130bcaa7 proved ``app/`` editable
#: and re-pointed F1/F2, t_6a5f2239 re-pointed ``drilling`` at the
#: kernel's F3 DrillingStrategy (hence that name's departure from this
#: set), and what remains is the app-local debt still to pay down.  The
#: set is recomputed from a live dispatch in
#: ``test_declared_legacy_name_collisions_match_reality``, so a new kernel
#: strategy (or a re-pointed one) forces a deliberate edit here instead of
#: drifting silently.
LEGACY_NAME_COLLISIONS = {
    "face_milling",
    "adaptive_clearing",
    "pocketing",
}


class _Spy:
    """Records the kwargs the executor hands to the kernel strategy."""

    def __init__(self) -> None:
        self.name: str | None = None
        self.kwargs: dict = {}

    def install(self, monkeypatch) -> None:
        real_get_strategy = strategy_executor.get_strategy

        def spy(name: str):
            strategy = real_get_strategy(name)
            real_generate = strategy.generate_toolpath

            def generate(stock, tool, **kwargs):
                self.name = name
                self.kwargs = kwargs
                return real_generate(stock, tool, **kwargs)

            strategy.generate_toolpath = generate  # type: ignore[method-assign]
            return strategy

        monkeypatch.setattr(strategy_executor, "get_strategy", spy)


# ---------------------------------------------------------------------------
# Inventory — the strategies must be reachable from the application layer
# ---------------------------------------------------------------------------

class TestInventory:
    def test_the_three_p5_strategies_are_listed(self) -> None:
        names = list_strategies()
        assert "adaptive_engagement" in names
        assert "waterline_finishing" in names
        assert "drilling" in names

    def test_every_kernel_strategy_is_reachable_from_the_app(self) -> None:
        """The regression this card exists to fix, stated as a general rule.

        Whatever the kernel registers next must not be able to ship without
        an app-layer entry point again.
        """
        missing = set(kernel_list_strategies()) - set(list_strategies())
        assert missing == set(), (
            "kernel strategies with no app-layer entry point: "
            f"{sorted(missing)}"
        )

    def test_declared_legacy_name_collisions_match_reality(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reachability alone is not dispatch identity.

        A name can exist in both registries while ``execute()`` still routes
        it to the legacy app-local planner — two different algorithms under
        one name.  That is exactly what ``LEGACY_NAME_COLLISIONS`` declares,
        and this recomputes it from a live run so the declaration cannot go
        stale.

        Only names BOTH registries know are considered, so a kernel strategy
        the app has not listed yet is ``test_every_kernel_strategy_is_
        reachable_from_the_app``'s failure (``execute()`` would raise
        ``Unknown strategy`` here, hiding this assertion), while one the app
        lists but still answers with a legacy planner shows up as undeclared.
        Intersecting also keeps this card's commit green whichever order it
        lands in relative to a concurrently-registering kernel strategy.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        both = set(kernel_list_strategies()) & set(list_strategies())

        answered_by_the_kernel: set[str] = set()
        for name in sorted(both):
            spy.name = None
            EXECUTOR.execute(strategy=name, tool=TOOL, stock_bbox=SMALL)
            if spy.name is not None:
                answered_by_the_kernel.add(name)

        legacy = both - answered_by_the_kernel
        assert legacy == LEGACY_NAME_COLLISIONS & both, (
            "the executor's kernel-vs-legacy split changed; update "
            "LEGACY_NAME_COLLISIONS (and the README strategy inventory) on "
            f"purpose.  now legacy: {sorted(legacy)}"
        )

    def test_strategy_names_and_selector_titles_are_unique(self) -> None:
        """What ``main_window`` relies on when it indexes the selector.

        ``_create_toolbar`` builds the combo from
        ``[s.replace('_', ' ').title() for s in list_strategies()]`` and the
        handlers map the selected index back with ``list_strategies()[idx]``,
        so two strategies whose display titles collide would make the selector
        ambiguous even though their names differ.
        """
        names = list_strategies()
        assert len(names) == len(set(names))
        for name in names:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", name), name
        titles = [name.replace("_", " ").title() for name in names]
        assert len(titles) == len(set(titles)), titles

    def test_unknown_strategy_is_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            EXECUTOR.execute(strategy="not_a_strategy", tool=TOOL, stock_bbox=STOCK)

    def test_get_strategy_params_rejects_an_unknown_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy_params("not_a_strategy")


# ---------------------------------------------------------------------------
# Parameter schemas
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_f1_schema_covers_the_parameters_f1_needs(self) -> None:
        schema = get_strategy_params("adaptive_engagement")
        assert set(schema) == {
            "step_over", "step_down", "engagement_gate", "feed_rate",
        }
        for key, spec in schema.items():
            assert spec["type"] == "float", key
            assert "default" in spec and "label" in spec, key
            assert spec["min"] < spec["max"], key

    def test_f1_default_step_over_is_a_valid_fraction_of_the_suite_tool(self) -> None:
        spec = get_strategy_params("adaptive_engagement")["step_over"]
        assert 0.0 < spec["default"] / TOOL.diameter <= 0.5

    def test_f1_engagement_gate_is_a_fraction_of_d(self) -> None:
        spec = get_strategy_params("adaptive_engagement")["engagement_gate"]
        assert (spec["min"], spec["default"], spec["max"]) == (0.01, 0.5, 1.0)

    def test_f2_schema_covers_the_parameters_f2_needs(self) -> None:
        schema = get_strategy_params("waterline_finishing")
        assert set(schema) == {
            "finish_mode", "cell_mm", "cusp_height_mm", "scallop_rings",
            "stock_to_leave_mm", "step_down", "feed_rate", "profile", "mesh",
        }

    def test_f2_finish_mode_offers_every_kernel_mode(self) -> None:
        spec = get_strategy_params("waterline_finishing")["finish_mode"]
        assert spec["type"] == "choice"
        assert spec["choices"] == list(FINISH_MODES)
        assert spec["default"] in spec["choices"]

    def test_f2_source_and_ring_params_are_nullable(self) -> None:
        """Blank means "derive it" — never clamped, never coerced."""
        schema = get_strategy_params("waterline_finishing")
        for key in ("scallop_rings", "profile", "mesh"):
            assert schema[key]["default"] is None, key
            assert schema[key]["nullable"] is True, key

    def test_f2_default_cell_mm_is_a_number_the_kernel_accepts(self) -> None:
        """The kernel's own default (0.05 mm) is refused on this stock.

        A schema whose default always fails is not an exposed strategy, so
        the app carries its own coarser interactive default.  The
        end-to-end proof that it plans is ``TestWaterlineFinishingDispatch
        ::test_execute_returns_a_toolpath_for_the_standard_stock``.
        """
        spec = get_strategy_params("waterline_finishing")["cell_mm"]
        assert spec["default"] > 0.05
        assert spec["min"] <= 0.05 <= spec["max"], "0.05 must stay requestable"

    def test_f3_schema_is_the_kernel_vocabulary_not_the_legacy_trio(self) -> None:
        """``peck_depth`` / ``retract`` / ``dwell`` are gone on purpose.

        None of the three names is a keyword DrillingStrategy accepts (see
        the schema comment for what each one became, or why it went), so
        keeping them would promise controls the kernel does not have.
        """
        schema = get_strategy_params("drilling")
        assert set(schema) == {
            "holes", "cycle_type", "pecking_depth", "retract_height_offset",
            "clearance_height_offset", "hole_toolpath_order",
            "hole_diameter_minimum", "hole_diameter_maximum",
            "feed_rate", "spindle_speed",
        }
        for legacy in ("peck_depth", "retract", "dwell"):
            assert legacy not in schema, legacy
        for key, spec in schema.items():
            assert "default" in spec and "label" in spec, key

    def test_f3_offers_only_cycle_types_the_capture_measured(self) -> None:
        """The other seven legal Choices make the kernel refuse outright."""
        spec = get_strategy_params("drilling")["cycle_type"]
        assert spec["type"] == "choice"
        assert spec["choices"] == list(MEASURED_CYCLE_TYPES)
        assert spec["default"] in spec["choices"]

    def test_f3_hole_order_never_offers_the_unmeasured_mode(self) -> None:
        """``order-inside-out`` has no capture; the kernel raises on it."""
        spec = get_strategy_params("drilling")["hole_toolpath_order"]
        assert spec["choices"] == [
            mode for mode in ORDER_MODES if mode not in UNMEASURED_ORDER_MODES
        ]
        assert "order-inside-out" not in spec["choices"]
        assert spec["default"] in spec["choices"]

    def test_f3_geometry_and_peck_defaults_are_blank(self) -> None:
        """Blank means the kernel's own answer, not an app-side guess.

        ``holes=None`` is turned into the demo grid at dispatch (the GUI
        cannot supply a table yet); ``pecking_depth=None`` is passed
        through as ``None`` so ``CycleConfig`` evaluates its stored
        expression (0.25 × D) instead of the app inventing a number.
        """
        schema = get_strategy_params("drilling")
        for key in ("holes", "pecking_depth"):
            assert schema[key]["default"] is None, key
            assert schema[key]["nullable"] is True, key

    def test_f3_default_diameter_range_selects_the_suite_tool(self) -> None:
        """The demo grid is drilled with TOOL (D = 10 mm); R11 would drop
        every one of its holes silently if the default range excluded it."""
        schema = get_strategy_params("drilling")
        assert schema["hole_diameter_minimum"]["default"] <= TOOL.diameter
        assert TOOL.diameter <= schema["hole_diameter_maximum"]["default"]


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_unknown_finish_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="finish_mode must be one of"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
                params={"finish_mode": "bogus"},
            )

    def test_float_params_are_still_clamped(self) -> None:
        """The legacy clamp must survive the schema refactor."""
        validated = EXECUTOR._validate_params(
            "face_milling",
            {"step_over": 1e6, "step_down": -3.0, "overlap": 2.0},
        )
        assert validated == {"step_over": 50.0, "step_down": 0.1, "overlap": 1.0}

    def test_f2_float_params_are_clamped_to_their_schema(self) -> None:
        validated = EXECUTOR._validate_params(
            "waterline_finishing", {"cell_mm": 99.0, "stock_to_leave_mm": -4.0},
        )
        assert validated["cell_mm"] == 5.0
        assert validated["stock_to_leave_mm"] == 0.0

    def test_f2_integer_param_is_integral(self) -> None:
        validated = EXECUTOR._validate_params(
            "waterline_finishing", {"scallop_rings": 7.0},
        )
        assert validated["scallop_rings"] == 7
        assert isinstance(validated["scallop_rings"], int)

    def test_nullable_params_accept_none(self) -> None:
        validated = EXECUTOR._validate_params(
            "waterline_finishing",
            {"scallop_rings": None, "profile": None, "mesh": None},
        )
        assert validated["scallop_rings"] is None
        assert validated["profile"] is None
        assert validated["mesh"] is None

    def test_object_params_are_passed_through_untouched(self) -> None:
        """No numeric range exists, so nothing may be clamped or coerced."""
        profile = [[-10.0, -10.0], [10.0, -10.0], [10.0, 10.0], [-10.0, 10.0]]
        validated = EXECUTOR._validate_params(
            "waterline_finishing", {"profile": profile},
        )
        assert validated["profile"] is profile

    def test_none_for_a_required_param_is_refused(self) -> None:
        with pytest.raises(ValueError, match="step_down must not be None"):
            EXECUTOR.execute(
                strategy="adaptive_engagement", tool=TOOL, stock_bbox=SMALL,
                params={"step_down": None},
            )

    def test_a_parameter_outside_the_schema_is_reported_not_dropped(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``stepdown`` is the KERNEL's spelling of the app's ``step_down``.

        Passing it here would otherwise vanish without a trace and the kernel
        would plan at its own default — indistinguishable from a correct run.
        """
        with caplog.at_level(logging.WARNING, logger="app.strategy_executor"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
                params={"stepdown": 5.0, "cell_mm": 0.5,
                        "finish_mode": "waterline"},
            )
        assert "outside its schema" in caplog.text
        assert "stepdown" in caplog.text

    def test_a_fractional_ring_count_is_refused_not_truncated(self) -> None:
        """One contract for one parameter: the kernel refuses 3.5 too."""
        with pytest.raises(ValueError, match="scallop_rings must be an integer"):
            EXECUTOR._validate_params(
                "waterline_finishing", {"scallop_rings": 3.5},
            )


# ---------------------------------------------------------------------------
# Dispatch: adaptive_engagement (F1)
# ---------------------------------------------------------------------------

class TestAdaptiveEngagementDispatch:
    def test_execute_returns_a_toolpath_for_the_standard_stock(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="adaptive_engagement", tool=TOOL, stock_bbox=STOCK,
        )
        assert isinstance(toolpath, ToolpathData)
        assert toolpath.strategy == "adaptive_engagement"
        assert toolpath.name == "Adaptive Engagement"
        assert toolpath.tool is TOOL
        assert len(toolpath.moves) > 0

    def test_recorded_params_are_the_validated_app_params(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="adaptive_engagement", tool=TOOL, stock_bbox=SMALL,
        )
        assert set(toolpath.params) == {
            "step_over", "step_down", "engagement_gate", "feed_rate",
        }

    def test_moves_are_typed_and_stay_inside_the_stock(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="adaptive_engagement", tool=TOOL, stock_bbox=STOCK,
        )
        for move in toolpath.moves:
            assert isinstance(move.move_type, MoveType)
        cut_z = [m.end.z for m in toolpath.moves
                 if m.move_type is not MoveType.RAPID]
        assert cut_z, "F1 produced no cutting moves"
        assert min(cut_z) >= STOCK.min.z - 1e-9
        assert max(cut_z) <= STOCK.max.z + 1e-9

    def test_step_over_in_mm_becomes_a_fraction_of_d(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The one unit translation the app owns for F1."""
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(
            strategy="adaptive_engagement", tool=TOOL, stock_bbox=STOCK,
            params={
                "step_over": 2.5, "step_down": 1.5,
                "feed_rate": 750.0, "engagement_gate": 0.25,
            },
        )

        assert spy.name == "adaptive_engagement"
        assert spy.kwargs["stepover"] == pytest.approx(2.5 / TOOL.diameter)
        assert spy.kwargs["stepdown"] == 1.5
        assert spy.kwargs["feed_rate"] == 750.0
        assert spy.kwargs["engagement_gate"] == 0.25
        # ...and nothing else: an app-level key leaked through as-is would be
        # silently ignored by the kernel, exactly like a mis-wired one.
        assert set(spy.kwargs) == {
            "stepover", "stepdown", "feed_rate", "engagement_gate",
            "top_of_stock", "bottom_of_stock",
        }

    def test_a_step_over_the_kernel_would_reject_is_refused_first(self) -> None:
        """Chip load is a tooling decision, so no silent clamp."""
        small_tool = ToolDef(diameter=6.0)
        with pytest.raises(ValueError, match="≤ 0.5 × D"):
            EXECUTOR.execute(
                strategy="adaptive_engagement", tool=small_tool,
                stock_bbox=STOCK, params={"step_over": 6.0},
            )

    def test_the_default_step_over_fits_the_suite_tool(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="adaptive_engagement", tool=TOOL, stock_bbox=SMALL,
        )
        assert len(toolpath.moves) > 0

    def test_a_degenerate_tool_diameter_is_a_value_error(self) -> None:
        """No ``ZeroDivisionError`` may escape the executor's contract."""
        with pytest.raises(ValueError, match="tool diameter must be a positive"):
            EXECUTOR.execute(
                strategy="adaptive_engagement", tool=ToolDef(diameter=0.0),
                stock_bbox=SMALL,
            )

    def test_the_default_step_over_needs_a_cutter_of_at_least_8mm(self) -> None:
        """Pinned limitation: the schema default is a fixed 4 mm.

        It validates for ``D >= 8 mm`` (the GUI's cutter is 10 mm) and is
        refused below that, with the ceiling named in mm so the caller knows
        exactly what to type.  If this ever stops raising, the default has
        become tool-relative — update the schema comment alongside it.
        """
        with pytest.raises(ValueError, match="≤ 0.5 × D"):
            EXECUTOR.execute(
                strategy="adaptive_engagement",
                tool=ToolDef(diameter=6.0),   # 4 mm is 0.667 x D
                stock_bbox=SMALL,
            )

    def test_kernel_diagnostics_reach_the_module_log(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``execute()`` drops the kernel's diagnostics from ``params``.

        The module log is then the only place they survive, so the docstring
        promising them has to be true at runtime — feed histogram included,
        as a digest rather than a wall of one-bin-per-line entries.
        """
        with caplog.at_level(logging.INFO, logger="app.strategy_executor"):
            EXECUTOR.execute(
                strategy="adaptive_engagement", tool=TOOL, stock_bbox=SMALL,
            )
        assert "Kernel strategy 'adaptive_engagement'" in caplog.text
        assert "feed_vocabulary" in caplog.text
        assert "feed_histogram" in caplog.text
        assert "bins /" in caplog.text, "the histogram should be a digest"


# ---------------------------------------------------------------------------
# Dispatch: waterline_finishing (F2)
# ---------------------------------------------------------------------------

class TestWaterlineFinishingDispatch:
    def test_execute_returns_a_toolpath_for_the_standard_stock(self) -> None:
        """The default path ``test_all_strategies_generate`` exercises.

        100 mm square stock, 10 mm tool, no user params: the kernel's own
        0.05 mm ``cell_mm`` default is refused here (5.8M section cells vs
        the 4M budget), so this passing is the proof that the app schema
        carries a default that actually plans.
        """
        toolpath = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=STOCK,
        )
        assert isinstance(toolpath, ToolpathData)
        assert toolpath.strategy == "waterline_finishing"
        assert toolpath.name == "Waterline Finishing"
        assert toolpath.tool is TOOL
        assert len(toolpath.moves) > 0

    def test_the_kernel_default_cell_is_refused_on_that_same_stock(self) -> None:
        """Pins WHY the app default is coarser than the kernel's.

        ``cell_mm = 0.05`` is the kernel's reference pitch and stays
        requestable (the schema range allows it), but on this 100 mm stock it
        needs a 5.8M-cell section raster against a 4M budget.  The refusal
        fires before any rastering happens, so this is cheap — and if the
        kernel ever raises ``MAX_RASTER_CELLS``, this test says so instead of
        the justification in the schema comment silently going stale.
        """
        with pytest.raises(ValueError, match="cell_mm"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=TOOL, stock_bbox=STOCK,
                params={"cell_mm": 0.05},
            )

    def test_recorded_params_are_the_validated_app_params(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
        )
        assert set(toolpath.params) == {
            "finish_mode", "cell_mm", "cusp_height_mm", "scallop_rings",
            "stock_to_leave_mm", "step_down", "feed_rate", "profile", "mesh",
        }

    def test_every_f2_parameter_reaches_the_kernel(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Nine app keys, nine kernel keywords — asserted, not assumed.

        ``waterline_finishing._build_config`` starts from ``dict(values)``,
        so a MIS-WIRED key is silently ignored and the kernel falls back to
        its own default — which for ``stepdown`` / ``feed_rate`` /
        ``stock_to_leave_mm`` happens to equal the app default, so no
        end-to-end assertion would ever notice.  Every key is checked with a
        value that differs from the kernel default, except ``mesh``, whose
        kernel default is also ``None`` — for that one the key's PRESENCE is
        what's asserted (drop the ``mesh=`` line below and this test fails
        with a ``KeyError``).
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL,
            stock_bbox=STOCK_AROUND_PROFILE,
            params={
                "finish_mode": "waterline",
                "cell_mm": 0.5,
                "cusp_height_mm": 0.01,
                "scallop_rings": 3,
                "stock_to_leave_mm": 1.5,
                "step_down": 5.0,
                "feed_rate": 750.0,
                "profile": PROFILE,
                "mesh": None,
            },
        )

        assert spy.name == "waterline_finishing"
        assert spy.kwargs["finish_mode"] == "waterline"
        assert spy.kwargs["cell_mm"] == 0.5
        assert spy.kwargs["cusp_height_mm"] == 0.01
        assert spy.kwargs["scallop_rings"] == 3
        assert spy.kwargs["stock_to_leave_mm"] == 1.5
        assert spy.kwargs["feed_rate"] == 750.0
        assert spy.kwargs["profile"] == PROFILE
        assert spy.kwargs["mesh"] is None
        # the one renamed key in either direction
        assert spy.kwargs["stepdown"] == 5.0, "app step_down -> kernel stepdown"
        # ...and nothing else: a leaked app-level key would be silently
        # ignored by the kernel, exactly like a mis-wired one.
        assert set(spy.kwargs) == {
            "finish_mode", "cell_mm", "cusp_height_mm", "scallop_rings",
            "stock_to_leave_mm", "stepdown", "feed_rate", "profile", "mesh",
            "top_of_stock", "bottom_of_stock",
        }

    def test_cut_levels_stay_inside_the_stock_z_range(self) -> None:
        """Guards the top/bottom-of-stock translation.

        Without it the kernel would plan against its own
        ``top_of_stock = 0.0`` / ``bottom_of_stock = -10.0`` defaults and
        emit levels BELOW ``SMALL.min.z``.
        """
        toolpath = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
        )
        cut_z = [m.end.z for m in toolpath.moves
                 if m.move_type is not MoveType.RAPID]
        assert cut_z, "F2 produced no cutting moves"
        assert min(cut_z) >= SMALL.min.z - 1e-9, "a cut level fell below the stock"
        assert max(cut_z) <= SMALL.max.z + 1e-9, "a cut level rose above the stock"
        assert min(cut_z) == pytest.approx(SMALL.min.z, abs=1e-9), (
            "the stock bottom is always a level of its own"
        )

    def test_finish_mode_selects_the_pass_kinds(self) -> None:
        waterline_only = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
            params={"finish_mode": "waterline"},
        )
        assert len(waterline_only.moves) > 0

        both = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
            params={"finish_mode": "both"},
        )
        assert len(both.moves) > len(waterline_only.moves), (
            "'both' must add the constant-scallop passes on top of waterline"
        )

    def test_profile_replaces_the_stock_footprint(self) -> None:
        """The ``profile`` parameter must actually change the path.

        With a profile the contour follows THAT outline offset outward by
        the tool radius; with neither source it follows the stock box the
        same way round.  Measuring the far side of the contour separates the
        two sources exactly: 10 mm + R vs 30 mm + R.
        """
        tool = ToolDef(diameter=6.0)
        radius = tool.radius

        from_profile = EXECUTOR.execute(
            strategy="waterline_finishing", tool=tool,
            stock_bbox=STOCK_AROUND_PROFILE,
            params={"profile": PROFILE, "cell_mm": 0.5,
                    "finish_mode": "waterline"},
        )
        from_stock = EXECUTOR.execute(
            strategy="waterline_finishing", tool=tool,
            stock_bbox=STOCK_AROUND_PROFILE,
            params={"cell_mm": 0.5, "finish_mode": "waterline"},
        )

        assert len(from_profile.moves) > 0
        assert len(from_stock.moves) > 0

        profile_reach = max(abs(m.end.x) for m in from_profile.moves)
        stock_reach = max(abs(m.end.x) for m in from_stock.moves)
        assert profile_reach == pytest.approx(10.0 + radius, abs=1e-6)
        assert stock_reach == pytest.approx(30.0 + radius, abs=1e-6)

    def test_without_a_source_the_stock_footprint_is_finished(self) -> None:
        """Declared fallback: no ``profile`` and no ``mesh`` means the block.

        The kernel finishes the outside walls of the stock itself, so the
        tool CENTRE path sits outside the block — by exactly one tool radius
        on the straights.  This is the app-layer default today because the
        GUI has no geometry source wired into ``execute()``; handing
        ``profile=`` or ``mesh=`` is how a caller points F2 at a real part.
        """
        toolpath = EXECUTOR.execute(
            strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
        )
        assert len(toolpath.moves) > 0
        for move in toolpath.moves:
            inside_block = (
                SMALL.min.x <= move.end.x <= SMALL.max.x
                and SMALL.min.y <= move.end.y <= SMALL.max.y
            )
            assert not inside_block, (
                "with no profile/mesh the contour should follow the outside "
                f"of the stock block, not sit inside it: {move.end}"
            )

    def test_profile_and_mesh_together_are_refused(self) -> None:
        mesh = {
            "vertices": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            "faces": [(0, 1, 2)],
        }
        with pytest.raises(ValueError, match="not both"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=TOOL, stock_bbox=SMALL,
                params={"profile": PROFILE, "mesh": mesh},
            )

    def test_a_stock_too_big_for_the_default_cell_reports_the_reason(self) -> None:
        """The declared limitation, surfaced as an error instead of a no-op.

        600 mm square at the default cell needs a section raster well over
        the kernel's 4M-cell budget; the user is told to raise ``cell_mm``
        rather than handed an empty toolpath.
        """
        huge = BBox(min=Vec3(-300, -300, 0), max=Vec3(300, 300, 20))
        with pytest.raises(ValueError, match="cell_mm"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=TOOL, stock_bbox=huge,
            )

    def test_a_kernel_range_error_is_reported(self) -> None:
        """A real kernel rejection, reached through the app's own params.

        ``cusp_height_mm`` may not exceed the tool radius; the app's schema
        allows up to 5 mm (fine for a 10 mm cutter), so a 6 mm cutter plus a
        5 mm cusp is refused by the kernel and must surface here.
        """
        small_tool = ToolDef(diameter=6.0)  # R = 3.0 mm < 5 mm
        with pytest.raises(ValueError, match="cusp_height_mm"):
            EXECUTOR.execute(
                strategy="waterline_finishing", tool=small_tool,
                stock_bbox=SMALL, params={"cusp_height_mm": 5.0},
            )


# ---------------------------------------------------------------------------
# Dispatch: drilling (F3)
# ---------------------------------------------------------------------------

class TestDrillingDispatch:
    def test_execute_returns_a_toolpath_for_the_standard_stock(self) -> None:
        toolpath = EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=STOCK,
        )
        assert isinstance(toolpath, ToolpathData)
        assert toolpath.strategy == "drilling"
        assert toolpath.name == "Drilling"
        assert toolpath.tool is TOOL
        assert len(toolpath.moves) > 0
        # params is the VALIDATED APP dict: the caller asked for nothing, so
        # every key is its schema default — the demo grid is dispatch-time
        # geometry, not a parameter the caller suddenly appears to have set.
        assert set(toolpath.params) == set(get_strategy_params("drilling"))
        assert toolpath.params["holes"] is None

    def test_the_default_path_is_answered_by_the_kernel(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The whole point of this card: no legacy planner may answer
        ``drilling`` any more, not even on the no-parameter path the GUI
        takes today.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(strategy="drilling", tool=TOOL, stock_bbox=STOCK)

        assert spy.name == "drilling"

    def test_the_no_param_geometry_is_the_legacy_3x3_demo_grid(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """What ``holes=None`` is translated to, asserted coordinate-wise.

        25 / 50 / 75 % of each stock axis, stock top to stock bottom, each
        hole as wide as the spindle's tool — the exact points the retired
        ``_drilling`` pecked at, so the default path's GEOMETRY is
        unchanged while the algorithm behind it is now the kernel's.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(strategy="drilling", tool=TOOL, stock_bbox=STOCK)

        holes = spy.kwargs["holes"]
        assert len(holes) == 9
        assert {h["x"] for h in holes} == {-25.0, 0.0, 25.0}
        assert {h["y"] for h in holes} == {-25.0, 0.0, 25.0}
        for h in holes:
            assert h["top_z"] == STOCK.max.z
            assert h["bottom_z"] == STOCK.min.z
            assert h["diameter"] == TOOL.diameter

    def test_the_demo_grid_is_drilled_through_the_stock_planes(self) -> None:
        """End-to-end geometry: measured cycle expansion, app's grid.

        The retract plane is stock top + 5 mm and the clearance plane
        another + 10 mm above it (the kernel's measured defaults, which
        this app schema mirrors), and each hole is cut from the stock top
        down to the stock bottom exactly as the legacy planner did.
        """
        toolpath = EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=STOCK,
        )
        cuts = [m for m in toolpath.moves if m.move_type is MoveType.LINEAR]
        assert len(cuts) == 9, "one plunge per grid hole on the plain cycle"
        assert {m.end.z for m in cuts} == {STOCK.min.z}
        assert {(m.end.x, m.end.y) for m in cuts} == {
            (x, y) for x in (-25.0, 0.0, 25.0) for y in (-25.0, 0.0, 25.0)
        }
        assert max(m.end.z for m in toolpath.moves) == STOCK.max.z + 15.0
        assert STOCK.max.z + 5.0 in {m.end.z for m in toolpath.moves}

    def test_the_default_feed_is_the_measured_plunge_expression(self) -> None:
        """``feed_rate`` 1000 → ``tool_feed_cutting`` 1000 → a flat end
        mill plunges at 1000/3, serialised as the post writes it, and the
        panel's spindle default rides on every move.
        """
        toolpath = EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=STOCK,
        )
        feeds = {m.feed for m in toolpath.moves
                 if m.move_type is MoveType.LINEAR}
        assert feeds == {333.333344}
        assert {m.spindle_speed for m in toolpath.moves} == {4000.0}

    def test_an_explicit_hole_table_passes_through_untouched(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=SMALL,
            params={"holes": HOLES},
        )

        assert spy.kwargs["holes"] is HOLES, "not rebuilt, not copied"

    def test_every_drilling_parameter_reaches_the_kernel(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ten app keys, six kernel keywords — one of them (``cycle``)
        being the nested dict of seven CycleConfig fields.

        ``DrillingStrategy._build_config`` ignores any keyword it does not
        know, so a MIS-WIRED key — a cycle field left at the top level, an
        app-only name passed through — is silently dropped and the kernel
        plans at its own default, which for several of these equals the
        app default.  Every value below differs from the kernel default on
        purpose, and the exact sets are asserted so nothing may leak.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=SMALL,
            params={
                "holes": HOLES,
                "cycle_type": "deep-drilling",
                "pecking_depth": 2.5,
                "retract_height_offset": 7.0,
                "clearance_height_offset": 12.0,
                "hole_toolpath_order": "order-by-x",
                "hole_diameter_minimum": 3.0,
                "hole_diameter_maximum": 50.0,
                "feed_rate": 750.0,
                "spindle_speed": 6000,
            },
        )

        assert spy.name == "drilling"
        assert spy.kwargs["holes"] is HOLES
        assert spy.kwargs["feed_rate"] == 750.0
        assert spy.kwargs["spindle_speed"] == 6000
        assert spy.kwargs["top_of_stock"] == SMALL.max.z
        assert spy.kwargs["bottom_of_stock"] == SMALL.min.z
        assert set(spy.kwargs) == {
            "holes", "cycle", "feed_rate", "spindle_speed",
            "top_of_stock", "bottom_of_stock",
        }
        assert spy.kwargs["cycle"] == {
            "cycle_type": "deep-drilling",
            "pecking_depth": 2.5,
            "retract_height_offset": 7.0,
            "clearance_height_offset": 12.0,
            "hole_toolpath_order": "order-by-x",
            "hole_diameter_minimum": 3.0,
            "hole_diameter_maximum": 50.0,
        }
        # a cycle key left at the top level would be ignored by the kernel;
        # a cycle key NESTED and also repeated up here would be a bug too
        assert set(spy.kwargs) & set(spy.kwargs["cycle"]) == set()

    def test_a_blank_peck_depth_reaches_the_kernel_as_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Blank must not be replaced by an app-chosen number.

        ``CycleConfig`` reads ``pecking_depth=None`` as "evaluate the
        stored expression" (0.25 × D); passing 0.0 or the schema's min
        instead would be the app pretending to know the tool.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=SMALL,
            params={"cycle_type": "deep-drilling"},
        )

        assert spy.kwargs["cycle"]["pecking_depth"] is None

    def test_pecking_depth_only_bites_on_a_peck_cycle(self) -> None:
        """The kernel's gate, observed from the app: ``pecking_depth`` is
        stored but inert on the default ``drilling`` cycle, and splits the
        plunge the moment ``deep-drilling`` is selected — so the schema
        label's promise is true at runtime.
        """
        hole = [HOLES[0]]
        plain = EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=SMALL,
            params={"holes": hole, "cycle_type": "drilling",
                    "pecking_depth": 2.0},
        )
        pecked = EXECUTOR.execute(
            strategy="drilling", tool=TOOL, stock_bbox=STOCK,
            params={"holes": [{"x": 10.0, "y": 10.0, "top_z": 20.0,
                               "bottom_z": 5.0, "diameter": 6.0}],
                    "cycle_type": "deep-drilling", "pecking_depth": 3.0},
        )

        def plunges(tp: ToolpathData) -> list[float]:
            return sorted(m.end.z for m in tp.moves
                          if m.move_type is not MoveType.RAPID)

        assert plunges(plain) == [0.0], "plain drilling is one plunge"
        assert len(plunges(pecked)) > 1, "deep drilling must peck"

    def test_the_legacy_keys_are_reported_and_never_reach_the_kernel(
        self, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``peck_depth`` / ``retract`` / ``dwell`` are warned about AND
        shown not to alias anything: the kernel still receives its own
        defaults, so a caller cannot half-migrate onto a name the schema
        dropped.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        with caplog.at_level(logging.WARNING, logger="app.strategy_executor"):
            EXECUTOR.execute(
                strategy="drilling", tool=TOOL, stock_bbox=SMALL,
                params={"peck_depth": 4.0, "retract": 3.0, "dwell": 1.0},
            )

        assert "outside its schema" in caplog.text
        for legacy in ("peck_depth", "retract", "dwell"):
            assert legacy in caplog.text, legacy
        assert spy.kwargs["cycle"] == {
            "cycle_type": "drilling",
            "pecking_depth": None,
            "retract_height_offset": 5.0,
            "clearance_height_offset": 10.0,
            "hole_toolpath_order": "optimize-order",
            "hole_diameter_minimum": 0.0,
            "hole_diameter_maximum": 100.0,
        }

    def test_a_malformed_hole_row_surfaces_the_kernel_error(self) -> None:
        """Hole-table validation is the kernel's; its message must reach
        the GUI instead of an empty toolpath.
        """
        with pytest.raises(ValueError, match="5-tuple"):
            EXECUTOR.execute(
                strategy="drilling", tool=TOOL, stock_bbox=SMALL,
                params={"holes": [[5.0, 5.0]]},
            )

    def test_an_inverted_diameter_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="hole_diameter_minimum must not"):
            EXECUTOR.execute(
                strategy="drilling", tool=TOOL, stock_bbox=SMALL,
                params={"hole_diameter_minimum": 50.0,
                        "hole_diameter_maximum": 10.0},
            )

    def test_a_table_the_range_selects_empty_is_refused_not_empty(
        self,
    ) -> None:
        """R11's silent empty selection becomes a ValueError at app level.

        The kernel is right to plan nothing when no hole matches (that is
        the measured Fusion behaviour), but the GUI would report the
        resulting 0-move toolpath as a completed cut — the exact failure
        mode ``_kernel_moves``' docstring rules out — so the executor
        names the range instead.
        """
        with pytest.raises(ValueError, match="0 moves"):
            EXECUTOR.execute(
                strategy="drilling", tool=TOOL, stock_bbox=SMALL,
                params={"holes": HOLES,          # 6 mm holes
                        "hole_diameter_minimum": 50.0,
                        "hole_diameter_maximum": 100.0},
            )

    def test_an_empty_hole_table_is_refused_not_planned(self) -> None:
        """``holes=[]`` is the other way back to zero moves.

        An explicitly empty table is even less ambiguous than an empty
        selection — the caller asked for no holes — and the GUI would
        still report the 0-move result as a completed cut, so it gets the
        same ValueError rather than R11's silent no-toolpath state.
        """
        with pytest.raises(ValueError, match="0 moves"):
            EXECUTOR.execute(
                strategy="drilling", tool=TOOL, stock_bbox=SMALL,
                params={"holes": []},
            )

    def test_kernel_diagnostics_reach_the_module_log(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``execute()`` keeps the app params on the result, so the
        kernel's own selection/plane/feed report survives only here."""
        with caplog.at_level(logging.INFO, logger="app.strategy_executor"):
            EXECUTOR.execute(strategy="drilling", tool=TOOL, stock_bbox=STOCK)
        assert "Kernel strategy 'drilling'" in caplog.text
        assert "holes_selected" in caplog.text
        assert "feed_histogram" in caplog.text
        assert "bins /" in caplog.text, "the histogram should be a digest"


# ---------------------------------------------------------------------------
# Kernel-backed dispatch plumbing (all kernel-backed strategies)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "strategy", ["adaptive_engagement", "waterline_finishing", "drilling"],
)
class TestKernelPlumbing:
    def test_stock_z_faces_come_from_the_bbox(
        self, monkeypatch: pytest.MonkeyPatch, strategy: str,
    ) -> None:
        """Every kernel-backed strategy is handed the same stock faces.

        ``drilling`` does not READ them — DrillingStrategy measures its
        planes from the ``stock`` argument, which is this same bbox, so
        the numbers coincide either way — hence for that strategy this
        pins the plumbing, not the plane arithmetic;
        ``TestDrillingDispatch
        ::test_the_demo_grid_is_drilled_through_the_stock_planes`` pins
        the latter.
        """
        spy = _Spy()
        spy.install(monkeypatch)

        EXECUTOR.execute(strategy=strategy, tool=TOOL, stock_bbox=SMALL)

        assert spy.name == strategy
        assert spy.kwargs["top_of_stock"] == SMALL.max.z
        assert spy.kwargs["bottom_of_stock"] == SMALL.min.z

    def test_a_kernel_error_toolpath_becomes_a_value_error(
        self, monkeypatch: pytest.MonkeyPatch, strategy: str,
    ) -> None:
        """Not an empty toolpath the GUI would call a successful cut."""

        class Refusing:
            def generate_toolpath(self, stock, tool, **kwargs):
                return ToolpathData(
                    name="Refusing", tool=tool, strategy=strategy,
                    params={"error": "parameters rejected on purpose"},
                )

        monkeypatch.setattr(
            strategy_executor, "get_strategy", lambda name: Refusing(),
        )

        with pytest.raises(ValueError, match="parameters rejected on purpose"):
            EXECUTOR.execute(strategy=strategy, tool=TOOL, stock_bbox=STOCK)
