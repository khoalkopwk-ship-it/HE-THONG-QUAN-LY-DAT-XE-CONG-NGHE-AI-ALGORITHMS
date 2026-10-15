from __future__ import annotations

import math
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách chim bay giữa hai tọa độ WGS84, đơn vị km."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))



def interpolate_points(
    path: list[tuple[float, float]],
    steps_per_edge: int = 5,
) -> list[tuple[float, float]]:
    """Chia nhỏ đường node-edge thành các điểm nhỏ để marker trượt trên bản đồ."""
    if len(path) <= 1:
        return path[:]

    result: list[tuple[float, float]] = []
    steps = max(1, steps_per_edge)
    for start, end in zip(path, path[1:]):
        s_lat, s_lng = start
        e_lat, e_lng = end
        for i in range(steps):
            t = i / steps
            result.append((s_lat + (e_lat - s_lat) * t, s_lng + (e_lng - s_lng) * t))
    result.append(path[-1])
    return result
