import struct

def parse_stl(path) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    with open(path, "rb") as file:
        data = bytearray(file.read())

    if data[:8] == b'solid ':
        # ASCII STL
        return parse_ascii_stl(data)
    else:
        # Binary STL
        return parse_binary_stl(data)


def parse_ascii_stl(data) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    lines = data.split(b'\n')
    vertices = []
    normals = []
    indices = []

    for line in lines:
        if b'vertex' in line:
            coord = tuple(float(x) for x in line.split()[1:])
            if len(coord) == 3:
                vertices.append(coord)
        elif b'normal' in line:
            coord = tuple(float(x) for x in line.split()[1:])
            if len(coord) == 3:
                normals.append(coord)
        elif b'endfacet' in line:
            indices.append(tuple(range(len(vertices) - 3, len(vertices))))

    return vertices, normals, indices


def parse_binary_stl(data) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices = []
    normals = []
    indices = []

    for i in range(0, len(data), 50):
        normal = struct.unpack_from('fff', data, offset=i)
        normals.append(normal)
        for j in range(3):
            vertex = struct.unpack_from('fff', data, offset=i + 4 * j)
            vertices.append(vertex)
        indices.append(tuple(range(len(vertices) - 3, len(vertices))))

    return vertices, normals, indices