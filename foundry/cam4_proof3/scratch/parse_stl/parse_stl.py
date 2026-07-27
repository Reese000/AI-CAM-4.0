import struct

def parse_stl(path: str) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    # First, try to read as an ASCII STL
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
            if 'solid' not in lines[0]:
                raise ValueError

            vertices = []
            faces = []
            face = []
            for line in lines:
                if 'vertex' in line:
                    coord = tuple(map(float, line.split()[1:]))
                    vertices.append(coord)
                    face.append(len(vertices) - 1)
                    if len(face) == 3:
                        faces.append(tuple(face))
                        face = []
            return vertices, [(0, 0, 1)] * len(faces), faces
    except:
        pass

    # If that fails, try to read as a binary STL
    with open(path, 'rb') as f:
        f.read(80)  # skip header
        num_triangles = struct.unpack('i', f.read(4))[0]
        vertices = []
        faces = []
        for i in range(num_triangles):
            normal = struct.unpack('fff', f.read(12))
            v1 = struct.unpack('fff', f.read(12))
            v2 = struct.unpack('fff', f.read(12))
            v3 = struct.unpack('fff', f.read(12))
            vertices.extend([v1, v2, v3])
            faces.append((3*i, 3*i+1, 3*i+2))
            f.read(2)  # skip attribute byte count
        return vertices, [normal] * len(faces), faces