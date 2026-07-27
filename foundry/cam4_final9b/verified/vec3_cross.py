def vec3_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])

# Test cases
print(vec3_cross((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
print(vec3_cross((2.0, 3.0, 4.0), (5.0, 6.0, 7.0)))