from typing import List, Dict, Tuple

def render_heidenhain(ir_segments: List[Dict]) -> str:
    """
    Render intermediate representation to Heidenhain-style G-code

    Examples:
    [{'cmd': 'G1', 'x': 10.0, 'y': 0.0}] -> 'L X+10.0 Y+0.0'
    [{'cmd': 'G2', 'x': 5.0, 'y': 5.0, 'i': 2.5, 'j': 0.0}] -> 'C X+5.0 Y+5.0 I+2.5 J+0.0'

    :param ir_segments: list of intermediate representation segments
    :return: string representation of the Heidenhain-style G-code
    """
    result = []
    for segment in ir_segments:
        if segment['cmd'] == 'G1':
            result.append('L X+{} Y+{}'.format(segment['x'], segment['y']))
        elif segment['cmd'] == 'G2':
            result.append('C X+{} Y+{} I+{} J+{}'.format(segment['x'], segment['y'], segment['i'], segment['j']))
    return '\n'.join(result)