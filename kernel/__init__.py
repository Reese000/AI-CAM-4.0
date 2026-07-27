"""
AI CAM 4.0 Kernel — Pure Python + NumPy CAM engine.

Zero Qt/PySide imports. Core types, STL import, G-code parsing,
signed distance fields, and machining strategies.

Usage:
    from kernel.types import Vec3, BBox, Transform, ToolpathData
    from kernel.stl import parse_stl
    from kernel.gcode import parse_gcode
    from kernel.sdf import SDFGrid, create_from_mesh
    from kernel.strategies import get_strategy, list_strategies
"""

from kernel.types import Vec3, BBox, Transform, ToolpathData, ToolDef, Material

__all__ = [
    "Vec3",
    "BBox",
    "Transform",
    "ToolpathData",
    "ToolDef",
    "Material",
]

__version__ = "4.0.0"
