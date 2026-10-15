"""Các thuật toán chính của demo SmartRide.

File này tập trung vào 3 phần để báo cáo:
- Nhóm tìm tài xế: Local Search, BFS, DFS, Greedy Search và UCS.
- Nhóm tìm đường: A*, UCS, BFS, DFS và Greedy Search.
- Các hàm chạy thuật toán theo tên để UI có thể chọn bằng combobox.

Bản này được gộp có chọn lọc từ bản Mai vào bản nền v4. Phần tìm đường vẫn
đọc trọng số từ ``CampusGraph.adj``, nên đường xấu/rất xấu/đường cấm của v4
vẫn tác động trực tiếp tới kết quả tìm đường.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass

from .geo import haversine_km
from .graph_data import CampusGraph
from .models import Driver, SearchCandidate, SearchReport


DRIVER_SEARCH_ALGORITHMS = ["Local Search", "BFS", "DFS", "Greedy", "UCS"]
ROUTE_SEARCH_ALGORITHMS = ["A*", "UCS", "DFS", "BFS", "Greedy"]


@dataclass
class UCSResult:
    """Kết quả trả về chung cho các thuật toán tìm đường."""

    path: list[str]
    cost_km: float
    visited_nodes: int


def local_search_drivers_in_circle(
    graph: CampusGraph,
    pickup_node_id: str,
    drivers: list[Driver],
    radius_km: float = 1.0,
    top_k: int | None = None,
) -> list[SearchCandidate]:
    """Local Search dùng để lọc tài xế gần điểm đón.

    Cách hiểu đơn giản cho báo cáo:
    1. Lấy tọa độ điểm đón làm tâm.
    2. Chỉ xét tài xế đang rảnh.
    3. Giữ lại tài xế nằm trong bán kính đang xét.
    4. Sắp xếp theo khoảng cách gần nhất; nếu truyền top_k thì mới giới hạn số lượng.

    Đây vẫn là thuật toán mặc định cho luồng gán chuyến. Các thuật toán còn lại
    được thêm để minh họa, lựa chọn thử nghiệm và so sánh.
    """
    pickup_lat, pickup_lng = graph.node_position(pickup_node_id)
    candidates: list[SearchCandidate] = []

    # Tính Haversine đúng 1 lần cho mỗi tài xế rảnh để tránh xử lý trùng.
    for driver in drivers:
        if driver.busy:
            continue

        distance = haversine_km(pickup_lat, pickup_lng, driver.lat, driver.lng)
        if distance <= radius_km:
            candidates.append(
                SearchCandidate(
                    driver=driver,
                    distance_km=distance,
                    path=[pickup_node_id, driver.node_id],
                )
            )

    candidates = sorted(candidates, key=lambda item: item.distance_km)
    return candidates if top_k is None else candidates[:top_k]


def _driver_by_node(drivers: list[Driver]) -> dict[str, list[Driver]]:
    """Gom tài xế rảnh theo node để BFS/DFS/UCS kiểm tra nhanh hơn."""
    grouped: dict[str, list[Driver]] = {}
    for driver in drivers:
        if not driver.busy:
            grouped.setdefault(driver.node_id, []).append(driver)
    return grouped


def _add_circle_candidates_not_reached(
    graph: CampusGraph,
    start_id: str,
    drivers: list[Driver],
    radius_km: float,
    found_driver_ids: set[str],
    candidates: list[SearchCandidate],
) -> None:
    """Bổ sung tài xế nằm trong bán kính tròn nhưng không nằm trên node BFS/DFS/UCS đã duyệt.

    Lý do: tài xế/khách có thể nằm trên node động gắn vào cạnh đường. Nếu chỉ lấy
    node đã duyệt trên graph, bảng so sánh có thể thiếu tài xế dù vị trí thực tế
    vẫn nằm trong bán kính Haversine.
    """
    pickup_lat, pickup_lng = graph.node_position(start_id)
    for driver in drivers:
        if driver.busy or driver.id in found_driver_ids:
            continue
        distance = haversine_km(pickup_lat, pickup_lng, driver.lat, driver.lng)
        if distance <= radius_km:
            candidates.append(
                SearchCandidate(
                    driver=driver,
                    distance_km=distance,
                    path=[start_id, driver.node_id],
                )
            )
            found_driver_ids.add(driver.id)


def _graph_driver_search(
    graph: CampusGraph,
    start_id: str,
    drivers: list[Driver],
    radius_km: float,
    kind: str,
) -> SearchReport:
    """Khung dùng chung cho BFS, DFS và UCS trong bài toán tìm tài xế."""
    pickup_lat, pickup_lng = graph.node_position(start_id)
    driver_by_node = _driver_by_node(drivers)
    candidates: list[SearchCandidate] = []
    found_driver_ids: set[str] = set()
    visited: set[str] = set()

    if kind == "ucs":
        frontier: list[tuple[float, str, list[str]]] = [(0.0, start_id, [start_id])]
        best_cost: dict[str, float] = {start_id: 0.0}
    elif kind == "bfs":
        frontier = deque([(start_id, [start_id])])
    else:
        frontier = [(start_id, [start_id])]

    while frontier:
        if kind == "ucs":
            cost, node_id, path = heapq.heappop(frontier)  # type: ignore[arg-type]
            if cost > radius_km:
                continue
        elif kind == "bfs":
            node_id, path = frontier.popleft()  # type: ignore[attr-defined]
            cost = 0.0
        else:
            node_id, path = frontier.pop()  # type: ignore[assignment]
            cost = 0.0

        if node_id in visited:
            continue

        node_lat, node_lng = graph.node_position(node_id)
        circle_distance = haversine_km(pickup_lat, pickup_lng, node_lat, node_lng)
        if kind != "ucs" and circle_distance > radius_km:
            continue

        visited.add(node_id)

        for driver in driver_by_node.get(node_id, []):
            if driver.id in found_driver_ids:
                continue
            driver_distance = haversine_km(pickup_lat, pickup_lng, driver.lat, driver.lng)
            if driver_distance <= radius_km:
                candidates.append(
                    SearchCandidate(
                        driver=driver,
                        distance_km=driver_distance,
                        path=path[:],
                    )
                )
                found_driver_ids.add(driver.id)

        for neighbor_id, weight in graph.adj.get(node_id, []):
            if neighbor_id in visited:
                continue

            if kind == "ucs":
                new_cost = cost + weight
                if new_cost <= radius_km and (neighbor_id not in best_cost or new_cost < best_cost[neighbor_id]):
                    best_cost[neighbor_id] = new_cost
                    heapq.heappush(frontier, (new_cost, neighbor_id, path + [neighbor_id]))  # type: ignore[arg-type]
                continue

            neighbor_lat, neighbor_lng = graph.node_position(neighbor_id)
            neighbor_circle_distance = haversine_km(
                pickup_lat,
                pickup_lng,
                neighbor_lat,
                neighbor_lng,
            )
            if neighbor_circle_distance <= radius_km:
                item = (neighbor_id, path + [neighbor_id])
                if kind == "bfs":
                    frontier.append(item)  # type: ignore[attr-defined]
                else:
                    frontier.append(item)  # type: ignore[attr-defined]

    # Đồng bộ tiêu chí kết quả với Local Search theo bán kính Haversine.
    _add_circle_candidates_not_reached(
        graph,
        start_id,
        drivers,
        radius_km,
        found_driver_ids,
        candidates,
    )

    return SearchReport(
        customer_id="",
        radius_km=radius_km,
        visited_nodes=len(visited),
        candidates=sorted(candidates, key=lambda item: item.distance_km),
    )


def bfs_drivers_in_circle(
    graph: CampusGraph,
    customer_node_id: str,
    drivers: list[Driver],
    radius_km: float,
) -> SearchReport:
    """BFS duyệt graph theo lớp để minh họa tìm tài xế quanh điểm đón."""
    return _graph_driver_search(graph, customer_node_id, drivers, radius_km, "bfs")


def dfs_drivers_in_circle(
    graph: CampusGraph,
    customer_node_id: str,
    drivers: list[Driver],
    radius_km: float,
    top_k: int | None = None,
) -> SearchReport:
    """DFS duyệt sâu trước, dùng để minh họa thứ tự duyệt khác BFS."""
    report = _graph_driver_search(graph, customer_node_id, drivers, radius_km, "dfs")
    if top_k is not None:
        report.candidates = report.candidates[:top_k]
    return report


def ucs_drivers_in_circle(
    graph: CampusGraph,
    customer_node_id: str,
    drivers: list[Driver],
    radius_km: float,
    top_k: int | None = None,
) -> SearchReport:
    """UCS tìm tài xế bằng chi phí đường đi trên graph có trọng số."""
    report = _graph_driver_search(graph, customer_node_id, drivers, radius_km, "ucs")
    if top_k is not None:
        report.candidates = report.candidates[:top_k]
    return report


def greedy_drivers_in_circle(
    graph: CampusGraph,
    pickup_node_id: str,
    drivers: list[Driver],
    radius_km: float,
    top_k: int | None = None,
) -> SearchReport:
    """Greedy Search ưu tiên tài xế có khoảng cách ước lượng gần nhất tới điểm đón."""
    pickup_lat, pickup_lng = graph.node_position(pickup_node_id)
    scored: list[tuple[float, Driver]] = []
    for driver in drivers:
        if driver.busy:
            continue
        distance = haversine_km(pickup_lat, pickup_lng, driver.lat, driver.lng)
        scored.append((distance, driver))

    checked = 0
    candidates: list[SearchCandidate] = []
    for distance, driver in sorted(scored, key=lambda item: item[0]):
        checked += 1
        if distance > radius_km:
            break
        candidates.append(SearchCandidate(driver=driver, distance_km=distance, path=[pickup_node_id, driver.node_id]))

    if top_k is not None:
        candidates = candidates[:top_k]

    return SearchReport(
        customer_id="",
        radius_km=radius_km,
        visited_nodes=checked,
        candidates=candidates,
    )


def run_driver_search_algorithm(
    graph: CampusGraph,
    pickup_node_id: str,
    drivers: list[Driver],
    radius_km: float,
    algorithm: str,
    top_k: int | None = None,
) -> SearchReport:
    """Chạy thuật toán tìm tài xế theo tên được chọn trên giao diện."""
    algorithm_key = algorithm.strip().lower()

    if algorithm_key in {"local", "local search"}:
        candidates = local_search_drivers_in_circle(
            graph,
            pickup_node_id,
            drivers,
            radius_km=radius_km,
            top_k=top_k,
        )
        checked = sum(1 for driver in drivers if not driver.busy)
        return SearchReport("", radius_km, checked, candidates)

    if algorithm_key == "bfs":
        report = bfs_drivers_in_circle(graph, pickup_node_id, drivers, radius_km)
    elif algorithm_key == "dfs":
        report = dfs_drivers_in_circle(graph, pickup_node_id, drivers, radius_km)
    elif algorithm_key in {"greedy", "greedy search"}:
        report = greedy_drivers_in_circle(graph, pickup_node_id, drivers, radius_km)
    elif algorithm_key == "ucs":
        report = ucs_drivers_in_circle(graph, pickup_node_id, drivers, radius_km)
    else:
        return run_driver_search_algorithm(graph, pickup_node_id, drivers, radius_km, "Local Search", top_k)

    if top_k is not None:
        report.candidates = report.candidates[:top_k]
    return report


def _path_cost(graph: CampusGraph, path: list[str]) -> float:
    """Tính tổng chi phí một đường đi theo trọng số hiện tại của graph."""
    total = 0.0
    for start_id, end_id in zip(path, path[1:]):
        for neighbor_id, weight in graph.adj.get(start_id, []):
            if neighbor_id == end_id:
                total += weight
                break
    return total


def ucs_shortest_path(graph: CampusGraph, start_id: str, goal_id: str) -> UCSResult:
    """Uniform Cost Search: luôn mở rộng đường có tổng chi phí nhỏ nhất trước."""
    heap: list[tuple[float, str, list[str]]] = [(0.0, start_id, [start_id])]
    best_cost: dict[str, float] = {start_id: 0.0}
    visited: set[str] = set()

    while heap:
        cost, node_id, path = heapq.heappop(heap)
        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == goal_id:
            return UCSResult(path=path, cost_km=cost, visited_nodes=len(visited))

        # Nếu đi qua node hiện tại rẻ hơn đường đã biết, cập nhật lại chi phí tốt nhất.
        for neighbor_id, weight in graph.adj.get(node_id, []):
            new_cost = cost + weight
            if neighbor_id not in best_cost or new_cost < best_cost[neighbor_id]:
                best_cost[neighbor_id] = new_cost
                heapq.heappush(heap, (new_cost, neighbor_id, path + [neighbor_id]))

    return UCSResult(path=[], cost_km=float("inf"), visited_nodes=len(visited))


def astar_shortest_path(graph: CampusGraph, start_id: str, goal_id: str) -> UCSResult:
    """A* tìm đường ngắn nhất trên đồ thị trọng số.

    g(n): tổng chi phí từ node bắt đầu đến node hiện tại.
    h(n): khoảng cách Haversine từ node hiện tại đến node đích.

    Vì h(n) là khoảng cách đường chim bay, thường không vượt quá chi phí đi
    theo đường trong graph, nên A* vẫn giữ tính tối ưu nhưng duyệt ít node hơn
    UCS trong bài toán bản đồ có tọa độ.
    """
    if start_id == goal_id:
        return UCSResult(path=[start_id], cost_km=0.0, visited_nodes=1)

    goal_lat, goal_lng = graph.node_position(goal_id)

    def heuristic(node_id: str) -> float:
        lat, lng = graph.node_position(node_id)
        return haversine_km(lat, lng, goal_lat, goal_lng)

    # Heap của A* ưu tiên f(n) = g(n) + h(n).
    heap: list[tuple[float, float, str, list[str]]] = [
        (heuristic(start_id), 0.0, start_id, [start_id])
    ]
    best_cost: dict[str, float] = {start_id: 0.0}
    visited: set[str] = set()

    while heap:
        _f_score, cost, node_id, path = heapq.heappop(heap)
        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == goal_id:
            return UCSResult(path=path, cost_km=cost, visited_nodes=len(visited))

        for neighbor_id, weight in graph.adj.get(node_id, []):
            new_cost = cost + weight
            if neighbor_id not in best_cost or new_cost < best_cost[neighbor_id]:
                best_cost[neighbor_id] = new_cost
                f_score = new_cost + heuristic(neighbor_id)
                heapq.heappush(heap, (f_score, new_cost, neighbor_id, path + [neighbor_id]))

    return UCSResult(path=[], cost_km=float("inf"), visited_nodes=len(visited))


def bfs_shortest_path(graph: CampusGraph, start_id: str, goal_id: str) -> UCSResult:
    """BFS tìm đường theo số bước cạnh, sau đó tính lại chi phí của path tìm được."""
    queue: deque[tuple[str, list[str]]] = deque([(start_id, [start_id])])
    visited: set[str] = set()

    while queue:
        node_id, path = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == goal_id:
            return UCSResult(path=path, cost_km=_path_cost(graph, path), visited_nodes=len(visited))

        for neighbor_id, _weight in graph.adj.get(node_id, []):
            if neighbor_id not in visited:
                queue.append((neighbor_id, path + [neighbor_id]))

    return UCSResult(path=[], cost_km=float("inf"), visited_nodes=len(visited))


def dfs_path(graph: CampusGraph, start_id: str, goal_id: str) -> UCSResult:
    """DFS tìm một đường đi bằng cách ưu tiên đi sâu trước."""
    stack: list[tuple[str, list[str]]] = [(start_id, [start_id])]
    visited: set[str] = set()

    while stack:
        node_id, path = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == goal_id:
            return UCSResult(path=path, cost_km=_path_cost(graph, path), visited_nodes=len(visited))

        for neighbor_id, _weight in reversed(graph.adj.get(node_id, [])):
            if neighbor_id not in visited:
                stack.append((neighbor_id, path + [neighbor_id]))

    return UCSResult(path=[], cost_km=float("inf"), visited_nodes=len(visited))


def greedy_shortest_path(graph: CampusGraph, start_id: str, goal_id: str) -> UCSResult:
    """Greedy Search ưu tiên node có h(n) gần đích nhất, không cộng chi phí đã đi."""
    goal_lat, goal_lng = graph.node_position(goal_id)

    def heuristic(node_id: str) -> float:
        lat, lng = graph.node_position(node_id)
        return haversine_km(lat, lng, goal_lat, goal_lng)

    heap: list[tuple[float, str, list[str]]] = [(heuristic(start_id), start_id, [start_id])]
    visited: set[str] = set()

    while heap:
        _score, node_id, path = heapq.heappop(heap)
        if node_id in visited:
            continue
        visited.add(node_id)

        if node_id == goal_id:
            return UCSResult(path=path, cost_km=_path_cost(graph, path), visited_nodes=len(visited))

        for neighbor_id, _weight in graph.adj.get(node_id, []):
            if neighbor_id not in visited:
                heapq.heappush(heap, (heuristic(neighbor_id), neighbor_id, path + [neighbor_id]))

    return UCSResult(path=[], cost_km=float("inf"), visited_nodes=len(visited))


def run_path_algorithm(graph: CampusGraph, start_id: str, goal_id: str, algorithm: str) -> UCSResult:
    """Chạy thuật toán tìm đường theo tên được chọn trên giao diện."""
    algorithm_key = algorithm.strip().lower()

    if algorithm_key in {"a*", "astar", "a star"}:
        return astar_shortest_path(graph, start_id, goal_id)
    if algorithm_key == "ucs":
        return ucs_shortest_path(graph, start_id, goal_id)
    if algorithm_key == "dfs":
        return dfs_path(graph, start_id, goal_id)
    if algorithm_key == "bfs":
        return bfs_shortest_path(graph, start_id, goal_id)
    if algorithm_key in {"greedy", "greedy search"}:
        return greedy_shortest_path(graph, start_id, goal_id)

    return astar_shortest_path(graph, start_id, goal_id)
