def vec3_normalize(v: tuple) -> tuple:
    mag = (v[0]**2 + v[1]**2 + v[2]**2)**0.5
    return (v[0]/mag, v[1]/mag, v[2]/mag)