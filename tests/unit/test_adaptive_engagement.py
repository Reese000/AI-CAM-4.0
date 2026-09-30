"""
Unit tests: adaptive roughing with engagement-gated feed (feature F1).

`Fusion 360 RE/docs/p5-execution-plan.md` section 4, row P5/3.

Vocabulary citations (sibling checkout `Fusion 360 RE`, read-only):

* R8 of `docs/behavior/adaptive.md` — every capture carries exactly three
  distinct feed values `{feed/3, 0.9*feed, feed}`: observed
  `{333.333344, 900, 1000}` @1000, `{166.666672, 450, 500}` @500,
  `{500, 1350, 1500}` @1500.
* `SCH:31720` — `tool_feedPlunge = tool_feedCutting / 3`.
* `SCH:35352` / `SCH:34760` — `reducedFeedrate` (the 0.9 arm), R10/R11.
* R12 — the feed-optimisation group *selects* a value; it never scales one,
  so a fourth value is impossible by construction.
* `SCH:34600` — `optimalLoad = tool_diameter * 0.4`, the constant radial
  engagement of every ring after the first.
"""

import pytest

from kernel.strategies import get_strategy, list_strategies
from kernel.strategies.adaptive_engagement import (
    DEFAULT_ENGAGEMENT_GATE,
    AdaptiveEngagementStrategy,
    feed_vocabulary,
    ring_engagement,
    select_feed,
)
from kernel.strategies.base import OperationParams
from kernel.types import BBox, MoveType, ToolDef, ToolpathData, Vec3

# Measured triplets from adaptive.md R8 (observed literals, feed in mm/min).
R8_OBSERVED = {
    500.0: (166.666672, 450.0, 500.0),
    1000.0: (333.333344, 900.0, 1000.0),
    1500.0: (500.0, 1350.0, 1500.0),
}

TOOL_DIAMETER = 6.35
FEED = 1000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_stock() -> BBox:
    """A 120 x 80 x 12 mm plate, top of stock at Z0."""
    return BBox(min=Vec3(-60.0, -40.0, -12.0), max=Vec3(60.0, 40.0, 0.0))


def make_operation(**extra: object) -> OperationParams:
    """A valid F1 operation; keyword overrides land in extra_args."""
    return OperationParams(
        strategy="adaptive_engagement",
        stock=make_stock(),
        tool=ToolDef(tool_id="T01", name="End Mill", diameter=TOOL_DIAMETER),
        stepover=0.4,
        stepdown=3.0,
        feed_rate=FEED,
        spindle_speed=8000.0,
        clearance_height=5.0,
        top_of_stock=0.0,
        bottom_of_stock=-12.0,
        extra_args=dict(extra),
    )


def run_toolpath(**extra: object) -> ToolpathData:
    return AdaptiveEngagementStrategy().run(make_operation(**extra))


def cutting_feeds(tp: ToolpathData) -> set[float]:
    return {m.feed for m in tp.moves if m.move_type is MoveType.LINEAR}


# ---------------------------------------------------------------------------
# The measured three-value vocabulary
# ---------------------------------------------------------------------------

class TestFeedVocabulary:
    """feed_vocabulary() must reproduce adaptive.md R8 and nothing else."""

    @pytest.mark.parametrize("feed", sorted(R8_OBSERVED))
    def test_reproduces_the_measured_triplet(self, feed):
        plunge, reduced, cutting = R8_OBSERVED[feed]
        vocab = feed_vocabulary(feed)
        assert vocab["plunge"] == pytest.approx(plunge, rel=1e-5)
        assert vocab["reduced"] == pytest.approx(reduced, rel=1e-9)
        assert vocab["cutting"] == pytest.approx(cutting, rel=1e-9)

    @pytest.mark.parametrize("feed", sorted(R8_OBSERVED))
    def test_is_exactly_three_values(self, feed):
        vocab = feed_vocabulary(feed)
        assert set(vocab) == {"plunge", "reduced", "cutting"}
        assert len(set(vocab.values())) == 3

    @pytest.mark.parametrize("feed", sorted(R8_OBSERVED))
    def test_arms_come_from_the_expression_graph(self, feed):
        """plunge == feed/3, reduced == 0.9*feed, cutting == feed."""
        vocab = feed_vocabulary(feed)
        assert vocab["plunge"] == pytest.approx(feed / 3.0)
        assert vocab["reduced"] == pytest.approx(feed * 0.9)
        assert vocab["cutting"] == pytest.approx(feed)

    @pytest.mark.parametrize("feed", [0.0, -100.0])
    def test_rejects_a_non_positive_feed(self, feed):
        with pytest.raises(ValueError):
            feed_vocabulary(feed)


