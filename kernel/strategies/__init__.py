"""
Machining strategies for AI CAM 4.0 kernel.

Strategy registry for toolpath generation algorithms.

Usage:
    from kernel.strategies import get_strategy, list_strategies
    strategy = get_strategy("face_milling")
    toolpath = strategy.generate_toolpath(stock, tool)
"""

from kernel.strategies.base import BaseStrategy
from kernel.strategies.face_milling import FaceMillingStrategy
from kernel.strategies.adaptive_clearing import AdaptiveClearingStrategy
from kernel.strategies.adaptive_engagement import AdaptiveEngagementStrategy
from kernel.strategies.pocketing import PocketingStrategy

# Strategy registry — maps name to class
_STRATEGIES: dict[str, type[BaseStrategy]] = {
    "face_milling": FaceMillingStrategy,
    "adaptive_clearing": AdaptiveClearingStrategy,
    "adaptive_engagement": AdaptiveEngagementStrategy,
    "pocketing": PocketingStrategy,
}


def get_strategy(name: str) -> BaseStrategy:
    """Get a strategy instance by name.

    Args:
        name: Strategy name (e.g., 'face_milling', 'adaptive_clearing').

    Returns:
        Instance of the requested strategy.

    Raises:
        KeyError: If strategy name is not registered.
    """
    if name not in _STRATEGIES:
        available = ", ".join(sorted(_STRATEGIES.keys()))
        raise KeyError(f"Unknown strategy '{name}'. Available: {available}")
    return _STRATEGIES[name]()


def list_strategies() -> list[str]:
    """List all registered strategy names.

    Returns:
        Sorted list of strategy name strings.
    """
    return sorted(_STRATEGIES.keys())


def register_strategy(name: str, strategy_class: type[BaseStrategy]) -> None:
    """Register a new strategy class.

    Args:
        name: Strategy name key.
        strategy_class: Class that inherits from BaseStrategy.

    Raises:
        TypeError: If strategy_class is not a BaseStrategy subclass.
    """
    if not (isinstance(strategy_class, type) and issubclass(strategy_class, BaseStrategy)):
        raise TypeError(f"strategy_class must be a BaseStrategy subclass, got {strategy_class}")
    _STRATEGIES[name] = strategy_class
