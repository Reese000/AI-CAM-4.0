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
    assert candidate.adaptive_clearing_paths((({"bbox": ((0,0,0), (100,100,20)), "model": "cylinder"}, {"diameter": 10.0, "stepover": 5.0}))) == [((10,10,20), (90,10,20)), ((90,20,20), (10,20,20))] (simplified)

def test_2(candidate):
    assert candidate.adaptive_clearing_paths((({"bbox": ((0,0,0), (50,50,10)), "model": "box"}, {"diameter": 12.0, "stepover": 6.0}))) == [((6,6,10), (44,6,10)), ((44,12,10), (6,12,10))] (simplified)
