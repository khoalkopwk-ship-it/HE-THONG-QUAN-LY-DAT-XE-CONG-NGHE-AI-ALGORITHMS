"""Luồng mô phỏng chuyến xe của SmartRide.

File này không xử lý giao diện. Nhiệm vụ chính là sinh dữ liệu, chọn tài xế
bằng Local Search, tìm đường bằng A*, rồi tạo dữ liệu cho UI chạy animation.
"""

from __future__ import annotations

import random
from typing import Callable

from .algorithms import (
    astar_shortest_path,
    run_driver_search_algorithm,
    run_path_algorithm,
)
from .config import INTERPOLATION_STEPS_PER_EDGE, SEARCH_RADII_KM
from .geo import interpolate_points
from .graph_data import CampusGraph
from .models import ActiveRide, Customer, Driver, RideHistory, SearchCandidate


class RideSimulation:
    """Quản lý dữ liệu mô phỏng: tài xế, khách, chuyến đang chạy và lịch sử."""

    def __init__(self, graph: CampusGraph) -> None:
        self.graph = graph
        self.drivers: list[Driver] = []
        self.customers: list[Customer] = []
        self.active_rides: list[ActiveRide] = []
        self.ride_history: list[RideHistory] = []

    def reset(self, *, clear_history: bool = False) -> None:
        self.drivers.clear()
        self.customers.clear()
        self.active_rides.clear()
        if clear_history:
            self.ride_history.clear()

    def _next_driver_id(self) -> str:
        max_number = 0
        for driver in self.drivers:
            suffix = driver.id[1:] if driver.id.startswith("D") else ""
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))
        return f"D{max_number + 1:02d}"

    def _next_customer_id(self) -> str:
        max_number = 0
        for customer in self.customers:
            suffix = customer.id[1:] if customer.id.startswith("C") else ""
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))
        return f"C{max_number + 1:02d}"

    def add_manual_driver(self, node_id: str, lat: float, lng: float) -> Driver:
        driver = Driver(id=self._next_driver_id(), node_id=node_id, lat=lat, lng=lng)
        self.drivers.append(driver)
        return driver

    def add_manual_customer(
        self,
        pickup_node_id: str,
        pickup_lat: float,
        pickup_lng: float,
        destination_node_id: str,
        dest_lat: float,
        dest_lng: float,
    ) -> Customer:
        customer = Customer(
            id=self._next_customer_id(),
            pickup_node_id=pickup_node_id,
            destination_node_id=destination_node_id,
            lat=pickup_lat,
            lng=pickup_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
        )
        self.customers.append(customer)
        return customer

    def generate_random_drivers(self, driver_count: int) -> None:
        """Chỉ sinh lại tài xế, giữ nguyên khách hàng hiện có."""
        self.drivers.clear()
        self.active_rides.clear()

        for _ in range(driver_count):
            node_id, lat, lng = self.graph.random_point_on_road(prefix="DRIVER")
            self.drivers.append(
                Driver(
                    id=self._next_driver_id(),
                    node_id=node_id,
                    lat=lat,
                    lng=lng,
                )
            )


    def generate_random_customers(self, customer_count: int) -> None:
        """Chỉ sinh lại khách hàng, giữ nguyên tài xế hiện có."""
        self.customers.clear()
        self.active_rides.clear()

        for _ in range(customer_count):
            pickup, lat, lng = self.graph.random_point_on_road(prefix="PICKUP")

            destination, dest_lat, dest_lng = self.graph.random_point_on_road(prefix="DEST")
            for _ in range(20):
                path_test = astar_shortest_path(self.graph, pickup, destination)
                if path_test.path and path_test.cost_km >= 0.35:
                    break
                destination, dest_lat, dest_lng = self.graph.random_point_on_road(prefix="DEST")

            self.customers.append(
                Customer(
                    id=self._next_customer_id(),
                    pickup_node_id=pickup,
                    destination_node_id=destination,
                    lat=lat,
                    lng=lng,
                    dest_lat=dest_lat,
                    dest_lng=dest_lng,
                )
            )
    
    def generate_random_entities(self, driver_count: int, customer_count: int) -> None:
        """Sinh mới cả tài xế và khách để chạy một lượt demo đầy đủ."""
        self.reset()
        # Xóa các node động cũ. Mỗi vị trí tài xế/khách/điểm đến mới sẽ được
        # sinh trên một cạnh đường bất kỳ của đồ thị, không chỉ nằm đúng tại giao lộ.
        self.graph.reset_dynamic_nodes()

        for _ in range(driver_count):
            node_id, lat, lng = self.graph.random_point_on_road(prefix="DRIVER")
            self.drivers.append(Driver(id=self._next_driver_id(), node_id=node_id, lat=lat, lng=lng))

        for _ in range(customer_count):
            pickup, lat, lng = self.graph.random_point_on_road(prefix="PICKUP")

            # Sinh điểm đến khác vị trí đón. Thử vài lần để tránh điểm đến quá gần điểm đón.
            destination, dest_lat, dest_lng = self.graph.random_point_on_road(prefix="DEST")
            for _ in range(20):
                path_test = astar_shortest_path(self.graph, pickup, destination)
                if path_test.path and path_test.cost_km >= 0.35:
                    break
                destination, dest_lat, dest_lng = self.graph.random_point_on_road(prefix="DEST")

            self.customers.append(
                Customer(
                    id=self._next_customer_id(),
                    pickup_node_id=pickup,
                    destination_node_id=destination,
                    lat=lat,
                    lng=lng,
                    dest_lat=dest_lat,
                    dest_lng=dest_lng,
                )
            )

    def _queue_text(self, queue: list[SearchCandidate]) -> str:
        if not queue:
            return "rỗng"
        return ", ".join(f"{item.driver.id}({item.distance_km:.2f}km)" for item in queue)

    def _format_radius(self, radius_km: float) -> str:
        """Định dạng bán kính nhất quán cho log giao diện."""
        return f"{radius_km:.1f} km"

    def _choose_driver_by_algorithm(
        self,
        customer: Customer,
        log: Callable[[str], None],
        driver_algorithm: str = "Local Search",
    ) -> Driver | None:
        """Tìm tài xế theo thuật toán đang được chọn trên giao diện.

        Mặc định vẫn là Local Search để giữ đúng luồng chính của bản v4.
        Khi người dùng chọn BFS/DFS/Greedy/UCS, hàm vẫn giữ đúng quy tắc chung:
        lấy toàn bộ tài xế phù hợp trong bán kính, sắp xếp theo khoảng cách/chi phí,
        sau đó random trong 3 tài xế gần nhất.
        """
        for radius in SEARCH_RADII_KM:
            report = run_driver_search_algorithm(
                self.graph,
                customer.pickup_node_id,
                self.drivers,
                radius,
                driver_algorithm,
                None,
            )
            all_candidates = sorted(report.candidates, key=lambda item: item.distance_km)
            top_candidates = all_candidates[:3]
            log(
                f"{driver_algorithm} bán kính {self._format_radius(radius)} quanh điểm đón: "
                f"tìm được {len(all_candidates)} tài xế -> {self._queue_text(all_candidates)}"
            )

            if not all_candidates:
                if radius < SEARCH_RADII_KM[-1]:
                    log(
                        f"Không có tài xế trong {self._format_radius(radius)}, "
                        f"mở rộng bán kính bằng {driver_algorithm}."
                    )
                continue

            log(f"Sắp xếp hàng đợi theo khoảng cách tăng dần: {self._queue_text(all_candidates)}")
            log(f"Lấy top {len(top_candidates)} gần nhất để random: {self._queue_text(top_candidates)}")
            selected = random.choice(top_candidates)
            log(f"Random chọn {selected.driver.id} trong top {len(top_candidates)} tài xế gần nhất.")
            return selected.driver

        log(f"Không tìm thấy tài xế bằng {driver_algorithm} trong toàn bộ bán kính cấu hình.")
        return None


    def prepare_assignments(
        self,
        log: Callable[[str], None],
        driver_algorithm: str = "Local Search",
        route_algorithm: str = "A*",
    ) -> list[ActiveRide]:
        """Tạo đơn cho tất cả khách hàng hiện có.

        Các khách hàng được xử lý tuần tự để tránh 2 khách chọn cùng 1 tài xế.
        Sau khi có danh sách ride, UI có thể animate các ride đồng thời.
        """
        self.active_rides.clear()

        for customer in self.customers:
            if customer.served:
                continue

            chosen_driver = self._choose_driver_by_algorithm(customer, log, driver_algorithm)

            if not chosen_driver:
                continue

            # Đánh dấu bận ngay sau khi chọn để khách sau không lấy trùng tài xế.
            chosen_driver.busy = True

            # Thuật toán tìm đường được chọn từ giao diện. Mặc định vẫn là A*.
            driver_to_customer = run_path_algorithm(
                self.graph,
                chosen_driver.node_id,
                customer.pickup_node_id,
                route_algorithm,
            )
            customer_to_destination = run_path_algorithm(
                self.graph,
                customer.pickup_node_id,
                customer.destination_node_id,
                route_algorithm,
            )

            if not driver_to_customer.path or not customer_to_destination.path:
                chosen_driver.busy = False
                continue

            log(
                f"{chosen_driver.id} đến điểm đón {customer.id}: "
                f"{driver_to_customer.cost_km:.2f} km"
            )
            log(
                f"Điểm đón {customer.id} đến điểm đích {customer.id}: "
                f"{customer_to_destination.cost_km:.2f} km"
            )
            log(
                f"Tổng quãng đường {chosen_driver.id} phục vụ {customer.id}: "
                f"{driver_to_customer.cost_km + customer_to_destination.cost_km:.2f} km"
            )

            pickup_coords = [self.graph.node_position(node_id) for node_id in driver_to_customer.path]
            dropoff_coords = [self.graph.node_position(node_id) for node_id in customer_to_destination.path]

            ride = ActiveRide(
                customer=customer,
                driver=chosen_driver,
                pickup_node_path=driver_to_customer.path,
                dropoff_node_path=customer_to_destination.path,
                pickup_points=interpolate_points(pickup_coords, INTERPOLATION_STEPS_PER_EDGE),
                dropoff_points=interpolate_points(dropoff_coords, INTERPOLATION_STEPS_PER_EDGE),
                pickup_distance_km=driver_to_customer.cost_km,
                dropoff_distance_km=customer_to_destination.cost_km,
                driver_start_lat=chosen_driver.lat,
                driver_start_lng=chosen_driver.lng,
            )
            self.active_rides.append(ride)

        return self.active_rides
