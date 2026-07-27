def bbox_contains(bbox: tuple[tuple[float, float, float], tuple[float, float, float]], point: tuple[float, float, float]) -> bool:
    min_x, min_y, min_z = bbox[0]
    max_x, max_y, max_z = bbox[1]
    px, py, pz = point
    return min_x <= px <= max_x and min_y <= py <= max_y and min_z <= pz <= max_z