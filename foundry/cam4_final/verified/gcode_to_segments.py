from typing import List, Tuple, Dict


def gcode_to_segments(commands: List[Tuple[str, Dict[str, float]]]) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float], str]]:
    current_pos = (0, 0, 0)
    segments = []
    for command in commands:
        if command[0] == 'G0':
            # Rapid move, ignore for now
            continue
        elif command[0] == 'G1':
            # Linear move
            new_pos = tuple(command[1].get(axis, current_pos[i]) for i, axis in enumerate('XYZ'))
            segments.append((current_pos, new_pos, 'linear'))
            current_pos = new_pos
        else:
            # Unsupported command, ignore for now
            continue
    return segments