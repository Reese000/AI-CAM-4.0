def bbox_from_points(points):
    # WRONG: returns identity instead of min/max bounds
    return (points[0], points[-1])
