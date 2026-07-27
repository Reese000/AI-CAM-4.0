def vec3_normalize(v: list[float]) -> list[float]:
    length = (v[0]**2 + v[1]**2 + v[2]**2)**0.5
    if length == 0:
        return [0, 0, 0]
    else:
        return [x / length for x in v]