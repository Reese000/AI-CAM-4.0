def parse_gcode(text) -> list[dict]:
    commands = text.strip().split('\n')
    result = []
    for command in commands:
        parts = command.strip().split(' ')
        cmd_type = parts[0].lower()
        if cmd_type == 'g0' or cmd_type == 'g1':
            cmd = {"type": "rapid" if cmd_type == 'g0' else "linear"}
            for p in parts[1:]:
                coord_type = p[0].lower()
                if coord_type in ['x', 'y', 'z']:
                    cmd[coord_type] = float(p[1:])
                elif coord_type == 'f':
                    cmd['feed'] = float(p[1:])
            result.append(cmd)
        elif cmd_type == 'm2':
            result.append({"type": "end"})
    return result