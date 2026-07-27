def render_heidenhain(ir_segments: list[dict]) -> str:
    result = []
    for segment in ir_segments:
        if segment['cmd'] == 'G1':
            result.append('L X+{} Y+{}'.format(segment['x'], segment['y']))
        elif segment['cmd'] == 'G2':
            result.append('C X+{} Y+{} I+{} J+{}'.format(segment['x'], segment['y'], segment['i'], segment['j']))
    return '\n'.join(result)