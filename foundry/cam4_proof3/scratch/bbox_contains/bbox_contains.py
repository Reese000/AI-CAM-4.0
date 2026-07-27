def bbox_contains(*args):
    if len(args) == 2:
        bbox, point = args
        min_corner, max_corner = bbox
    elif len(args) == 3:
        min_corner, max_corner, point = args
    else:
        raise ValueError("Invalid number of arguments")
    
    for i in range(3):
        if not (min_corner[i] <= point[i] <= max_corner[i]):
            return False
    return True