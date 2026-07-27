def face_milling_paths(stock: dict, tool: dict) -> list[dict]:
    tool_radius = tool['diameter'] / 2
    stock_min, stock_max = stock['bbox']
    stock_center = tuple((a + b) / 2 for a, b in zip(stock_min, stock_max))
    z_height = stock_max[2] - tool_radius
    path = {
        'type': 'linear',
        'points': [(stock_min[0], stock_min[1], z_height), (stock_max[0], stock_min[1], z_height)]
    }
    return [path]