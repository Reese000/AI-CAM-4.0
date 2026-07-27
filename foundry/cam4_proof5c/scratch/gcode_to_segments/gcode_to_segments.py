def gcode_to_segments(commands):
    segments = []
    current_point = (0, 0, 0)
    current_feed = 0

    for command in commands:
        if command["type"] in ["rapid", "linear"]:
            new_point = (command.get("x", current_point[0]), command.get("y", current_point[1]), command.get("z", current_point[2]))
            current_feed = command.get("feed", current_feed)

            if command["type"] == "linear":
                segments.append((current_point, new_point, current_feed))

            current_point = new_point

    return segments