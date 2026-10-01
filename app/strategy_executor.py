"""
AI CAM 4.0 Strategy Executor — Bridge between UI and kernel strategies.

Takes user parameters from the UI, invokes the corresponding kernel
strategy, and returns a canonical ToolpathData (NOT wrapped).

The executor owns no Qt state. It's a pure function from params → ToolpathData.

Two of the strategies are dispatched to real kernel strategies — F1
``adaptive_engagement`` and F2 ``waterline_finishing``, the two P5 features —
so the app layer and the kernel cannot drift apart on them.  The other five
(``face_milling``, ``adaptive_clearing``, ``pocketing``, ``contour``,
``drilling``) are the legacy app-local planners this module has always had.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from kernel.strategies import get_strategy
from kernel.types import (
    BBox,
    Material,
    Move,
    MoveType,
    ToolDef,
    ToolpathData,
    Vec3,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy parameter schemas
# ---------------------------------------------------------------------------

STRATEGY_PARAMS: dict[str, dict[str, Any]] = {
    "face_milling": {
        "step_over": {"type": "float", "default": 8.0, "min": 0.1, "max": 50.0, "label": "Step Over (mm)"},
        "step_down": {"type": "float", "default": 2.0, "min": 0.1, "max": 20.0, "label": "Step Down (mm)"},
        "overlap": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "Overlap"},
    },
    "adaptive_clearing": {
        "step_over": {"type": "float", "default": 5.0, "min": 0.1, "max": 30.0, "label": "Step Over (mm)"},
        "step_down": {"type": "float", "default": 3.0, "min": 0.1, "max": 20.0, "label": "Step Down (mm)"},
        "tolerance": {"type": "float", "default": 0.05, "min": 0.01, "max": 1.0, "label": "Tolerance (mm)"},
    },
    # F1 (P5/3) — kernel-backed: dispatch translates the app's mm step_over
    # into the kernel's stepover-as-a-fraction-of-D, see _adaptive_engagement.
    # step_over's DEFAULT assumes a cutter of D >= 8 mm (the GUI's is 10 mm).
    # On a smaller tool the default is more than 0.5 x D, so execute() refuses
    # it and names the ceiling in mm instead of cutting at an unrequested chip
    # load — the schema's min/max is a UI range, not a promise that every
    # value validates for every tool.
    "adaptive_engagement": {
        "step_over": {"type": "float", "default": 4.0, "min": 0.1, "max": 50.0, "label": "Step Over (mm, ≤ 0.5×D)"},
        "step_down": {"type": "float", "default": 2.0, "min": 0.1, "max": 20.0, "label": "Step Down (mm)"},
        "engagement_gate": {"type": "float", "default": 0.5, "min": 0.01, "max": 1.0, "label": "Engagement Gate (×D)"},
        "feed_rate": {"type": "float", "default": 1000.0, "min": 1.0, "max": 5000.0, "label": "Feed Rate (mm/min)"},
    },
    "pocketing": {
        "step_over": {"type": "float", "default": 6.0, "min": 0.1, "max": 40.0, "label": "Step Over (mm)"},
        "step_down": {"type": "float", "default": 2.0, "min": 0.1, "max": 20.0, "label": "Step Down (mm)"},
        "finish_allowance": {"type": "float", "default": 0.3, "min": 0.0, "max": 5.0, "label": "Finish Allowance (mm)"},
    },
    # F2 (P5/4) — kernel-backed, see _waterline_finishing.
    #
    # cell_mm: the kernel's reference pitch is 0.05 mm, but on a 100 mm
    # square part that needs a 2408 x 2408 section raster (5.8M cells) and
    # the kernel refuses it (MAX_RASTER_CELLS = 4_000_000).  0.25 mm plans
    # the same part inside the budget; tighten it towards 0.05 mm on small
    # parts, loosen it on parts several hundred mm across — the app has no
    # parameter panel yet, so a stock too big for the default comes back
    # as a ValueError telling the caller which way to move.
    "waterline_finishing": {
        "finish_mode": {"type": "choice", "default": "both", "choices": ["waterline", "scallop", "both"], "label": "Finish Mode"},
        "cell_mm": {"type": "float", "default": 0.25, "min": 0.01, "max": 5.0, "label": "Raster Cell (mm; raise for large stock)"},
        "cusp_height_mm": {"type": "float", "default": 0.02, "min": 0.001, "max": 5.0, "label": "Cusp Height (mm)"},
        "scallop_rings": {"type": "int", "default": None, "nullable": True, "min": 1, "max": 256, "label": "Scallop Rings (blank = derive from footprint)"},
        "stock_to_leave_mm": {"type": "float", "default": 0.0, "min": 0.0, "max": 10.0, "label": "Stock to Leave (mm)"},
        "step_down": {"type": "float", "default": 1.0, "min": 0.01, "max": 20.0, "label": "Step Down (mm)"},
        "feed_rate": {"type": "float", "default": 1000.0, "min": 1.0, "max": 5000.0, "label": "Feed Rate (mm/min)"},
        "profile": {"type": "object", "default": None, "nullable": True, "label": "Profile ([x, y] polygon; blank = stock footprint)"},
        "mesh": {"type": "object", "default": None, "nullable": True, "label": "Mesh (parse_stl dict; blank = stock footprint)"},
    },
    "contour": {
        "step_down": {"type": "float", "default": 1.0, "min": 0.1, "max": 10.0, "label": "Step Down (mm)"},
        "tolerance": {"type": "float", "default": 0.02, "min": 0.001, "max": 1.0, "label": "Tolerance (mm)"},
    },
    "drilling": {
        "peck_depth": {"type": "float", "default": 5.0, "min": 0.5, "max": 50.0, "label": "Peck Depth (mm)"},
        "retract": {"type": "float", "default": 2.0, "min": 0.5, "max": 10.0, "label": "Retract (mm)"},
        "dwell": {"type": "float", "default": 0.5, "min": 0.0, "max": 5.0, "label": "Dwell (s)"},
    },
}


def list_strategies() -> list[str]:
    """Return all available strategy names."""
    return list(STRATEGY_PARAMS.keys())


def get_strategy_params(strategy_name: str) -> dict[str, Any]:
    """Return the parameter schema for a strategy."""
    if strategy_name not in STRATEGY_PARAMS:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    return STRATEGY_PARAMS[strategy_name]


# ---------------------------------------------------------------------------
# Strategy executor — pure function, no Qt
# ---------------------------------------------------------------------------

def _diagnostics(reported: dict[str, Any]) -> dict[str, Any]:
    """Kernel diagnostics in a form worth putting on one log line.

    ``feed_histogram`` can carry hundreds of one-feed-each bins; its digest
    (how many bins, how many moves) is what a reader needs, and it keeps the
    histogram — which ``execute()`` does not copy into the returned
    ``ToolpathData`` — on record somewhere.
    """
    out: dict[str, Any] = {}
    for key, value in reported.items():
        if key == "feed_histogram" and isinstance(value, dict):
            out[key] = f"{len(value)} bins / {sum(value.values())} moves"
        else:
            out[key] = value
    return out


class StrategyExecutor:
    """
    Bridge between UI parameters and toolpath generation.

    Usage:
        executor = StrategyExecutor()
        toolpath = executor.execute(
            strategy="face_milling",
            tool=ToolDef(diameter=10.0),
            stock_bbox=BBox(...),
            params={"step_over": 8.0, "step_down": 2.0},
        )
    """

    def execute(
        self,
        strategy: str,
        tool: ToolDef,
        stock_bbox: BBox,
        params: dict[str, Any] | None = None,
        material: Material = Material.ALUMINUM,
    ) -> ToolpathData:
        """
        Generate a toolpath for the given strategy and parameters.

        Returns a canonical ToolpathData — NOT wrapped in any UI type.
        ``params`` on the result is the VALIDATED APP parameter dict (what
        the caller asked for), not the kernel strategy's diagnostics — those
        (``profile_source``, ``passes``, achieved cusp height, the feed
        histogram as a bin/move digest, …) are written to the module log by
        ``_kernel_moves`` instead.  Kernel-backed strategies are invoked
        here; the five legacy app-local planners return their own moves.
        """
        params = params or {}

        # Validate and fill defaults
        validated = self._validate_params(strategy, params)

        logger.info(
            "Executing strategy '%s' with tool D=%.1fmm, stock=%.1f×%.1f×%.1fmm",
            strategy,
            tool.diameter,
            stock_bbox.size.x,
            stock_bbox.size.y,
            stock_bbox.size.z,
        )

        # Dispatch to the specific strategy
        dispatch = {
            "face_milling": self._face_milling,
            "adaptive_clearing": self._adaptive_clearing,
            "adaptive_engagement": self._adaptive_engagement,
            "pocketing": self._pocketing,
            "waterline_finishing": self._waterline_finishing,
            "contour": self._contour,
            "drilling": self._drilling,
        }

        if strategy not in dispatch:
            raise ValueError(f"Unknown strategy: {strategy}")

        moves = dispatch[strategy](tool, stock_bbox, validated)

        toolpath = ToolpathData(
            name=strategy.replace("_", " ").title(),
            tool=tool,
            material=material,
            moves=moves,
            strategy=strategy,
            params=validated,
        )

        logger.info(
            "Strategy '%s' generated %d moves", strategy, len(moves)
        )
        return toolpath

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    def _validate_params(
        self, strategy: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge user params with defaults, enforcing each schema spec.

        ``float`` specs are clamped to their ``min``/``max`` and ``int``
        specs likewise — the behaviour the legacy strategies have always
        had — except that an ``int`` spec REFUSES a non-integral value
        instead of truncating it, because the kernel strategy rejects a
        fractional ring count too and one parameter must keep one contract.
        ``choice`` specs must match one of their ``choices``; ``object`` specs
        are passed through untouched because there is no numeric range to
        clamp them to — the kernel strategy owns their validation.  A spec
        marked ``nullable`` may stay ``None`` (used by ``scallop_rings``,
        ``profile`` and ``mesh``, which all mean "derive it" when blank).

        A key in ``params`` that the schema does not know is logged as a
        warning and dropped: swallowing ``stepdown`` (the kernel's spelling
        of ``step_down``) in silence would plan at a default with no trace
        that the caller ever asked for something else.
        """
        schema = STRATEGY_PARAMS.get(strategy, {})
        if schema:
            # A typo'd key would otherwise be dropped on the floor and the
            # kernel would fall back to a default that may equal the app's —
            # silent, and indistinguishable from a correct run.
            unknown = sorted(set(params) - set(schema))
            if unknown:
                logger.warning(
                    "%s: ignoring parameter(s) outside its schema: %s "
                    "(known: %s)",
                    strategy, unknown, sorted(schema),
                )
        result: dict[str, Any] = {}
        for key, spec in schema.items():
            value = params.get(key, spec["default"])
            if value is None:
                if spec.get("nullable"):
                    result[key] = None
                    continue
                raise ValueError(
                    f"{strategy}.{key} must not be None "
                    f"(default {spec['default']!r})"
                )
            kind = spec.get("type", "float")
            if kind == "float":
                value = max(spec["min"], min(spec["max"], value))
            elif kind == "int":
                # Reject rather than truncate: the kernel strategy refuses a
                # fractional ring count outright, and two validators giving
                # two answers for one parameter is worse than either alone.
                as_float = float("nan")
                try:
                    as_float = float(value)
                    integral = math.isfinite(as_float) and int(as_float) == as_float
                except (TypeError, ValueError, OverflowError):
                    integral = False
                if not integral:
                    raise ValueError(
                        f"{strategy}.{key} must be an integer, got {value!r}"
                    )
                value = int(max(spec["min"], min(spec["max"], int(as_float))))
            elif kind == "choice":
                if value not in spec["choices"]:
                    raise ValueError(
                        f"{strategy}.{key} must be one of "
                        f"{list(spec['choices'])}, got {value!r}"
                    )
            # "object" specs fall through unclamped on purpose.
            result[key] = value
        return result

    # ------------------------------------------------------------------
    # Face milling — zigzag across the top surface
    # ------------------------------------------------------------------

    def _face_milling(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        step_over = params["step_over"]
        step_down = params["step_down"]
        r = tool.radius

        moves: list[Move] = []

        # Start above stock
        z_top = bbox.max.z
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(bbox.min.x - r, bbox.min.y - r, z_top + 10),
        ))

        # Zigzag passes across X
        y = bbox.min.y + r
        direction = 1  # 1 = +X, -1 = -X
        pass_num = 0

        while y <= bbox.max.y - r:
            z = z_top - step_down * (pass_num // max(1, int((bbox.max.y - bbox.min.y) / step_over) + 1))

            # Lead-in
            x_start = bbox.min.x - r if direction == 1 else bbox.max.x + r
            x_end = bbox.max.x + r if direction == 1 else bbox.min.x - r

            # Rapid to start of pass
            moves.append(Move(
                move_type=MoveType.RAPID,
                end=Vec3(x_start, y, z + 5),
            ))
            moves.append(Move(
                move_type=MoveType.RAPID,
                end=Vec3(x_start, y, z),
            ))

            # Cutting pass
            moves.append(Move(
                move_type=MoveType.LINEAR,
                end=Vec3(x_end, y, z),
                feed=1000.0,
                spindle_speed=8000,
            ))

            # Lead-out
            moves.append(Move(
                move_type=MoveType.RETRACT,
                end=Vec3(x_end, y, z + 5),
            ))

            y += step_over
            direction *= -1
            pass_num += 1

        # Final retract
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(bbox.min.x, bbox.min.y, z_top + 20),
        ))

        return moves

    # ------------------------------------------------------------------
    # Adaptive clearing — trochoidal-style adaptive roughing
    # ------------------------------------------------------------------

    def _adaptive_clearing(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        step_over = params["step_over"]
        step_down = params["step_down"]
        tolerance = params["tolerance"]
        r = tool.radius

        moves: list[Move] = []

        # Stock bounds with tool offset
        x_min = bbox.min.x + r
        x_max = bbox.max.x - r
        y_min = bbox.min.y + r
        y_max = bbox.max.y - r

        # Initial rapid
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(x_min, y_min, bbox.max.z + 10),
        ))

        # Adaptive passes — spiral inward from stock boundary
        z = bbox.max.z
        depth_passes = max(1, int(bbox.size.z / step_down))

        for d in range(depth_passes):
            z = bbox.max.z - (d + 1) * step_down
            if z < bbox.min.z:
                z = bbox.min.z

            # Spiral path: rectangular spirals getting smaller
            inset = d * step_over * 0.3  # Slight variation per depth
            cx = bbox.center.x
            cy = bbox.center.y

            # Entry move
            moves.append(Move(
                move_type=MoveType.RAPID,
                end=Vec3(x_min - inset, cy, z + 5),
            ))
            moves.append(Move(
                move_type=MoveType.LINEAR,
                end=Vec3(x_min - inset, cy, z),
                feed=800.0,
                spindle_speed=10000,
            ))

            # Trochoidal-style path: wave along X
            current_x = x_min - inset
            current_y = cy
            segments_x = max(1, int((x_max - x_min) / step_over))

            for s in range(segments_x):
                target_x = x_min + (s + 1) * (x_max - x_min) / segments_x

                # Wave pattern
                wave_y = current_y + step_over * 0.3 * (1 if s % 2 == 0 else -1)
                wave_y = max(y_min, min(y_max, wave_y))

                moves.append(Move(
                    move_type=MoveType.LINEAR,
                    end=Vec3(target_x, wave_y, z),
                    feed=800.0,
                    spindle_speed=10000,
                ))
                current_x = target_x
                current_y = wave_y

            # Step over in Y
            moves.append(Move(
                move_type=MoveType.LINEAR,
                end=Vec3(current_x, current_y + step_over, z),
                feed=600.0,
                spindle_speed=10000,
            ))

            # Return pass
            for s in range(segments_x, 0, -1):
                target_x = x_min + (s - 1) * (x_max - x_min) / segments_x
                wave_y = current_y - step_over * 0.3 * (1 if s % 2 == 0 else -1)
                wave_y = max(y_min, min(y_max, wave_y))
                moves.append(Move(
                    move_type=MoveType.LINEAR,
                    end=Vec3(target_x, wave_y, z),
                    feed=800.0,
                    spindle_speed=10000,
                ))
                current_x = target_x
                current_y = wave_y

            # Retract for next depth
            moves.append(Move(
                move_type=MoveType.RETRACT,
                end=Vec3(current_x, current_y, z + 5),
            ))

        # Final retract
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(bbox.center.x, bbox.center.y, bbox.max.z + 20),
        ))

        return moves

    # ------------------------------------------------------------------
    # Adaptive engagement (F1) — kernel-backed
    # ------------------------------------------------------------------

    def _adaptive_engagement(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        """Run the kernel's F1 strategy.

        The app speaks ``step_over`` in mm (like every other strategy in
        this file); the kernel's ``stepover`` is a fraction of the tool
        diameter and must land in (0, 0.5] — the bound mirrored below from
        ``kernel.strategies.adaptive_engagement``.  The translation happens
        here and an out-of-range result is refused rather than silently
        clamped: halving the stepover halves the chip load, which is a
        tooling decision, not a UI nicety.

        The diameter is checked before the division so a degenerate
        ``ToolDef`` reaches the caller as this module's uniform
        ``ValueError`` instead of a ``ZeroDivisionError``.
        """
        if not math.isfinite(tool.diameter) or tool.diameter <= 0:
            raise ValueError(
                f"adaptive_engagement: tool diameter must be a positive "
                f"finite number, got {tool.diameter!r}"
            )
        step_over = params["step_over"]
        fraction = step_over / tool.diameter
        if not 0.0 < fraction <= 0.5:
            raise ValueError(
                f"adaptive_engagement step_over {step_over:g} mm is "
                f"{fraction:.4g} × D for a {tool.diameter:g} mm tool; it must "
                f"be ≤ 0.5 × D, i.e. ≤ {0.5 * tool.diameter:g} mm"
            )
        return self._kernel_moves(
            "adaptive_engagement",
            tool,
            bbox,
            stepover=fraction,
            stepdown=params["step_down"],
            feed_rate=params["feed_rate"],
            engagement_gate=params["engagement_gate"],
        )

    # ------------------------------------------------------------------
    # Shared kernel dispatch
    # ------------------------------------------------------------------

    def _kernel_moves(
        self, strategy_name: str, tool: ToolDef, bbox: BBox, **kwargs: Any
    ) -> list[Move]:
        """Run a kernel strategy over ``bbox`` and hand back its moves.

        ``execute()``'s contract only carries a stock bounding box, so the
        stock faces are supplied here.  ``waterline_finishing`` would
        otherwise fall back to its own ``top_of_stock = 0.0`` /
        ``bottom_of_stock = -10.0`` defaults — a different z range from the
        stock on screen — and finish the wrong slice of material.

        A kernel strategy reports a rejected parameter set as an error
        ``ToolpathData`` (empty ``moves``, message in ``params['error']``)
        instead of raising.  Turning that into a ``ValueError`` keeps the
        executor's failure mode uniform: the GUI already surfaces a raised
        exception in a dialog, whereas an empty toolpath would look like a
        successful no-op cut.
        """
        strategy = get_strategy(strategy_name)
        toolpath = strategy.generate_toolpath(
            bbox,
            tool,
            top_of_stock=bbox.max.z,
            bottom_of_stock=bbox.min.z,
            **kwargs,
        )
        reported = toolpath.params or {}
        error = reported.get("error")
        if error:
            raise ValueError(f"{strategy_name}: {error}")
        logger.info(
            "Kernel strategy '%s' returned %d moves (kernel params: %s)",
            strategy_name,
            len(toolpath.moves),
            _diagnostics(reported),
        )
        return toolpath.moves

    # ------------------------------------------------------------------
    # Pocketing — offset-based pocket clearing
    # ------------------------------------------------------------------

    def _pocketing(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        step_over = params["step_over"]
        step_down = params["step_down"]
        finish_allowance = params["finish_allowance"]
        r = tool.radius

        moves: list[Move] = []

        # Plunge to center
        cx, cy = bbox.center.x, bbox.center.y
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(cx, cy, bbox.max.z + 10),
        ))

        depth_passes = max(1, int(bbox.size.z / step_down))

        for d in range(depth_passes):
            z = bbox.max.z - (d + 1) * step_down
            z = max(bbox.min.z, z)

            # Plunge
            moves.append(Move(
                move_type=MoveType.LINEAR,
                end=Vec3(cx, cy, z),
                feed=200.0,
                spindle_speed=6000,
            ))

            # Spiral outward from center
            current_offset = 0.0
            max_offset = min(bbox.size.x, bbox.size.y) / 2 - r - finish_allowance

            while current_offset <= max_offset:
                half = current_offset

                # Rectangular spiral segment
                corners = [
                    (cx - half, cy - half),
                    (cx + half, cy - half),
                    (cx + half, cy + half),
                    (cx - half, cy + half),
                    (cx - half, cy - half),  # close the loop
                ]

                for px, py in corners:
                    moves.append(Move(
                        move_type=MoveType.LINEAR,
                        end=Vec3(px, py, z),
                        feed=1000.0,
                        spindle_speed=6000,
                    ))

                current_offset += step_over

            # Retract
            moves.append(Move(
                move_type=MoveType.RETRACT,
                end=Vec3(cx, cy, z + 5),
            ))

        # Final retract
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(cx, cy, bbox.max.z + 20),
        ))

        return moves

    # ------------------------------------------------------------------
    # Waterline finishing (F2) — kernel-backed
    # ------------------------------------------------------------------

    def _waterline_finishing(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        """Run the kernel's F2 waterline + constant-scallop strategy.

        ``profile`` / ``mesh`` are passed straight through: ``None`` (the
        default) makes the kernel finish the stock footprint, a ``profile``
        polygon finishes that outline, and a ``mesh`` finishes the sectioned
        model.  Giving the kernel both at once is its own error and surfaces
        here as a ``ValueError``.
        """
        return self._kernel_moves(
            "waterline_finishing",
            tool,
            bbox,
            finish_mode=params["finish_mode"],
            cell_mm=params["cell_mm"],
            cusp_height_mm=params["cusp_height_mm"],
            scallop_rings=params["scallop_rings"],
            stock_to_leave_mm=params["stock_to_leave_mm"],
            stepdown=params["step_down"],
            feed_rate=params["feed_rate"],
            profile=params["profile"],
            mesh=params["mesh"],
        )

    # ------------------------------------------------------------------
    # Contour — follow the profile at each depth level
    # ------------------------------------------------------------------

    def _contour(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        step_down = params["step_down"]
        r = tool.radius

        moves: list[Move] = []

        # Rectangular profile (simplified — real contour follows actual geometry)
        x_min = bbox.min.x + r
        x_max = bbox.max.x - r
        y_min = bbox.min.y + r
        y_max = bbox.max.y - r

        depth_passes = max(1, int(bbox.size.z / step_down))

        # Start rapid
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(x_min, y_min, bbox.max.z + 10),
        ))

        for d in range(depth_passes):
            z = bbox.max.z - (d + 1) * step_down
            z = max(bbox.min.z, z)

            # Plunge
            moves.append(Move(
                move_type=MoveType.LINEAR,
                end=Vec3(x_min, y_min, z),
                feed=200.0,
                spindle_speed=6000,
            ))

            # Profile: rectangle
            profile = [
                (x_max, y_min),
                (x_max, y_max),
                (x_min, y_max),
                (x_min, y_min),
            ]
            for px, py in profile:
                moves.append(Move(
                    move_type=MoveType.LINEAR,
                    end=Vec3(px, py, z),
                    feed=1200.0,
                    spindle_speed=6000,
                ))

            # Retract
            moves.append(Move(
                move_type=MoveType.RETRACT,
                end=Vec3(x_min, y_min, z + 5),
            ))

        # Final retract
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(bbox.center.x, bbox.center.y, bbox.max.z + 20),
        ))

        return moves

    # ------------------------------------------------------------------
    # Drilling — canned cycle at specified points
    # ------------------------------------------------------------------

    def _drilling(
        self, tool: ToolDef, bbox: BBox, params: dict[str, Any]
    ) -> list[Move]:
        peck_depth = params["peck_depth"]
        retract = params["retract"]
        dwell = params["dwell"]

        moves: list[Move] = []

        # Default: drill a pattern of holes across the stock
        # 3x3 grid for demonstration
        x_positions = [
            bbox.min.x + bbox.size.x * frac
            for frac in [0.25, 0.5, 0.75]
        ]
        y_positions = [
            bbox.min.y + bbox.size.y * frac
            for frac in [0.25, 0.5, 0.75]
        ]

        # Start rapid
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(x_positions[0], y_positions[0], bbox.max.z + 10),
        ))

        for y in y_positions:
            for x in x_positions:
                # Rapid to hole position
                moves.append(Move(
                    move_type=MoveType.RAPID,
                    end=Vec3(x, y, bbox.max.z + 2),
                ))

                # Peck drilling
                z = bbox.max.z
                while z > bbox.min.z:
                    z -= peck_depth
                    z = max(bbox.min.z, z)

                    moves.append(Move(
                        move_type=MoveType.DRILL,
                        end=Vec3(x, y, z),
                        feed=300.0,
                        spindle_speed=4000,
                    ))

                    # Retract for chip breaking
                    moves.append(Move(
                        move_type=MoveType.RETRACT,
                        end=Vec3(x, y, z + retract),
                    ))

                # Full retract
                moves.append(Move(
                    move_type=MoveType.RAPID,
                    end=Vec3(x, y, bbox.max.z + 5),
                ))

        # Final retract
        moves.append(Move(
            move_type=MoveType.RAPID,
            end=Vec3(bbox.center.x, bbox.center.y, bbox.max.z + 20),
        ))

        return moves
