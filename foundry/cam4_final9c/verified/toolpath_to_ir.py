def vec3_length(v: tuple[float, float, float]) -> float:
    return (v[0]**2 + v[1]**2 + v[2]**2)**0.5

def toolpath_to_ir(toolpath: list[dict]) -> list[dict]:
    intermediate_representation = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            pt1, pt2 = segment['points'][0], segment['points'][1]
            ir_segment = {'cmd': 'G1', 'x': pt2[0], 'y': pt2[1], 'z': pt2[2]}
        elif segment['type'] == 'arc':
            center, start, end = segment['center'], segment['start'], segment['end']
            ir_segment = {'cmd': 'G2', 'x': end[0], 'y': end[1], 'i': center[0], 'j': center[1]}
        intermediate_representation.append(ir_segment)
    return intermediate_representation