# ---------------------------------------------------------------------------
# THE GUARDED SELECTION LINE
# ---------------------------------------------------------------------------

class TestSelectFeedGate:
    """select_feed() selects one vocabulary value from engagement."""

    def test_fresh_full_diameter_slot_selects_the_reduced_arm(self):
        # First ring: cutter fully surrounded, ae == D >= 0.5 * D.
        assert select_feed(TOOL_DIAMETER, TOOL_DIAMETER, FEED) == pytest.approx(
            FEED * 0.9
        )

    def test_constant_engagement_ring_selects_the_cutting_arm(self):
        # Every later ring: ae == 0.4 * D (SCH:34600 optimalLoad = D * 0.4).
        assert select_feed(0.4 * TOOL_DIAMETER, TOOL_DIAMETER, FEED) == pytest.approx(
            FEED
        )

    def test_the_gate_boundary_is_inclusive(self):
        boundary = DEFAULT_ENGAGEMENT_GATE * TOOL_DIAMETER
        assert select_feed(boundary, TOOL_DIAMETER, FEED) == pytest.approx(FEED * 0.9)
        assert select_feed(boundary - 1e-9, TOOL_DIAMETER, FEED) == pytest.approx(FEED)

    def test_a_plunge_is_priced_at_feed_over_three_regardless_of_engagement(self):
        assert select_feed(
            TOOL_DIAMETER, TOOL_DIAMETER, FEED, is_plunge=True
        ) == pytest.approx(FEED / 3.0)
        assert select_feed(
            0.0, TOOL_DIAMETER, FEED, is_plunge=True
        ) == pytest.approx(FEED / 3.0)

    @pytest.mark.parametrize("ae_factor", [0.0, 0.1, 0.4, 0.5, 0.75, 1.0, 1.5])
    @pytest.mark.parametrize("gate", [0.1, 0.5, 0.99])
    def test_selection_never_leaves_the_vocabulary(self, ae_factor, gate):
        vocab = feed_vocabulary(FEED)
        selected = select_feed(
            ae_factor * TOOL_DIAMETER, TOOL_DIAMETER, FEED, engagement_gate=gate
        )
        assert selected in set(vocab.values())

    @pytest.mark.parametrize("gate", [0.1, 0.5, 0.99])
    def test_the_gate_selects_it_does_not_modulate(self, gate):
        """R12: the group scales nothing — only whole vocabulary values."""
        vocab = feed_vocabulary(FEED)
        allowed = {vocab["reduced"], vocab["cutting"]}
        for step in range(0, 101):
            ae = TOOL_DIAMETER * step / 100.0
            assert select_feed(ae, TOOL_DIAMETER, FEED, engagement_gate=gate) in allowed

    def test_default_gate_is_the_documented_half_diameter(self):
        assert DEFAULT_ENGAGEMENT_GATE == 0.5


# ---------------------------------------------------------------------------
# Engagement geometry
# ---------------------------------------------------------------------------

