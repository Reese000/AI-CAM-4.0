def render_fanuc(ir_segments):
    if not ir_segments:
        return ""
    
    lines = []
    first_segment = ir_segments[0]
    start_point = first_segment["from"]
    lines.append(f"G0 X{start_point[0]:.3f} Y{start_point[1]:.3f} Z{start_point[2]:.3f}")
    
    for segment in ir_segments:
        to_point = segment["to"]
        feed = segment["feed"]
        lines.append(f"G1 X{to_point[0]:.3f} Y{to_point[1]:.3f} Z{to_point[2]:.3f} F{feed:.3f}")
    
    return "\n".join(lines)