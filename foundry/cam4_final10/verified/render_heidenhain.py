def render_heidenhain(ir_segments):
    result = []
    for segment in ir_segments:
        if segment['cmd'] == 'G1':
            line = 'L'
        elif segment['cmd'] == 'G2':
            line = 'C'
        else:
            raise ValueError(f'Unknown command: {segment["cmd"]}')
        line += ' X+' if segment.get('x', 0) >= 0 else ' X-'
        line += f'{abs(segment.get("x", 0))}'
        line += ' Y+' if segment.get('y', 0) >= 0 else ' Y-'
        line += f'{abs(segment.get("y", 0))}'
        if 'i' in segment:
            line += ' I+' if segment['i'] >= 0 else ' I-'
            line += f'{abs(segment.get("i", 0))}'
        if 'j' in segment:
            line += ' J+' if segment['j'] >= 0 else ' J-'
            line += f'{abs(segment.get("j", 0))}'
        result.append(line)
    return '\n'.join(result)