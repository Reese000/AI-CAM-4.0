def stock_heightmap(stock_dims: tuple[float, float, float], resolution: float) -> dict:
    width = int(stock_dims[0] / resolution)
    height = int(stock_dims[1] / resolution)
    zmap = [[stock_dims[2]] * width for _ in range(height)]
    return {'width': width, 'height': height, 'zmap': zmap}