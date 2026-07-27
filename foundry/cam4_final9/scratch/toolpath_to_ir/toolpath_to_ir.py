def toolpath_to_ir(toolpath: list[dict]) -> list[dict]:
    from math import sqrt
    
    def vec3_length(v: tuple[float, float, float]) -> float:
        return sqrt(v[0]**2 + v[1]**2 + v[2]**2)

    ir = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            p1, p2 = segment['points'][0], segment['points'][1]
            ir.append({'cmd': 'G1', 'x': p2[0], 'y': p2[1], 'z': p2[2]})
        elif segment['type'] == 'arc':
            center, start, end = segment['center'], segment['start'], segment['end']
            ir.append({'cmd': 'G2', 'x': end[0], 'y': end[1], 'i': center[0] - start[0], 'j': center[1] - start[1]})

    return ir