def stl_fix_normals(vertices, faces):
    def vec3_sub(a, b):
        return a[0] - b[0], a[1] - b[1], a[2] - b[2]

    def vec3_cross(a, b):
        return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]

    def vec3_length(v):
        return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5

    new_normals = []
    for face in faces:
        v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        
        # Compute face normal using cross product
        n = vec3_cross(vec3_sub(v2, v1), vec3_sub(v3, v1))
        
        # Normalize the normal
        n_length = vec3_length(n)
        n = n[0] / n_length, n[1] / n_length, n[2] / n_length
        
        new_normals.append(n)
    return new_normals

# Test the function with mock data
mock_inverted_faces = [(0, 1, 2), (3, 4, 5), (6, 7, 8)]
mock_inverted_vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0), (1.0, 1.0, 0.0), (1.0, 1.0, 1.0), (0.0, 0.0, -1.0)]

print(stl_fix_normals(mock_inverted_vertices, mock_inverted_faces))