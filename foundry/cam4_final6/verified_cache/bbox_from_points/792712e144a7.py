def bbox_from_points(points):
    min_point = points[0]
    max_point = points[0]
    for point in points:
        min_point = vec3_add(min_point, point, min)
        max_point = vec3_add(max_point, point, max)
    return min_point, max_point

def vec3_add(a, b, op):
    return tuple(op(x, y) for x, y in zip(a, b))