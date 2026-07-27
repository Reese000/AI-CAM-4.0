def parse_gcode(text: str) -> list[dict[str, float]]:
    commands = []
    for line in text.split('\n'):
        parts = line.strip().split(' ')
        command = {'code': int(parts[0][1:]), 'params': {}}
        for part in parts[1:]:
            command['params'][part[0]] = float(part[1:])
        commands.append(command)
    return commands