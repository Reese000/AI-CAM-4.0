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

def test_1(candidate):
    assert candidate.adaptive_clearing_paths((0, 0, 0), (10, 10, 5), 2.0) == [(1,1,5), (1,9,5), (9,9,5), (9,1,5), ...]

def test_2(candidate):
    assert candidate.adaptive_clearing_paths((-5, -5, 0), (5, 5, 2), 1.0) == [(-4,-4,2), (-4,4,2), (4,4,2), ...]
