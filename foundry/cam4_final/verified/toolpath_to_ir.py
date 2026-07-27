from typing import List, Tuple

def toolpath_to_ir(toolpath: List[Tuple[float, float, float]]) -> List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]]:
    intermediate_representation = []

    for i in range(1, len(toolpath)):
        intermediate_representation.append(('linear', toolpath[i - 1], toolpath[i]))

    return intermediate_representation