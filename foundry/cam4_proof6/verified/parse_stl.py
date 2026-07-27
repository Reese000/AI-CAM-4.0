import struct

def parse_stl(path):
    with open(path, 'rb') as f:
        data = bytearray(f.read())

    # Detect if the STL is binary or ASCII
    if data[80:83].decode() == 'fac':
        # Read the STL as a binary STL
        num_triangles = struct.unpack('@I', data[84:88])[0]
        triangles = []
        vertices = []
        normals = []
        for i in range(num_triangles):
            offset = 84 + (i * 50)
            triangles.append(struct.unpack('@3f', data[offset:offset+12]))
            offset += 12
            vertices.append(struct.unpack('@3f', data[offset:offset+12]))
            offset += 12
            normal = struct.unpack('@3f', data[offset:offset+12])
            normals.append(normal)
        return vertices, normals, triangles
    else:
        # Read the STL as an ASCII STL
        lines = data.decode().split('\n')
        triangles = []
        vertices = []
        normals = []
        for line in lines:
            line = line.strip()
            if line.startswith('vertex'):
                vertices.append(tuple(map(float, line[6:].split())))
            elif line.startswith('normal'):
                normals.append(tuple(map(float, line[6:].split())))
            elif line.startswith('facet normal'):
                triangles.append((len(vertices)-3, len(vertices)-2, len(vertices)-1))
        return vertices, normals, triangles