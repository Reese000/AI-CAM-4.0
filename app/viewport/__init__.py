"""
AI CAM 4.0 — Viewport Package
==============================

OpenGL 3.3 Core Profile viewport with Qt/PySide6 integration.
Split into focused modules from day one (never a monolith).

Architecture (v4 lessons from v3):
- ALL GL operations happen on the main thread only
- None-guards on every GL resource (VAO/VBO/IBO)
- Shader errors are logged, never silently swallowed
- samples=0 for NVIDIA RTX 4070 Ti compatibility
- setSwapInterval(0) to prevent driver hangs

Module layout:
    shell.py            — GLViewportWidget (QOpenGLWidget subclass)
    renderer.py         — GL state machine, VBO/IBO, shader management
    camera.py           — OrbitCamera with orbit/zoom/pan
    input_handler.py    — Mouse/keyboard → camera action mapping
    stock_renderer.py   — Z-map heightfield solid rendering
    mesh_renderer.py    — STL mesh + toolpath line rendering
    overlays.py         — Status HUD, orientation cube, grid
    gl_constants.py     — Shader source, color palette, GL enums
    renderer_utils.py   — compile_shader(), uniform helpers
"""

from __future__ import annotations

__version__ = "4.0.0"

__all__ = [
    "GLViewportWidget",
    "OrbitCamera",
    "InputHandler",
    "StockRenderer",
    "MeshRenderer",
    "StatusOverlay",
    "OrientationCube",
    "GridRenderer",
]
