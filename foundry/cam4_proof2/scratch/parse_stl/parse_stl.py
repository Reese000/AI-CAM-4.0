import struct

def parse_stl(path):
    with open(path, 'rb') as f:
        data = f.read()

    is_binary = False
    if len(data) % 50 == 84:  # binary stl files are multiples of 50 off 84
        is_binary = True

    vertices = []
    normals = []
    faces = []

    if is_binary:
        # Binary STL
        # Skip the header (80 bytes)
        data = data[84:]
        num_faces = struct.unpack('<I', data[:4])[0]
        data = data[4:]

        for i in range(num_faces):
            # Read the normal
            nx, ny, nz = struct.unpack('<fff', data[:12])
            normals.append((nx, ny, nz))

            # Read the vertices
            for j in range(3):
                vx, vy, vz = struct.unpack('<fff', data[12*j:12*(j+1)])
                vertices.append((vx, vy, vz))

            # Read the attribute byte count and ignore it
            data = data[48:]

        # Convert vertices and normals to lists of tuples
        vertices = [tuple(x) for x in vertices]
        normals = [tuple(x) for x in normals]

        # Generate face indices
        for i in range(0, len(vertices), 3):
            faces.append((i, i+1, i+2))
    else:
        # ASCII STL
        lines = data.decode().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('facet normal'):
                parts = line.split()
                nx, ny, nz = float(parts[2]), float(parts[3]), float(parts[4])
                normals.append((nx, ny, nz))
            elif line.startswith('vertex'):
                parts = line.split()
                vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                vertices.append((vx, vy, vz))
                if len(vertices) % 3 == 0:
                    faces.append((len(vertices)-3, len(vertices)-2, len(vertices)-1))

        vertices = [tuple(x) for x in vertices]
        normals = [tuple(x) for x in normals]

    return vertices, normals, faces