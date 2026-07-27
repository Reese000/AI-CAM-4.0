def parse_stl(path: str) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices = []
    normals = []
    faces = []
    with open(path, 'rb') as f:
        if f.read(80).strip() != b'STL file':
            raise ValueError('Not a STL file')
        f.seek(0)
        size = struct.unpack('i', f.read(4))[0]
        for _ in range(size):
            normal = struct.unpack('fff', f.read(12))
            vertices_indices = struct.unpack('iii', f.read(12))
            attributes = struct.unpack('h', f.read(2))[0]
            vertices.extend([(struct.unpack('fff', f.read(12)) for _ in range(3))])
            faces.append(vertices_indices)
            normals.append(normal)
    return vertices, normals, faces

def vec3_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]

def vec3_length(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)