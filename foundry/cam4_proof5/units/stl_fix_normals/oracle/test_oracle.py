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

def test_single_triangle_direction(candidate):
    """CCW triangle (0,0,0)->(1,0,0)->(0,1,0) has outward normal (0,0,1)."""
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    faces = [(0, 1, 2)]
    normals = candidate.stl_fix_normals(vertices, faces)
    assert isinstance(normals, list)
    assert len(normals) == 1
    nx, ny, nz = normals[0]
    mag = (nx**2 + ny**2 + nz**2)**0.5
    assert abs(mag - 1.0) < 0.01, f"Normal not unit vector: magnitude={mag}"
    # Direction must be ~(0,0,1) — dot product with expected > 0.99
    dot = nz  # dot((nx,ny,nz), (0,0,1)) = nz
    assert dot > 0.99, f"Wrong direction: normal=({nx:.3f},{ny:.3f},{nz:.3f}), expected ~(0,0,1)"

def test_two_triangles_direction(candidate):
    """Two faces sharing edge: face 0 normal ~(0,0,1), face 1 normal ~(1,0,0)."""
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    faces = [(0, 1, 2), (0, 2, 3)]
    normals = candidate.stl_fix_normals(vertices, faces)
    assert len(normals) == 2
    # Face 0: (0,0,0)->(1,0,0)->(0,1,0) -> normal ~(0,0,1)
    n0 = normals[0]
    mag0 = sum(c**2 for c in n0)**0.5
    assert abs(mag0 - 1.0) < 0.01
    assert n0[2] > 0.99, f"Face 0 wrong direction: {n0}"
    # Face 1: (0,0,0)->(0,1,0)->(0,0,1) -> normal ~(1,0,0)
    n1 = normals[1]
    mag1 = sum(c**2 for c in n1)**0.5
    assert abs(mag1 - 1.0) < 0.01
    assert n1[0] > 0.99, f"Face 1 wrong direction: {n1}"
