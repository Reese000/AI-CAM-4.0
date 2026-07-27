def parse_gcode(text: str) -> list[dict]:
    result = []
    lines = text.split('\n')
    for i, line in enumerate(lines, start=1):
        if not line or line.startswith(';'):
            continue
        parts = line.split(' ')
        cmd = parts[0]
        args = {}
        for part in parts[1:]:
            key, value = part[0], part[1:]
            args[key] = float(value)
        result.append({'line': i, 'cmd': cmd, 'args': args})
    return result