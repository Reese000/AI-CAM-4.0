def stl_fix_normals(vertices, faces):
    new_normals = []
    for face in faces:
        v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        normal = vec3_cross(vec3_sub(v2, v1), vec3_sub(v3, v1))
        normal_length = vec3_length(normal)
        new_normals.append((normal[0] / normal_length, normal[1] / normal_length, normal[2] / normal_length))
    return new_normals

# Assume the following functions are already defined

def vec3_sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]

def vec3_cross(a, b):
    return a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]

def vec3_length(v):
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5