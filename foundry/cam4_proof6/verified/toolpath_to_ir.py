from typing import List, Tuple

def toolpath_to_ir(toolpath: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> List[dict]:
    result = []
    for i in range(len(toolpath)):
        move_type = 'move' # All moves in this context are considered as linear moves
        feed = 100.0 # Arbitrary feed value, can be modified as per requirement
        result.append({
            "type": move_type,
            "from": toolpath[i][0],
            "to": toolpath[i][1],
            "feed": feed
        })
    return result

def vec3_length(v: Tuple[float, float, float]) -> float:
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5