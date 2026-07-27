def render_fanuc(ir_segments):
    result = []
    for segment in ir_segments:
        line = segment['cmd']
        for key, value in segment.items():
            if key != 'cmd':
                line += ' ' + key.upper() + str(value)
        result.append(line)
    return '\n'.join(result)