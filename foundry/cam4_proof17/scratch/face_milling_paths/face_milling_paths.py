import math
from typing import List, Tuple

def face_milling_paths(stock: dict, tool: dict) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    # Extract stock bounding box
    bbox = stock["bbox"]
    (x_min, y_min, z_min), (x_max, y_max, z_max) = bbox
    
    # Extract tool diameter
    diameter = tool["diameter"]
    radius = diameter / 2.0
    
    # Cutting height is at stock top (z_max)
    cutting_height = z_max
    
    # Generate zigzag pattern along X direction, stepping in Y
    paths = []
    
    # Calculate number of passes in Y direction
    # Tool should step over by diameter to cover area without gaps
    y_steps = math.ceil((y_max - y_min) / diameter)
    
    for i in range(y_steps):
        current_y = y_min + i * diameter
        
        # Ensure we don't exceed stock bounds
        if current_y > y_max:
            break
        
        # Alternate direction for zigzag
        if i % 2 == 0:
            # Move from left to right
            start_point = (x_min, current_y, cutting_height)
            end_point = (x_max, current_y, cutting_height)
        else:
            # Move from right to left
            start_point = (x_max, current_y, cutting_height)
            end_point = (x_min, current_y, cutting_height)
        
        paths.append((start_point, end_point))
    
    return paths