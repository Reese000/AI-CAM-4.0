def render_heidenhain(ir_segments: list[dict]) -> str:
    result = ''
    for segment in ir_segments:
        if segment['cmd'] == 'G1':
            result += 'L X+{x} Y+{y}'.format(x=segment['x'], y=segment['y'])
        elif segment['cmd'] == 'G2':
            result += 'C X+{x} Y+{y} I+{i} J+{j}'.format(x=segment['x'], y=segment['y'], i=segment['i'], j=segment['j'])
        result += '\n'
    return result.strip()