from typing import List, Tuple

def parse_gcode(text: str) -> List[Tuple[str, dict]]:
    lines = text.split('\n')
    commands = []
    for line in lines:
        split_line = line.split(' ')
        cmd = split_line[0]
        args = {}
        for arg in split_line[1:]:
            key = arg[0]
            val = float(arg[1:])
            args[key] = val
        commands.append((cmd, args))
    return commands