def parse_gcode(text: str) -> list[dict]:
    if not text:
        return []
    
    lines = text.split('\n')
    result = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        command = {}
        tokens = line.split()
        
        for token in tokens:
            if len(token) < 2:
                continue
            
            key = token[0]
            value_str = token[1:]
            
            try:
                value = int(value_str)
            except ValueError:
                try:
                    value = float(value_str)
                except ValueError:
                    continue
            
            command[key] = value
        
        if command:
            result.append(command)
    
    return result