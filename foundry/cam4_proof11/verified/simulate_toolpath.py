def simulate_toolpath(stock, toolpath):
    if not stock or not stock[0]:
        return []
    heightmap = [row[:] for row in stock[0]]
    rows = len(heightmap)
    cols = len(heightmap[0]) if rows > 0 else 0
    frames = []
    for segment in toolpath:
        if len(segment) == 2:
            start, end = segment
            z = float(min(start[2], end[2]))
        else:
            z = float(segment[2])
        frame = []
        for i in range(rows):
            row = []
            for j in range(cols):
                row.append(min(heightmap[i][j], z))
            frame.append(row)
        heightmap = frame
        frames.append(frame)
    return frames