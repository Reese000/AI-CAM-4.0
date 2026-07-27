def gcode_to_segments(commands):
    segments = []
    last_point = None
    for command in commands:
        if command['type'] in ('rapid', 'linear'):
            current_point = (command.get('x', 0.0), command.get('y', 0.0), command.get('z', 0.0))
            if last_point is not None:
                segments.append((last_point, current_point, command.get('feed', None)))
            last_point = current_point
    return segments

print(gcode_to_segments([{"type": "rapid", "x": 0.0, "y": 0.0, "z": 5.0}, {"type": "linear", "x": 10.0, "y": 0.0, "z": 0.0, "feed": 50.0}]))
print(gcode_to_segments([{"type": "rapid", "x": 0.0, "y": 0.0, "z": 5.0}]))