def render_fanuc(ir_segments: list[dict]) -> str:
    gcode = ''
    for segment in ir_segments:
        gcode += segment['cmd']
        for key in segment:
            if key != 'cmd':
                gcode += ' ' + key.upper() + str(segment[key])
        gcode += '\n'
    return gcode.strip()