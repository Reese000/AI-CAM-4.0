def toolpath_to_ir(toolpath: list[dict]) -> list[dict]:
    from math import sqrt

    def vec3_length(v: tuple[float, float, float]) -> float:
        return sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    def vec3_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

    def vec3_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

    def linear_to_ir(segment: dict) -> dict:
        end = segment['points'][-1]
        return {'cmd': 'G1', 'x': end[0], 'y': end[1], 'z': end[2]}

    def arc_to_ir(segment: dict) -> dict:
        start = segment['start']
        end = segment['end']
        center = segment['center']
        mid = vec3_scale(vec3_add(start, end), 0.5)
        if vec3_length(vec3_sub(mid, center)) > 1e-6:
            raise ValueError("Arc is not centered at the midpoint of start and end")
        return {'cmd': 'G2', 'x': end[0], 'y': end[1], 'i': center[0], 'j': center[1]}

    def vec3_scale(v: tuple[float, float, float], s: float) -> tuple[float, float, float]:
        return (v[0]*s, v[1]*s, v[2]*s)

    ir = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            ir.append(linear_to_ir(segment))
        elif segment['type'] == 'arc':
            ir.append(arc_to_ir(segment))
        else:
            raise ValueError(f"Unknown segment type: {segment['type']}")
    return ir