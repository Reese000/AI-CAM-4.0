def stl_fix_normals(vertices, faces):
    import math

    def vec3_sub(a, b):
        return a[0] - b[0], a[1] - b[1], a[2] - b[2]

    def vec3_cross(a, b):
        return a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]

    def vec3_length(v):
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    fixed_normals = []
    for face in faces:
        v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        # calculate the cross product of two edges in the face
        cross = vec3_cross(vec3_sub(v2, v1), vec3_sub(v3, v1))
        # normalize the cross product
        norm = vec3_length(cross)
        fixed_normals.append((cross[0]/norm, cross[1]/norm, cross[2]/norm))

    return fixed_normals