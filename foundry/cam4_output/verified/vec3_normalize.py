def vec3_length(v: tuple[float,float,float]) -> float:
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

def vec3_normalize(v: tuple[float,float,float]) -> tuple[float,float,float]:
    length = vec3_length(v)
    return (v[0]/length, v[1]/length, v[2]/length)