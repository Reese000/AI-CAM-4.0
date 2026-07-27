def pocketing_paths(stock, tool):
    segments = []
    diameter = tool['diameter']
    stepover = tool['stepover']
    radius = diameter / 2.0
    
    for pocket in stock['pockets']:
        # Get pocket bounds
        p1, p2 = pocket
        # Get depth from pocket's Z coordinates
        min_z = min(p1[2], p2[2])
        max_z = max(p1[2], p2[2])
        
        # Compute effective bounds for tool center
        min_x = min(p1[0], p2[0]) + radius
        max_x = max(p1[0], p2[0]) - radius
        min_y = min(p1[1], p2[1]) + radius
        max_y = max(p1[1], p2[1]) - radius
        
        # Skip if pocket is too small for tool
        if min_x >= max_x or min_y >= max_y:
            continue
            
        # Use the maximum Z as cutting depth
        depth = max_z
        
        # Generate zigzag pattern
        current_y = min_y
        direction = 1  # 1 for left-to-right, -1 for right-to-left
        
        while current_y <= max_y:
            if direction == 1:
                start_x = min_x
                end_x = max_x
            else:
                start_x = max_x
                end_x = min_x
            
            segments.append(((start_x, current_y, depth), (end_x, current_y, depth)))
            current_y += stepover
            direction *= -1
            
    return segments