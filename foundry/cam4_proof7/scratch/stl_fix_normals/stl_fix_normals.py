def stl_fix_normals(vertices, faces):
    from math import sqrt

    def vec3_sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def vec3_cross(a, b):
        return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])

    def vec3_length(v):
        return sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])

    new_normals = []
    for face in faces:
        v1 = vertices[face[0]]
        v2 = vertices[face[1]]
        v3 = vertices[face[2]]
        
        edge1 = vec3_sub(v2, v1)
        edge2 = vec3_sub(v3, v1)
        
        normal = vec3_cross(edge1, edge2)
        
        # Normalize the normal
        length = vec3_length(normal)
        normal = (normal[0]/length, normal[1]/length, normal[2]/length)
        
        new_normals.append(normal)
        
    return new_normals