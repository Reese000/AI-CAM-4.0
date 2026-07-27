def parse_gcode(text: str) -> list[dict]:
    commands = text.split('\n')
    result = []
    for i, cmd in enumerate(commands, 1):
        parts = cmd.split()
        if parts[0].startswith(';'):
            continue
        command = {'line': i, 'cmd': parts[0]}
        args = {}
        for part in parts[1:]:
            key, value = part[0], part[1:]
            args[key] = float(value)
        command['args'] = args
        result.append(command)
    return result