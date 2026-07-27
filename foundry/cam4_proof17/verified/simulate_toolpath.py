def simulate_toolpath(stock, toolpath):
    """
    Simulate material removal along toolpath, returning heightmap frames for animation.
    
    Args:
        stock: 2D heightmap (list of lists of floats) from stock_heightmap
        toolpath: list of segments, each segment is ((x1,y1,z1), (x2,y2,z2))
    
    Returns:
        List of heightmap frames (each frame is list of lists of floats)
    """
    # Create working copy of stock
    current = [row[:] for row in stock]
    frames = []
    
    for segment in toolpath:
        (x1, y1, z1), (x2, y2, z2) = segment
        
        # Calculate bounding box of segment
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)
        
        # Get grid dimensions
        rows = len(current)
        cols = len(current[0]) if rows > 0 else 0
        
        # Process cells that might be affected
        # Convert to integer indices (assuming coordinates map to grid indices)
        i_start = max(0, int(x_min))
        i_end = min(rows - 1, int(x_max))
        j_start = max(0, int(y_min))
        j_end = min(cols - 1, int(y_max))
        
        # For each cell in the affected region
        for i in range(i_start, i_end + 1):
            for j in range(j_start, j_end + 1):
                # Check if line segment passes through this cell
                # Using simple point-in-segment test with tolerance
                # Project point (i,j) onto line segment
                dx = x2 - x1
                dy = y2 - y1
                length_sq = dx * dx + dy * dy
                
                if length_sq < 1e-10:  # Segment is essentially a point
                    # Check if point is within cell
                    if abs(i - x1) < 0.5 and abs(j - y1) < 0.5:
                        z = z1
                else:
                    # Parameter t for projection
                    t = max(0, min(1, ((i - x1) * dx + (j - y1) * dy) / length_sq))
                    # Closest point on segment
                    x_proj = x1 + t * dx
                    y_proj = y1 + t * dy
                    z = z1 + t * (z2 - z1)
                    
                    # Check if projected point is within cell
                    if abs(i - x_proj) < 0.5 and abs(j - y_proj) < 0.5:
                        # Remove material if tool is lower than current height
                        if z < current[i][j]:
                            current[i][j] = z
        
        # Save frame after each segment
        frames.append([row[:] for row in current])
    
    return frames