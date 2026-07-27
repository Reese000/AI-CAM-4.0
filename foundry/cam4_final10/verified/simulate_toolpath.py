from typing import List, Dict, Tuple

def simulate_toolpath(stock: Dict[str, int], toolpath: List[Dict[str, int]]) -> List[Dict[str, int]]:
    # Initialize simulation frames list
    frames = []

    # Get the zmap from the stock
    zmap = stock.get('zmap', [])

    # Iterate over each dict in toolpath
    for dict in toolpath:
        # Get the x, y, z coordinates and radius from the dict
        x, y, z = dict.get('x', 0), dict.get('y', 0), dict.get('z', 0)
        radius = dict.get('radius', 0)

        # Iterate over each point in the zmap
        for i in range(len(zmap)):
            for j in range(len(zmap[i])):
                # Check if the point is within the toolpath
                if vec3_length((x - i, y - j, z)) <= radius:
                    # If so, reduce the z value by the toolpath's z value
                    zmap[i][j] = max(0, zmap[i][j] - z)

        # Append the current zmap to the frames
        frames.append({'width': stock['width'], 'height': stock['height'], 'zmap': zmap})

    # Return the simulation frames
    return frames