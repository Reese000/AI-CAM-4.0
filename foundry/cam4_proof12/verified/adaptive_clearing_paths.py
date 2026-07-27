from typing import List, Tuple
import math


def adaptive_clearing_paths(stock: dict, tool: dict) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    
    # Get the bounding box of the stock
    stock_bbox = stock["bbox"]
    # Get the diameter of the tool
    tool_diameter = tool["diameter"]
    # Get the stepover of the tool
    tool_stepover = tool["stepover"]
    
    # Compute the initial and final points for the toolpath
    initial_point = (stock_bbox[0][0] + tool_diameter/2, stock_bbox[0][1] + tool_diameter/2, stock_bbox[1][2])
    final_point = (stock_bbox[1][0] - tool_diameter/2, stock_bbox[1][1] - tool_diameter/2, stock_bbox[1][2])
    
    # Compute the step size for the toolpath
    step_size = (final_point[0] - initial_point[0]) / tool_stepover
    
    # Initialize the list of toolpaths
    toolpaths = []
    
    # Generate the toolpaths
    for i in range(math.ceil(tool_stepover)):
        toolpath_start = (initial_point[0] + i*step_size, initial_point[1], initial_point[2])
        toolpath_end = (final_point[0] - i*step_size, final_point[1], final_point[2])
        toolpaths.append((toolpath_start, toolpath_end))
        
    return toolpaths


# Test the function
stock = {"bbox": ((0,0,0), (100,100,20)), "model": "cylinder"}
tool = {"diameter": 10.0, "stepover": 5.0}
print(adaptive_clearing_paths(stock, tool))

stock = {"bbox": ((0,0,0), (50,50,10)), "model": "box"}
tool = {"diameter": 12.0, "stepover": 6.0}
print(adaptive_clearing_paths(stock, tool))