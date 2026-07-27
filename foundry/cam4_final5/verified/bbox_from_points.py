def bbox_from_points(points, second=None):
    if second is None:
        pts = points
    else:
        pts = [points, second]
    min_x = min(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    min_z = min(p[2] for p in pts)
    max_x = max(p[0] for p in pts)
    max_y = max(p[1] for p in pts)
    max_z = max(p[2] for p in pts)
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))