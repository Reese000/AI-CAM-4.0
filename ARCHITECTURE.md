# AI CAM 4.0 — Architecture Plan

## Core Principles (from v3 lessons learned)

1. **Kernel and GUI are separate packages.** Kernel has ZERO Qt/PySide imports. GUI imports kernel, never the reverse.
2. **One MainWindow, no versions.** Refactor in place.
3. **Viewport is 8 files from day one.** Never a 5,000-line monolith.
4. **Data flows one way:** Strategy → `ToolpathData` → Simulation → `SimulationFrame[]` → Viewport. No wrapping.
5. **No stubs in production.** Every UI element does something or doesn't exist.
6. **Test the user path, not the code path.** 50 real integration tests > 5,000 unit tests.
7. **Ship the happy path first.** STL → strategy → toolpath → simulate → export. Every other feature is secondary.

## Directory Structure

```
ai_cam/
├── kernel/           # ZERO Qt imports. Pure Python + numpy.
│   ├── types.py      # Vec3, BBox, Transform, ToolpathData
│   ├── sdf.py        # Signed distance fields
│   ├── gcode.py      # G-code parser
│   ├── stl.py        # STL import
│   └── strategies/   # CAM strategies
│       ├── base.py   # with validate_params() wired into generate_toolpath()
│       ├── face_milling.py
│       └── ...
├── simulation/       # ZERO Qt imports. Pure Python + numpy.
│   ├── engine.py     # StockModel + SimulationEngine
│   └── refinement.py # Feature-adaptive mesh refinement
├── post/             # ZERO Qt imports. Pure Python.
│   ├── ir.py         # Intermediate representation
│   ├── fanuc.py      # Fanuc renderer
│   └── heidenhain.py # Heidenhain renderer
├── app/              # Qt/PySide6 lives here ONLY
│   ├── main_window.py  # Single MainWindow
│   ├── viewport/
│   │   ├── shell.py        # Qt widget, event routing (~500 lines)
│   │   ├── renderer.py     # GL draw calls, VBO/IBO (~600 lines)
│   │   ├── camera.py       # Orbit, zoom, pan (~300 lines)
│   │   ├── input_handler.py # Mouse/keyboard (~400 lines)
│   │   ├── stock_renderer.py # Stock solid (~400 lines)
│   │   ├── mesh_renderer.py  # Mesh + toolpath (~400 lines)
│   │   ├── overlays.py      # SSAO, orientation, status (~300 lines)
│   │   ├── grid.py          # Grid rendering (~200 lines)
│   │   ├── gl_constants.py  # GL constants, shaders, colors
│   │   └── renderer_utils.py # compile_shader, uniform helpers
│   └── workers.py    # FrameWorker, SegmentWorker (QThread)
├── tests/
│   ├── smoke/        # App boot, import checks (~10 tests)
│   ├── integration/  # Full pipeline tests (~50 tests)
│   └── unit/         # Kernel + component tests (~500 tests)
├── cli.py            # Headless CLI with --dialect flag
├── pyproject.toml
└── Makefile
```

## Data Flow (One Direction, No Wrapping)

```
User Action
    ↓
Strategy.generate_toolpath(stock, tool) → list[ToolpathData]  # Canonical format
    ↓
SimulationEngine.simulate_to_frames(toolpath) → list[SimulationFrame]
    ↓
SimulationController (QObject)
    ↓ state_changed signal
Viewport.update_simulation_state(frame)
    ↓
Stock mesh + tool position updated
    ↓
G-code export: segments_to_ir(toolpath) → IR → Renderer → .nc file
```

## Minimal Scope (v4.0)

### Must Have (Day 1)
- [ ] Kernel types (Vec3, BBox, Transform, ToolpathData)
- [ ] STL import
- [ ] 3 CAM strategies (face_milling, adaptive_clearing, pocketing)
- [ ] Viewport shell with basic rendering
- [ ] MainWindow with File → Import STL
- [ ] Basic simulation (Z-map heightfield)
- [ ] G-code export (Fanuc)
- [ ] Smoke tests (app boots, STL loads)

### Must Have (Week 1)
- [ ] All viewport components (8 files)
- [ ] Toolpath visualization
- [ ] Simulation playback
- [ ] 10+ CAM strategies
- [ ] Integration tests (50 tests)

### Nice to Have (Later)
- [ ] Heidenhain post-processor
- [ ] Feature recognition
- [ ] DFM bridge
- [ ] Undo/redo
- [ ] Batch processing

## Testing Strategy

1. **Smoke tests** (10): App boots, STL loads, strategy generates, G-code exports
2. **Integration tests** (50): Full pipeline STL → strategy → toolpath → simulate → export
3. **Unit tests** (500): Kernel functions, strategy logic, simulation math

## Success Criteria

A feature is done when ALL of these are true:
1. The code is written
2. A test verifies it works
3. The test passes in a CLEAN environment
4. A human has opened the app and used the feature
5. The feature works end-to-end (not just in isolation)
