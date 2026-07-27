"""
Face milling strategy for AI CAM 4.0 kernel.

Generates parallel raster passes to machine a flat top surface.
The simplest and most common CAM operation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from kernel.strategies.base import BaseStrategy, OperationParams
from kernel.types import BBox, ToolpathData, ToolDef, Vec3


class FaceMillingStrategy(BaseStrategy):
    """Face milling — parallel raster passes across the top surface.

    Strategy:
        1. Start at the top of stock Z.
        2. Create parallel passes along the X-axis, stepping over in Y.
        3. Each pass is a linear G1 move at the feed rate.
        4. Between passes, do a rapid (G0) move to the next start point.
        5. Step down and repeat until bottom_of_stock is reached.
    """

    @property
    def name(self) -> str:
        return "face_milling"

    @property
    def description(self) -> str:
        return "Parallel raster passes for face milling"

    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate face milling parameters."""
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

        if operation.spindle_speed <= 0:
            errors.append(f"Spindle speed must be positive, got {operation.spindle_speed}")

        if operation.top_of_stock <= operation.bottom_of_stock:
            errors.append(
                f"top_of_stock ({operation.top_of_stock}) must be > "
                f"bottom_of_stock ({operation.bottom_of_stock})"
            )

        return errors

    def generate_toolpath(
        self,
        stock: BBox,
        tool: ToolDef,
        **kwargs: Any,
    ) -> ToolpathData:
        """Generate face milling toolpath.

        Args:
            stock: Bounding box of the stock.
            tool: Tool definition.
            **kwargs: Override defaults — stepover, stepdown, feed_rate,
                      spindle_speed, clearance_height, top_of_stock,
                      bottom_of_stock.

        Returns:
            ToolpathData with the generated toolpath.
        """
        # Extract parameters with defaults
        stepover_frac = kwargs.get("stepover", 0.5)
        stepdown = kwargs.get("stepdown", 1.0)
        feed = kwargs.get("feed_rate", 1000.0)
        speed = kwargs.get("spindle_speed", 10000.0)
        clearance = kwargs.get("clearance_height", 5.0)
        top_z = kwargs.get("top_of_stock", stock.max_point.z)
        bottom_z = kwargs.get("bottom_of_stock", stock.min_point.z)

        # Compute pass parameters
        tool_radius = tool.effective_radius
        stepover = tool.diameter * stepover_frac
        depth_of_cut = top_z - bottom_z

        # Stock bounds
        x_min = stock.min_point.x + tool_radius
        x_max = stock.max_point.x - tool_radius
        y_min = stock.min_point.y + tool_radius
        y_max = stock.max_point.y - tool_radius

        # Y positions for each pass
        y_positions = np.arange(y_min, y_max + stepover * 0.01, stepover)
        if len(y_positions) == 0:
            y_positions = np.array([stock.center.y])

        # Z levels for each depth pass
        z_levels = []
        z = top_z
        while z > bottom_z + 1e-6:
            z_levels.append(z)
            z -= stepdown
        z_levels.append(bottom_z)

        tp = ToolpathData(
            metadata={
                "strategy": self.name,
                "tool_diameter": tool.diameter,
                "total_passes": len(z_levels) * len(y_positions),
            }
        )

        # Generate passes
        for z_level in z_levels:
            # Lead-in rapid
            start_y = y_positions[0]
            tp.append(
                point=Vec3(x_min - 5.0, start_y, clearance),
                speed=speed,
                feed=0.0,
                rapid=True,
            )

            # Rapid down to Z level
            tp.append(
                point=Vec3(x_min - 5.0, start_y, z_level),
                speed=speed,
                feed=0.0,
                rapid=True,
            )

            for i, y in enumerate(y_positions):
                if i % 2 == 0:
                    # Left to right
                    start = Vec3(x_min, y, z_level)
                    end = Vec3(x_max, y, z_level)
                else:
                    # Right to left
                    start = Vec3(x_max, y, z_level)
                    end = Vec3(x_min, y, z_level)

                # Lead-in
                tp.append(
                    point=start,
                    speed=speed,
                    feed=feed,
                    rapid=False,
                )

                # Cutting pass
                tp.append(
                    point=end,
                    speed=speed,
                    feed=feed,
                    rapid=False,
                )

                # Lift for repositioning (if more passes at this Z)
                if i < len(y_positions) - 1:
                    next_y = y_positions[i + 1]
                    tp.append(
                        point=Vec3(end.x, end.y, z_level + 1.0),
                        speed=speed,
                        feed=0.0,
                        rapid=True,
                    )
                    tp.append(
                        point=Vec3(
                            x_min if (i + 1) % 2 == 0 else x_max,
                            next_y,
                            z_level + 1.0,
                        ),
                        speed=speed,
                        feed=0.0,
                        rapid=True,
                    )
                    tp.append(
                        point=Vec3(
                            x_min if (i + 1) % 2 == 0 else x_max,
                            next_y,
                            z_level,
                        ),
                        speed=speed,
                        feed=0.0,
                        rapid=True,
                    )

            # Lead-out rapid back to clearance
            tp.append(
                point=Vec3(stock.center.x, stock.center.y, clearance),
                speed=speed,
                feed=0.0,
                rapid=True,
            )

        return tp
