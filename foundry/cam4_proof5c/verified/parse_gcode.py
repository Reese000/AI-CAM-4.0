def parse_gcode(text: str) -> list[dict]:
    commands = text.split("\n")
    result = []
    for command in commands:
        parts = command.split(" ")
        cmd_type = parts[0]
        args = parts[1:]
        cmd = {"type": "unknown"}
        if cmd_type == "G0":
            cmd["type"] = "rapid"
        elif cmd_type == "G1":
            cmd["type"] = "linear"
        elif cmd_type == "M2":
            cmd["type"] = "end"
            result.append(cmd)
            break
        else:
            result.append(cmd)
            continue
        for arg in args:
            arg_type = arg[0]
            arg_val = float(arg[1:])
            if arg_type == "X":
                cmd["x"] = arg_val
            elif arg_type == "Y":
                cmd["y"] = arg_val
            elif arg_type == "Z":
                cmd["z"] = arg_val
            elif arg_type == "F":
                cmd["feed"] = arg_val
        result.append(cmd)
    return result