from __future__ import annotations

APP_NAME = "QKM SmartRide - Local Search A* Demo"

# Khu vực demo: Làng Đại học / ĐHQG TP.HCM, dùng làm nền mô phỏng nhỏ.
MAP_CENTER = (10.873649, 106.794534)
MAP_ZOOM = 14

DEFAULT_DRIVER_COUNT = 20
DEFAULT_CUSTOMER_COUNT = 3
SEARCH_RADII_KM = [0.5, 1.0, 1.5]
ANIMATION_INTERVAL_MS = 100
INTERPOLATION_STEPS_PER_EDGE = 5
SNAP_TO_ROAD_MAX_DISTANCE_M = 80

# Màu marker/path dùng bởi tkintermapview. Nếu môi trường không hỗ trợ màu, app vẫn chạy
# vì thư viện sẽ bỏ qua hoặc dùng màu mặc định.
COLOR_DRIVER_FREE = "green"
COLOR_DRIVER_BUSY = "orange"
COLOR_CUSTOMER = "red"
COLOR_DESTINATION = "purple"
COLOR_ROUTE_PICKUP = "blue"
COLOR_ROUTE_DROPOFF = "black"
COLOR_GRAPH_EDGE = "green"
COLOR_GRAPH_NODE = "gray"

# Màu cho trạng thái đường trong Graph Editor.
COLOR_ROAD_BAD = "yellow"
COLOR_ROAD_VERY_BAD = "red"
COLOR_ROAD_BLOCKED = "red"

