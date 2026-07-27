from typing import Tuple
import math

def vec3_normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    return (v[0]/length, v[1]/length, v[2]/length)