def bbox_from_points(points):
    min_point = tuple(min(axis) for axis in zip(*points))
    max_point = tuple(max(axis) for axis in zip(*points))
    return min_point, max_point

def vec3_add(a, b):
    return a[0]+b[0], a[1]+b[1], a[2]+b[2]