def vec3_normalize(v):
    x, y, z = v
    magnitude = (x*x + y*y + z*z)**0.5
    if magnitude == 0:
        return (0.0, 0.0, 0.0)
    return (x/magnitude, y/magnitude, z/magnitude)