def bbox_from_points(*points):
    if len(points) == 1 and isinstance(points[0], list):
        points = points[0]
    
    if not points:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    
    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    min_z = min(p[2] for p in points)
    
    max_x = max(p[0] for p in points)
    max_y = max(p[1] for p in points)
    max_z = max(p[2] for p in points)
    
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))