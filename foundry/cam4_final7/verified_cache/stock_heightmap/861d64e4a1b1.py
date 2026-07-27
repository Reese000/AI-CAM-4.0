def stock_heightmap(stock_dims: tuple[float, float, float], resolution: int) -> list[list[float]]:
    return [[stock_dims[2]] * resolution for _ in range(resolution)]