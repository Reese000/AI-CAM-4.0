def render_fanuc(ir_segments) -> str:
    lines = []
    
    for i, segment in enumerate(ir_segments):
        from_x, from_y, from_z = segment['from']
        to_x, to_y, to_z = segment['to']
        feed = segment['feed']
        
        # First move uses G0 (rapid) to starting position
        if i == 0:
            lines.append(f"G0 X{from_x:.3f} Y{from_y:.3f} Z{from_z:.3f}")
        
        # All moves to target position use G1 (linear) with feed
        lines.append(f"G1 X{to_x:.3f} Y{to_y:.3f} Z{to_z:.3f} F{feed:.3f}")
    
    return "\n".join(lines)