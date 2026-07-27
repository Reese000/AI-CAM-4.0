def face_milling_paths(stock, tool):
    stock_bbox = stock['bbox']
    tool_radius = tool['diameter'] / 2
    start_point = (stock_bbox[0][0], stock_bbox[0][1], stock_bbox[1][2])
    end_point = (stock_bbox[1][0], stock_bbox[1][1], stock_bbox[1][2])
    path = [start_point, end_point]
    while start_point[0] < end_point[0]:
        start_point = (start_point[0] + tool_radius * 2, start_point[1], start_point[2])
        end_point = (end_point[0] - tool_radius * 2, end_point[1], end_point[2])
        if start_point[0] < end_point[0]:
            path.append(start_point)
            path.append(end_point)
    return [(path[i], path[i+1]) for i in range(0, len(path) - 1, 2)]

def bbox_from_points(points):
    min_coords = [min(coords) for coords in zip(*points)]
    max_coords = [max(coords) for coords in zip(*points)]
    return tuple(min_coords), tuple(max_coords)