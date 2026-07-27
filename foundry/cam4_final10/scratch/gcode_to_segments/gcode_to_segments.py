def gcode_to_segments(commands):
    segments = []
    for cmd in commands:
        if cmd['cmd'] == 'G1':
            segments.append({'type': 'linear', 'start': (0,0,0), 'end': (cmd['args']['X'], cmd['args']['Y'], 0)})
        elif cmd['cmd'] == 'G2':
            segments.append({'type': 'arc', 'center': (cmd['args']['I'], cmd['args']['J'], 0), 'start': (0,0,0), 'end': (cmd['args']['X'], cmd['args']['Y'], 0)})
    return segments