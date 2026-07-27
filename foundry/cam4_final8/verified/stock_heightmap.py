def stock_heightmap(stock_dims: tuple[float, float, float], resolution: float) -> dict:
    width, height, height_value = int(stock_dims[0]/resolution), int(stock_dims[1]/resolution), stock_dims[2]
    zmap = [[height_value]*width for _ in range(height)]
    return {'width': width, 'height': height, 'zmap': zmap}