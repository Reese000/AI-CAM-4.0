def render_fanuc(ir_segments) -> str:
    lines = []
    if ir_segments:
        first_from = ir_segments[0]["from"]
        lines.append(f"G0 X{first_from[0]:.3f} Y{first_from[1]:.3f} Z{first_from[2]:.3f}")
        for seg in ir_segments:
            to_point = seg["to"]
            feed = seg["feed"]
            lines.append(f"G1 X{to_point[0]:.3f} Y{to_point[1]:.3f} Z{to_point[2]:.3f} F{feed:.3f}")
    return "\n".join(lines)