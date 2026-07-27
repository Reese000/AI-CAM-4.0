def stl_fix_normals(vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> list[tuple[float, float, float]]:
    """
    Fix inverted normals in STL mesh by ensuring consistent outward orientation

    :param vertices: list of vertices coordinates
    :param faces: list of faces indices
    :return: list of fixed normals
    """
    import numpy as np

    # Calculate the normal of each face
    face_normals = []
    for face in faces:
        v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        normal = np.cross(np.subtract(v2, v1), np.subtract(v3, v1))
        face_normals.append(normal)

    # Check if the normal of each face is pointing outward or inward
    # Assuming all faces have the same orientation, we just need to check the first face
    if np.dot(face_normals[0], np.subtract(v2, v1)) < 0:
        # If the first face normal is pointing inward, invert all face normals
        face_normals = [-normal for normal in face_normals]

    # Return the fixed normals
    return face_normals