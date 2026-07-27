def bbox_contains(bbox_or_min, bbox_or_max_or_point, point_if_given=None):
    if point_if_given is not None:
        min_corner = bbox_or_min
        max_corner = bbox_or_max_or_point
        point = point_if_given
    else:
        bbox = bbox_or_min
        point = bbox_or_max_or_point
        min_corner = bbox[0]
        max_corner = bbox[1]
    return all(min_corner[i] <= point[i] <= max_corner[i] for i in range(3))