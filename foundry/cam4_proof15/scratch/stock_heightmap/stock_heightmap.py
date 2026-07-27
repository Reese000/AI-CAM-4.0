def stock_heightmap(stock_dims, resolution):
    x_size, y_size, z_size = stock_dims
    return [[z_size]*resolution for _ in range(resolution)]