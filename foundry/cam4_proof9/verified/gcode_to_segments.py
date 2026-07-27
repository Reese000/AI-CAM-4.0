def gcode_to_segments(commands):
    segments = []
    current_position = (0,0,0)
    for command in commands:
        if command["type"] == "rapid":
            current_position = (command["x"], command["y"], command["z"])
        elif command["type"] == "linear":
            new_position = (command["x"], command["y"], command["z"])
            segments.append((current_position, new_position, command["feed"]))
            current_position = new_position
    return segments