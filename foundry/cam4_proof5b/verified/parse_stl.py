import struct

def parse_stl(path):
    with open(path, 'rb') as f:
        data = f.read()

    if data[:8] == b'solid':
        return parse_ascii_stl(data)
    else:
        return parse_binary_stl(data)


def parse_ascii_stl(data):
    data = data.decode('utf-8')
    lines = data.split('\n')
    vertices = []
    normals = []
    faces = []
    for line in lines:
        line = line.strip()
        if line.startswith('vertex'):
            coords = list(map(float, line[6:].split()))
            vertices.append(coords)
        elif line.startswith('normal'):
            coords = list(map(float, line[6:].split()))
            normals.append(coords)
        elif line.startswith('endloop'):
            faces.append(tuple(range(len(vertices) - 3, len(vertices))))
        elif line.startswith('solid') or line.startswith('endsolid'):
            continue
        else:
            raise ValueError('Invalid line in STL file: {}'.format(line))
    return vertices, normals, faces


def parse_binary_stl(data):
    vertices = []
    normals = []
    faces = []
    for i in range(0, len(data), 50):
        normal = struct.unpack_from('3f', data, i)
        vertices.extend(struct.unpack_from('3f3f', data, i + 12))
        faces.append(tuple(range(len(vertices) - 3, len(vertices))))
    return vertices[::3], normals, faces