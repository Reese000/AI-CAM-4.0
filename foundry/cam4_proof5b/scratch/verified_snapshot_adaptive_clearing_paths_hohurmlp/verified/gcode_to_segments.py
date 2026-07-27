def gcode_to_segments(commands):
    segments = []
    start_point = None

    for command in commands:
        if command["type"] in ("rapid", "linear"):
            end_point = (command["x"], command["y"], command["z"])
            feed_rate = command.get("feed", None)

            if start_point is not None and feed_rate is not None:
                segments.append((start_point, end_point, feed_rate))

            start_point = end_point

    return segments