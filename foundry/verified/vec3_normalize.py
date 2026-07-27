def vec3_normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
    return (v[0] / length, v[1] / length, v[2] / length)