def parse_gcode(text):
    commands = text.split('\n')
    result = []

    for command in commands:
        parts = command.split(' ')
        cmd_dict = {}

        for part in parts:
            if part[0].upper() == 'G':
                if part == 'G0':
                    cmd_dict['type'] = 'rapid'
                elif part == 'G1':
                    cmd_dict['type'] = 'linear'
            elif part[0].upper() == 'X':
                cmd_dict['x'] = float(part[1:])
            elif part[0].upper() == 'Y':
                cmd_dict['y'] = float(part[1:])
            elif part[0].upper() == 'Z':
                cmd_dict['z'] = float(part[1:])
            elif part[0].upper() == 'F':
                cmd_dict['feed'] = float(part[1:])
            elif part[0].upper() == 'M' and int(part[1:]) == 2:
                cmd_dict['type'] = 'end'

        result.append(cmd_dict)

    return result