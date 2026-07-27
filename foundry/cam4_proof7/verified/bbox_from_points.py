def bbox_from_points(points):
    return ((min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points)), 
            (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points)))