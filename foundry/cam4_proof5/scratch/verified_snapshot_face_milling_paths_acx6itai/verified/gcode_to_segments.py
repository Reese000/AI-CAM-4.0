def gcode_to_segments(commands):
    segments = []
    current_position = (0.0, 0.0, 0.0)
    feed = 0.0

    for command in commands:
        if command["type"] == "rapid":
            current_position = (command.get("x", current_position[0]), 
                                command.get("y", current_position[1]), 
                                command.get("z", current_position[2]))
        elif command["type"] == "linear":
            new_position = (command.get("x", current_position[0]), 
                            command.get("y", current_position[1]), 
                            command.get("z", current_position[2]))
            feed = command.get("feed", feed)
            segments.append((current_position, new_position, feed))
            current_position = new_position

    return segments