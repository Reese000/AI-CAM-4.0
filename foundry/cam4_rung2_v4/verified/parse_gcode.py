def parse_gcode(text: str) -> list:
    commands = text.split('\n')
    result = []
    for command in commands:
        parts = command.strip().split(' ')
        command_parts = {}
        command_parts['type'] = parts[0]
        for part in parts[1:]:
            command_parts[part[0]] = float(part[1:])
        result.append(command_parts)
    return result