class TestRingEngagement:
    """ae for each offset ring: full D for the fresh slot, the band after."""

    def test_first_ring_is_a_fully_engaged_slot(self):
        assert ring_engagement(True, 0.0, 10.0, 40.0) == 10.0

    def test_first_ring_is_bounded_by_the_material_present(self):
        # Footprint narrower than the cutter: only 2 * half-width of material.
        assert ring_engagement(True, 0.0, 10.0, 3.0) == 6.0

    def test_later_ring_engagement_is_the_band(self):
        assert ring_engagement(False, 4.0, 10.0, 40.0) == 4.0

    def test_band_is_clamped_to_the_cutter(self):
        assert ring_engagement(False, 25.0, 10.0, 40.0) == 10.0

    def test_negative_band_never_produces_negative_engagement(self):
        assert ring_engagement(False, -3.0, 10.0, 40.0) == 0.0

    def test_default_stepover_gives_constant_engagement_below_the_gate(self):
        """0.4 * D (SCH:34600) sits under the 0.5 * D gate: constant by design."""
        ae = ring_engagement(False, TOOL_DIAMETER * 0.4, TOOL_DIAMETER, 40.0)
        assert ae == pytest.approx(TOOL_DIAMETER * 0.4)
        assert ae < DEFAULT_ENGAGEMENT_GATE * TOOL_DIAMETER


# ---------------------------------------------------------------------------
# Registration glue
# ---------------------------------------------------------------------------

class TestRegistration:
    """The module is reachable through the kernel strategy registry."""

    def test_registered_by_name(self):
        assert "adaptive_engagement" in list_strategies()
        strategy = get_strategy("adaptive_engagement")
        assert isinstance(strategy, AdaptiveEngagementStrategy)
        assert strategy.name == "adaptive_engagement"
        assert "engagement-gated feed" in strategy.description


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_operation_has_no_errors(self):
        assert AdaptiveEngagementStrategy().validate_params(make_operation()) == []

    def _errors(self, mutate) -> list[str]:
        operation = make_operation()
        mutate(operation)
        return AdaptiveEngagementStrategy().validate_params(operation)

    def test_missing_tool(self):
        errors = self._errors(lambda op: setattr(op, "tool", None))
        assert any("Tool definition is required" in e for e in errors)

    def test_missing_stock(self):
        errors = self._errors(lambda op: setattr(op, "stock", None))
        assert any("Stock definition is required" in e for e in errors)

    @pytest.mark.parametrize("stepover", [0.0, -0.1, 0.75])
    def test_stepover_outside_the_adaptive_range(self, stepover):
        errors = self._errors(lambda op: setattr(op, "stepover", stepover))
        assert any("Stepover" in e for e in errors)

    @pytest.mark.parametrize("stepdown", [0.0, -2.0])
    def test_stepdown_must_be_positive(self, stepdown):
        errors = self._errors(lambda op: setattr(op, "stepdown", stepdown))
        assert any("Stepdown" in e for e in errors)

    @pytest.mark.parametrize("feed", [0.0, -500.0])
    def test_feed_must_be_positive(self, feed):
        errors = self._errors(lambda op: setattr(op, "feed_rate", feed))
        assert any("Feed rate" in e for e in errors)

    @pytest.mark.parametrize("gate", [0.0, -0.2, 1.5, "fast"])
    def test_gate_must_be_a_fraction_of_the_diameter(self, gate):
        errors = self._errors(lambda op: op.extra_args.update(engagement_gate=gate))
        assert any("engagement_gate" in e for e in errors)

    def test_bottom_must_not_be_above_the_top(self):
        errors = self._errors(
            lambda op: setattr(op, "top_of_stock", op.bottom_of_stock - 1.0)
        )
        assert any("top_of_stock" in e for e in errors)

    def test_run_raises_on_an_invalid_operation(self):
        operation = make_operation()
        operation.stepover = 0.9
        with pytest.raises(ValueError) as excinfo:
            AdaptiveEngagementStrategy().run(operation)
        assert "Stepover" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Generated toolpath
# ---------------------------------------------------------------------------

