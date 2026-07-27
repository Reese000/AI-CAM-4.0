"""
Base strategy class for AI CAM 4.0 kernel.

All machining strategies must inherit from BaseStrategy and implement
the generate_toolpath method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from kernel.types import BBox, ToolpathData, ToolDef


@dataclass
class OperationParams:
    """Parameters for a machining operation.

    Attributes:
        strategy: Strategy name (e.g., 'face_milling').
        stock: Bounding box of the stock material.
        tool: Tool definition.
        stepover: Lateral stepover as fraction of tool diameter (0.0 - 1.0).
        stepdown: Axial depth of cut in mm.
        feed_rate: Feed rate in mm/min.
        spindle_speed: Spindle speed in RPM.
        clearance_height: Safe Z height for rapid moves in mm.
        top_of_stock: Z height of stock top in mm.
        bottom_of_stock: Z height of stock bottom in mm.
        extra_args: Strategy-specific parameters.
    """

    strategy: str = ""
    stock: BBox | None = None
    tool: ToolDef | None = None
    stepover: float = 0.5
    stepdown: float = 1.0
    feed_rate: float = 1000.0
    spindle_speed: float = 10000.0
    clearance_height: float = 5.0
    top_of_stock: float = 0.0
    bottom_of_stock: float = -10.0
    extra_args: dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """Abstract base class for all machining strategies.

    Subclasses must implement:
        - validate_params(operation): Validate operation parameters.
        - generate_toolpath(stock, tool): Generate the toolpath.
        - name: Property returning the strategy name.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name identifier."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of the strategy."""
        return self.name.replace("_", " ").title()

    @abstractmethod
    def validate_params(self, operation: OperationParams) -> list[str]:
        """Validate operation parameters for this strategy.

        Args:
            operation: Operation parameters to validate.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        ...

    @abstractmethod
    def generate_toolpath(
        self, stock: BBox, tool: ToolDef, **kwargs: Any
    ) -> ToolpathData:
        """Generate a toolpath for the given stock and tool.

        Args:
            stock: Bounding box of the stock material.
            tool: Tool definition.
            **kwargs: Strategy-specific parameters.

        Returns:
            ToolpathData with the generated toolpath.
        """
        ...

    def run(self, operation: OperationParams) -> ToolpathData:
        """Validate parameters and generate toolpath (convenience method).

        This wires validate_params into generate_toolpath:
        1. Validates the operation parameters.
        2. If validation fails, raises ValueError with all errors.
        3. Calls generate_toolpath with the validated parameters.

        Args:
            operation: Complete operation parameters.

        Returns:
            ToolpathData with the generated toolpath.

        Raises:
            ValueError: If parameter validation fails.
        """
        errors = self.validate_params(operation)
        if errors:
            error_msg = f"Validation failed for '{self.name}':\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            raise ValueError(error_msg)

        if operation.stock is None or operation.tool is None:
            raise ValueError("Stock and tool must be provided")

        # Merge extra_args into kwargs
        kwargs = dict(operation.extra_args)
        kwargs.setdefault("stepover", operation.stepover)
        kwargs.setdefault("stepdown", operation.stepdown)
        kwargs.setdefault("feed_rate", operation.feed_rate)
        kwargs.setdefault("spindle_speed", operation.spindle_speed)
        kwargs.setdefault("clearance_height", operation.clearance_height)
        kwargs.setdefault("top_of_stock", operation.top_of_stock)
        kwargs.setdefault("bottom_of_stock", operation.bottom_of_stock)

        return self.generate_toolpath(operation.stock, operation.tool, **kwargs)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
