import importlib.util, os, sys, pytest

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

def test_returns_frames_with_stock_state(candidate):
    """Each frame must contain a stock/heightmap state key."""
    stock = {"heightmap": [[10.0]*5 for _ in range(5)], "dims": (5, 5), "resolution": 1.0}
    toolpath = [{"x": 0, "y": 0, "z": 5.0, "type": "move"}]
    result = candidate.simulate_toolpath(stock, toolpath)
    assert isinstance(result, list)
    assert len(result) >= 1
    for i, frame in enumerate(result):
        assert isinstance(frame, dict), f"Frame {i} is not a dict: {type(frame)}"
        # Frame must contain some stock state (heightmap, stock, or similar)
        has_stock = any(k in frame for k in ["heightmap", "stock", "state", "stock_heightmap", "frame"])
        assert has_stock, f"Frame {i} missing stock state key: {list(frame.keys())}"