class TestGeneratedToolpath:
    def test_moves_are_generated(self):
        tp = run_toolpath()
        assert isinstance(tp, ToolpathData)
        assert tp.strategy == "adaptive_engagement"
        assert len(tp.moves) > 0

    def test_every_cutting_move_carries_a_measured_feed(self):
        vocab = feed_vocabulary(FEED)
        tp = run_toolpath()
        assert cutting_feeds(tp) <= set(vocab.values())
        assert cutting_feeds(tp) == set(vocab.values())

    def test_rapids_carry_no_feed(self):
        tp = run_toolpath()
        rapids = [m for m in tp.moves if m.move_type is MoveType.RAPID]
        assert rapids, "the path must rapid between levels"
        assert all(m.feed == 0.0 for m in rapids)

    def test_one_plunge_per_level_priced_at_feed_over_three(self):
        tp = run_toolpath()
        levels = tp.params["levels"]
        histogram = tp.params["feed_histogram"]
        plunge_key = f"{FEED / 3.0:.6f}"
        assert histogram[plunge_key] == levels

    def test_each_levels_first_ring_takes_the_reduced_arm(self):
        """The fresh full-diameter slot is the only ae >= gate * D by design."""
        tp = run_toolpath()
        levels = tp.params["levels"]
        histogram = tp.params["feed_histogram"]
        assert histogram[f"{FEED * 0.9:.6f}"] == levels
        # ...and the constant-engagement rings take the cutting arm.
        assert histogram[f"{FEED:.6f}"] > 0

    def test_histogram_partitions_the_cutting_moves(self):
        tp = run_toolpath()
        histogram = tp.params["feed_histogram"]
        linear_moves = [m for m in tp.moves if m.move_type is MoveType.LINEAR]
        assert sum(histogram.values()) == len(linear_moves)
        assert set(histogram) == {
            f"{value:.6f}" for value in feed_vocabulary(FEED).values()
        }

    def test_params_expose_the_vocabulary_and_the_gate(self):
        tp = run_toolpath()
        vocab = feed_vocabulary(FEED)
        assert tp.params["feed_vocabulary"] == {
            key: round(value, 6) for key, value in vocab.items()
        }
        assert tp.params["engagement_gate"] == DEFAULT_ENGAGEMENT_GATE
        assert tp.params["gate_mm"] == pytest.approx(
            DEFAULT_ENGAGEMENT_GATE * TOOL_DIAMETER
        )

    def test_engagement_reaches_the_full_diameter(self):
        tp = run_toolpath()
        assert tp.params["engagement_max_mm"] == pytest.approx(TOOL_DIAMETER)

    @pytest.mark.parametrize("gate,count_by_arm", [(0.1, "all"), (0.99, "split")])
    def test_the_gate_only_moves_moves_between_the_three_arms(
        self, gate, count_by_arm
    ):
        """Raising/lowering the gate never introduces a fourth feed value."""
        vocab = feed_vocabulary(FEED)
        tp = run_toolpath(engagement_gate=gate)
        assert cutting_feeds(tp) <= set(vocab.values())
        histogram = tp.params["feed_histogram"]
        if count_by_arm == "all":
            # 0.1 * D is under every engagement we generate: no cutting arm left.
            assert f"{FEED:.6f}" not in histogram
        else:
            # 0.99 * D is above the band engagement: both arms stay populated.
            assert f"{FEED:.6f}" in histogram
            assert f"{FEED * 0.9:.6f}" in histogram

    def test_a_toolpath_the_cutter_cannot_enter_reports_the_error(self):
        tiny = BBox(min=Vec3(-1.0, -1.0, -5.0), max=Vec3(1.0, 1.0, 0.0))
        tp = AdaptiveEngagementStrategy().generate_toolpath(
            tiny, ToolDef(diameter=TOOL_DIAMETER), stepover=0.4, stepdown=1.0
        )
        assert tp.moves == []
        assert "error" in tp.params
