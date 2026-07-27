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
    assert candidate.render_fanuc(["{'type': 'rapid'", 'start': (0.0, 0.0, 5.0), 'end': (0.0, 0.0, 5.0)}, "{'type': 'feed'", 'start': (0.0, 0.0, 5.0), 'end': (10.0, 0.0, 5.0)}]) == 'G00 Z5.000\nG00 X0.000 Y0.000\nG01 X10.000 Y0.000 F100.0'

def test_2(candidate):
    assert candidate.render_fanuc(["{'type': 'feed'", 'start': (0.0, 0.0, 0.0), 'end': (5.0, 5.0, 0.0)}]) == 'G01 X5.000 Y5.000 Z0.000 F100.0'
