"""
Smoke test: verify that all core modules import without error.

This is the first gate — if this fails, nothing works.
"""

import importlib
import sys


def test_import_kernel_types():
    """Kernel types import successfully."""
    mod = importlib.import_module("kernel.types")
    assert hasattr(mod, "Vec3")
    assert hasattr(mod, "BBox")
    assert hasattr(mod, "ToolpathData")
    assert hasattr(mod, "ToolDef")
    assert hasattr(mod, "Material")


def test_import_kernel_init():
    """Kernel package imports successfully."""
    mod = importlib.import_module("kernel")
    assert mod.__version__ == "4.0.0"


def test_import_simulation_engine():
    """Simulation engine imports successfully."""
    mod = importlib.import_module("simulation.engine")
    assert hasattr(mod, "StockModel")
    assert hasattr(mod, "SimulationEngine")
    assert hasattr(mod, "SimulationFrame")


def test_import_simulation_controller():
    """Simulation controller imports successfully."""
    mod = importlib.import_module("simulation.controller")
    assert hasattr(mod, "SimulationController")
    assert hasattr(mod, "SimState")


def test_import_post_ir():
    """Post IR imports successfully."""
    mod = importlib.import_module("post.ir")
    assert hasattr(mod, "IRSegment")
    assert hasattr(mod, "SegmentType")
    assert hasattr(mod, "segments_to_ir")


def test_import_post_fanuc():
    """Fanuc post-processor imports successfully."""
    mod = importlib.import_module("post.fanuc")
    assert hasattr(mod, "FanucRenderer")
    assert hasattr(mod, "BaseRenderer")


def test_import_post_heidenhain():
    """Heidenhain post-processor imports successfully."""
    mod = importlib.import_module("post.heidenhain")
    assert hasattr(mod, "HeidenhainRenderer")


def test_import_strategy_executor():
    """Strategy executor imports successfully."""
    mod = importlib.import_module("app.strategy_executor")
    assert hasattr(mod, "StrategyExecutor")
    assert hasattr(mod, "list_strategies")


def test_import_app_package():
    """App package imports without error."""
    import app
    assert app is not None


def test_list_strategies_nonempty():
    """list_strategies() returns at least one strategy."""
    from app.strategy_executor import list_strategies
    strategies = list_strategies()
    assert len(strategies) >= 3
    assert "face_milling" in strategies
