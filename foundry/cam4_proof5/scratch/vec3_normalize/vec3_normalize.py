def vec3_normalize(v):
    length = vec3_length(v)
    if length == 0:
        return v
    return tuple(i/length for i in v)

def vec3_length(v):
    return sum(i**2 for i in v)**0.5