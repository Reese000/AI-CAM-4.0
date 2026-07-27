def render_heidenhain(ir_segments) -> str:
    lines = []
    lines.append("0 BEGIN PGM 1 MM")
    lines.append("1 TOOL CALL 1 Z S1000")
    
    # Initial rapid moves to starting position
    start_from = ir_segments[0]["from"]
    x, y, z = start_from
    lines.append(f"2 L Z{z:+.0f} R0 FMAX")
    lines.append(f"3 L X{x:+.0f} Y{y:+.0f} Z{z:+.0f} R0 FMAX")
    
    # Process each segment
    line_num = 4
    for segment in ir_segments:
        to_x, to_y, to_z = segment["to"]
        feed = segment["feed"]
        lines.append(f"{line_num} L X{to_x:+.0f} Y{to_y:+.0f} Z{to_z:+.0f} R0 F{feed:.0f}")
        line_num += 1
    
    lines.append(f"{line_num} END PGM 1 MM")
    
    return "\n".join(lines)