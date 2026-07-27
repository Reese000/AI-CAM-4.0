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
    assert candidate.pocketing_paths((({"pockets": [((20,20,0), (80,80,5))]}, {"diameter": 8.0, "stepover": 4.0}))) == [((24,24,5), (76,24,5)), ((76,28,5), (24,28,5))] (simplified spiral)

def test_2(candidate):
    assert candidate.pocketing_paths((({"pockets": [((10,10,0), (40,40,3))]}, {"diameter": 10.0, "stepover": 5.0}))) == [((15,15,3), (35,15,3)), ((35,20,3), (15,20,3))] (simplified spiral)
