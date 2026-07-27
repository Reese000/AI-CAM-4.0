def render_heidenhain(ir_segments) -> str:
    def format_number(n):
        if n == int(n):
            return str(int(n))
        else:
            return str(n)
    
    lines = []
    lines.append("0 BEGIN PGM 1 MM")
    lines.append("1 TOOL CALL 1 Z S1000")
    
    if ir_segments:
        start_point = ir_segments[0]["from"]
        lines.append(f"2 L Z+{format_number(start_point[2])} R0 FMAX")
        lines.append(f"3 L X+{format_number(start_point[0])} Y+{format_number(start_point[1])} Z+{format_number(start_point[2])} R0 FMAX")
        
        for i, segment in enumerate(ir_segments):
            line_num = 4 + i
            to_point = segment["to"]
            feed = segment["feed"]
            lines.append(f"{line_num} L X+{format_number(to_point[0])} Y+{format_number(to_point[1])} Z+{format_number(to_point[2])} R0 F{format_number(feed)}")
    
    lines.append(f"{4 + len(ir_segments)} END PGM 1 MM")
    return "\n".join(lines)