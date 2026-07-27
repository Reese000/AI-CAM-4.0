def parse_gcode(text) -> list:
    lines = text.split('\n')
    commands = []
    for line in lines:
        parts = line.strip().split(' ')
        command = parts[0]
        params = {}
        for part in parts[1:]:
            param_name = part[0]
            param_value = float(part[1:])
            params[param_name] = param_value
        commands.append({'command': command, 'params': params})
    return commands