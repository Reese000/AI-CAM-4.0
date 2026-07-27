def render_heidenhain(ir_segments: list[dict]) -> str:
    lines = []
    for segment in ir_segments:
        cmd = segment['cmd']
        if cmd == 'G1':
            line = f"L X{segment['x']:+.1f} Y{segment['y']:+.1f}"
            lines.append(line)
        elif cmd == 'G2':
            line = f"C X{segment['x']:+.1f} Y{segment['y']:+.1f} I{segment['i']:+.1f} J{segment['j']:+.1f}"
            lines.append(line)
    return '\n'.join(lines)