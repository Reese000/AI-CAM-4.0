def parse_stl(path):
    with open(path, "rb") as file:
        data = file.read()

    is_binary = data[:5] != b'solid'

    if is_binary:
        faces = len(data) // 50
        vertices = []
        normals = []
        indices = []

        for face in range(faces):
            offset = face * 50
            normal = data[offset:offset+3]
            vertices.extend([data[offset+3+i*3:offset+3+(i+1)*3] for i in range(3)])
            indices.append((face*3, face*3+1, face*3+2))
            normals.extend([normal]*3)

    else:
        lines = data.decode().split('\n')
        vertices = []
        normals = []
        indices = []

        for line in lines:
            if 'vertex' in line:
                vertices.append(tuple(map(float, line.split()[1:])))
            elif 'facet normal' in line:
                normals.append(tuple(map(float, line.split()[2:])))

        indices = [(i, i+1, i+2) for i in range(0, len(vertices), 3)]

    return vertices, normals, indices