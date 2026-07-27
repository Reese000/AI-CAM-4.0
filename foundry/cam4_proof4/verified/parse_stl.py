def parse_stl(path):
    import struct
    with open(path, 'rb') as file:
        data = file.read()
    is_binary = data[:5].decode() != 'solid'
    if is_binary:
        count = struct.unpack('@I', data[80:84])[0]
        faces = []
        vertices = []
        normals = []
        for i in range(84, len(data), 50):
            normals.append(struct.unpack('@3f', data[i:i+12]))
            vertices.append(struct.unpack('@3f', data[i+12:i+24]))
            vertices.append(struct.unpack('@3f', data[i+24:i+36]))
            vertices.append(struct.unpack('@3f', data[i+36:i+48]))
            faces.append((3*(i//50), 3*(i//50)+1, 3*(i//50)+2))
        return vertices, normals, faces
    else:
        lines = data.decode().split('\n')
        vertices = []
        faces = []
        normals = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('vertex'):
                vertices.append(tuple(map(float, line[6:].split())))
            elif line.startswith('endfacet'):
                faces.append(tuple(range(len(vertices)-3, len(vertices))))
            elif line.startswith('normal'):
                normals.append(tuple(map(float, line[6:].split())))
            i += 1
        return vertices, normals, faces