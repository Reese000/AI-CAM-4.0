import math

def toolpath_to_ir(toolpath: list[dict]) -> list[dict]:
    result = []
    for segment in toolpath:
        if segment['type'] == 'linear':
            points = segment['points']
            start = points[0]
            end = points[1]
            result.append({
                'cmd': 'G1',
                'x': float(end[0]),
                'y': float(end[1]),
                'z': float(end[2])
            })
        elif segment['type'] == 'arc':
            center = segment['center']
            start = segment['start']
            end = segment['end']
            
            # Calculate direction using cross product in XY plane
            vec_start = (start[0] - center[0], start[1] - center[1])
            vec_end = (end[0] - center[0], end[1] - center[1])
            cross = vec_start[0] * vec_end[1] - vec_start[1] * vec_end[0]
            
            if cross > 0:
                cmd = 'G3'
            else:
                cmd = 'G2'
            
            i = float(center[0] - start[0])
            j = float(center[1] - start[1])
            
            result.append({
                'cmd': cmd,
                'x': float(end[0]),
                'y': float(end[1]),
                'i': i,
                'j': j
            })
    return result