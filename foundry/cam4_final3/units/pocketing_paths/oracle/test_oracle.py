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
    assert candidate.pocketing_paths(("{'dims': (10,10,5)", 'resolution': 0.5}, "{'diameter': 5", 'length': 20})) == [{'type': 'line', 'start': (2.5,2.5,-1), 'end': (7.5,2.5,-1)}, {'type': 'line', 'start': (7.5,7.5,-1), 'end': (2.5,7.5,-1)}]

def test_2(candidate):
    assert candidate.pocketing_paths(("{'dims': (5,5,5)", 'resolution': 0.5}, "{'diameter': 2", 'length': 10})) == [{'type': 'line', 'start': (1,1,-1), 'end': (4,1,-1)}, {'type': 'line', 'start': (4,4,-1), 'end': (1,4,-1)}]
