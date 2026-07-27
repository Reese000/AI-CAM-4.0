def parse_gcode(text: str) -> list[dict]:
    commands = text.split('\n')
    parsed_commands = []
    for command in commands:
        parts = command.split(' ')
        cmd_type = parts[0]
        if cmd_type in ('G0', 'G1'):
            parsed = {'type': 'linear' if cmd_type == 'G1' else 'rapid'}
            for part in parts[1:]:
                coord_type, value = part[0].lower(), float(part[1:])
                parsed[coord_type] = value
            if 'f' in parsed:
                parsed['feed'] = parsed.pop('f')
            parsed_commands.append(parsed)
        elif cmd_type == 'M2':
            parsed_commands.append({'type': 'end'})
    return parsed_commands