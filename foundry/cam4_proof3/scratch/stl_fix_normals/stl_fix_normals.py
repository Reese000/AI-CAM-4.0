def stl_fix_normals(vertices, faces):
    def vec3_sub(a, b):
        return a[0] - b[0], a[1] - b[1], a[2] - b[2]

    def vec3_cross(a, b):
        return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]

    def vec3_length(v):
        return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5

    new_faces = []
    for face in faces:
        v1, v2, v3 = [vertices[i] for i in face]
        side1 = vec3_sub(v2, v1)
        side2 = vec3_sub(v3, v1)
        normal = vec3_cross(side1, side2)
        normal_length = vec3_length(normal)
        # Ensure the normal is normalized (has a length of 1)
        normal = tuple(component / normal_length for component in normal)
        new_faces.append(normal)

    return new_faces