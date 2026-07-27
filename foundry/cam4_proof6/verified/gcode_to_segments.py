def gcode_to_segments(commands):
    segments = []
    current_position = (0.0, 0.0, 0.0)

    for command in commands:
        if command["type"] == "rapid" or command["type"] == "linear":
            start_point = current_position
            end_point = (command.get("x", current_position[0]),
                         command.get("y", current_position[1]),
                         command.get("z", current_position[2]))
            feed = command.get("feed", None)

            if start_point != end_point and feed is not None:
                segments.append((start_point, end_point, feed))

            current_position = end_point

    return segments