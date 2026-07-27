from math import sqrt

def vec3_length(v):
    return sqrt(v[0]**2 + v[1]**2 + v[2]**2)

def toolpath_to_ir(toolpath):
    result = []
    feed = 100.0
    for segment in toolpath:
        from_point = segment[0]
        to_point = segment[1]
        length = vec3_length((to_point[0] - from_point[0], to_point[1] - from_point[1], to_point[2] - from_point[2]))
        result.append({"type": "move", "from": from_point, "to": to_point, "feed": feed})
    return result