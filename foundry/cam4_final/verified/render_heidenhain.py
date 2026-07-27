from typing import List, Tuple
import math

def vec3_length(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

def render_heidenhain(ir_segments: List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]]) -> str:
    out_lines = []
    for i, seg in enumerate(ir_segments):
        action, start, end = seg
        out_line = f'{i} G00 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f}\n{i+1} '
        if action == 'linear':
            out_line += 'G01 '
        elif action == 'arc':
            out_line += 'G02 '
        elif action == 'clockwise_arc':
            out_line += 'G03 '
        else:
            raise ValueError(f"unknown action '{action}'")
        out_line += f'X{end[0]:.3f} Y{end[1]:.3f} Z{end[2]:.3f}'
        out_lines.append(out_line)
    return '\n'.join(out_lines)