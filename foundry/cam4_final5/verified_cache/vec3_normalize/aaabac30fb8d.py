def vec3_length(v):
    x, y, z = v
    return (x * x + y * y + z * z) ** 0.5


def vec3_normalize(v):
    x, y, z = v
    length = vec3_length(v)
    return (x / length, y / length, z / length)