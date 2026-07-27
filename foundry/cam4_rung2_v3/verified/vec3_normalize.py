def vec3_length(v: tuple[float, float, float]) -> float:
    x, y, z = v
    return (x**2 + y**2 + z**2)**0.5

def vec3_normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = vec3_length(v)
    if length == 0:
        return v
    else:
        x, y, z = v
        return (x/length, y/length, z/length)