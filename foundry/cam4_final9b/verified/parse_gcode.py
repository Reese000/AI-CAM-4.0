def parse_gcode(text: str) -> list[dict]:
    lines = text.split("\n")
    commands = []
    for i, line in enumerate(lines, 1):
        cmd_dict = {'line': i, 'cmd': None, 'args': {}}
        if line.startswith(';') or not line.strip():
            continue
        parts = line.split(' ')
        cmd_dict['cmd'] = parts[0]
        for part in parts[1:]:
            arg, val = part[0], float(part[1:])
            cmd_dict['args'][arg] = val
        commands.append(cmd_dict)
    return commands