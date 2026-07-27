def adaptive_clearing_paths(stock, tool):
    bbox = stock["bbox"]
    min_x, min_y, min_z = bbox[0]
    max_x, max_y, max_z = bbox[1]
    
    tool_radius = tool["diameter"] / 2.0
    stepover = tool["stepover"]
    
    start_y = min_y + tool_radius
    end_y = max_y - tool_radius
    
    paths = []
    current_y = start_y
    direction = 1  # 1 = positive x, -1 = negative x
    
    while current_y <= end_y:
        if direction == 1:
            start = (min_x + tool_radius, current_y, max_z)
            end = (max_x - tool_radius, current_y, max_z)
        else:
            start = (max_x - tool_radius, current_y, max_z)
            end = (min_x + tool_radius, current_y, max_z)
        
        paths.append((start, end))
        current_y += stepover
        direction *= -1
    
    return paths