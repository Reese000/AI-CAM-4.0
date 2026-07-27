"""
AI CAM 4.0 Strategy Executor — Bridge between UI and kernel strategies.

Takes user parameters from the UI, invokes the corresponding kernel
strategy, and returns a canonical ToolpathData (NOT wrapped).

The executor owns no Qt state. It's a pure function from params → ToolpathData.
"""

from __future__ import annotations

import logging
from typing import Any

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
    "pocketing": {
        "step_over": {"type": "float", "default": 6.0, "min": 0.1, "max": 40.0, "label": "Step Over (mm)"},
        "step_down": {"type": "float", "default": 2.0, "min": 0.1, "max": 20.0, "label": "Step Down (mm)"},
        "finish_allowance": {"type": "float", "default": 0.3, "min": 0.0, "max": 5.0, "label": "Finish Allowance (mm)"},
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
            "pocketing": self._pocketing,
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
        """Merge user params with defaults, enforcing min/max."""
        schema = STRATEGY_PARAMS.get(strategy, {})
        result: dict[str, Any] = {}
        for key, spec in schema.items():
            value = params.get(key, spec["default"])
            value = max(spec["min"], min(spec["max"], value))
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
