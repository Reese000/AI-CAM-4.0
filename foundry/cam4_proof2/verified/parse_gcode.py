def parse_gcode(text):
    def parse_command(cmd):
        cmd_type = cmd[:2]
        params = cmd[2:].split()
        command = {}

        if cmd_type in ("G0", "G1"):
            command["type"] = "rapid" if cmd_type == "G0" else "linear"
            for p in params:
                if 'X' in p:
                    command["x"] = float(p[1:])
                if 'Y' in p:
                    command["y"] = float(p[1:])
                if 'Z' in p:
                    command["z"] = float(p[1:])
                if 'F' in p:
                    command["feed"] = float(p[1:])
            return command

        elif cmd_type == "M2":
            command["type"] = "end"
            return command

    return [parse_command(cmd) for cmd in text.split("\n")]