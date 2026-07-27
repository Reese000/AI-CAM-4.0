def render_fanuc(ir_segments) -> str:
    lines = []
    for i, move in enumerate(ir_segments):
        from_x, from_y, from_z = move['from']
        to_x, to_y, to_z = move['to']
        feed = move['feed']
        
        # First move or position change requires rapid move to starting point
        if i == 0:
            lines.append(f"G0 X{from_x:.3f} Y{from_y:.3f} Z{from_z:.3f}")
        
        # Linear move to target point
        lines.append(f"G1 X{to_x:.3f} Y{to_y:.3f} Z{to_z:.3f} F{feed:.3f}")
    
    return "\n".join(lines)