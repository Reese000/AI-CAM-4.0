"""
Pocket clearing strategy for AI CAM 4.0 kernel.

Generates toolpaths to clear material from a pocket/interior region.
Uses offset-inward contours from the pocket boundary.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, Move, MoveType, ToolpathData, ToolDef, Vec3


class PocketingStrategy(BaseStrategy):
    """Pocket clearing — offset-inward contour clearing.

    Strategy:
        1. Starting from the pocket boundary (stock bounds),
           generate concentric inward offsets.
        2. Each offset contour is spaced by the stepover amount.
        3. The innermost offset clears the center.
        4. Repeats at each Z-level until bottom_of_stock.

    For rectangular pockets this produces concentric rectangular contours.
    More sophisticated implementations would handle arbitrary boundaries.
    """

    @property
    def name(self) -> str:
        return "pocketing"

    @property
    def description(self) -> str:
        return "Offset-inward pocket clearing"

    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate pocketing parameters."""
        errors: list[str] = []

        if operation.tool is None:
            errors.append("Tool definition is required")
        elif operation.tool.diameter <= 0:
            errors.append("Tool diameter must be positive")

        if operation.stock is None:
            errors.append("Stock definition is required")

        if operation.stepover <= 0 or operation.stepover > 1.0:
            errors.append(f"Stepover must be in (0, 1], got {operation.stepover}")

        if operation.stepdown <= 0:
            errors.append(f"Stepdown must be positive, got {operation.stepdown}")

        if operation.feed_rate <= 0:
            errors.append(f"Feed rate must be positive, got {operation.feed_rate}")

        return errors

    def generate_toolpath(
        self,
        stock: BBox,
        tool: ToolDef,
        **kwargs: Any,
    ) -> ToolpathData:
        """Generate pocket clearing toolpath.

        Args:
            stock: Bounding box of the stock (defines pocket boundary).
            tool: Tool definition.
            **kwargs: Override defaults.

        Returns:
            ToolpathData with the generated toolpath.
        """
        # Parameters
        stepover_frac = kwargs.get("stepover", 0.5)
        stepdown = kwargs.get("stepdown", 1.0)
        feed = kwargs.get("feed_rate", 1500.0)
        speed = kwargs.get("spindle_speed", 10000.0)
        clearance = kwargs.get("clearance_height", 5.0)
        top_z = kwargs.get("top_of_stock", stock.max.z)
        bottom_z = kwargs.get("bottom_of_stock", stock.min.z)

        tool_radius = tool.effective_radius
        stepover = tool.diameter * stepover_frac

        # Stock bounds (with tool radius offset)
        x_min = stock.min.x + tool_radius
        x_max = stock.max.x - tool_radius
        y_min = stock.min.y + tool_radius
        y_max = stock.max.y - tool_radius

        if x_max <= x_min or y_max <= y_min:
            tp = ToolpathData(strategy=self.name, params={"error": "Stock too small for tool"})
            return tp

        # Compute number of offset contours
        half_width = (x_max - x_min) / 2.0
        half_height = (y_max - y_min) / 2.0
        max_offset = min(half_width, half_height)

        offsets = []
        offset = 0.0
        while offset <= max_offset + 1e-6:
            offsets.append(offset)
            offset += stepover
        if not offsets:
            offsets = [0.0]

        # Z levels
        z_levels = []
        z = top_z
        while z > bottom_z + 1e-6:
            z_levels.append(z)
            z -= stepdown
        z_levels.append(bottom_z)

        tp = ToolpathData(
            strategy=self.name,
            params={
                "tool_diameter": tool.diameter,
                "z_levels": len(z_levels),
                "offset_passes": len(offsets),
            }
        )

        for z_level in z_levels:
            center_x = (stock.min.x + stock.max.x) / 2.0
            center_y = (stock.min.y + stock.max.y) / 2.0

            # Lead-in
            tp.moves.append(Move(move_type=MoveType.RAPID, end=Vec3(center_x, center_y, clearance), spindle_speed=speed, feed=0.0))
            tp.moves.append(Move(move_type=MoveType.RAPID, end=Vec3(center_x, center_y, z_level), spindle_speed=speed, feed=0.0))

            # Generate offset contours from outside in
            for i, offset_val in enumerate(offsets):
                # Rectangle contour at this offset
                ox_min = stock.min.x + tool_radius + offset_val
                ox_max = stock.max.x - tool_radius - offset_val
                oy_min = stock.min.y + tool_radius + offset_val
                oy_max = stock.max.y - tool_radius - offset_val

                if ox_max < ox_min or oy_max < oy_min:
                    continue

                # Rapid to start of this contour
                contour_start = Vec3(ox_min, oy_min, z_level)
                tp.moves.append(Move(move_type=MoveType.RAPID, end=Vec3(ox_min, oy_min, z_level + 1.0), spindle_speed=speed, feed=0.0))
                tp.moves.append(Move(move_type=MoveType.RAPID, end=contour_start, spindle_speed=speed, feed=0.0))

                # Walk the rectangular contour
                corners = [
                    Vec3(ox_max, oy_min, z_level),  # → right
                    Vec3(ox_max, oy_max, z_level),  # ↑ up
                    Vec3(ox_min, oy_max, z_level),  # ← left
                    Vec3(ox_min, oy_min, z_level),  # ↓ back to start
                ]

                for corner in corners:
                    tp.moves.append(Move(move_type=MoveType.LINEAR, end=corner, spindle_speed=speed, feed=feed))

            # Lead-out
            tp.moves.append(Move(move_type=MoveType.RAPID, end=Vec3(center_x, center_y, clearance), spindle_speed=speed, feed=0.0))

        return tp
