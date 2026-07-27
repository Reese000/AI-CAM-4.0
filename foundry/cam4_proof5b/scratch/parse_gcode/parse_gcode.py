def parse_gcode(text):
    commands = text.split("\n")
    parsed_commands = []

    for command in commands:
        args = command.split(" ")
        type_of_command = args[0]
        command_dict = {}

        if type_of_command == "G0":
            command_dict["type"] = "rapid"
        elif type_of_command == "G1":
            command_dict["type"] = "linear"
        elif type_of_command == "M2":
            command_dict["type"] = "end"
            parsed_commands.append(command_dict)
            continue

        for arg in args[1:]:
            param = arg[0]
            value = float(arg[1:])

            if param == "X":
                command_dict["x"] = value
            elif param == "Y":
                command_dict["y"] = value
            elif param == "Z":
                command_dict["z"] = value
            elif param == "F":
                command_dict["feed"] = value

        parsed_commands.append(command_dict)

    return parsed_commands