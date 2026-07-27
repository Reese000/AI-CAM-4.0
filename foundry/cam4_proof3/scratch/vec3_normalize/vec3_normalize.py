def vec3_length(v):
    x, y, z = v
    return (x**2 + y**2 + z**2)**0.5

def vec3_normalize(v):
    length = vec3_length(v)
    if length == 0:
        return (0.0, 0.0, 0.0)
    else:
        x, y, z = v
        return (x/length, y/length, z/length)