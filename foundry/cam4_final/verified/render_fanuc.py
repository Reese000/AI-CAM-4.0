from typing import List, Tuple
import math

def render_fanuc(ir_segments: List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]]) -> str:
    def vec3_length(v: Tuple[float, float, float]) -> float:
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    result = []
    for segment in ir_segments:
        command, start, end = segment
        if command == 'linear':
            result.append('G0 X{:.3f} Y{:.3f} Z{:.3f}'.format(start[0], start[1], start[2]))
            result.append('G1 X{:.3f} Y{:.3f} Z{:.3f}'.format(end[0], end[1], end[2]))
        else:
            raise ValueError(f'Unknown command: {command}')
    return '\n'.join(result)