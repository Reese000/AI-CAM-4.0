from typing import List, Dict, Tuple
import math

def vec3_length(v: Tuple[float, float, float]) -> float:
    x, y, z = v
    return math.sqrt(x**2 + y**2 + z**2)

def toolpath_to_ir(toolpath: List[Dict]) -> List[Dict]:
    ir = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            pt1, pt2 = segment['points'][0], segment['points'][1]
            ir.append({'cmd': 'G1', 'x': pt2[0], 'y': pt2[1], 'z': pt2[2]})
        elif segment['type'] == 'arc':
            center, start, end = segment['center'], segment['start'], segment['end']
            ir.append({'cmd': 'G2', 'x': end[0], 'y': end[1], 'i': center[0]-start[0], 'j': center[1]-start[1]})
    return ir