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

def test_10x10_grid(candidate):
    result = candidate.stock_heightmap([100.0, 100.0, 20.0], 10)
    assert isinstance(result, list)
    assert len(result) == 10
    assert all(len(row) == 10 for row in result)

def test_5x5_grid(candidate):
    result = candidate.stock_heightmap([50.0, 50.0, 5.0], 5)
    assert isinstance(result, list)
    assert len(result) == 5
    assert all(len(row) == 5 for row in result)
