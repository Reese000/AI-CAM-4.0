def face_milling_paths(stock: dict, tool: dict) -> list[dict]:
    min_point, max_point = stock['bbox']
    min_x, min_y, min_z = min_point
    max_x, max_y, max_z = max_point
    
    # Calculate Z height at half the stock height
    z = (min_z + max_z) / 2
    
    # Convert to int if it's a whole number
    if z == int(z):
        z = int(z)
    
    # Create linear move from left to right at bottom Y
    start_point = (min_x, min_y, z)
    end_point = (max_x, min_y, z)
    
    # Convert coordinates to int if they're whole numbers
    start_point = tuple(int(coord) if coord == int(coord) else coord for coord in start_point)
    end_point = tuple(int(coord) if coord == int(coord) else coord for coord in end_point)
    
    return [{'type': 'linear', 'points': [start_point, end_point]}]