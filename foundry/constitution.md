# AI CAM 4.0 Constitution

## What This Is
A minimal-scope, maximum-functionality CAD/CAM system for CNC machining.
Desktop application with 3D viewport, toolpath generation, simulation, and G-code export.

## Architecture
- **Kernel**: Pure Python + NumPy (ZERO Qt imports). Geometry primitives, STL import, G-code parser, CAM strategies, SDF simulation.
- **Viewport**: PySide6 + OpenGL 3.3 core profile. Split into 8 focused files.
- **Simulation**: Z-map heightfield stock model, frame-based playback.
- **Post-processors**: Fanuc and Heidenhain G-code renderers.

## Required Units (functions)

### Layer 0 — Geometry primitives
1. `vec3_add(a, b)` — Add two 3D vectors
2. `vec3_sub(a, b)` — Subtract two 3D vectors
3. `vec3_dot(a, b)` — Dot product
4. `vec3_cross(a, b)` — Cross product
5. `vec3_length(v)` — Vector magnitude
6. `vec3_normalize(v)` — Unit vector

### Layer 1 — Bounding box
7. `bbox_from_points(points)` — Compute bounding box from point list
8. `bbox_contains(bbox, point)` — Test if point is inside bbox

### Layer 2 — STL import
9. `parse_stl(path)` — Parse binary/ASCII STL file, return vertices/normals/faces
10. `stl_fix_normals(vertices, faces)` — Fix inverted normals

### Layer 3 — G-code
11. `parse_gcode(text)` — Parse G-code text into command list
12. `gcode_to_segments(commands)` — Convert G-code commands to toolpath segments

### Layer 4 — CAM strategies
13. `face_milling_paths(stock, tool)` — Generate face milling toolpath
14. `adaptive_clearing_paths(stock, tool)` — Generate adaptive clearing toolpath
15. `pocketing_paths(stock, tool)` — Generate pocket clearing toolpath

### Layer 5 — Simulation
16. `stock_heightmap(stock_dims, resolution)` — Create Z-map heightfield
17. `simulate_toolpath(stock, toolpath)` — Simulate material removal, return frames

### Layer 6 — Post-processing
18. `toolpath_to_ir(toolpath)` — Convert toolpath to intermediate representation
19. `render_fanuc(ir_segments)` — Render Fanuc G-code
20. `render_heidenhain(ir_segments)` — Render Heidenhain G-code

## Dependencies (DAG)
- Layer 0: no deps
- Layer 1: depends on vec3_add
- Layer 2: depends on vec3_add, vec3_length
- Layer 3: standalone
- Layer 4: depends on bbox_from_points, vec3_add, vec3_length
- Layer 5: depends on stock_heightmap, vec3_length
- Layer 6: depends on toolpath_to_ir, vec3_length

## Composition
Each layer is a Python module. The final program imports from all layers.
Main workflow: Import STL → Select strategy → Generate toolpath → Simulate → Export G-code.
