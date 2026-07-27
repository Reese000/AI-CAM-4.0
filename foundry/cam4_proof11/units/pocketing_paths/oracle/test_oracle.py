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

def test_returns_list_of_segments(candidate):
    stock = {"pockets": [((20,20,0), (80,80,5))]}
    tool = {"diameter": 8.0, "stepover": 4.0}
    result = candidate.pocketing_paths(stock, tool)
    assert isinstance(result, list)
    assert len(result) >= 1

def test_segments_are_2tuples(candidate):
    stock = {"pockets": [((20,20,0), (80,80,5))]}
    tool = {"diameter": 8.0, "stepover": 4.0}
    result = candidate.pocketing_paths(stock, tool)
    for seg in result:
        assert isinstance(seg, tuple)
        assert len(seg) == 2
        start, end = seg
        assert len(start) == 3
        assert len(end) == 3

def test_at_cutting_height(candidate):
    stock = {"pockets": [((20,20,0), (80,80,5))]}
    tool = {"diameter": 8.0, "stepover": 4.0}
    result = candidate.pocketing_paths(stock, tool)
    for seg in result:
        z_start = seg[0][2]
        z_end = seg[1][2]
        assert abs(z_start - 5.0) < 0.1, f"Start Z={z_start}, expected ~5"
        assert abs(z_end - 5.0) < 0.1, f"End Z={z_end}, expected ~5"

def test_segments_inside_pocket(candidate):
    stock = {"pockets": [((20,20,0), (80,80,5))]}
    tool = {"diameter": 8.0, "stepover": 4.0}
    result = candidate.pocketing_paths(stock, tool)
    for seg in result:
        x_start, y_start = seg[0][0], seg[0][1]
        x_end, y_end = seg[1][0], seg[1][1]
        # Segments should be within pocket bounds (with tool radius margin)
        margin = tool["diameter"] / 2
        assert 20 - margin <= x_start <= 80 + margin, f"x_start={x_start} outside pocket"
        assert 20 - margin <= y_start <= 80 + margin, f"y_start={y_start} outside pocket"
