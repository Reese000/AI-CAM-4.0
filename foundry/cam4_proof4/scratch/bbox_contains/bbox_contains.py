def bbox_contains(min_corner, max_corner, point):
    for i in range(len(point)):
        if point[i] < min_corner[i] or point[i] > max_corner[i]:
            return False
    return True