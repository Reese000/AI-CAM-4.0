def parse_gcode(text: str) -> list[dict]:
    result = []
    line_num = 1
    for line in text.split('\n'):
        if not line or line.startswith(';'):
            line_num += 1
            continue
        cmd, *args = line.strip().split(' ')
        args_dict = {}
        for arg in args:
            key = arg[0]
            value = float(arg[1:])
            args_dict[key] = value
        result.append({'line': line_num, 'cmd': cmd, 'args': args_dict})
        line_num += 1
    return result