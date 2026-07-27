from __future__ import annotations
import importlib.util, os, sys
import pytest

def _load_candidate():
    candidate_path = os.environ.get("FOUNDRY_CANDIDATE_PATH")
    if not candidate_path:
        pytest.fail("FOUNDRY_CANDIDATE_PATH env var not set; oracle cannot locate candidate")
    spec = importlib.util.spec_from_file_location("candidate_under_test", candidate_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate_under_test"] = module
    spec.loader.exec_module(module)
    return module

@pytest.fixture(scope="module")
def candidate():
    return _load_candidate()

def test_validate_vec3_valid(candidate):
    assert candidate.validate_vec3((1, 2, 3)) == (1, 2, 3)

def test_validate_vec3_invalid_type(candidate):
    with pytest.raises(ValueError):
        candidate.validate_vec3((1, "2", 3))

def test_validate_vec3_invalid_length(candidate):
    with pytest.raises(ValueError):
        candidate.validate_vec3((1, 2))