def bbox_contains(bbox1, bbox2, point):
    min_corner = tuple(min(a, b) for a, b in zip(bbox1, bbox2))
    max_corner = tuple(max(a, b) for a, b in zip(bbox1, bbox2))
    
    for i in range(3):
        if point[i] < min_corner[i] or point[i] > max_corner[i]:
            return False
    return True