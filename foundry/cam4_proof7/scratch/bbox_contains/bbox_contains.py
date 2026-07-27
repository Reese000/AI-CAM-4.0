def bbox_contains(*args):
    if len(args) == 2:
        bbox, point = args
        min_point, max_point = bbox
    elif len(args) == 3:
        min_point, max_point, point = args
    else:
        raise ValueError("Invalid number of arguments")
    
    for i in range(len(point)):
        if not (min_point[i] <= point[i] <= max_point[i]):
            return False
    return True