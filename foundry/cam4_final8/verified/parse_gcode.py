def parse_gcode(text: str) -> list[dict]:
    lines = text.split('\n')
    commands = []
    for i, line in enumerate(lines, start=1):
        if not line.startswith(';'):
            parts = line.split(' ')
            cmd = parts[0]
            args = {}
            for part in parts[1:]:
                arg, val = part[0], part[1:]
                args[arg] = float(val)
            commands.append({'line': i, 'cmd': cmd, 'args': args})
    return commands