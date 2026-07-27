import struct

def parse_stl(path):
    with open(path, 'rb') as f:
        data = f.read()

    # Detect binary or ASCII by checking if the first 5 bytes are 'solid'
    if data[:5] == b'solid':
        return parse_ascii_stl(data)
    else:
        return parse_binary_stl(data)


def parse_ascii_stl(data):
    lines = data.decode('utf-8').split('\n')

    vertices = []
    normals = []
    faces = []

    face_buffer = []

    for line in lines:
        line = line.strip()

        if line.startswith('facet normal'):
            normal = list(map(float, line[13:].split()))
        elif line.startswith('vertex'):
            vertex = list(map(float, line[6:].split()))
            face_buffer.append(len(vertices))
            vertices.append(vertex)

            if len(face_buffer) == 3:
                faces.append(face_buffer)
                face_buffer = []

    return vertices, normals, faces


def parse_binary_stl(data):
    vertices = []
    normals = []
    faces = []

    # Binary STL files have a 80-byte header, followed by a uint32 for the number of triangles
    num_triangles = struct.unpack_from('<I', data, 80)[0]

    for i in range(num_triangles):
        # Each triangle is 12 floats for the normal, followed by 9 floats for the vertices
        # Then there's a uint16 for the attribute byte count, which we don't need
        offset = 84 + i * 50

        normal = struct.unpack_from('<3f', data, offset)
        v1, v2, v3 = struct.unpack_from('<9f', data, offset + 12)

        v1, v2, v3 = list(v1), list(v2), list(v3)

        if len(vertices) > 0 and vertices[-1] == v1:
            v1_index = len(vertices) - 1
        else:
            v1_index = len(vertices)
            vertices.append(v1)

        if len(vertices) > 0 and vertices[-1] == v2:
            v2_index = len(vertices) - 1
        else:
            v2_index = len(vertices)
            vertices.append(v2)

        if len(vertices) > 0 and vertices[-1] == v3:
            v3_index = len(vertices) - 1
        else:
            v3_index = len(vertices)
            vertices.append(v3)

        faces.append((v1_index, v2_index, v3_index))
        normals.append(normal)

    return vertices, normals, faces