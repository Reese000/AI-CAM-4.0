def face_milling_paths(stock: dict, tool: dict) -> list[dict]:
    # Get stock bounds
    bbox = stock.get('bbox', ((0,0,0), (100,100,10)))
    min_x, min_y, min_z = bbox[0]
    max_x, max_y, max_z = bbox[1]
    
    # Calculate center Z position for toolpath
    z_height = (min_z + max_z) / 2.0
    
    # Create single linear pass from left to right at bottom Y
    return [{'type': 'linear', 'points': [(min_x, min_y, z_height), (max_x, min_y, z_height)]}]