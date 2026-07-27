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
    assert candidate.render_heidenhain(["{'start':(0,0,10)", 'end':(10,10,0), 'type':'linear'}]) == '0 BEGIN PGM 1\n1 L X+0 Y+0 Z+10 R0 F1000\n2 L X+10 Y+10 Z+0 R0 F1000\n3 END PGM 1'

def test_2(candidate):
    assert candidate.render_heidenhain(["{'start':(0,0,10)", 'end':(10,10,0), 'type':'linear'}, "{'start':(10,10,0)", 'end':(10,10,5), 'type':'rapid'}]) == '0 BEGIN PGM 1\n1 L X+0 Y+0 Z+10 R0 F1000\n2 L X+10 Y+10 Z+0 R0 F1000\n3 L X+10 Y+10 Z+5 R0 F1000\n4 END PGM 1'
