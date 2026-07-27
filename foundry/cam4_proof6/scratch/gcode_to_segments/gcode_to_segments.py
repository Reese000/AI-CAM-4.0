def gcode_to_segments(commands):
    segments = []
    for command in commands:
        if command["type"] == "linear":
            start = (previous_x, previous_y, previous_z) if "previous_x" in locals() else (command["x"], command["y"], command["z"])
            end = (command["x"], command["y"], command["z"])
            feed = command["feed"]
            segments.append((start, end, feed))
        previous_x, previous_y, previous_z = command["x"], command["y"], command["z"]
    return segments