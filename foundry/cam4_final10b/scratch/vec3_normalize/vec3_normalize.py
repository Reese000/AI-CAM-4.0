def vec3_length(v: tuple[float, float, float]) -> float:
    x, y, z = v
    return (x * x + y * y + z * z) ** 0.5


def vec3_normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = vec3_length(v)
    if length == 0:
        return (0.0, 0.0, 0.0)
    else:
        x, y, z = v
        return (x / length, y / length, z / length)