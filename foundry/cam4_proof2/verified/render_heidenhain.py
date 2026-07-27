def render_heidenhain(ir_segments) -> str:
    def format_axis(axis, value):
        if value >= 0:
            return f"{axis}+{value:g}"
        else:
            return f"{axis}-{abs(value):g}"

    lines = ["0 BEGIN PGM 1 MM", "1 TOOL CALL 1 Z S1000"]
    
    if not ir_segments:
        lines.append("2 END PGM 1 MM")
        return "\n".join(lines)

    start = ir_segments[0]['from']
    lines.append(f"2 L {format_axis('Z', start[2])} R0 FMAX")
    lines.append(f"3 L {format_axis('X', start[0])} {format_axis('Y', start[1])} {format_axis('Z', start[2])} R0 FMAX")

    line_num = 4
    for seg in ir_segments:
        to = seg['to']
        feed = seg['feed']
        line = f"{line_num} L {format_axis('X', to[0])} {format_axis('Y', to[1])} {format_axis('Z', to[2])} R0 F{feed:g}"
        lines.append(line)
        line_num += 1

    lines.append(f"{line_num} END PGM 1 MM")
    return "\n".join(lines)