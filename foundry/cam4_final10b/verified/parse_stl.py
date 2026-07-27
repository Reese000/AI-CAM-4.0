import struct

def parse_stl(path: str) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    def vec3_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    def vec3_length(v: tuple[float, float, float]) -> float:
        return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

    vertices = []
    faces = []
    normals = []
    with open(path, "rb") as f:
        data = f.read()
        if data.startswith(b'solid'):
            # ASCII STL
            lines = data.split(b'\n')
            for line in lines:
                if line.strip().startswith(b'vertex'):
                    vertices.append(tuple(float(x) for x in line.strip().split()[1:]))
                elif line.strip().startswith(b'endfacet'):
                    faces.append(tuple(range(len(vertices) - 3, len(vertices))))
                    normal = vec3_add(vec3_add(vertices[-3], vertices[-2]), vertices[-1])
                    normal = tuple(x / vec3_length(normal) for x in normal)
                    normals.extend([normal] * 3)
        else:
            # Binary STL
            triangles = struct.unpack_from('<iiii', data, 80)
            for i in range(triangles[0]):
                normal = struct.unpack_from('<fff', data, 84 + i * 50)
                v1, v2, v3 = struct.unpack_from('<fff', data, 84 + i * 50 + 4 * 3), struct.unpack_from('<fff', data, 84 + i * 50 + 4 * 6), struct.unpack_from('<fff', data, 84 + i * 50 + 4 * 9)
                vertices.extend([v1, v2, v3])
                faces.append((3 * i, 3 * i + 1, 3 * i + 2))
                normals.append(normal)
    return vertices, normals, faces