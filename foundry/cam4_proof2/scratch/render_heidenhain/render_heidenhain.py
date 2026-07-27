def render_heidenhain(ir_segments) -> str:
    lines = []
    lines.append("0 BEGIN PGM 1 MM")
    lines.append("1 TOOL CALL 1 Z S1000")
    
    if ir_segments:
        # Get starting point from first segment
        start = ir_segments[0]["from"]
        lines.append(f"2 L Z+{start[2]:g} R0 FMAX")
        lines.append(f"3 L X+{start[0]:g} Y+{start[1]:g} Z+{start[2]:g} R0 FMAX")
        
        # Process each segment
        for i, seg in enumerate(ir_segments):
            to_point = seg["to"]
            feed = seg["feed"]
            line_num = 4 + i
            lines.append(f"{line_num} L X+{to_point[0]:g} Y+{to_point[1]:g} Z+{to_point[2]:g} R0 F{feed:g}")
        
        end_num = 4 + len(ir_segments)
        lines.append(f"{end_num} END PGM 1 MM")
    else:
        lines.append("2 END PGM 1 MM")
    
    return "\n".join(lines)