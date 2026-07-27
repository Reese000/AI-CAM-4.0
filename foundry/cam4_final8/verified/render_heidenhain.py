from typing import List, Dict, Tuple

def render_heidenhain(ir_segments: List[Dict]) -> str:
    def render_linear(segment: Dict) -> str:
        return f"L X+{segment['x']} Y+{segment['y']}"

    def render_arc(segment: Dict) -> str:
        return f"C X+{segment['x']} Y+{segment['y']} I+{segment['i']} J+{segment['j']}"

    renderers = {
        'G1': render_linear,
        'G2': render_arc,
    }

    return '\n'.join(renderers[segment['cmd']](segment) for segment in ir_segments)

def toolpath_to_ir(toolpath: List[Dict]) -> List[Dict]:
    def linear_to_ir(segment: Dict) -> Dict:
        start, end = segment['points']
        return {
            'cmd': 'G1',
            'x': end[0],
            'y': end[1],
            'z': end[2],
        }

    def arc_to_ir(segment: Dict) -> Dict:
        center, start, end = segment['center'], segment['start'], segment['end']
        return {
            'cmd': 'G2',
            'x': end[0],
            'y': end[1],
            'i': center[0] - start[0],
            'j': center[1] - start[1],
        }

    converters = {
        'linear': linear_to_ir,
        'arc': arc_to_ir,
    }

    return [converters[segment['type']](segment) for segment in toolpath]

def vec3_length(v: Tuple[float, float, float]) -> float:
    return sum(x**2 for x in v)**0.5