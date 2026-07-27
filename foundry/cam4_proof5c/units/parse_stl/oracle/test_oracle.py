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

import tempfile, os

def test_parse_ascii_triangle(candidate):
    stl_content = """solid test
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid test"""
    with tempfile.NamedTemporaryFile(suffix='.stl', mode='w', delete=False) as f:
        f.write(stl_content)
        tmp_path = f.name
    try:
        result = candidate.parse_stl(tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 3
        vertices, normals, faces = result
        assert len(vertices) >= 3
        assert len(faces) >= 1
    finally:
        os.unlink(tmp_path)
