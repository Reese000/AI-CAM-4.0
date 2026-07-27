def bbox_contains(min_point, max_point, point):
    return (min_point[0] <= point[0] <= max_point[0] and
            min_point[1] <= point[1] <= max_point[1] and
            min_point[2] <= point[2] <= max_point[2])