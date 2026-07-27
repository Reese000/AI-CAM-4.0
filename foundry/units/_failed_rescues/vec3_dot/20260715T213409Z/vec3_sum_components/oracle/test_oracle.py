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

def test_sum_components_basic(candidate):
    assert candidate.vec3_sum_components((1, 2, 3)) == 6.0

def test_sum_components_zero(candidate):
    assert candidate.vec3_sum_components((0, 0, 0)) == 0.0

def test_sum_components_floats(candidate):
    assert candidate.vec3_sum_components((1.5, 2.5, 3.5)) == pytest.approx(7.5)

def test_sum_components_negative(candidate):
    assert candidate.vec3_sum_components((-1, 2, -3)) == pytest.approx(-2.0)
