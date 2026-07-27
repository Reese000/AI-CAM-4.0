def bbox_from_points(points):
    if not points:
        raise ValueError("The list of points must not be empty")
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    for x, y, z in points:
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)
        min_z, max_z = min(min_z, z), max(max_z, z)
    return (min_x, min_y, min_z), (max_x, max_y, max_z)


def vec3_add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]