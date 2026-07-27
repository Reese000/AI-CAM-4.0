def render_heidenhain(ir_segments):
    if not ir_segments:
        return ""
    
    lines = []
    lines.append("0 BEGIN PGM 1 MM")
    lines.append("1 TOOL CALL 1 Z S1000")
    
    first_from = ir_segments[0]["from"]
    lines.append("2 L Z+{} R0 FMAX".format(int(first_from[2])))
    lines.append("3 L X+{} Y+{} Z+{} R0 FMAX".format(
        int(first_from[0]), int(first_from[1]), int(first_from[2])))
    
    line_num = 4
    for seg in ir_segments:
        to_point = seg["to"]
        feed = seg["feed"]
        
        # Format feed without decimal if it's integer
        feed_str = str(int(feed)) if feed == int(feed) else str(feed)
        
        lines.append("{} L X+{} Y+{} Z+{} R0 F{}".format(
            line_num, int(to_point[0]), int(to_point[1]), int(to_point[2]), feed_str))
        line_num += 1
    
    lines.append("{} END PGM 1 MM".format(line_num))
    
    return "\n".join(lines)