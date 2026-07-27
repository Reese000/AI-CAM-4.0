def stl_fix_normals(vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> list[tuple[float, float, float]]:
    """
    Fix inverted normals in STL mesh by ensuring consistent outward orientation
    """
    # Compute normal of each face
    face_normals = [(vertices[face[1]][0] - vertices[face[0]][0], vertices[face[1]][1] - vertices[face[0]][1], vertices[face[1]][2] - vertices[face[0]][2]) for face in faces]

    # Compute dot product of each face normal with the vector from the first vertex of the first face to the second
    dot_products = [face_normal[0] * (vertices[faces[0][1]][0] - vertices[faces[0][0]][0]) + face_normal[1] * (vertices[faces[0][1]][1] - vertices[faces[0][0]][1]) + face_normal[2] * (vertices[faces[0][1]][2] - vertices[faces[0][0]][2]) for face_normal in face_normals]

    # If the dot product is negative, invert the face normal
    corrected_face_normals = [(face_normal[0] * (1 if dot_product > 0 else -1), face_normal[1] * (1 if dot_product > 0 else -1), face_normal[2] * (1 if dot_product > 0 else -1)) for face_normal, dot_product in zip(face_normals, dot_products)]

    return corrected_face_normals