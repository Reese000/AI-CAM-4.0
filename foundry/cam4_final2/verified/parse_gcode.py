def parse_gcode(text: str) -> list[dict]:
    commands = text.strip().split('\n')
    parsed_commands = []
    for command in commands:
        parts = command.split()
        command_dict = {}
        for part in parts:
            param, value = part[0], float(part[1:])
            if param.upper() == 'G':
                command_dict['code'] = 'G'
                command_dict['number'] = int(value)
            else:
                command_dict[param] = value
        parsed_commands.append(command_dict)
    return parsed_commands