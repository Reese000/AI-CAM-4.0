def bbox_from_points(*args):
    if len(args) == 1:
        points = args[0]
    else:
        points = args
    
    if not points:
        return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    
    min_point = points[0]
    max_point = points[0]
    
    for point in points[1:]:
        if point[0] < min_point[0]:
            min_point = (point[0], min_point[1], min_point[2])
        if point[1] < min_point[1]:
            min_point = (min_point[0], point[1], min_point[2])
        if point[2] < min_point[2]:
            min_point = (min_point[0], min_point[1], point[2])
        
        if point[0] > max_point[0]:
            max_point = (point[0], max_point[1], max_point[2])
        if point[1] > max_point[1]:
            max_point = (max_point[0], point[1], max_point[2])
        if point[2] > max_point[2]:
            max_point = (max_point[0], max_point[1], point[2])
    
    return (min_point, max_point)