from typing import List, Dict, Tuple

def vec3_length(v: Tuple[float, float, float]) -> float:
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

def toolpath_to_ir(toolpath: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> List[Dict]:
    result = []
    for segment in toolpath:
        start, end = segment
        direction = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        length = vec3_length(direction)
        feed = 100.0
        result.append({
            "type": "move",
            "from": start,
            "to": end,
            "feed": feed
        })
    return result