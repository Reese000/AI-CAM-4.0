def pocketing_paths(stock, tool):
    pockets = stock.get('pockets', [])
    tool_diameter = tool.get('diameter', 0)
    stepover = tool.get('stepover', 0)
    tool_radius = tool_diameter / 2.0
    
    all_segments = []
    
    for pocket in pockets:
        p1, p2 = pocket
        
        min_x = min(p1[0], p2[0])
        max_x = max(p1[0], p2[0])
        min_y = min(p1[1], p2[1])
        max_y = max(p1[1], p2[1])
        top_z = max(p1[2], p2[2])
        
        if max_x - min_x <= tool_diameter or max_y - min_y <= tool_diameter:
            continue
            
        left = min_x + tool_radius
        right = max_x - tool_radius
        bottom = min_y + tool_radius
        top = max_y - tool_radius
        
        if left >= right or bottom >= top:
            continue
            
        current_y = bottom
        direction = 1
        
        while current_y <= top:
            if direction == 1:
                start = (left, current_y, top_z)
                end = (right, current_y, top_z)
            else:
                start = (right, current_y, top_z)
                end = (left, current_y, top_z)
                
            all_segments.append((start, end))
            current_y += stepover
            direction *= -1
            
    return all_segments