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

def test_returns_list_of_frames(candidate):
    """Result must be a non-empty list of frames."""
    stock = [[20.0]*10 for _ in range(10)]
    toolpath = [((0, 0, 10), (100, 0, 10))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) >= 1, "Expected at least 1 frame"

def test_frames_are_2d_grids(candidate):
    """Each frame must be a 2D list (heightmap grid)."""
    stock = [[10.0]*5 for _ in range(5)]
    toolpath = [((0, 0, 5), (50, 0, 5))]
    result = candidate.simulate_toolpath(stock, toolpath)
    for i, frame in enumerate(result):
        assert isinstance(frame, list), f"Frame {i} not a list: {type(frame)}"
        assert len(frame) >= 1, f"Frame {i} is empty"
        for j, row in enumerate(frame):
            assert isinstance(row, list), f"Frame {i} row {j} not a list"
            assert len(row) >= 1, f"Frame {i} row {j} is empty"

def test_material_removal(candidate):
    """After a cutting pass, at least one cell should be lower than initial."""
    height = 10.0
    res = 8
    stock = [[height]*res for _ in range(res)]
    toolpath = [((0, res//2, 3), (res-1, res//2, 3))]
    result = candidate.simulate_toolpath(stock, toolpath)
    any_reduced = False
    for frame in result:
        for row in frame:
            for cell in row:
                if cell < height:
                    any_reduced = True
                    break
    assert any_reduced, "No material removed"

def test_accepts_2d_from_stock_heightmap(candidate):
    """stock_heightmap returns list[list[float]] — simulate must accept it directly."""
    stock_2d = [[20.0]*10 for _ in range(10)]
    toolpath = [((2,2,20), (8,2,20)), ((8,4,20), (2,4,20))]
    result = candidate.simulate_toolpath(stock_2d, toolpath)
    assert isinstance(result, list) and len(result) >= 1

def test_float_coordinates_accepted(candidate):
    """Toolpath coords from face_milling_paths are floats — must work."""
    stock = [[20.0]*20 for _ in range(16)]
    # These are the float coords that face_milling_paths produces
    toolpath = [((0.0, 5.0, 20.0), (100.0, 5.0, 20.0)),
                ((100.0, 15.0, 20.0), (0.0, 15.0, 20.0))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert isinstance(result, list) and len(result) >= 1

def test_multi_segment_toolpath(candidate):
    """Multiple toolpath segments produce multiple frames."""
    stock = [[30.0]*10 for _ in range(10)]
    toolpath = [((0,0,30), (9,0,30)),
                ((9,3,30), (0,3,30)),
                ((0,6,30), (9,6,30))]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert len(result) >= 3, f"Expected ≥3 frames, got {len(result)}"
