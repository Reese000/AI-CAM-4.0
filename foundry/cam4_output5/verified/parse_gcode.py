def parse_gcode(text: str) -> list[dict]:
    lines = text.split('\n')
    commands = []
    for line in lines:
        command = {}
        parts = line.split(' ')
        command['cmd'] = parts[0]
        for part in parts[1:]:
            param, value = part[0], part[1:]
            command[param] = float(value)
        commands.append(command)
    return commands