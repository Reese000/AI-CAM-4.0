# AI CAM 4.0

Minimal-scope, maximum-functionality CAD/CAM system for CNC machining. Built from lessons learned in AI CAM 3.0 — clean architecture, zero stubs, one-way data flow.

## Purpose

AI CAM 4.0 is a desktop CNC CAM application that takes an STL model, generates toolpaths using configurable machining strategies, simulates material removal, and exports machine-ready G-code (Fanuc and Heidenhain). It targets real-world CNC milling workflows for a machine shop environment.

## Tech Stack

- **Language:** Python 3.10+
- **GUI:** PySide6 (Qt 6) with PyOpenGL for the 3D viewport
- **Math:** NumPy, SciPy (for SDF interpolation)
- **Testing:** pytest, pytest-timeout, hypothesis
- **Build:** setuptools via `pyproject.toml`

## Setup

```bash
# Clone
git clone https://github.com/Reese000/AI-CAM-4.0.git
cd AI-CAM-4.0

# Create virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Install dev dependencies (for testing)
pip install -e ".[dev]"
```

## Running

```bash
# Launch the GUI
python -m app

# Or via entry point (if installed)
ai-cam
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Architecture

The project follows a strict layered architecture with **zero Qt imports in the kernel**:

```
kernel/              ← Pure Python + NumPy. Zero Qt imports.
  types.py           ← Vec3, BBox, Transform, ToolDef, Material, Move, ToolpathData
  stl.py             ← Binary + ASCII STL parser with normal fixing
  gcode.py           ← G-code parser (G0-G3, M-codes, modal tracking)
  sdf.py             ← Z-map heightfield SDF for tool-part proximity
  strategies/        ← CAM strategies (face milling, adaptive clearing, adaptive engagement, pocketing, waterline finishing, drilling)
    base.py          ← BaseStrategy ABC with validate_params() → generate_toolpath()
    face_milling.py  ← Parallel raster passes
    adaptive_clearing.py ← Trochoidal-style constant-engagement roughing
    adaptive_engagement.py ← F1: adaptive roughing + engagement-gated feed
    pocketing.py     ← Offset-inward contour clearing
    waterline_finishing.py ← F2: waterline (Z-level) + constant-scallop finishing
    drilling.py      ← Canned drilling cycles

simulation/          ← Pure Python + NumPy. Zero Qt imports.
  engine.py          ← StockModel (Z-map heightfield), SimulationEngine
  controller.py      ← Qt-backed playback controller (play/pause/seek)

post/                ← Pure Python. Zero Qt imports.
  ir.py              ← Intermediate representation (ToolpathData → IRSegments)
  fanuc.py           ← Fanuc G-code renderer (.nc output)
  heidenhain.py      ← Heidenhain format renderer (.nc output)

app/                 ← Qt/PySide6 lives here ONLY.
  __main__.py        ← Entry point, sys.path cleanup, dark palette
  main_window.py     ← Single MainWindow with menus, toolbar, GL viewport
  strategy_executor.py ← Bridge: UI params → kernel strategy → ToolpathData
                      (adaptive_engagement / waterline_finishing dispatch to kernel/strategies/)
  workers.py         ← QThread-based frame generation
  viewport/          ← (planned) 8-file OpenGL viewport decomposition
```

### Data Flow (one direction, no wrapping)

```
User Action
    ↓
Strategy.generate_toolpath(stock, tool) → ToolpathData
    ↓
SimulationEngine.simulate_to_frames(toolpath) → SimulationFrame[]
    ↓
SimulationController (QObject, signals)
    ↓
Viewport.update_simulation_state(frame)
    ↓
