def parse_gcode(text: str) -> list[dict[str, float]]:
    commands = text.split('\n')
    parsed = []
    for command in commands:
        parts = command.split(' ')
        code = int(parts[0][1:])
        params = {}
        for part in parts[1:]:
            key = part[0]
            value = float(part[1:])
            params[key] = value
        parsed.append({'code': code, 'params': params})
    return parsed