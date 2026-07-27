def render_fanuc(ir_segments) -> str:
    lines = []
    for i, seg in enumerate(ir_segments):
        if i == 0:
            x0, y0, z0 = seg["from"]
            lines.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{z0:.3f}")
        
        x1, y1, z1 = seg["to"]
        if seg["type"] == "rapid":
            lines.append(f"G0 X{x1:.3f} Y{y1:.3f} Z{z1:.3f}")
        else:
            feed = seg.get("feed", 100.0)
            lines.append(f"G1 X{x1:.3f} Y{y1:.3f} Z{z1:.3f} F{feed:.3f}")
    
    return "\n".join(lines)