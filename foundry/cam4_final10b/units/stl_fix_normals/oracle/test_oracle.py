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

def test_single_triangle(candidate):
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    faces = [(0, 1, 2)]
    normals = candidate.stl_fix_normals(vertices, faces)
    assert isinstance(normals, list)
    assert len(normals) == 1
    assert len(normals[0]) == 3
    # Normal must be a unit vector (magnitude ~1)
    nx, ny, nz = normals[0]
    mag = (nx**2 + ny**2 + nz**2)**0.5
    assert abs(mag - 1.0) < 0.01, f"Normal not unit vector: magnitude={mag}"

def test_two_triangles(candidate):
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    faces = [(0, 1, 2), (0, 2, 3)]
    normals = candidate.stl_fix_normals(vertices, faces)
    assert len(normals) == 2
    for n in normals:
        assert len(n) == 3
        mag = sum(c**2 for c in n)**0.5
        assert abs(mag - 1.0) < 0.01
