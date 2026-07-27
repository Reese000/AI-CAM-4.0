import struct

def parse_stl(path) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices = []
    normals = []
    indices = []

    with open(path, "rb") as file:
        data = file.read()

    # Check if it's binary or ASCII
    if data[:80].strip() == b'':  # If it's binary
        faces = (len(data) - 84) // 50

        for i in range(faces):
            # Unpack the normal
            n = struct.unpack_from('fff', data, 84 + i * 50)
            # Unpack the vertices
            v = struct.unpack_from('fff', data, 84 + i * 50 + 12)
            # Add them to the lists
            vertices.append(tuple(v))
            normals.append(tuple(n))
            # The index is always the same for binary STL
            indices.append((i, i, i))
    else:  # Else, it's ASCII
        lines = data.decode().split('\n')

        for i, line in enumerate(lines):
            if "vertex" in line:
                v = tuple(map(float, line.split()[1:]))
                # Add the vertex to the list
                vertices.append(v)
                # The normals and indices are just placeholder
                # as ASCII STL does not contain this information
                normals.append((0.0, 0.0, 0.0))
                indices.append((i, i, i))

    return vertices, normals, indices