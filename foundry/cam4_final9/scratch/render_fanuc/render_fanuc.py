def render_fanuc(ir_segments: list[dict]) -> str:
    res = []
    for segment in ir_segments:
        cmd = segment['cmd']
        args = [f'{k.upper()}{v}' for k, v in segment.items() if k != 'cmd']
        res.append(f'{cmd} {" ".join(args)}')
    return '\n'.join(res)