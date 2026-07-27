def bbox_from_points(point1: list[float], point2: list[float]) -> tuple[list[float], list[float]]:
    min_point = [min(point1[i], point2[i]) for i in range(3)]
    max_point = [max(point1[i], point2[i]) for i in range(3)]
    return min_point, max_point