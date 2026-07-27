def parse_gcode(text: str) -> list[dict]:
    commands = text.split('\n')
    parsed_commands = []

    for command in commands:
        parts = command.split(' ')
        type_or_axis = parts[0].lower()

        if type_or_axis == 'g0':
            cmd = {"type": "rapid"}
        elif type_or_axis == 'g1':
            cmd = {"type": "linear"}
        elif type_or_axis == 'm2':
            parsed_commands.append({"type": "end"})
            continue
        else:
            continue

        for part in parts[1:]:
            axis = part[0].lower()
            value = float(part[1:])

            if axis in ('x', 'y', 'z'):
                cmd[axis] = value
            elif axis == 'f':
                cmd['feed'] = value

        parsed_commands.append(cmd)

    return parsed_commands