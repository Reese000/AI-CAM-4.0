from typing import List, Tuple
from math import sqrt

def vec3_length(v: Tuple[float, float, float]) -> float:
    return sqrt(v[0]**2 + v[1]**2 + v[2]**2)

def toolpath_to_ir(toolpath: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> List[dict]:
    intermediate_representation = []
    feed = 100.0  # constant feed rate for now
    for segment in toolpath:
        from_point, to_point = segment
        move_type = "move"  # for now, assume all moves are linear
        distance = vec3_length((to_point[0] - from_point[0], to_point[1] - from_point[1], to_point[2] - from_point[2]))
        # assuming feed is constant for simplicity, we can add dynamic feed rate calculation in future if needed
        move_metadata = {"type": move_type, "from": from_point, "to": to_point, "feed": feed}
        intermediate_representation.append(move_metadata)
    return intermediate_representation