def gcode_to_segments(commands):
    segments = []
    last_position = None
    for cmd in commands:
        if cmd["type"] in ["rapid", "linear"]:
            current_position = (cmd.get("x", 0), cmd.get("y", 0), cmd.get("z", 0))
            feed_rate = cmd.get("feed", None)
            if last_position is not None and feed_rate is not None:
                segments.append((last_position, current_position, feed_rate))
            last_position = current_position
    return segments