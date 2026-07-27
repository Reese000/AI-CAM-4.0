def stl_fix_normals(vertices, faces):
    def vec3_sub(a, b):
        return a[0] - b[0], a[1] - b[1], a[2] - b[2]

    def vec3_cross(a, b):
        return a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]

    def vec3_length(v):
        return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

    new_faces = []
    for face in faces:
        v1 = vertices[face[0]]
        v2 = vertices[face[1]]
        v3 = vertices[face[2]]

        # Compute face normal
        edge1 = vec3_sub(v2, v1)
        edge2 = vec3_sub(v3, v1)
        face_normal = vec3_cross(edge1, edge2)

        # Normalize face normal
        length = vec3_length(face_normal)
        face_normal = (face_normal[0]/length, face_normal[1]/length, face_normal[2]/length)

        new_faces.append(face_normal)

    return new_faces