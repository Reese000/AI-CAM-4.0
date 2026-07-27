def parse_gcode(text: str) -> list[dict]:
    result = []
    for line in text.split('\n'):
        cmd_parts = line.split()
        cmd = {}
        for part in cmd_parts:
            cmd['cmd'] = cmd_parts[0]
            if part[0] in ['X', 'Y', 'Z', 'A', 'B', 'I', 'J', 'R']:
                cmd[part[0]] = float(part[1:])
        result.append(cmd)
    return result