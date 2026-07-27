def stl_fix_normals(vertices, faces):
    def vec3_sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def vec3_cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def vec3_length(v):
        return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5

    new_normals = []
    for face in faces:
        v1 = vertices[face[1]]
        v2 = vertices[face[2]]
        v3 = vertices[face[0]]

        cross = vec3_cross(vec3_sub(v2, v1), vec3_sub(v3, v1))
        length = vec3_length(cross)

        if length == 0:
            normal = (0.0, 0.0, 0.0)
        else:
            normal = (cross[0] / length, cross[1] / length, cross[2] / length)
        new_normals.append(normal)

    return new_normals