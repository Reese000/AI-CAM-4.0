def render_fanuc(ir_segments) -> str:
    if not ir_segments:
        return ""
    
    lines = []
    # Start with rapid move to first segment's start point
    start = ir_segments[0]['from']
    lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f}")
    
    for seg in ir_segments:
        to_point = seg['to']
        feed = seg['feed']
        lines.append(f"G1 X{to_point[0]:.3f} Y{to_point[1]:.3f} Z{to_point[2]:.3f} F{feed:.3f}")
    
    return "\n".join(lines)