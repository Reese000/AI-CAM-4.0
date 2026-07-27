def parse_gcode(text):
    commands = []
    for line in text.split("\n"):
        parts = line.strip().split(" ")
        command = {}
        for part in parts:
            param = part[0]
            value = float(part[1:])
            if param == "G":
                type_code = int(value)
                if type_code == 0:
                    command["type"] = "rapid"
                elif type_code == 1:
                    command["type"] = "linear"
            elif param in "XYZ":
                command[param.lower()] = value
            elif param == "F":
                command["feed"] = value
            elif param == "M" and value == 2:
                command["type"] = "end"
        commands.append(command)
    return commands