def toolpath_to_ir(toolpath) -> list[dict]:
    result = []
    for segment in toolpath:
        start, end = segment
        feed = 100.0
        result.append({
            "type": "move",
            "from": start,
            "to": end,
            "feed": feed
        })
    return result