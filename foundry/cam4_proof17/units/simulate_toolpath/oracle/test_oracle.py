import importlib.util, os, sys, pytest, math

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

# ── Basic structure ──────────────────────────────────────────────────────

def test_returns_list_of_frames(candidate):
    stock = [[20.0]*10 for _ in range(10)]
    toolpath = [((0, 0, 10), (9, 0, 10))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert isinstance(result, list) and len(result) >= 1

def test_frames_are_2d_grids(candidate):
    stock = [[10.0]*5 for _ in range(5)]
    toolpath = [((0, 0, 5), (4, 0, 5))]
    result = candidate.simulate_toolpath(stock, toolpath)
    for frame in result:
        assert isinstance(frame, list) and len(frame) >= 1
        for row in frame:
            assert isinstance(row, list) and len(row) >= 1

def test_accepts_2d_from_stock_heightmap(candidate):
    stock_2d = [[20.0]*10 for _ in range(10)]
    toolpath = [((2,2,20), (8,2,20))]
    result = candidate.simulate_toolpath(stock_2d, toolpath)
    assert isinstance(result, list) and len(result) >= 1

# ── Locality: cells far from tool must be UNCHANGED ──────────────────────

def test_locality_far_cells_unchanged(candidate):
    """Cells far from the swept segment must remain at initial height."""
    size = 20
    initial = 50.0
    stock = [[initial]*size for _ in range(size)]
    z_cut = 10.0
    # Cut a small region: just one segment near corner
    toolpath = [((0, 0, z_cut), (1, 0, z_cut))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert len(result) >= 1
    frame = result[-1]
    # Count changed cells
    changed = sum(1 for i in range(size) for j in range(size)
                  if frame[i][j] < initial - 0.01)
    # A correct simulation changes only cells near the tool path.
    # A flood impl changes ALL 400 cells. Must change < 50%.
    assert changed < size * size * 0.5, \
        f"Flood detected: {changed}/{size*size} cells changed — no locality"

def test_locality_nearby_cells_changed(candidate):
    """Some cells near the tool path must be lowered."""
    size = 20
    initial = 50.0
    stock = [[initial]*size for _ in range(size)]
    z_cut = 10.0
    toolpath = [((0, 0, z_cut), (size-1, 0, z_cut))]
    result = candidate.simulate_toolpath(stock, toolpath)
    frame = result[-1]
    changed = sum(1 for i in range(size) for j in range(size)
                  if frame[i][j] < initial - 0.01)
    assert changed >= 1, "No cells were lowered at all"

# ── Removal: some cells must be lowered ──────────────────────────────────

def test_removal_some_cells_lowered(candidate):
    """After a cutting pass, some cells must be below initial height."""
    size = 10
    initial = 30.0
    stock = [[initial]*size for _ in range(size)]
    z_cut = 5.0
    toolpath = [((0, 0, z_cut), (size-1, 0, z_cut))]
    result = candidate.simulate_toolpath(stock, toolpath)
    frame = result[-1]
    any_lowered = any(frame[i][j] < initial - 0.01
                      for i in range(size) for j in range(size))
    assert any_lowered, "No material removed — all cells still at initial height"

# ── Monotonicity: heights never increase ─────────────────────────────────

def test_monotonicity_heights_never_increase(candidate):
    """No cell should ever increase in height across frames."""
    size = 10
    initial = 40.0
    stock = [[initial]*size for _ in range(size)]
    toolpath = [
        ((0, 0, 20), (size-1, 0, 20)),
        ((0, 0, 10), (size-1, 0, 10)),
    ]
    result = candidate.simulate_toolpath(stock, toolpath)
    prev = stock
    for frame in result:
        for i in range(size):
            for j in range(size):
                assert frame[i][j] <= prev[i][j] + 1e-9, \
                    f"Height increased at ({i},{j}): {prev[i][j]} → {frame[i][j]}"
        prev = frame

# ── Multi-segment: multiple frames ───────────────────────────────────────

def test_multi_segment_produces_frames(candidate):
    stock = [[30.0]*10 for _ in range(10)]
    toolpath = [
        ((0,0,30), (9,0,30)),
        ((9,3,30), (0,3,30)),
        ((0,6,30), (9,6,30)),
    ]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert len(result) >= 3, f"Expected ≥3 frames, got {len(result)}"

def test_float_coordinates_accepted(candidate):
    stock = [[20.0]*20 for _ in range(16)]
    toolpath = [((0.0, 5.0, 20.0), (100.0, 5.0, 20.0)),
                ((100.0, 15.0, 20.0), (0.0, 15.0, 20.0))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert isinstance(result, list) and len(result) >= 1
