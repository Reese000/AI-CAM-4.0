def toolpath_to_ir(toolpath):
    import math
    def vec3_length(v):
        return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    ir = []
    feed = 100.0

    for segment in toolpath:
        from_point = segment[0]
        to_point = segment[1]
        move_type = "move" if vec3_length(tuple(b - a for a, b in zip(from_point, to_point))) > 0 else "rapid"
        ir.append({"type": move_type, "from": from_point, "to": to_point, "feed": feed})

    return ir