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
    assert candidate.snake_to_camel('snake_case') == 'snakeCase'

def test_2(candidate):
    assert candidate.snake_to_camel('already_camel') == 'alreadyCamel'

def test_3(candidate):
    assert candidate.snake_to_camel('single') == 'single'

def test_4(candidate):
    assert candidate.snake_to_camel('multiple_underscores_here') == 'multipleUnderscoresHere'
