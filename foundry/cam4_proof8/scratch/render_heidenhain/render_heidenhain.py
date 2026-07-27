def render_heidenhain(ir_segments) -> str:
    def format_coord(val):
        if val == int(val):
            return f"+{int(val)}"
        else:
            return f"+{val:.1f}"
    
    def format_feed(feed):
        if feed == int(feed):
            return str(int(feed))
        else:
            return f"{feed:.1f}"
    
    lines = []
    lines.append("0 BEGIN PGM 1 MM")
    lines.append("1 TOOL CALL 1 Z S1000")
    
    if ir_segments:
        first_from = ir_segments[0]["from"]
        z_start = first_from[2]
        lines.append(f"2 L Z{format_coord(z_start)} R0 FMAX")
        lines.append(f"3 L X{format_coord(first_from[0])} Y{format_coord(first_from[1])} Z{format_coord(first_from[2])} R0 FMAX")
        
        line_num = 4
        for segment in ir_segments:
            to_point = segment["to"]
            feed = segment["feed"]
            line = f"{line_num} L X{format_coord(to_point[0])} Y{format_coord(to_point[1])} Z{format_coord(to_point[2])} R0 F{format_feed(feed)}"
            lines.append(line)
            line_num += 1
        
        lines.append(f"{line_num} END PGM 1 MM")
    
    return "\n".join(lines)