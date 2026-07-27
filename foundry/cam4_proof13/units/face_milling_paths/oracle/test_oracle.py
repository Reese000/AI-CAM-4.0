import importlib.util, os, sys, pytest
import math

def _load_candidate():
    p = os.environ.get("FOUNDRY_CANDIDATE_PATH")
    if not p:
        pytest.fail("FOUNDRY_CANDIDATE_PATH not set")
    if os.name == "nt" and len(p) > 2 and p[0] == "/" and p[2] == "/":
        p = p[1].upper() + ":" + p[2:]
    spec = importlib.util.spec_from_file_location("candidate_under_test", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["candidate_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod

@pytest.fixture(scope="module")
def candidate():
    return _load_candidate()

def _tool_swept_cells(segments, tool_radius, grid_min, grid_max, resolution=1.0):
    """Rasterize tool-swept area. Returns set of (gx, gy) cells covered."""
    x_min, y_min = grid_min
    x_max, y_max = grid_max
    cells = set()
    nx = max(1, int((x_max - x_min) / resolution))
    ny = max(1, int((y_max - y_min) / resolution))
    for seg in segments:
        (sx, sy, _), (ex, ey, _) = seg
        steps = max(1, int(math.hypot(ex-sx, ey-sy) / resolution))
        for i in range(steps + 1):
            t = i / steps if steps > 0 else 0
            cx = sx + t * (ex - sx)
            cy = sy + t * (ey - sy)
            # Mark all cells within tool radius
            for gx in range(nx):
                for gy in range(ny):
                    px = x_min + (gx + 0.5) * resolution
                    py = y_min + (gy + 0.5) * resolution
                    if math.hypot(px - cx, py - cy) <= tool_radius + resolution * 0.5:
                        cells.add((gx, gy))
    return cells, nx * ny

def test_returns_list_of_segments(candidate):
    stock = {"bbox": ((0,0,0), (100,100,10))}
    tool = {"diameter": 10.0}
    result = candidate.face_milling_paths(stock, tool)
    assert isinstance(result, list)
    assert len(result) >= 1

def test_at_cutting_height(candidate):
    stock = {"bbox": ((0,0,0), (100,100,10))}
    tool = {"diameter": 10.0}
    result = candidate.face_milling_paths(stock, tool)
    for seg in result:
        assert len(seg) == 2
        assert len(seg[0]) == 3 and len(seg[1]) == 3
        assert abs(seg[0][2] - 10.0) < 0.1, f"Start Z={seg[0][2]}, expected 10"
        assert abs(seg[1][2] - 10.0) < 0.1, f"End Z={seg[1][2]}, expected 10"

def test_coverage_95_percent(candidate):
    stock = {"bbox": ((0,0,0), (100,100,10))}
    tool = {"diameter": 10.0}
    result = candidate.face_milling_paths(stock, tool)
    radius = tool["diameter"] / 2.0
    cells, total = _tool_swept_cells(result, radius, (0,0), (100,100), resolution=2.0)
    coverage = len(cells) / total if total > 0 else 0
    assert coverage >= 0.95, f"Coverage {coverage:.1%} < 95%"

def test_stepover_not_exceeds_diameter(candidate):
    stock = {"bbox": ((0,0,0), (100,100,10))}
    tool = {"diameter": 10.0}
    result = candidate.face_milling_paths(stock, tool)
    if len(result) < 2:
        return  # single pass is fine for small areas
    # Check Y-distance between adjacent passes
    for i in range(len(result) - 1):
        y1 = result[i][0][1]
        y2 = result[i+1][0][1]
        dy = abs(y2 - y1)
        if dy > 0:  # skip zero-distance (same line)
            assert dy <= tool["diameter"] * 1.1,                 f"Stepover {dy:.1f} > diameter {tool['diameter']} between pass {i} and {i+1}"

def test_bounds_within_stock(candidate):
    stock = {"bbox": ((0,0,0), (100,100,10))}
    tool = {"diameter": 10.0}
    result = candidate.face_milling_paths(stock, tool)
    margin = tool["diameter"] / 2.0
    for seg in result:
        for pt in [seg[0], seg[1]]:
            assert pt[0] >= -margin, f"X={pt[0]} below stock min"
            assert pt[0] <= 100 + margin, f"X={pt[0]} above stock max"
            assert pt[1] >= -margin, f"Y={pt[1]} below stock min"
            assert pt[1] <= 100 + margin, f"Y={pt[1]} above stock max"
