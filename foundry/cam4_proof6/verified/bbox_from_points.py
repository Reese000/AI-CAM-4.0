def bbox_from_points(*args):
    if len(args) == 1:
        points = args[0]
    elif len(args) == 2:
        points = [args[0], args[1]]
    else:
        raise ValueError("Invalid number of arguments")
    
    if not points:
        raise ValueError("No points provided")
    
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    for point in points:
        x, y, z = point
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        min_z = min(min_z, z)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        max_z = max(max_z, z)
    
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))