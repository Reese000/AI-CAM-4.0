def bbox_from_points(arg1, arg2=None):
    if isinstance(arg1, tuple) and len(arg1) == 3 and isinstance(arg2, tuple) and len(arg2) == 3:
        points = [arg1, arg2]
    else:
        points = arg1

    if not points:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    min_z = min(p[2] for p in points)
    max_x = max(p[0] for p in points)
    max_y = max(p[1] for p in points)
    max_z = max(p[2] for p in points)
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))