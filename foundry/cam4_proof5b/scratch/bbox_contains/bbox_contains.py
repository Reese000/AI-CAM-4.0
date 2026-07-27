def bbox_contains(min_point, max_point, point):
    return all(min_point[i] <= point[i] <= max_point[i] for i in range(3))