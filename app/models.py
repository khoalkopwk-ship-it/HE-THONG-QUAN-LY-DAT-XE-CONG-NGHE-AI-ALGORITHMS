from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Driver:
    id: str
    node_id: str
    lat: float
    lng: float
    busy: bool = False
    marker: object | None = None


@dataclass
class Customer:
    id: str
    pickup_node_id: str
    destination_node_id: str
    lat: float
    lng: float
    dest_lat: float
    dest_lng: float
    served: bool = False
    marker: object | None = None
    destination_marker: object | None = None


@dataclass
class SearchCandidate:
    driver: Driver
    distance_km: float
    path: list[str] = field(default_factory=list)


@dataclass
class SearchReport:
    customer_id: str
    radius_km: float
    visited_nodes: int
    candidates: list[SearchCandidate]


@dataclass
class RideHistory:
    id: str
    driver_id: str
    customer_id: str
    pickup_lat: float
    pickup_lng: float
    dest_lat: float
    dest_lng: float
    driver_start_lat: float
    driver_start_lng: float
    pickup_distance_km: float
    dropoff_distance_km: float
    total_distance_km: float
    # Các node/path gốc được lưu để có thể so sánh lại A* và UCS
    # cho tất cả chuyến đã hoàn thành, không chỉ chuyến mẫu hiện tại.
    driver_start_node_id: str = ""
    pickup_node_id: str = ""
    destination_node_id: str = ""
    pickup_node_path: list[str] = field(default_factory=list)
    dropoff_node_path: list[str] = field(default_factory=list)
    pickup_route_coords: list[tuple[float, float]] = field(default_factory=list)
    dropoff_route_coords: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class ActiveRide:
    customer: Customer
    driver: Driver
    pickup_node_path: list[str]
    dropoff_node_path: list[str]
    pickup_points: list[tuple[float, float]]
    dropoff_points: list[tuple[float, float]]
    pickup_distance_km: float = 0.0
    dropoff_distance_km: float = 0.0
    driver_start_lat: float = 0.0
    driver_start_lng: float = 0.0
    stage: str = "to_pickup"
    step_index: int = 0
    history_saved: bool = False
    pickup_path_obj: object | None = None
    dropoff_path_obj: object | None = None
