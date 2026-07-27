def toolpath_to_ir(toolpath) -> list[dict]:
    result = []
    for segment in toolpath:
        start, end = segment
        move = {
            "type": "move",
            "from": start,
            "to": end,
            "feed": 100.0
        }
        result.append(move)
    return result