G-code export: segments_to_ir(toolpath) → IR → FanucRenderer/HeidenhainRenderer → .nc
```

## Current Status

### Working (verified)
- **Kernel types:** Vec3, BBox, Transform, ToolDef, Material, Move, ToolpathData — all fully implemented
- **STL parser:** Binary + ASCII, normal fixing, vertex deduplication
- **G-code parser:** Full G/M code support with modal tracking
- **SDF engine:** Z-map heightfield with scipy interpolation
- **6 CAM strategies:** Face milling, adaptive clearing, adaptive engagement (F1, engagement-gated feed), pocketing, waterline finishing (F2, Z-level + constant scallop), drilling — all generating valid toolpaths
- **Simulation engine:** Z-map heightfield stock model with vectorized cut simulation
- **Simulation controller:** Qt-backed playback with play/pause/stop/seek
- **Post-processors:** IR intermediate representation, Fanuc renderer, Heidenhain renderer
- **GUI:** MainWindow with menus, toolbar, GL viewport, strategy selector, simulation controls
- **Background workers:** QThread-based frame generation
- **Tests:** 850+ lines covering kernel types, STL parsing, G-code, SDF, strategies, post-processors

### In Progress / WIP
- **Viewport:** Currently a single `GLViewportWidget` in main_window.py — ARCHITECTURE.md plans 8-file decomposition but not yet split out
- **App-layer strategy routing:** `strategy_executor.py` still answers five names with its own legacy planners — `face_milling`, `adaptive_clearing`, `pocketing`, `contour` and `drilling`. Four of those collide with a kernel algorithm of the same name (the kernel has no `contour`), so for those four two algorithms currently share one name. Only F1 (`adaptive_engagement`) and F2 (`waterline_finishing`) dispatch to the kernel. `app/` sat on the P5 no-touch list, which is why the cards that landed the kernel algorithms could not re-point the executor; the split is declared in `LEGACY_NAME_COLLISIONS` in `tests/integration/test_strategy_executor_dispatch.py` and recomputed by a test that fails if it drifts.
- **Foundry verification:** Multiple foundry run directories contain verified kernel function implementations (vec3 ops, parsing, milling paths) — these are artifacts of the Foundry Manager verification system

### Not Yet Implemented
- STL-based geometry (B-rep, feature recognition)
- Multi-axis machining
- Heidenhain post-processor (renderer exists, not tested with real output)
- Undo/redo (stacks defined, not wired)
- Batch processing
- DFM bridge integration
- CLI headless mode

## Relationship to AI CAM 3.0

**AI CAM 4.0 is a deliberate clean rewrite inspired by lessons learned from AI CAM 3.0.** It is not a fork, branch, or incremental evolution of 3.0 — it's a fresh start with a radically simpler architecture.

### Evidence

| Aspect | AI CAM 3.0 | AI CAM 4.0 |
|--------|-----------|-----------|
| **Size** | ~822 files, 136KB main_window.py | ~30 source files, 1031-line main_window.py |
| **Package** | `ai-cam-3` v0.2.0 | `ai-cam` v4.0.0 |
| **Dependencies** | numpy, scipy, pydantic, PySide6 + optional CAD/ML/GPU/server | numpy, scipy, PySide6, PyOpenGL |
| **kernel/** | assembly, brep, cad, feature, kinematics, octree, sketcher, tool_library, material_db | types.py, stl.py, gcode.py, sdf.py, strategies/ |
| **simulation/** | collision, physics, vibration, thermal, kinematics, machine_library, material_removal | engine.py (Z-map heightfield), controller.py |
| **Post-processors** | DNC, jerk_limiting, MDP_format, optimization, renderers | ir.py → fanuc.py, heidenhain.py |
| **Architecture** | Multiple main_window versions (v2, v3), tightly coupled | Single main_window, strict kernel/GUI separation |
| **Shared code** | None — completely different file names, types, APIs | None |

### Design Philosophy

The ARCHITECTURE.md explicitly states 7 principles "from v3 lessons learned":

1. Kernel and GUI are separate packages (3.0 had Qt mixed into kernel)
2. One MainWindow, no versions (3.0 had main_window.py, v2, v3)
3. Viewport is 8 files from day one (3.0 had a monolithic gl_viewport.py)
4. Data flows one way, no wrapping (3.0 had complex wrapping patterns)
5. No stubs in production (3.0 had audit-identified stub issues)
6. Test the user path, not the code path (3.0 had thousands of unit tests)
7. Ship the happy path first (3.0 tried to do everything at once)

### Summary

4.0 is a **focused subset** of 3.0's ambitions — it does fewer things but does them correctly from the start. The intent is to get a working STL → toolpath → simulate → export pipeline solid before adding complexity. If 4.0 succeeds, features from 3.0 (B-rep, feature recognition, multi-axis, DFM bridge) would be ported into 4.0's clean architecture.

## License

Private — Reese CNC Machine Shop LLC.
