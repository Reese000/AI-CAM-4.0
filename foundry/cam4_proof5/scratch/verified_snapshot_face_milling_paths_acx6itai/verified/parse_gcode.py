def parse_gcode(text: str) -> list[dict]:
    commands = text.split('\n')
    parsed_commands = []

    for command in commands:
        parts = command.strip().split(' ')
        cmd_dict = {}

        if parts[0] == 'G0':
            cmd_dict['type'] = 'rapid'
        elif parts[0] == 'G1':
            cmd_dict['type'] = 'linear'
        elif parts[0] == 'M2':
            cmd_dict['type'] = 'end'
            parsed_commands.append(cmd_dict)
            continue

        for part in parts[1:]:
            param = part[0].lower()
            value = float(part[1:])

            if param in ['x', 'y', 'z', 'a', 'b', 'c']:
                cmd_dict[param] = value
            elif param == 'f':
                cmd_dict['feed'] = value

        parsed_commands.append(cmd_dict)

    return parsed_commands