def bbox_from_points(points):
    min_x = min(points, key=lambda p: p[0])[0]
    min_y = min(points, key=lambda p: p[1])[1]
    min_z = min(points, key=lambda p: p[2])[2]
    max_x = max(points, key=lambda p: p[0])[0]
    max_y = max(points, key=lambda p: p[1])[1]
    max_z = max(points, key=lambda p: p[2])[2]
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))