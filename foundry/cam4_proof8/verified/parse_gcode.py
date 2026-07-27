def parse_gcode(text) -> list[dict]:
    commands = text.strip().split("\n")
    parsed_commands = []

    for command in commands:
        parts = command.split(" ")
        action = parts[0]

        if action == "G0":
            parsed = {"type": "rapid"}
            for part in parts[1:]:
                coord, value = part[0], float(part[1:])
                parsed[coord.lower()] = value
            parsed_commands.append(parsed)

        elif action == "G1":
            parsed = {"type": "linear"}
            for part in parts[1:]:
                coord_or_feed, value = part[0], float(part[1:])
                if coord_or_feed == "F":
                    parsed["feed"] = value
                else:
                    parsed[coord_or_feed.lower()] = value
            parsed_commands.append(parsed)

        elif action == "M2":
            parsed_commands.append({"type": "end"})

    return parsed_commands