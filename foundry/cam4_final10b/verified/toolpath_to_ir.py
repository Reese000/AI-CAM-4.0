def toolpath_to_ir(toolpath: list[dict]) -> list[dict]:
    def vec3_length(v: tuple[float, float, float]) -> float:
        return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

    ir = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            pt1, pt2 = segment['points']
            ir.append({'cmd': 'G1', 'x': pt2[0], 'y': pt2[1], 'z': pt2[2]})
        elif segment['type'] == 'arc':
            center, start, end = segment['center'], segment['start'], segment['end']
            ir.append({'cmd': 'G2', 'x': end[0], 'y': end[1], 'i': center[0] - start[0], 'j': center[1] - start[1]})
        else:
            raise ValueError("Unsupported segment type")

    return ir