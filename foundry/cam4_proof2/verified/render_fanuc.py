def render_fanuc(ir_segments):
    lines = []
    for i, segment in enumerate(ir_segments):
        if i == 0:
            # First segment: rapid move to start point, then linear move to end point
            start_x, start_y, start_z = segment["from"]
            end_x, end_y, end_z = segment["to"]
            feed = segment["feed"]
            lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f} Z{start_z:.3f}")
            lines.append(f"G1 X{end_x:.3f} Y{end_y:.3f} Z{end_z:.3f} F{feed:.3f}")
        else:
            # Subsequent segments: linear move to end point only
            end_x, end_y, end_z = segment["to"]
            feed = segment["feed"]
            lines.append(f"G1 X{end_x:.3f} Y{end_y:.3f} Z{end_z:.3f} F{feed:.3f}")
    return "\n".join(lines)