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
    assert candidate.parse_gcode('G0 X10 Y20 Z30\nG1 X5 Y5 Z5 F100') == [{'code':0,'params':{'X':10,'Y':20,'Z':30}}, {'code':1,'params':{'X':5,'Y':5,'Z':5,'F':100}}]

def test_2(candidate):
    assert candidate.parse_gcode('G0 Z5\nM3 S1000') == [{'code':0,'params':{'Z':5}}, {'code':3,'params':{'S':1000}}]
