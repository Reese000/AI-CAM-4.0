def parse_gcode(text: str) -> list[dict[str, any]]:
    commands = text.split('\n')
    parsed_commands = []
    for command in commands:
        parts = command.split(' ')
        cmd_dict = {}
        for part in parts:
            key = part[0]
            value = int(part[1:]) if part[1:].isdigit() else part[1:]
            cmd_dict[key] = value
        parsed_commands.append(cmd_dict)
    return parsed_commands