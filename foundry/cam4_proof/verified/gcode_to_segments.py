def gcode_to_segments(commands) -> list[tuple[tuple[float, float, float], tuple[float, float, float], float]]:
    segments = []
    current_position = (0.0, 0.0, 0.0)
    for command in commands:
        if command["type"] == "rapid" or command["type"] == "linear":
            next_position = (command.get("x", current_position[0]), command.get("y", current_position[1]), command.get("z", current_position[2]))
            feed_rate = command.get("feed", None)
            if feed_rate is not None:
                segments.append((current_position, next_position, feed_rate))
            current_position = next_position
    return segments