def gcode_to_segments(commands):
    segments = []
    for cmd in commands:
        if cmd['cmd'] == 'G1':
            start = (0,0,0) if not segments else segments[-1]['end']
            end = (cmd['args']['X'], cmd['args']['Y'], 0)
            segments.append({'type': 'linear', 'start': start, 'end': end})
        elif cmd['cmd'] == 'G2':
            start = (0,0,0) if not segments else segments[-1]['end']
            center = (cmd['args']['I'], cmd['args']['J'], 0)
            end = (cmd['args']['X'], cmd['args']['Y'], 0)
            segments.append({'type': 'arc', 'center': center, 'start': start, 'end': end})
    return segments

# Test cases
print(gcode_to_segments([{'cmd': 'G1', 'args': {'X': 10.0, 'Y': 0.0}}]))
print(gcode_to_segments([{'cmd': 'G2', 'args': {'X': 5.0, 'Y': 5.0, 'I': 2.5, 'J': 0.0}}]))
print(gcode_to_segments([{'cmd': 'G1', 'args': {'X': 10.0, 'Y': 0.0}}, {'cmd': 'G2', 'args': {'X': 5.0, 'Y': 5.0, 'I': 2.5, 'J': 0.0}}]))