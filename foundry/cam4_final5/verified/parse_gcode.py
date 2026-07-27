def parse_gcode(text: str) -> list[dict]:
    lines = text.split('\n')
    commands = []

    for line in lines:
        cmd_dict = {}
        params = line.split(' ')
        cmd_dict['cmd'] = params[0]

        for param in params[1:]:
            cmd_dict[param[0]] = float(param[1:])

        commands.append(cmd_dict)

    return commands