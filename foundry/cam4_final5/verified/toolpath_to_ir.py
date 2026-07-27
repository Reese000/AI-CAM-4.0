def toolpath_to_ir(toolpath: list[tuple[float, float, float]]) -> list[dict]:
    intermediate_rep = []
    for i in range(len(toolpath)):
        if i == 0:
            intermediate_rep.append({'type': 'rapid', 'start': toolpath[i], 'end': toolpath[i]})
        else:
            intermediate_rep.append({'type': 'feed', 'start': toolpath[i-1], 'end': toolpath[i]})
    return intermediate_rep