def render_fanuc(ir_segments: list[dict]) -> str:
    result = []
    for segment in ir_segments:
        cmd = segment['cmd']
        args_str = ' '.join([f'{key.upper()}{value}' for key, value in segment.items() if key != 'cmd'])
        result.append(f'{cmd} {args_str}')
    return '\n'.join(result)