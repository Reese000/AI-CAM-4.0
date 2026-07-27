def bbox_from_points(points):
    min_point = tuple(min(axis) for axis in zip(*points))
    max_point = tuple(max(axis) for axis in zip(*points))
    return min_point, max_point

def vec3_add(a, b):
    return tuple(a_i + b_i for a_i, b_i in zip(a, b))