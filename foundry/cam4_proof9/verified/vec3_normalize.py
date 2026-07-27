def vec3_length(v):
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5


def vec3_normalize(v):
    length = vec3_length(v)
    
    if length == 0:
        return v
    else:
        return (v[0]/length, v[1]/length, v[2]/length)