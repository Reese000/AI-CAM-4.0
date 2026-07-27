def stock_heightmap(stock_dims, resolution):
    x_dim, y_dim, z_height = stock_dims
    rows = [ [z_height]*resolution for _ in range(resolution)]
    return rows