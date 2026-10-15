"""Giao diện Tkinter cho demo SmartRide.

File này chủ yếu dựng dashboard, bản đồ và các bảng/biểu đồ so sánh. Phần
thuật toán thật nằm ở algorithms.py và simulation.py; UI chỉ gọi và hiển thị kết quả.
"""

from __future__ import annotations

import heapq
import math
import random
import time
import tkinter as tk
from collections import deque
from types import SimpleNamespace
from PIL import Image, ImageTk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

try:
    from tkintermapview import TkinterMapView
except Exception: 
    TkinterMapView = None 

from .driver_profiles import get_driver_profile
from .config import (
    ANIMATION_INTERVAL_MS,
    APP_NAME,
    COLOR_CUSTOMER,
    COLOR_DESTINATION,
    COLOR_DRIVER_BUSY,
    COLOR_DRIVER_FREE,
    COLOR_GRAPH_EDGE,
    COLOR_GRAPH_NODE,
    COLOR_ROAD_BAD,
    COLOR_ROAD_BLOCKED,
    COLOR_ROAD_VERY_BAD,
    COLOR_ROUTE_DROPOFF,
    COLOR_ROUTE_PICKUP,
    DEFAULT_CUSTOMER_COUNT,
    DEFAULT_DRIVER_COUNT,
    MAP_CENTER,
    MAP_ZOOM,
    SNAP_TO_ROAD_MAX_DISTANCE_M,
    SEARCH_RADII_KM,
)
from .geo import haversine_km
from .graph_data import (
    CampusGraph,
    ROAD_BAD,
    ROAD_BLOCKED,
    ROAD_CONDITION_LABELS,
    ROAD_NORMAL,
    ROAD_VERY_BAD,
)
from .models import ActiveRide, Customer, Driver, RideHistory
from .simulation import RideSimulation
from .algorithms import (
    DRIVER_SEARCH_ALGORITHMS,
    ROUTE_SEARCH_ALGORITHMS,
    run_driver_search_algorithm,
    run_path_algorithm,
)


APP_BG = "#EEF5FB"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#F6FAFD"
BORDER = "#D4E2F0"
TEXT_PRIMARY = "#102033"
TEXT_SECONDARY = "#5E6F84"
ACCENT = "#0B76D1"
ACCENT_HOVER = "#075EA8"
DANGER = "#E5484D"
DANGER_HOVER = "#C92F35"
MUTED_BUTTON = "#E5EDF5"
MUTED_BUTTON_HOVER = "#D4E2F0"
SUCCESS = "#14B8A6"
SUCCESS_HOVER = "#0F8F82"
DARK_SURFACE = "#102A43"
DARK_SURFACE_2 = "#153B5A"
NAV_BG = "#102A43"
NAV_HOVER = "#173B5D"
NAV_ACTIVE = "#0B76D1"
NAV_TEXT = "#EAF6FF"
NAV_MUTED = "#91B9D8"
METRIC_BG = "#EAF6FF"
METRIC_BORDER = "#B7D7F2"
LOG_BG = "#0A1B2E"
LOG_FG = "#DCEBFF"
DASHBOARD_WIDTH_RATIO = 0.32
DASHBOARD_MIN_WIDTH = 500
NAV_COLLAPSED_WIDTH = 76
NAV_EXPANDED_WIDTH = 236
DASHBOARD_DEFAULT_WIDTH = 520
DASHBOARD_MAX_WIDTH = 760


def _darken_color(color: str, factor: float = 0.78) -> str:
    """Làm đậm mã màu hex để dùng cho trạng thái đang nhấn/đang chọn."""

    if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
        return color
    try:
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
    except ValueError:
        return color
    red = max(0, min(255, int(red * factor)))
    green = max(0, min(255, int(green * factor)))
    blue = max(0, min(255, int(blue * factor)))
    return f"#{red:02X}{green:02X}{blue:02X}"


class RoundedFrame(tk.Frame):
    """Khung bo góc đơn giản dùng Canvas, phù hợp cho dashboard Tkinter."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        radius: int = 18,
        padding: int = 14,
        bg: str = APP_BG,
        fill: str = SURFACE,
        outline: str = BORDER,
    ) -> None:
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        self.radius = radius
        self.padding = padding
        self.bg = bg
        self.fill = fill
        self.outline = outline
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=fill, highlightthickness=0, bd=0)
        self._window = self.canvas.create_window(
            (padding, padding),
            window=self.body,
            anchor="nw",
        )
        self._shape: int | None = None
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> int:
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _draw(self) -> None:
        width = max(self.canvas.winfo_width(), self.body.winfo_reqwidth() + self.padding * 2)
        height = max(self.canvas.winfo_height(), self.body.winfo_reqheight() + self.padding * 2)
        self.canvas.delete("card-shape")
        self._rounded_rect(
            1,
            1,
            max(2, width - 2),
            max(2, height - 2),
            self.radius,
            fill=self.fill,
            outline=self.outline,
            width=1,
            tags="card-shape",
        )
        self.canvas.tag_lower("card-shape")
        self.canvas.itemconfigure(
            self._window,
            width=max(1, width - self.padding * 2),
        )

    def _on_body_configure(self, _event: tk.Event) -> None:
        req_w = self.body.winfo_reqwidth() + self.padding * 2
        req_h = self.body.winfo_reqheight() + self.padding * 2
        self.canvas.configure(width=req_w, height=req_h)
        self._draw()

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        self._draw()


class RoundedButton(tk.Canvas):
    """Nút bo góc cho giao diện Tkinter hiện đại."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        bg: str = SURFACE,
        fill: str = ACCENT,
        hover_fill: str = ACCENT_HOVER,
        fg: str = "#FFFFFF",
        radius: int = 14,
        height: int = 42,
        width: int = 1,
        font: tuple[str, int, str] = ("Segoe UI", 10, "bold"),
        active_fill: str | None = None,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.text = text
        self.command = command
        self.fill = fill
        self.hover_fill = hover_fill
        self.active_fill = active_fill or _darken_color(hover_fill, 0.82)
        self.pressed_fill = _darken_color(hover_fill, 0.70)
        self.current_fill = fill
        self.fg = fg
        self.radius = radius
        self.button_height = height
        self.button_font = font
        self.is_pressed = False
        self.is_hovered = False
        self.is_active = False
        self._command_running = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> int:
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _refresh_current_fill(self) -> None:
        if self.is_pressed:
            self.current_fill = self.pressed_fill
        elif self.is_active:
            self.current_fill = self.active_fill
        elif self.is_hovered:
            self.current_fill = self.hover_fill
        else:
            self.current_fill = self.fill

    def _draw(self) -> None:
        self.delete("all")
        self._refresh_current_fill()
        width = max(20, self.winfo_width())
        height = self.button_height
        offset = 2 if self.is_pressed else 0
        self._rounded_rect(1, 1 + offset, width - 2, height - 2 + offset, self.radius, fill=self.current_fill, outline="")
        self.create_text(
            width // 2,
            height // 2 + offset,
            text=self.text,
            fill=self.fg,
            font=self.button_font,
        )

    def _on_enter(self, _event: tk.Event) -> None:
        self.is_hovered = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self.is_hovered = False
        self.is_pressed = False
        self._draw()

    def _on_press(self, _event: tk.Event) -> None:
        self.is_pressed = True
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if self._command_running:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.button_height
        self.is_pressed = False
        self.is_hovered = inside
        self._draw()
        if not inside:
            return
        self._command_running = True
        self.after(70, self._run_command_after_press)

    def _run_command_after_press(self) -> None:
        try:
            self.command()
        finally:
            self._command_running = False
            self.is_pressed = False
            self._draw()

    def set_text(self, text: str) -> None:
        self.text = text
        self._draw()

    def set_colors(self, fill: str, hover_fill: str | None = None, fg: str | None = None, active_fill: str | None = None) -> None:
        self.fill = fill
        self.hover_fill = hover_fill or fill
        self.active_fill = active_fill or _darken_color(self.hover_fill, 0.82)
        self.pressed_fill = _darken_color(self.hover_fill, 0.70)
        if fg is not None:
            self.fg = fg
        self._draw()

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._draw()


class NavItemButton(tk.Canvas):
    """Nút điều hướng bo góc dùng cho thanh dashboard thu gọn/mở rộng."""

    def __init__(
        self,
        parent: tk.Misc,
        icon: str,
        label: str,
        command: Callable[[], None],
        *,
        bg: str = NAV_BG,
        height: int = 46,
        radius: int = 15,
    ) -> None:
        super().__init__(
            parent,
            width=NAV_COLLAPSED_WIDTH - 16,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.icon = icon
        self.label = label
        self.command = command
        self.canvas_bg = bg
        self.item_height = height
        self.radius = radius
        self.expanded = False
        self.selected = False
        self.hovered = False
        self.is_pressed = False
        self._command_running = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> int:
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _draw(self) -> None:
        self.delete("all")
        width = max(20, self.winfo_width())
        height = self.item_height
        if self.is_pressed:
            fill = _darken_color(NAV_ACTIVE if self.selected else NAV_HOVER, 0.78)
            fg = "#FFFFFF"
        elif self.selected:
            fill = NAV_ACTIVE
            fg = "#FFFFFF"
        elif self.hovered:
            fill = NAV_HOVER
            fg = NAV_TEXT
        else:
            fill = NAV_BG
            fg = NAV_TEXT

        offset = 2 if self.is_pressed else 0
        self._rounded_rect(1, 1 + offset, width - 2, height - 2 + offset, self.radius, fill=fill, outline="")
        self.create_text(
            24,
            height // 2 + offset,
            text=self.icon,
            fill=fg,
            font=("Segoe UI Symbol", 17, "bold"),
        )
        if self.expanded:
            self.create_text(
                54,
                height // 2 + offset,
                text=self.label,
                fill=fg,
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )

    def _on_enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self.is_pressed = False
        self._draw()

    def _on_press(self, _event: tk.Event) -> None:
        self.is_pressed = True
        self.hovered = True
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if self._command_running:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.item_height
        self.is_pressed = False
        self.hovered = inside
        self._draw()
        if not inside:
            return
        self._command_running = True
        self.after(70, self._run_command_after_press)

    def _run_command_after_press(self) -> None:
        try:
            self.command()
        finally:
            self._command_running = False
            self.is_pressed = False
            self._draw()

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        target_width = (NAV_EXPANDED_WIDTH if expanded else NAV_COLLAPSED_WIDTH) - 16
        self.configure(width=target_width)
        self._draw()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._draw()


class SmartRideDemoApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)

        # Mở cửa sổ lớn hơn để sidebar/dashboard không bị che chức năng
        self.root.geometry("1366x850")
        self.root.minsize(1280, 760)

        # Tự động phóng to cửa sổ khi mở app
        try:
            self.root.state("zoomed")   # Windows
        except tk.TclError:
            self.root.attributes("-zoomed", True)   # Linux

        self.graph = CampusGraph()
        self.sim = RideSimulation(self.graph)
        self.map_widget: Any = None
        self.graph_paths: list[Any] = []
        self.node_markers: list[Any] = []
        self.route_paths: list[Any] = []
        self.history_overlay_paths: list[Any] = []
        self.history_overlay_markers: list[Any] = []
        self.is_animating = False
        self.map_action: str | None = None
        self.pending_pickup: dict[str, float | str] | None = None
        self.pending_pickup_marker: Any = None
        self.history_listbox: tk.Listbox | None = None
        self.driver_info_card: RoundedFrame | None = None
        self.algorithm_demo_card: RoundedFrame | None = None
        self.selected_driver_id: str | None = None
        self.algorithm_demo_customer_id: str | None = None
        self.inline_search_radius_var = tk.StringVar(value="0.5")
        self.inline_status_container: tk.Frame | None = None
        self.inline_status_tree: ttk.Treeview | None = None
        self.inline_queue_canvas: tk.Canvas | None = None
        self.inline_queue_scrollbar: ttk.Scrollbar | None = None
        self.inline_queue_inner: tk.Frame | None = None
        self.inline_queue_window: int | None = None
        self.inline_queue_cells: list[tk.Widget] = []
        self.inline_queue_cell_by_driver: dict[str, tk.Label] = {}
        self.inline_queue_columns = 8
        self.inline_queue_animation_job: str | None = None
        self.inline_queue_animation_token = 0
        self.inline_demo_status_var = tk.StringVar(value="Chọn thuật toán để bắt đầu minh họa.")

        self.driver_count_var = tk.IntVar(value=DEFAULT_DRIVER_COUNT)
        self.customer_count_var = tk.IntVar(value=DEFAULT_CUSTOMER_COUNT)
        self.animation_interval_var = tk.IntVar(value=ANIMATION_INTERVAL_MS)
        self.show_graph_var = tk.BooleanVar(value=False)
        self.show_nodes_var = tk.BooleanVar(value=False)
        self.driver_algorithm_var = tk.StringVar(value="Local Search")
        self.route_algorithm_var = tk.StringVar(value="A*")

        # Icon lấy từ bản Mai. Nếu thiếu file hoặc môi trường không hỗ trợ icon,
        # marker màu mặc định vẫn được dùng để tránh lỗi runtime.
        self.driver_free_icon = self._load_map_icon("driver_motorbike.png", (36, 36))
        self.driver_busy_icon = self._load_map_icon("ride_motobike.png", (42, 42))
        self.customer_icon = self._load_map_icon("customer.png", (28, 35))
        self.no_entry_icon = self._load_map_icon("BienCam.png", (17, 17))

        # Công cụ phụ trợ để tự vẽ graph trên nền OSM rồi xuất code tọa độ.
        self.editor_mode_var = tk.BooleanVar(value=False)
        self.editor_lock_map_var = tk.BooleanVar(value=True)
        # Mặc định tắt tự nối để tránh 2 đường song song bị bắt node/nối chéo.
        # Chỉ bật khi người dùng thật sự muốn tạo ngã ba/ngã tư.
        self.editor_auto_join_var = tk.BooleanVar(value=False)
        self.editor_dead_end_var = tk.BooleanVar(value=False)
        # Khi bật, click lên cạnh gần nhất để đánh dấu đường xấu/rất xấu/cấm.
        # Các trạng thái này ảnh hưởng trực tiếp tới trọng số khi A*/UCS tìm đường.
        self.editor_mark_bad_road_var = tk.BooleanVar(value=False)
        self.editor_road_condition_var = tk.StringVar(value=ROAD_BAD)
        self.editor_delete_graph_mode = False
        self.editor_drag_action: str | None = None
        self.editor_processed_edges_in_drag: set[Any] = set()
        self.editor_created_nodes: set[str] = set()
        self.graph_dirty = False
        self._suppress_editor_option_callback = False
        self.editor_min_point_distance_var = tk.IntVar(value=15)  # mét, khoảng cách tối thiểu để tạo node mới
        self.editor_snap_distance_var = tk.IntVar(value=8)  # mét, bán kính bắt node khi bật tự nối
        self.editor_nodes: list[tuple[str, float, float]] = []

        self.editor_mode_var.trace_add("write", lambda *_: self._on_editor_option_changed())
        self.editor_lock_map_var.trace_add("write", lambda *_: self._on_editor_option_changed())
        self.editor_auto_join_var.trace_add("write", lambda *_: self._on_editor_option_changed())
        self.editor_dead_end_var.trace_add("write", lambda *_: self._on_editor_option_changed())
        self.editor_mark_bad_road_var.trace_add("write", lambda *_: self._on_editor_option_changed())
        self.editor_edges: list[tuple[str, str]] = []
        self.editor_edge_conditions: dict[tuple[str, str], str] = dict(self.graph.road_conditions)
        self.editor_dead_end_nodes: set[str] = set()
        self.editor_current_stroke: list[str] = []
        self.editor_paths: list[Any] = []
        self.editor_markers: list[Any] = []
        self.editor_is_drawing = False
        self.editor_bindings_active = False
        self.editor_saved_bindings: dict[str, str] = {}
        self.editor_road_condition_buttons_frame: tk.Frame | None = None
        self.editor_road_condition_buttons: list[RoundedButton] = []
        self.editor_road_condition_button_by_condition: dict[str, RoundedButton] = {}
        self.editor_clear_main_frame: tk.Frame | None = None
        self.editor_clear_actions_frame: tk.Frame | None = None
        self.editor_clear_main_button: RoundedButton | None = None
        self.editor_clear_select_button: RoundedButton | None = None
        self.editor_clear_all_button: RoundedButton | None = None
        self.editor_clear_cancel_button: RoundedButton | None = None
        self.editor_graph_show_button: RoundedButton | None = None
        self.editor_graph_hide_button: RoundedButton | None = None
        self.editor_nodes_show_button: RoundedButton | None = None
        self.editor_nodes_hide_button: RoundedButton | None = None

        self.stats_driver_var = tk.StringVar(value="0")
        self.stats_customer_var = tk.StringVar(value="0")
        self.stats_active_ride_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="Sẵn sàng. Hãy sinh dữ liệu rồi chạy giả lập.")
        
        # Các nút điều khiển giả lập (sẽ được tạo trong _build_layout)
        self.pause_button: RoundedButton | None = None
        self.resume_button: RoundedButton | None = None
        self.run_button: RoundedButton | None = None
        
        # State variables for continuous manual creation
        self.add_driver_mode = False
        self.create_order_mode = False
        self.order_state_var = tk.StringVar(value="điểm đón")  # "điểm đón" hoặc "điểm đến"
        self.manual_cancel_button: RoundedButton | None = None
        self.manual_order_button: RoundedButton | None = None
        self.manual_add_driver_button: RoundedButton | None = None
        self.manual_delete_order_button: RoundedButton | None = None
        self.dashboard_user_resized = False
        self.dashboard_target_width = DASHBOARD_DEFAULT_WIDTH

        self._build_styles()
        self._build_layout()
        self._refresh_history_list()
        self._init_map()
        self._draw_graph()
        self._refresh_entities()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def run(self) -> None:
        self.root.mainloop()

    def _mark_graph_dirty(self) -> None:
        """Đánh dấu graph nền đã thay đổi để hỏi lưu khi đóng app."""

        self.graph_dirty = True

    def _graph_tool_active(self) -> bool:
        return bool(self.editor_mode_var.get() or self.editor_mark_bad_road_var.get() or self.editor_delete_graph_mode)

    def _manual_tool_active(self) -> bool:
        return bool(self.map_action)

    def _warn_unrelated_action(self, current: str, requested: str) -> None:
        messagebox.showwarning(
            "Thao tác đang sử dụng",
            f"Đang sử dụng chức năng {current}. Hãy bấm Hủy hoặc tắt chức năng hiện tại trước khi dùng {requested}.",
        )

    def _refresh_action_buttons(self) -> None:
        """Đổi màu giữ trạng thái cho các nút đang được sử dụng."""

        if self.manual_add_driver_button:
            self.manual_add_driver_button.set_active(self.map_action == "add_driver_continuous")
        if self.manual_delete_order_button:
            self.manual_delete_order_button.set_active(self.map_action == "delete_order")
        if self.manual_order_button:
            self.manual_order_button.set_active(self.map_action in {"create_order_pickup", "create_order_destination"})
        if self.manual_cancel_button:
            self.manual_cancel_button.set_active(self.map_action is not None)

        selected_condition = self.editor_road_condition_var.get()
        for condition, button in self.editor_road_condition_button_by_condition.items():
            button.set_active(self.editor_mark_bad_road_var.get() and condition == selected_condition)

        if self.editor_clear_main_button:
            self.editor_clear_main_button.set_active(self.editor_delete_graph_mode)
        if self.editor_clear_select_button:
            self.editor_clear_select_button.set_active(self.editor_delete_graph_mode)
        if self.editor_clear_all_button:
            self.editor_clear_all_button.set_active(False)
        if self.editor_clear_cancel_button:
            self.editor_clear_cancel_button.set_active(False)

        if self.editor_graph_show_button:
            self.editor_graph_show_button.set_active(self.show_graph_var.get())
        if self.editor_graph_hide_button:
            self.editor_graph_hide_button.set_active(not self.show_graph_var.get())
        if self.editor_nodes_show_button:
            self.editor_nodes_show_button.set_active(self.show_nodes_var.get())
        if self.editor_nodes_hide_button:
            self.editor_nodes_hide_button.set_active(not self.show_nodes_var.get())

    def _current_graph_data_code(self) -> str:
        """Sinh phần dữ liệu graph hiện tại để ghi lại vào app/graph_data.py."""

        def exported_name(node_id: str) -> str:
            dead_ends = getattr(self.graph, "dead_end_ids", set())
            if node_id in dead_ends and not node_id.endswith("_DEAD_END"):
                return f"{node_id}_DEAD_END"
            return node_id

        node_positions = self.graph.base_node_positions()
        edge_list = self.graph.edges_raw()
        dead_ends = sorted(getattr(self.graph, "dead_end_ids", set()))
        road_conditions = [
            (a, b, condition)
            for a, b, condition in self.graph.road_condition_items()
            if condition != ROAD_NORMAL
        ]

        lines: list[str] = []
        lines.append("GRAPH_NODES: dict[str, tuple[float, float]] = {")
        for node_id, lat, lng in node_positions:
            comment = "  # hẻm cụt" if node_id in dead_ends else ""
            lines.append(f'    "{exported_name(node_id)}": ({lat:.6f}, {lng:.6f}),{comment}')
        lines.append("}")
        lines.append("")
        lines.append("GRAPH_DEAD_ENDS = {")
        for node_id in dead_ends:
            lines.append(f'    "{exported_name(node_id)}",')
        lines.append("}")
        lines.append("")
        lines.append("GRAPH_EDGES_RAW = [")
        for a, b in edge_list:
            if a in self.graph.base_node_ids and b in self.graph.base_node_ids:
                lines.append(f'    ("{exported_name(a)}", "{exported_name(b)}"),')
        lines.append("]")
        lines.append("")
        lines.append("# Những cạnh có trạng thái đặc biệt được lưu tại đây khi người dùng chọn lưu thay đổi.")
        lines.append("# bad: trọng số x1.5, very_bad: trọng số x2.0, blocked: không cho đi qua.")
        lines.append("GRAPH_ROAD_CONDITIONS: dict[tuple[str, str], str] = {")
        for a, b, condition in road_conditions:
            if a in self.graph.base_node_ids and b in self.graph.base_node_ids:
                label = ROAD_CONDITION_LABELS.get(condition, condition)
                lines.append(f'    ("{exported_name(a)}", "{exported_name(b)}"): "{condition}",  # {label}')
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _save_graph_data_to_source(self) -> None:
        """Ghi graph hiện tại về app/graph_data.py để lần chạy sau dùng lại."""

        data_path = Path(__file__).with_name("graph_data.py")
        text = data_path.read_text(encoding="utf-8")
        start = text.index("GRAPH_NODES: dict")
        end = text.index("\nclass CampusGraph:")
        data_path.write_text(text[:start] + self._current_graph_data_code() + text[end:], encoding="utf-8")
        self.graph_dirty = False
        self._log("[Graph Editor] Đã lưu thay đổi graph vào app/graph_data.py.")

    def _on_close(self) -> None:
        """Hỏi lưu graph khi người dùng tắt chương trình."""

        if not self.graph_dirty:
            self.root.destroy()
            return

        answer = messagebox.askyesnocancel(
            "Lưu thay đổi graph",
            "Graph nền đã có thay đổi trong phiên này. Bạn có muốn lưu các node, cạnh và đánh dấu đường vào code gốc để dùng cho lần chạy sau không?",
        )
        if answer is None:
            return
        if answer:
            try:
                self._save_graph_data_to_source()
            except Exception as exc:
                close_anyway = messagebox.askyesno(
                    "Không lưu được graph",
                    f"Không lưu được thay đổi vào app/graph_data.py.\nLỗi: {exc}\n\nBạn vẫn muốn đóng chương trình không?",
                )
                if not close_anyway:
                    return
        self.root.destroy()

    def _build_styles(self) -> None:
        self.root.configure(bg=APP_BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=APP_BG)
        style.configure("TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 10))
        style.configure("Horizontal.TScale", background=SURFACE, troughcolor=MUTED_BUTTON)
        style.configure(
            "Modern.TNotebook",
            background=APP_BG,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "Modern.TNotebook.Tab",
            background=MUTED_BUTTON,
            foreground=TEXT_SECONDARY,
            padding=(18, 9),
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[("selected", SURFACE), ("active", "#DCEBFA")],
            foreground=[("selected", ACCENT), ("active", TEXT_PRIMARY)],
        )
        style.configure(
            "Comparison.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT_PRIMARY,
            rowheight=28,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.configure(
            "Comparison.Treeview.Heading",
            background=DARK_SURFACE,
            foreground=NAV_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(8, 8),
        )
        style.map(
            "Comparison.Treeview",
            background=[("selected", METRIC_BG)],
            foreground=[("selected", TEXT_PRIMARY)],
        )
        style.configure(
            "Modern.Vertical.TScrollbar",
            gripcount=0,
            background=BORDER,
            darkcolor=BORDER,
            lightcolor=BORDER,
            troughcolor=APP_BG,
            bordercolor=APP_BG,
            arrowcolor=TEXT_SECONDARY,
            relief="flat",
        )
        style.configure(
            "Modern.Horizontal.TScrollbar",
            gripcount=0,
            background=BORDER,
            darkcolor=BORDER,
            lightcolor=BORDER,
            troughcolor=SURFACE,
            bordercolor=SURFACE,
            arrowcolor=TEXT_SECONDARY,
            relief="flat",
        )
        style.configure(
            "InlineStatus.Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=TEXT_PRIMARY,
            rowheight=26,
            font=("Segoe UI", 9),
        )
        
        style.configure(
            "InlineStatus.Treeview.Heading",
            background="#E0F2FE",
            foreground="#075985",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(6, 6),
        )
        
        style.map(
            "InlineStatus.Treeview",
            background=[("selected", "#BAE6FD")],
            foreground=[("selected", "#075985")],
        )
        
        style.map(
            "InlineStatus.Treeview.Heading",
            background=[("active", "#BAE6FD")],
        )

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.main_splitter = tk.PanedWindow(
            self.root,
            orient="horizontal",
            sashwidth=8,
            sashrelief="flat",
            showhandle=False,
            bd=0,
            bg=APP_BG,
            relief="flat",
            opaqueresize=True,
        )
        self.main_splitter.grid(row=0, column=0, sticky="nsew")
        self.main_splitter.bind("<B1-Motion>", self._on_dashboard_splitter_drag, add="+")
        self.main_splitter.bind("<ButtonRelease-1>", self._on_dashboard_splitter_release, add="+")

        dashboard_outer = tk.Frame(self.main_splitter, width=DASHBOARD_DEFAULT_WIDTH, bg=APP_BG, highlightthickness=0, bd=0)
        dashboard_outer.grid_propagate(False)
        dashboard_outer.rowconfigure(0, weight=1)
        dashboard_outer.columnconfigure(0, weight=1)
        self.dashboard_outer = dashboard_outer

        self.dashboard_nav_rail = tk.Frame(
            dashboard_outer,
            width=NAV_COLLAPSED_WIDTH,
            bg=DARK_SURFACE,
            highlightthickness=0,
            bd=0,
        )
        self.dashboard_nav_rail.place(x=0, y=0, relheight=1, width=NAV_COLLAPSED_WIDTH)
        self.dashboard_nav_rail.grid_propagate(False)
        self.dashboard_nav_rail.rowconfigure(6, weight=1)
        self.dashboard_nav_expanded = False
        self.dashboard_nav_items: dict[str, dict[str, tk.Widget]] = {}
        self.active_dashboard_key: str | None = None

        self._build_dashboard_nav()

        sidebar_outer = tk.Frame(dashboard_outer, bg=APP_BG, highlightthickness=0, bd=0)
        sidebar_outer.grid(row=0, column=0, sticky="nsew", padx=(NAV_COLLAPSED_WIDTH + 10, 0))
        sidebar_outer.rowconfigure(0, weight=1)
        sidebar_outer.columnconfigure(0, weight=1)

        sidebar_canvas = tk.Canvas(sidebar_outer, highlightthickness=0, bd=0, bg=APP_BG)
        sidebar_scrollbar = ttk.Scrollbar(
            sidebar_outer,
            orient="vertical",
            command=sidebar_canvas.yview,
            style="Modern.Vertical.TScrollbar",
        )
        sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)
        sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sidebar_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))

        sidebar = tk.Frame(sidebar_canvas, bg=APP_BG, highlightthickness=0, bd=0)
        sidebar_window = sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        self.dashboard_canvas = sidebar_canvas
        self.dashboard_body = sidebar
        # Tương thích với cơ chế minh họa thuật toán từ dự án quynh.zip.
        self.sidebar_canvas = sidebar_canvas
        self.sidebar = sidebar
        self.dashboard_sections: dict[str, tk.Frame] = {
            "overview": tk.Frame(sidebar, bg=APP_BG, highlightthickness=0, bd=0),
            "rides": tk.Frame(sidebar, bg=APP_BG, highlightthickness=0, bd=0),
            "algorithm_demo": tk.Frame(sidebar, bg=APP_BG, highlightthickness=0, bd=0),
            "routes": tk.Frame(sidebar, bg=APP_BG, highlightthickness=0, bd=0),
            "history": tk.Frame(sidebar, bg=APP_BG, highlightthickness=0, bd=0),
        }

        def _on_sidebar_configure(_event: tk.Event) -> None:
            sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))

        def _on_sidebar_canvas_configure(event: tk.Event) -> None:
            sidebar_canvas.itemconfigure(sidebar_window, width=event.width)

        def _on_sidebar_mousewheel(event: tk.Event) -> None:
            if getattr(event, "num", None) == 4:
                sidebar_canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                sidebar_canvas.yview_scroll(3, "units")
            else:
                sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_sidebar_mousewheel(_event: tk.Event) -> None:
            sidebar_canvas.bind_all("<MouseWheel>", _on_sidebar_mousewheel)
            sidebar_canvas.bind_all("<Button-4>", _on_sidebar_mousewheel)
            sidebar_canvas.bind_all("<Button-5>", _on_sidebar_mousewheel)

        def _unbind_sidebar_mousewheel(_event: tk.Event) -> None:
            sidebar_canvas.unbind_all("<MouseWheel>")
            sidebar_canvas.unbind_all("<Button-4>")
            sidebar_canvas.unbind_all("<Button-5>")

        sidebar.bind("<Configure>", _on_sidebar_configure)
        sidebar_canvas.bind("<Configure>", _on_sidebar_canvas_configure)
        sidebar_canvas.bind("<Enter>", _bind_sidebar_mousewheel)
        sidebar_canvas.bind("<Leave>", _unbind_sidebar_mousewheel)

        # ==============================================================
        # Dashboard: Tổng quan
        # ==============================================================
        overview_section = self.dashboard_sections["overview"]
        self._dashboard_page_title(
            overview_section,
            "Tổng quan",
            "Thiết lập dữ liệu, tạo thủ công, chú thích bản đồ và log thuật toán.",
        )

        group_card = RoundedFrame(overview_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        group_card.pack(fill="x", pady=(0, 14))
        self._section_header(group_card.body, "Nhóm 14", "Thông tin thành viên và mức độ hoàn thành")

        members_table = tk.Frame(group_card.body, bg=SURFACE)
        members_table.pack(fill="x", pady=(8, 2))
        members_table.columnconfigure(0, weight=3)
        members_table.columnconfigure(1, weight=2)
        members_table.columnconfigure(2, weight=2)

        member_headers = ["Họ và Tên", "MSSV", "Mức độ hoàn thành (%)"]
        for col, header_text in enumerate(member_headers):
            tk.Label(
                members_table,
                text=header_text,
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 9, "bold"),
                anchor="center",
            ).grid(row=0, column=col, sticky="ew", padx=3, pady=(0, 6))

        members = [
            ("Đặng Nguyễn Minh Khoa", "24110253", "100"),
            ("Tôn Nữ Phương Quỳnh", "24110316", "100"),
            ("Nguyễn Thị Trúc Mai", "24110284", "100"),
        ]
        for row, member in enumerate(members, start=1):
            for col, value in enumerate(member):
                tk.Label(
                    members_table,
                    text=value,
                    bg=SURFACE,
                    fg=TEXT_PRIMARY if col == 0 else TEXT_SECONDARY,
                    font=("Segoe UI", 8, "bold" if col == 2 else "normal"),
                    anchor="center" if col > 0 else "w",
                ).grid(row=row, column=col, sticky="ew", padx=3, pady=3)

        control_card = RoundedFrame(overview_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        control_card.pack(fill="x", pady=(0, 14))
        self._section_header(control_card.body, "Thiết lập dữ liệu", "Điều chỉnh số lượng và tốc độ minh họa")
        self._build_slider(control_card.body, "Số tài xế", self.driver_count_var, 1, 40)
        self._build_slider(control_card.body, "Số khách hàng", self.customer_count_var, 1, 12)
        self._build_slider(control_card.body, "Tốc độ demo (ms/lần cập nhật)", self.animation_interval_var, 10, 2000)

        algorithm_box = tk.Frame(control_card.body, bg=control_card.body["bg"])
        algorithm_box.pack(fill="x", pady=(8, 4))
        algorithm_box.columnconfigure(1, weight=1)

        tk.Label(
            algorithm_box,
            text="Tìm tài xế:",
            bg=control_card.body["bg"],
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        ttk.Combobox(
            algorithm_box,
            textvariable=self.driver_algorithm_var,
            values=DRIVER_SEARCH_ALGORITHMS,
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="ew", pady=(0, 4))

        tk.Label(
            algorithm_box,
            text="Tìm đường:",
            bg=control_card.body["bg"],
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            algorithm_box,
            textvariable=self.route_algorithm_var,
            values=ROUTE_SEARCH_ALGORITHMS,
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="ew")

        self._build_button(
            control_card.body,
            "Sinh tài xế ngẫu nhiên",
            self.generate_random_drivers,
            fill=ACCENT,
            hover_fill=ACCENT_HOVER,
        )
        self._build_button(
            control_card.body,
            "Sinh khách hàng ngẫu nhiên",
            self.generate_random_customers,
            fill=ACCENT,
            hover_fill=ACCENT_HOVER,
        )

        button_container = tk.Frame(control_card.body, bg=control_card.body["bg"])
        button_container.pack(fill="x", pady=(8, 0))

        self.run_button = RoundedButton(
            button_container,
            "Chạy giả lập",
            self.run_simulation,
            bg=control_card.body["bg"],
            fill=SUCCESS,
            hover_fill=SUCCESS_HOVER,
        )
        self.run_button.pack(fill="x", side="left", expand=True, padx=(0, 4))

        self.pause_button = RoundedButton(
            button_container,
            "Tạm dừng",
            self.pause_simulation,
            bg=control_card.body["bg"],
            fill="#F59E0B",
            hover_fill="#D97706",
        )
        self.pause_button.pack(fill="x", side="left", expand=True, padx=2)
        self.pause_button.pack_forget()

        self.resume_button = RoundedButton(
            button_container,
            "Tiếp tục",
            self.resume_simulation,
            bg=control_card.body["bg"],
            fill=SUCCESS,
            hover_fill=SUCCESS_HOVER,
        )
        self.resume_button.pack(fill="x", side="left", expand=True, padx=(4, 0))
        self.resume_button.pack_forget()

        reload_reset_frame = tk.Frame(control_card.body, bg=control_card.body["bg"])
        reload_reset_frame.pack(fill="x", pady=(8, 0))
        reload_reset_frame.columnconfigure(0, weight=1, uniform="reload_reset")
        reload_reset_frame.columnconfigure(1, weight=1, uniform="reload_reset")

        reload_button = RoundedButton(
            reload_reset_frame,
            "Tải lại",
            self.clear_routes,
            bg=control_card.body["bg"],
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        reload_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        reset_button = RoundedButton(
            reload_reset_frame,
            "Làm mới",
            self.reset_demo,
            bg=control_card.body["bg"],
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        reset_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._build_button(
            control_card.body,
            "So sánh thuật toán",
            self.show_algorithm_comparison,
            fill=DANGER,
            hover_fill=DANGER_HOVER,
        )

        manual_card = RoundedFrame(overview_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        manual_card.pack(fill="x", pady=(0, 14))
        self._section_header(manual_card.body, "Tạo thủ công", "Click gần đường/node để tạo dữ liệu mới")

        tk.Label(
            manual_card.body,
            text="Tạo tài xế",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 4))

        driver_button_frame = tk.Frame(manual_card.body, bg=SURFACE)
        driver_button_frame.pack(fill="x")
        driver_button_frame.columnconfigure(0, weight=1)

        self.manual_add_driver_button = RoundedButton(
            driver_button_frame,
            "Thêm tài xế",
            self.begin_add_driver,
            bg=SURFACE,
            fill=ACCENT,
            hover_fill=ACCENT_HOVER,
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.manual_add_driver_button.grid(row=0, column=0, sticky="ew")

        tk.Label(
            manual_card.body,
            text="Tạo đơn đặt xe",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 4))

        order_button_frame = tk.Frame(manual_card.body, bg=SURFACE)
        order_button_frame.pack(fill="x")
        order_button_frame.columnconfigure(0, weight=1, uniform="manual_btn")
        order_button_frame.columnconfigure(1, weight=1, uniform="manual_btn")

        self.manual_order_button = RoundedButton(
            order_button_frame,
            "Tạo",
            self.begin_create_order,
            bg=SURFACE,
            fill="#F97316",
            hover_fill="#EA580C",
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.manual_order_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.manual_delete_order_button = RoundedButton(
            order_button_frame,
            "Xóa",
            self.delete_order,
            bg=SURFACE,
            fill=DANGER,
            hover_fill=DANGER,
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.manual_delete_order_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.manual_cancel_button = RoundedButton(
            manual_card.body,
            "Hủy",
            self.cancel_manual_action,
            bg=SURFACE,
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
            height=34,
            width=1,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.manual_cancel_button.pack_forget()

        legend_card = RoundedFrame(overview_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        legend_card.pack(fill="x", pady=(0, 14))
        self._section_header(legend_card.body, "Chú thích bản đồ", "Màu marker và tuyến đường")
        legend_grid = tk.Frame(legend_card.body, bg=SURFACE)
        legend_grid.pack(fill="x", pady=(8, 0))
        self._legend_item(legend_grid, "Tài xế rảnh", COLOR_DRIVER_FREE, 0, 0)
        self._legend_item(legend_grid, "Tài xế bận", COLOR_DRIVER_BUSY, 0, 1)
        self._legend_item(legend_grid, "Điểm đón", COLOR_CUSTOMER, 1, 0)
        self._legend_item(legend_grid, "Điểm đến", COLOR_DESTINATION, 1, 1)
        self._legend_item(legend_grid, "Xe đến khách", COLOR_ROUTE_PICKUP, 2, 0)
        self._legend_item(legend_grid, "Khách đến đích", COLOR_ROUTE_DROPOFF, 2, 1)

        log_card = RoundedFrame(overview_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        log_card.pack(fill="both", expand=True, pady=(0, 6))
        self._section_header(log_card.body, "Log thuật toán", "Kết quả xử lý của mô phỏng")
        log_frame = tk.Frame(log_card.body, bg=SURFACE)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            font=("Cascadia Mono", 9),
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground=LOG_FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
        )
        log_scroll = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # ==============================================================
        # Dashboard: Quản lý chuyến xe
        # ==============================================================
        rides_section = self.dashboard_sections["rides"]
        self._dashboard_page_title(
            rides_section,
            "Quản lý chuyến xe",
            "Thông tin chuyến xe và thông tin tài xế đang hoạt động.",
        )
        self.driver_info_card = RoundedFrame(
            rides_section,
            radius=22,
            padding=0,
            bg=APP_BG,
            fill=SURFACE,
            outline=BORDER,
        )
        self.driver_info_card.pack(fill="both", expand=True, pady=(0, 14))
        self._render_empty_driver_info()

        # ==============================================================
        # Dashboard: Minh họa thuật toán
        # ==============================================================
        algorithm_demo_section = self.dashboard_sections["algorithm_demo"]
        self._dashboard_page_title(
            algorithm_demo_section,
            "Minh họa thuật toán",
            "Click vào điểm đón của khách hàng trên bản đồ để xem hàng đợi tìm tài xế.",
        )
        self.algorithm_demo_card = RoundedFrame(
            algorithm_demo_section,
            radius=22,
            padding=0,
            bg=APP_BG,
            fill=SURFACE,
            outline=BORDER,
        )
        self.algorithm_demo_card.pack(fill="both", expand=True, pady=(0, 14))
        self._render_empty_algorithm_demo_info()

        # ==============================================================
        # Dashboard: Đường đi
        # ==============================================================
        routes_section = self.dashboard_sections["routes"]
        self._dashboard_page_title(
            routes_section,
            "Đường đi",
            "Graph Editor dùng để vẽ, nối, đánh dấu và lưu cấu trúc đường nội bộ.",
        )
        editor_card = RoundedFrame(routes_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        editor_card.pack(fill="x", pady=(0, 14))
        self._section_header(editor_card.body, "Graph Editor", "Chọn node và tự động nối đường khi vẽ")
        self._build_checkbox(
            editor_card.body,
            "Bật chế độ vẽ graph",
            self.editor_mode_var,
            command=self._on_editor_option_changed,
        )
        self._build_checkbox(
            editor_card.body,
            "Khóa bản đồ khi vẽ",
            self.editor_lock_map_var,
            command=self._on_editor_option_changed,
        )
        self._build_checkbox(
            editor_card.body,
            "Nối vào node gần nhất",
            self.editor_auto_join_var,
            command=self._on_editor_option_changed,
        )
        self._build_checkbox(
            editor_card.body,
            "Đánh dấu node cuối là hẻm cụt",
            self.editor_dead_end_var,
            command=self._on_editor_option_changed,
        )
        self._build_checkbox(
            editor_card.body,
            "Đánh dấu đường xấu",
            self.editor_mark_bad_road_var,
            command=self._on_editor_option_changed,
        )
        self._build_road_condition_buttons(editor_card.body)
        self._build_slider(editor_card.body, "Khoảng cách tạo node mới (m)", self.editor_min_point_distance_var, 5, 60)
        self._build_slider(editor_card.body, "Bán kính bắt node cũ (m)", self.editor_snap_distance_var, 5, 80)
        self._build_graph_display_controls(editor_card.body)
        self._build_button(
            editor_card.body,
            "Hoàn tác node cuối",
            self.editor_undo_last_node,
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
        )
        self._build_graph_clear_controls(editor_card.body)

        # ==============================================================
        # Dashboard: Lịch sử
        # ==============================================================
        history_section = self.dashboard_sections["history"]
        self._dashboard_page_title(
            history_section,
            "Lịch sử",
            "Danh sách chuyến đi đã hoàn tất trong phiên demo hiện tại.",
        )
        history_card = RoundedFrame(history_section, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        history_card.pack(fill="x", pady=(0, 14))
        self._section_header(history_card.body, "Lịch sử chuyến đi", "Chọn chuyến cũ để xem lại trên bản đồ")
        self.history_listbox = tk.Listbox(
            history_card.body,
            height=8,
            bg=SURFACE_SOFT,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            font=("Segoe UI", 8),
        )
        self.history_listbox.pack(fill="x", pady=(8, 6))
        self.history_listbox.bind("<<ListboxSelect>>", lambda _event: self.show_selected_history())
        self._build_button(
            history_card.body,
            "Hiển thị chuyến đã chọn",
            self.show_selected_history,
            fill=ACCENT,
            hover_fill=ACCENT_HOVER,
        )
        self._build_button(
            history_card.body,
            "Ẩn tuyến lịch sử",
            self.clear_history_overlay,
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
        )


        main = tk.Frame(self.main_splitter, bg=APP_BG, highlightthickness=0, bd=0)
        self.main_splitter.add(dashboard_outer, minsize=DASHBOARD_MIN_WIDTH)
        self.main_splitter.add(main, minsize=620)
        main.rowconfigure(1, weight=1, minsize=620)
        main.columnconfigure(0, weight=1)

        topbar = RoundedFrame(main, radius=20, padding=12, bg=APP_BG, fill=SURFACE, outline=BORDER)
        topbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        topbar.body.columnconfigure(0, weight=1)
        topbar.body.columnconfigure(1, weight=0)
        title_block = tk.Frame(topbar.body, bg=SURFACE)
        title_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="Bản đồ mô phỏng hệ thống đặt xe",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            textvariable=self.status_var,
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        topbar_stats = tk.Frame(topbar.body, bg=SURFACE)
        topbar_stats.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._build_topbar_demo_summary(topbar_stats)

        map_shell = RoundedFrame(main, radius=22, padding=6, bg=APP_BG, fill=SURFACE, outline=BORDER)
        map_shell.grid(row=1, column=0, sticky="nsew")
        map_shell.body.rowconfigure(0, weight=1)
        map_shell.body.columnconfigure(0, weight=1)

        self.map_container = tk.Frame(map_shell.body, bg=SURFACE, highlightthickness=0, bd=0)
        self.map_container.grid(row=0, column=0, sticky="nsew")

        footer = tk.Frame(main, bg=APP_BG)
        footer.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        tk.Label(
            footer,
            text="Gợi ý: sinh dữ liệu trước, sau đó chạy giả lập để quan sát tài xế di chuyển từ vị trí ban đầu đến điểm đón và điểm đến.",
            bg=APP_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
        ).pack(anchor="w")


        self._show_dashboard_section("overview")
        self.root.bind("<Configure>", self._sync_dashboard_width, add="+")
        self.root.after(150, self._sync_dashboard_width)

    def _sync_dashboard_width(self, _event: tk.Event | None = None) -> None:
        if _event is not None and getattr(_event, "widget", None) is not self.root:
            return
        outer = getattr(self, "dashboard_outer", None)
        splitter = getattr(self, "main_splitter", None)
        if outer is None or splitter is None:
            return

        root_width = self.root.winfo_width()
        if root_width <= 1:
            root_width = self.root.winfo_screenwidth()

        if not self.dashboard_user_resized:
            target_width = max(DASHBOARD_MIN_WIDTH, int(root_width * DASHBOARD_WIDTH_RATIO))
            target_width = min(target_width, DASHBOARD_MAX_WIDTH)
            target_width = max(target_width, DASHBOARD_DEFAULT_WIDTH)
            self.dashboard_target_width = target_width
            try:
                splitter.sash_place(0, target_width, 0)
            except tk.TclError:
                pass
        else:
            current_width = outer.winfo_width()
            if current_width < DASHBOARD_MIN_WIDTH:
                try:
                    splitter.sash_place(0, DASHBOARD_MIN_WIDTH, 0)
                except tk.TclError:
                    pass

    def _on_dashboard_splitter_drag(self, _event: tk.Event | None = None) -> None:
        self.dashboard_user_resized = True

    def _on_dashboard_splitter_release(self, _event: tk.Event | None = None) -> None:
        self.dashboard_user_resized = True
        outer = getattr(self, "dashboard_outer", None)
        if outer is not None:
            self.dashboard_target_width = max(DASHBOARD_MIN_WIDTH, outer.winfo_width())

    def _bind_dashboard_nav_hover(self, widget: tk.Widget) -> None:
        widget.bind("<Enter>", lambda _event: self._set_dashboard_nav_expanded(True), add="+")

    def _build_dashboard_nav(self) -> None:
        nav = getattr(self, "dashboard_nav_rail", None)
        if not nav:
            return

        nav.configure(bg=NAV_BG)
        nav.columnconfigure(0, weight=1)
        nav.bind("<Enter>", lambda _event: self._set_dashboard_nav_expanded(True))
        nav.bind("<Leave>", lambda _event: self._set_dashboard_nav_expanded(False))

        header_shell = tk.Frame(nav, bg=NAV_BG, highlightthickness=0, bd=0)
        header_shell.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 8))
        header_shell.columnconfigure(0, weight=0)
        header_shell.columnconfigure(1, weight=1)

        menu_button = tk.Label(
            header_shell,
            text="☰",
            bg=NAV_BG,
            fg=NAV_TEXT,
            font=("Segoe UI", 19, "bold"),
            anchor="w",
            padx=12,
            pady=10,
            cursor="hand2",
        )
        menu_button.grid(row=0, column=0, sticky="w")
        self.dashboard_menu_button = menu_button
        self._bind_dashboard_nav_hover(menu_button)

        brand_label = tk.Label(
            header_shell,
            text="QKM SmartRide",
            bg=NAV_BG,
            fg=NAV_TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        brand_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self.dashboard_brand_label = brand_label
        self._bind_dashboard_nav_hover(brand_label)

        nav_items = [
            ("overview", "▦", "Tổng quan"),
            ("rides", "▤", "Quản lý chuyến xe"),
            ("algorithm_demo", "▧", "Minh họa thuật toán"),
            ("routes", "▣", "Đường đi"),
            ("history", "▥", "Lịch sử"),
        ]
        for row_index, (key, icon, label) in enumerate(nav_items, start=1):
            button = NavItemButton(
                nav,
                icon,
                label,
                lambda section_key=key: self._show_dashboard_section(section_key),
                bg=NAV_BG,
            )
            button.grid(row=row_index, column=0, sticky="ew", padx=8, pady=(4, 0))
            self._bind_dashboard_nav_hover(button)
            self.dashboard_nav_items[key] = {"button": button}

        bottom_hint = tk.Label(
            nav,
            text="QKM",
            bg=NAV_BG,
            fg=NAV_MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor="center",
            pady=10,
        )
        bottom_hint.grid(row=7, column=0, sticky="sew", padx=12)
        self.dashboard_nav_hint = bottom_hint

        self._set_dashboard_nav_expanded(False)

    def _set_dashboard_nav_expanded(self, expanded: bool) -> None:
        nav = getattr(self, "dashboard_nav_rail", None)
        items = getattr(self, "dashboard_nav_items", {})
        if not nav:
            return

        self.dashboard_nav_expanded = expanded
        target_width = NAV_EXPANDED_WIDTH if expanded else NAV_COLLAPSED_WIDTH
        nav.configure(width=target_width)
        try:
            nav.place_configure(width=target_width)
            nav.grid_propagate(False)
            nav.tkraise()
            nav.update_idletasks()
        except tk.TclError:
            pass

        for item in items.values():
            button = item.get("button")
            if hasattr(button, "set_expanded"):
                button.set_expanded(expanded)

        menu_button = getattr(self, "dashboard_menu_button", None)
        if menu_button is not None:
            menu_button.configure(anchor="w", padx=12, bg=NAV_BG, fg=NAV_TEXT)

        brand_label = getattr(self, "dashboard_brand_label", None)
        if brand_label is not None:
            if expanded:
                brand_label.grid()
            else:
                brand_label.grid_remove()

        hint = getattr(self, "dashboard_nav_hint", None)
        if hint is not None:
            hint.configure(
                text="QKM SmartRide" if expanded else "QKM",
                anchor="w" if expanded else "center",
                fg=NAV_TEXT if expanded else NAV_MUTED,
            )

    def _show_dashboard_section(self, key: str) -> None:
        sections = getattr(self, "dashboard_sections", None)
        if not sections or key not in sections:
            return

        for section in sections.values():
            section.pack_forget()
        sections[key].pack(fill="both", expand=True)
        self.active_dashboard_key = key
        self._update_dashboard_nav_selection()

        canvas = getattr(self, "dashboard_canvas", None)
        body = getattr(self, "dashboard_body", None)
        if canvas is not None and body is not None:
            canvas.yview_moveto(0)
            self.root.after_idle(lambda: canvas.configure(scrollregion=canvas.bbox("all")))

    def _update_dashboard_nav_selection(self) -> None:
        items = getattr(self, "dashboard_nav_items", {})
        active_key = getattr(self, "active_dashboard_key", None)
        for key, item in items.items():
            button = item.get("button")
            if hasattr(button, "set_selected"):
                button.set_selected(key == active_key)

    def _dashboard_page_title(self, parent: tk.Frame, title: str, subtitle: str) -> None:
        header = tk.Frame(parent, bg=APP_BG)
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header,
            text=title,
            bg=APP_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=subtitle,
            bg=APP_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _build_topbar_demo_summary(self, parent: tk.Frame) -> None:
        
        metrics = tk.Frame(parent, bg=SURFACE)
        metrics.pack(anchor="e")
        self._topbar_metric(metrics, "Tài xế", self.stats_driver_var, 0)
        self._topbar_metric(metrics, "Khách", self.stats_customer_var, 1)
        self._topbar_metric(metrics, "Chuyến", self.stats_active_ride_var, 2)

    def _topbar_metric(self, parent: tk.Frame, label: str, variable: tk.StringVar, col: int) -> None:
        box = tk.Frame(parent, bg=METRIC_BG, highlightbackground=METRIC_BORDER, highlightthickness=1)
        box.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
        tk.Label(
            box,
            textvariable=variable,
            bg=METRIC_BG,
            fg=ACCENT,
            font=("Segoe UI", 15, "bold"),
            width=4,
        ).pack(side="left", padx=(10, 4), pady=8)
        tk.Label(
            box,
            text=label,
            bg=METRIC_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 10), pady=8)

    # ------------------------------------------------------------------
    # Thẻ thông tin tài xế / chuyến đi
    # ------------------------------------------------------------------
    def _clear_driver_info_card(self) -> None:
        if not self.driver_info_card:
            return
        for child in self.driver_info_card.body.winfo_children():
            child.destroy()

    def _render_empty_driver_info(self) -> None:
        self.selected_driver_id = None
        self._clear_driver_info_card()
        if not self.driver_info_card:
            return

        body = self.driver_info_card.body
        body.configure(bg=SURFACE)

        header = tk.Frame(body, bg=METRIC_BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Thông tin chuyến đi",
            bg=METRIC_BG,
            fg=ACCENT,
            font=("Segoe UI", 12, "bold"),
            padx=16,
            pady=10,
        ).pack(anchor="w")

        tk.Label(
            body,
            text=(
                "Sau khi sinh dữ liệu hoặc chạy giả lập, click vào marker tài xế "
                "để xem thông tin tài xế và chuyến đi đang phụ trách."
            ),
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 10),
            wraplength=320,
            justify="left",
            padx=16,
            pady=16,
        ).pack(anchor="w")

    def _money_text(self, value: int) -> str:
        return f"{value:,}".replace(",", ".") + " VND"

    def _estimate_fare_vnd(self, ride: ActiveRide) -> int:
        total_km = ride.pickup_distance_km + ride.dropoff_distance_km
        base_fare = 12000
        per_km = 4500
        fare = base_fare + int(total_km * per_km)
        return max(18000, round(fare / 1000) * 1000)

    def _find_active_ride_by_driver_id(self, driver_id: str) -> ActiveRide | None:
        for ride in self.sim.active_rides:
            if ride.driver.id == driver_id and ride.stage != "done":
                return ride
        return None

    def _render_badge_row(self, parent: tk.Frame, badges: tuple[str, ...]) -> None:
        if not badges:
            return

        tk.Label(
            parent,
            text="Tài xế được biết đến vì",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="center", pady=(4, 2))

        badge_box = tk.Frame(parent, bg=SURFACE)
        badge_box.pack(fill="x", padx=10, pady=(2, 8))
        visible_badges = badges[:3]
        for badge in visible_badges:
            item = tk.Frame(badge_box, bg=SURFACE)
            item.pack(side="left", expand=True, fill="x", padx=2)
            tk.Label(
                item,
                text="⬡",
                bg=SURFACE,
                fg="#14B8A6",
                font=("Segoe UI", 18, "bold"),
            ).pack()
            tk.Label(
                item,
                text=badge,
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 7, "bold"),
                wraplength=82,
                justify="center",
            ).pack()

    def _render_route_info(self, parent: tk.Frame, ride: ActiveRide | None) -> None:
        route_box = tk.Frame(parent, bg=SURFACE)
        route_box.pack(fill="x", padx=12, pady=(12, 8))
        route_box.columnconfigure(1, weight=1)
    
        if ride:
            pickup_text = f"{ride.customer.id} - Điểm đón\nNode: {ride.customer.pickup_node_id}"
            dest_text = f"{ride.customer.id} - Điểm đến\nNode: {ride.customer.destination_node_id}"
        else:
            pickup_text = "Chưa có chuyến đang chạy"
            dest_text = "Chưa có điểm đến"
    
        tk.Label(
            route_box,
            text="Đón",
            bg=SURFACE,
            fg="#0E7490",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="nw", padx=(0, 12), pady=(0, 10))
    
        tk.Label(
            route_box,
            text=pickup_text,
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
            justify="left",
            wraplength=340,
        ).grid(row=0, column=1, sticky="w", pady=(0, 10))
    
        tk.Label(
            route_box,
            text="Đến",
            bg=SURFACE,
            fg="#EF4444",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=1, column=0, sticky="nw", padx=(0, 12), pady=(8, 0))
    
        tk.Label(
            route_box,
            text=dest_text,
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
            justify="left",
            wraplength=340,
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))
    def _render_driver_trip_info(self, driver: Driver, *, switch_to_rides: bool = True) -> None:
        self._clear_driver_info_card()
        if not self.driver_info_card:
            return

        self.selected_driver_id = driver.id
        profile = get_driver_profile(driver.id)
        ride = self._find_active_ride_by_driver_id(driver.id)

        # Lấy chuyến đã hoàn thành gần nhất của tài xế.
        # thẻ thông tin vẫn hiển thị trạng thái hoàn thành thay vì chỉ rơi về thông tin rảnh chung.
        completed_history: RideHistory | None = None
        if ride is None and not driver.busy:
            for history in reversed(self.sim.ride_history):
                if history.driver_id == driver.id:
                    completed_history = history
                    break

        body = self.driver_info_card.body
        body.configure(bg=SURFACE)

        if ride:
            if ride.stage == "to_pickup":
                title = "Tài xế đang đến điểm đón"
            elif ride.stage == "to_dropoff":
                title = "Tài xế đang chở khách"
            else:
                title = "Thông tin chuyến đi"
        elif completed_history is not None:
            title = "Tài xế đã hoàn thành chuyến"
        elif driver.busy:
            title = "Tài xế đang phục vụ chuyến"
        else:
            title = "Thông tin tài xế"

        header = tk.Frame(body, bg=METRIC_BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text=title,
            bg=METRIC_BG,
            fg=ACCENT,
            font=("Segoe UI", 12, "bold"),
            padx=16,
            pady=10,
        ).pack(anchor="w")

        profile_box = tk.Frame(body, bg=SURFACE)
        profile_box.pack(fill="x", padx=12, pady=(10, 6))

        avatar = tk.Canvas(profile_box, width=50, height=50, bg=SURFACE, highlightthickness=0)
        avatar.create_oval(4, 4, 46, 46, fill="#E2E8F0", outline="#CBD5E1")
        avatar.create_text(25, 25, text=driver.id, fill=TEXT_PRIMARY, font=("Segoe UI", 9, "bold"))
        avatar.pack(side="left")

        name_box = tk.Frame(profile_box, bg=SURFACE)
        name_box.pack(side="left", padx=(12, 0), fill="x", expand=True)
        tk.Label(
            name_box,
            text=profile.name,
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            name_box,
            text=f"{profile.vehicle_name} • {profile.license_plate}",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            name_box,
            text=f"Đánh giá {profile.rating:.1f}  |  Tỉ lệ nhận {profile.acceptance_rate}%",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        if ride is not None:
            pay_box = tk.Frame(body, bg="#DCFCE7", highlightbackground="#DCFCE7", highlightthickness=1)
            pay_box.pack(fill="x", padx=10, pady=(6, 8))
            pay_box.columnconfigure(0, weight=1)
            pay_box.columnconfigure(1, weight=1)
            tk.Label(
                pay_box,
                text=profile.payment_method,
                bg="#DEFCE7",
                fg="#0F5D3F",
                font=("Segoe UI", 12, "bold"),
                padx=10,
                pady=8,
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                pay_box,
                text=self._money_text(self._estimate_fare_vnd(ride)),
                bg="#DCFCE7",
                fg="#0F5D3F",
                font=("Segoe UI", 12, "bold"),
                padx=10,
                pady=8,
            ).grid(row=0, column=1, sticky="e")

        self._render_badge_row(body, profile.badges)

        if completed_history is None:
            self._render_route_info(body, ride)

        detail_box = tk.Frame(body, bg=SURFACE)
        detail_box.pack(fill="x", padx=12, pady=(18, 18))
        detail_box.columnconfigure(0, weight=1)
        detail_box.columnconfigure(1, weight=1)

        if ride:
            total_km = ride.pickup_distance_km + ride.dropoff_distance_km

            tk.Label(
                detail_box,
                text=f"Đón khách: {ride.pickup_distance_km:.2f} km",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=0, sticky="w", pady=(0, 12))

            tk.Label(
                detail_box,
                text=f"Khoảng cách đến đích: {ride.dropoff_distance_km:.2f} km",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=1, sticky="w", padx=(30, 0), pady=(0, 12))

            tk.Label(
                detail_box,
                text=f"Tổng quãng đường: {total_km:.2f} km",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=0, sticky="w")

            tk.Label(
                detail_box,
                text=f"Trạng thái chuyến: {ride.stage}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=1, sticky="w", padx=(30, 0))

        elif completed_history is not None:
            tk.Label(
                detail_box,
                text=f"Dịch vụ: {profile.service}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=0, sticky="w", pady=(0, 18))

            tk.Label(
                detail_box,
                text=f"SĐT: {profile.phone}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=1, sticky="w", padx=(36, 0), pady=(0, 18))

            tk.Label(
                detail_box,
                text=f"Vị trí hiện tại: {driver.node_id}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=0, sticky="w")

            tk.Label(
                detail_box,
                text="Trạng thái: Rảnh",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=1, sticky="w", padx=(36, 0))

        else:
            tk.Label(
                detail_box,
                text=f"Dịch vụ: {profile.service}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=0, sticky="w", pady=(0, 12))

            tk.Label(
                detail_box,
                text=f"SĐT: {profile.phone}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=0, column=1, sticky="w", padx=(30, 0), pady=(0, 12))

            tk.Label(
                detail_box,
                text=f"Vị trí hiện tại: {driver.node_id}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=0, sticky="w")

            tk.Label(
                detail_box,
                text=f"Trạng thái: {'Bận' if driver.busy else 'Rảnh'}",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                font=("Segoe UI", 10),
            ).grid(row=1, column=1, sticky="w", padx=(30, 0))
        button_frame = tk.Frame(body, bg=SURFACE)
        button_frame.pack(fill="x", padx=12, pady=(6, 10))
        if ride is not None:
            self._build_button(
                button_frame,
                "Hủy chuyến",
                self.cancel_selected_ride,
                fill=DANGER,
                hover_fill=DANGER_HOVER,
                fg="#FFFFFF",
            )
        else:
            self._build_button(
                button_frame,
                "Xóa tài xế",
                lambda driver_id=driver.id: self.delete_selected_driver(driver_id),
                fill=DANGER,
                hover_fill=DANGER_HOVER,
                fg="#FFFFFF",
            )
        self._build_button(
            button_frame,
            "Đóng thông tin",
            self._render_empty_driver_info,
            fill="#F59E0B",
            hover_fill="#D97706",
            fg="#FFFFFF",
        )

        if switch_to_rides and hasattr(self, "dashboard_sections"):
            self._show_dashboard_section("rides")

    def _render_empty_algorithm_demo_info(self) -> None:
        """Hiển thị trạng thái rỗng cho menu Minh họa thuật toán."""
        card = getattr(self, "algorithm_demo_card", None)
        if not card:
            return
        for child in card.body.winfo_children():
            child.destroy()

        shell = tk.Frame(card.body, bg=SURFACE)
        shell.pack(fill="both", expand=True, padx=16, pady=18)
        tk.Label(
            shell,
            text="Chưa chọn điểm đón",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="Click vào marker khách hàng/điểm đón trên bản đồ để mở hàng đợi minh họa tìm tài xế.",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9),
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _find_customer_by_id(self, customer_id: str) -> Customer | None:
        for customer in self.sim.customers:
            if customer.id == customer_id:
                return customer
        for ride in self.sim.active_rides:
            if ride.customer.id == customer_id:
                return ride.customer
        return None

    def _find_active_ride_by_customer_id(self, customer_id: str) -> ActiveRide | None:
        for ride in self.sim.active_rides:
            if ride.customer.id == customer_id and ride.stage != "done":
                return ride
        return None

    def show_algorithm_demo_for_customer(self, customer_id: str) -> None:
        """Mở menu Minh họa thuật toán từ marker điểm đón của khách hàng."""
        self.algorithm_demo_customer_id = customer_id
        self._cancel_inline_queue_animation()
        self._render_algorithm_demo_for_customer(customer_id)
        self._show_dashboard_section("algorithm_demo")
        self.status_var.set(f"Đang minh họa thuật toán tìm tài xế cho {customer_id}.")

    def _render_algorithm_demo_for_customer(self, customer_id: str | None) -> None:
        card = getattr(self, "algorithm_demo_card", None)
        if not card:
            return

        self._cancel_inline_queue_animation()
        for child in card.body.winfo_children():
            child.destroy()

        if not customer_id:
            self._render_empty_algorithm_demo_info()
            return

        customer = self._find_customer_by_id(customer_id)
        if customer is None:
            self._render_empty_algorithm_demo_info()
            return

        active_ride = self._find_active_ride_by_customer_id(customer.id)
        demo_context = active_ride if active_ride is not None else SimpleNamespace(customer=customer, driver=None)
        self.inline_demo_status_var.set("Chọn thuật toán để bắt đầu minh họa hàng đợi.")

        header = tk.Frame(card.body, bg=SURFACE)
        header.pack(fill="x", padx=14, pady=(14, 4))
        tk.Label(
            header,
            text=f"Điểm đón {customer.id}",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=(
                f"Node đón: {customer.pickup_node_id}  |  "
                f"Điểm đến: {customer.destination_node_id}  |  "
                f"Trạng thái: {'đang có chuyến' if active_ride else 'đang chờ gán tài xế'}"
            ),
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

        self._render_algorithm_demo_inside_driver_info(card.body, demo_context)


    def _render_algorithm_demo_inside_driver_info(self, parent: tk.Frame, ride: Any) -> None:
        demo_box = tk.Frame(
            parent,
            bg="#FFFFFF",
            highlightbackground="#CBD5E1",
            highlightthickness=1,
        )
        demo_box.pack(fill="x", padx=10, pady=(8, 10))

        header = tk.Frame(demo_box, bg="#0F172A")
        header.pack(fill="x")

        tk.Label(
            header,
            text="Hàng đợi minh họa thuật toán",
            bg="#0F172A",
            fg="#FFFFFF",
            font=("Segoe UI", 12, "bold"),
            padx=12,
            pady=8,
        ).pack(anchor="w")

        content = tk.Frame(demo_box, bg="#FFFFFF")
        content.pack(fill="both", expand=True, padx=10, pady=10)

        title_row = tk.Frame(content, bg="#FFFFFF")
        title_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            title_row,
            text="Hàng đợi mô phỏng",
            bg="#FFFFFF",
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        status_note = tk.Label(
            content,
            textvariable=self.inline_demo_status_var,
            bg="#EAF4FF",
            fg="#075985",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            padx=8,
            pady=5,
            wraplength=330,
            justify="left",
        )
        status_note.pack(fill="x", pady=(0, 8))

        radius_input_row = tk.Frame(content, bg="#FFFFFF")
        radius_input_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            radius_input_row,
            text="Bán kính tìm kiếm (km):",
            bg="#FFFFFF",
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 8))

        tk.Entry(
            radius_input_row,
            textvariable=self.inline_search_radius_var,
            width=7,
            font=("Segoe UI", 9, "bold"),
            justify="center",
            relief="flat",
            highlightbackground="#CBD5E1",
            highlightthickness=1,
        ).pack(side="left")

        button_row = tk.Frame(content, bg="#FFFFFF")
        button_row.pack(fill="x", pady=(0, 8))
        for col in range(3):
            button_row.columnconfigure(col, weight=1, uniform="inline_algo")

        demo_algorithms = [
            ("Local Search", "#BAE6FD", "#075985"),
            ("BFS", "#FDE68A", "#78350F"),
            ("DFS", "#DDD6FE", "#5B21B6"),
            ("Greedy", "#BBF7D0", "#166534"),
            ("UCS", "#FED7AA", "#9A3412"),
        ]
        for index, (algorithm_name, fill_color, text_color) in enumerate(demo_algorithms):
            row = index // 3
            col = index % 3
            button = RoundedButton(
                button_row,
                algorithm_name,
                lambda name=algorithm_name: self._run_inline_driver_search_demo(ride, name),
                bg="#FFFFFF",
                fill=fill_color,
                hover_fill=fill_color,
                fg=text_color,
                radius=10,
                height=34,
                width=1,
                font=("Segoe UI", 7, "bold"),
            )
            left_pad = 0 if col == 0 else 3
            right_pad = 0 if col == 2 else 3
            button.grid(row=row, column=col, sticky="ew", padx=(left_pad, right_pad), pady=(0, 4))

        queue_shell = tk.Frame(
            content,
            bg="#FFFFFF",
            highlightbackground="#111827",
            highlightthickness=1,
        )
        queue_shell.pack(fill="x", pady=(4, 8))
        queue_shell.columnconfigure(0, weight=1)
        queue_shell.rowconfigure(0, weight=1)

        self.inline_queue_canvas = tk.Canvas(
            queue_shell,
            height=88,
            bg="#FFFFFF",
            highlightthickness=0,
            bd=0,
        )
        self.inline_queue_scrollbar = ttk.Scrollbar(
            queue_shell,
            orient="vertical",
            command=self.inline_queue_canvas.yview,
        )
        self.inline_queue_inner = tk.Frame(
            self.inline_queue_canvas,
            bg="#FFFFFF",
        )
        self.inline_queue_window = self.inline_queue_canvas.create_window(
            (0, 0),
            window=self.inline_queue_inner,
            anchor="nw",
        )
        self.inline_queue_canvas.configure(
            yscrollcommand=self.inline_queue_scrollbar.set,
        )
        self.inline_queue_canvas.grid(row=0, column=0, sticky="ew")
        self.inline_queue_scrollbar.grid(row=0, column=1, sticky="ns")

        self.inline_queue_cells = []
        self.inline_queue_columns = 8

        def _on_queue_inner_configure(_event: tk.Event) -> None:
            self.inline_queue_canvas.configure(
                scrollregion=self.inline_queue_canvas.bbox("all")
            )

        def _on_queue_canvas_configure(event: tk.Event) -> None:
            self.inline_queue_canvas.itemconfigure(
                self.inline_queue_window,
                width=event.width,
            )

        self.inline_queue_inner.bind("<Configure>", _on_queue_inner_configure)
        self.inline_queue_canvas.bind("<Configure>", _on_queue_canvas_configure)

        tk.Label(
            content,
            text="Bảng trạng thái thuật toán",
            bg="#FFFFFF",
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(4, 3))
        self.inline_status_container = tk.Frame(content, bg="#FFFFFF")
        self.inline_status_container.pack(fill="both", expand=True, pady=(0, 2))

        self._build_inline_step_table()

    def _clear_inline_status_container(self) -> None:
        container = getattr(self, "inline_status_container", None)
        if not container:
            return

        for child in container.winfo_children():
            child.destroy()

        self.inline_status_tree = None

    def _build_inline_step_table(self) -> None:
        container = getattr(self, "inline_status_container", None)
        if not container:
            return

        self._clear_inline_status_container()

        columns = ("step", "algorithm", "radius", "driver", "distance", "result")

        self.inline_status_tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            height=4,
            style="InlineStatus.Treeview",
        )
        headings = {
            "step": "Bước",
            "algorithm": "Thuật toán",
            "radius": "R",
            "driver": "Tài xế",
            "distance": "KC",
            "result": "Kết quả",
        }

        widths = {
            "step": 38,
            "algorithm": 88,
            "radius": 34,
            "driver": 86,
            "distance": 48,
            "result": 132,
        }

        for col in columns:
            self.inline_status_tree.heading(col, text=headings[col])
            self.inline_status_tree.column(
                col,
                width=widths[col],
                minwidth=widths[col],
                anchor="center",
                stretch=False,
            )

        y_scroll = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.inline_status_tree.yview,
        )

        self.inline_status_tree.configure(
            yscrollcommand=y_scroll.set,
        )

        self.inline_status_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")

        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

    def _run_inline_driver_search_demo(self, ride: ActiveRide, algorithm: str) -> None:
        if not hasattr(self, "inline_queue_inner"):
            return

        self._cancel_inline_queue_animation()
        self._clear_inline_queue()
        self._build_inline_step_table()
        self._clear_inline_status_table()

        try:
            selected_radius = float(self.inline_search_radius_var.get())
        except Exception:
            selected_radius = 1.0

        selected_radius = max(0.1, selected_radius)
        selected_driver_id = ride.driver.id if ride and ride.driver else None

        demo_data = self._prepare_visual_driver_search_demo(
            ride=ride,
            radius=selected_radius,
            algorithm=algorithm,
        )
        queue_order = demo_data["queue_order"]
        ordered_candidates = demo_data["ordered_candidates"]
        visited_steps = int(demo_data["visited_steps"])

        if not queue_order:
            self._render_inline_queue([])
            self._set_inline_demo_status(
                f"{algorithm}: không có tài xế phù hợp trong bán kính {selected_radius:g} km."
            )
            self._add_inline_status_row(
                algorithm,
                selected_radius,
                "-",
                None,
                f"Không có tài xế phù hợp sau {visited_steps} bước",
            )
            return

        self._animate_visual_driver_search_queue(
            ride=ride,
            radius=selected_radius,
            selected_driver_id=selected_driver_id,
            algorithm=algorithm,
            queue_order=queue_order,
            ordered_candidates=ordered_candidates,
            visited_steps=visited_steps,
            scan_message=str(demo_data["scan_message"]),
            reorder_message=str(demo_data["reorder_message"]),
            add_result=str(demo_data["add_result"]),
            sort_result=str(demo_data["sort_result"]),
        )

    def _set_inline_demo_status(self, text: str) -> None:
        """Cập nhật dòng mô tả ngắn phía trên hàng đợi minh họa."""
        var = getattr(self, "inline_demo_status_var", None)
        if var is not None:
            var.set(text)

    def _driver_search_animation_delay_ms(self, algorithm: str) -> int:
        """Quy đổi thuật toán sang tốc độ minh họa hàng đợi.

        Thời gian được giữ trong khoảng 0.5s đến 3s theo yêu cầu: thuật toán
        càng trực tiếp thì thêm tài xế nhanh hơn, thuật toán duyệt graph sâu/rộng
        thì chậm hơn để người xem dễ quan sát.
        """
        delays = {
            "Greedy": 500,
            "Local Search": 800,
            "BFS": 1200,
            "UCS": 1800,
            "DFS": 3000,
        }
        return max(500, min(3000, delays.get(algorithm, 1000)))

    def _cancel_inline_queue_animation(self) -> None:
        job = getattr(self, "inline_queue_animation_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self.inline_queue_animation_job = None
        self.inline_queue_animation_token += 1

    def _available_demo_drivers_for_ride(self, ride: Any) -> list[Driver]:
        """Lấy danh sách tài xế dùng cho minh họa mà không làm đổi trạng thái thật."""
        active_driver = getattr(ride, "driver", None)
        active_driver_id = getattr(active_driver, "id", None)
        available: list[Driver] = []
        for driver in self.sim.drivers:
            if driver.busy and driver.id != active_driver_id:
                continue
            available.append(driver)
        return available

    def _prepare_visual_driver_search_demo(
        self,
        *,
        ride: ActiveRide,
        radius: float,
        algorithm: str,
    ) -> dict[str, object]:
        """Chuẩn bị dữ liệu minh họa riêng cho từng thuật toán tìm tài xế.

        Mỗi thuật toán có thứ tự duyệt khác nhau, nhưng phần minh họa đều có
        cùng cấu trúc trực quan: duyệt/phát hiện ứng viên, đưa vào hàng đợi,
        sắp xếp hoặc chuẩn hóa hàng đợi, lấy top 3 và chạy hiệu ứng chọn.
        """
        normalized = algorithm.strip().lower()
        if normalized in {"local", "local search"}:
            return self._prepare_local_visual_demo(ride, radius)
        if normalized == "greedy":
            return self._prepare_greedy_visual_demo(ride, radius)
        if normalized == "bfs":
            return self._prepare_graph_visual_demo(ride, radius, "BFS", "bfs")
        if normalized == "dfs":
            return self._prepare_graph_visual_demo(ride, radius, "DFS", "dfs")
        if normalized == "ucs":
            return self._prepare_graph_visual_demo(ride, radius, "UCS", "ucs")
        return self._prepare_local_visual_demo(ride, radius)

    def _prepare_local_visual_demo(self, ride: ActiveRide, radius: float) -> dict[str, object]:
        customer = ride.customer
        queue_order: list[tuple[Driver, float]] = []
        visited_steps = 0

        for driver in self._available_demo_drivers_for_ride(ride):
            distance = haversine_km(
                customer.lat,
                customer.lng,
                driver.lat,
                driver.lng,
            )
            visited_steps += 1
            if distance <= radius:
                queue_order.append((driver, distance))

        ordered_candidates = sorted(queue_order, key=lambda item: item[1])
        return {
            "queue_order": queue_order,
            "ordered_candidates": ordered_candidates,
            "visited_steps": visited_steps,
            "scan_message": f"Local Search: duyệt từng tài xế trong bán kính {radius:g} km và đưa tài xế phù hợp vào hàng đợi.",
            "reorder_message": "Local Search: sắp xếp hàng đợi theo khoảng cách tăng dần rồi lấy top 3 gần nhất.",
            "add_result": "Trong bán kính",
            "sort_result": "Tăng dần theo KC",
        }

    def _prepare_greedy_visual_demo(self, ride: ActiveRide, radius: float) -> dict[str, object]:
        customer = ride.customer
        scored: list[tuple[float, Driver]] = []
        visited_steps = 0

        for driver in self._available_demo_drivers_for_ride(ride):
            distance = haversine_km(
                customer.lat,
                customer.lng,
                driver.lat,
                driver.lng,
            )
            scored.append((distance, driver))

        queue_order: list[tuple[Driver, float]] = []
        for distance, driver in sorted(scored, key=lambda item: item[0]):
            visited_steps += 1
            if distance > radius:
                # Greedy ưu tiên khoảng cách ước lượng nhỏ nhất, nên khi gặp
                # ứng viên vượt bán kính thì các ứng viên sau cũng xa hơn.
                break
            queue_order.append((driver, distance))

        ordered_candidates = queue_order[:]
        return {
            "queue_order": queue_order,
            "ordered_candidates": ordered_candidates,
            "visited_steps": visited_steps,
            "scan_message": f"Greedy: tính heuristic h(n) là khoảng cách tới điểm đón, rồi xét tài xế gần nhất trước trong bán kính {radius:g} km.",
            "reorder_message": "Greedy: hàng đợi đã được ưu tiên theo h(n) tăng dần, lấy top 3 để chọn.",
            "add_result": "h(n) nhỏ",
            "sort_result": "Ưu tiên h(n)",
        }

    def _prepare_graph_visual_demo(
        self,
        ride: ActiveRide,
        radius: float,
        display_name: str,
        kind: str,
    ) -> dict[str, object]:
        customer = ride.customer
        pickup_lat, pickup_lng = self.graph.node_position(customer.pickup_node_id)
        available = self._available_demo_drivers_for_ride(ride)

        driver_by_node: dict[str, list[Driver]] = {}
        distance_by_driver: dict[str, float] = {}
        for driver in available:
            distance = haversine_km(
                pickup_lat,
                pickup_lng,
                driver.lat,
                driver.lng,
            )
            distance_by_driver[driver.id] = distance
            driver_by_node.setdefault(driver.node_id, []).append(driver)

        queue_order: list[tuple[Driver, float]] = []
        found_driver_ids: set[str] = set()
        visited_nodes: set[str] = set()
        start_id = customer.pickup_node_id

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
                if cost > radius:
                    continue
            elif kind == "bfs":
                node_id, path = frontier.popleft()  # type: ignore[attr-defined]
                cost = 0.0
            else:
                node_id, path = frontier.pop()  # type: ignore[assignment]
                cost = 0.0

            if node_id in visited_nodes:
                continue

            try:
                node_lat, node_lng = self.graph.node_position(node_id)
            except KeyError:
                continue

            circle_distance = haversine_km(pickup_lat, pickup_lng, node_lat, node_lng)
            if kind != "ucs" and circle_distance > radius:
                continue

            visited_nodes.add(node_id)

            for driver in driver_by_node.get(node_id, []):
                if driver.id in found_driver_ids:
                    continue
                distance = distance_by_driver.get(driver.id)
                if distance is None:
                    continue
                if distance <= radius:
                    queue_order.append((driver, distance))
                    found_driver_ids.add(driver.id)

            for neighbor_id, weight in self.graph.adj.get(node_id, []):
                if neighbor_id in visited_nodes:
                    continue
                if kind == "ucs":
                    new_cost = cost + weight
                    if new_cost <= radius and (neighbor_id not in best_cost or new_cost < best_cost[neighbor_id]):
                        best_cost[neighbor_id] = new_cost
                        heapq.heappush(frontier, (new_cost, neighbor_id, path + [neighbor_id]))  # type: ignore[arg-type]
                    continue

                try:
                    neighbor_lat, neighbor_lng = self.graph.node_position(neighbor_id)
                except KeyError:
                    continue
                neighbor_distance = haversine_km(
                    pickup_lat,
                    pickup_lng,
                    neighbor_lat,
                    neighbor_lng,
                )
                if neighbor_distance <= radius:
                    item = (neighbor_id, path + [neighbor_id])
                    if kind == "bfs":
                        frontier.append(item)  # type: ignore[attr-defined]
                    else:
                        frontier.append(item)  # type: ignore[attr-defined]

        # Một số tài xế nằm trên node động của marker, không nằm trực tiếp trong
        # graph nền. Bổ sung các tài xế này theo cùng điều kiện bán kính để bảng
        # minh họa không bị thiếu so với kết quả thuật toán thật.
        for driver in available:
            if driver.id in found_driver_ids:
                continue
            distance = distance_by_driver.get(driver.id)
            if distance is not None and distance <= radius:
                queue_order.append((driver, distance))
                found_driver_ids.add(driver.id)

        if kind == "bfs":
            scan_message = f"BFS: duyệt graph theo từng lớp từ điểm đón trong bán kính {radius:g} km, gặp tài xế thì đưa vào hàng đợi."
            reorder_message = "BFS: chuẩn hóa hàng đợi theo khoảng cách để lấy top 3 ứng viên gần nhất."
            add_result = "Theo lớp BFS"
            sort_result = "Top gần nhất"
        elif kind == "dfs":
            scan_message = f"DFS: đi sâu theo một nhánh graph trước trong bán kính {radius:g} km, tài xế gặp được sẽ vào hàng đợi."
            reorder_message = "DFS: sau khi duyệt sâu, sắp xếp hàng đợi theo khoảng cách để lấy top 3."
            add_result = "Theo nhánh DFS"
            sort_result = "Top gần nhất"
        else:
            scan_message = f"UCS: mở rộng node có chi phí nhỏ nhất trước trong bán kính {radius:g} km, tài xế gặp được sẽ vào hàng đợi."
            reorder_message = "UCS: ưu tiên ứng viên có chi phí/khoảng cách thấp hơn, sau đó lấy top 3."
            add_result = "Chi phí thấp"
            sort_result = "Ưu tiên chi phí"

        ordered_candidates = sorted(queue_order, key=lambda item: item[1])
        return {
            "queue_order": queue_order,
            "ordered_candidates": ordered_candidates,
            "visited_steps": len(visited_nodes),
            "scan_message": scan_message,
            "reorder_message": reorder_message,
            "add_result": add_result,
            "sort_result": sort_result,
        }


    def _queue_cell_style(self, state: str) -> tuple[str, str, int]:
        """Bảng màu cho ô tài xế trong hàng đợi minh họa."""
        styles = {
            "normal": ("#DCFCE7", "#166534", 1),
            "checking": ("#FDE68A", "#78350F", 2),
            "sorted": ("#E0F2FE", "#075985", 1),
            "top": ("#DBEAFE", "#1D4ED8", 2),
            "flash": ("#F59E0B", "#FFFFFF", 3),
            "selected": ("#EF4444", "#FFFFFF", 3),
        }
        return styles.get(state, styles["normal"])

    def _format_queue_cell_text(self, driver: Driver, distance_km: float | None) -> str:
        if distance_km is None:
            return driver.id
        return f"{driver.id}\n{distance_km:.2f} km"

    def _append_inline_queue_cell(
        self,
        driver: Driver,
        index: int,
        *,
        distance_km: float | None = None,
        state: str = "normal",
    ) -> None:
        inner = getattr(self, "inline_queue_inner", None)
        canvas = getattr(self, "inline_queue_canvas", None)
        if not inner:
            return

        columns = getattr(self, "inline_queue_columns", 8)
        for col in range(columns):
            inner.columnconfigure(col, weight=1, uniform="inline_queue")

        row = index // columns
        col = index % columns
        bg, fg, bd = self._queue_cell_style(state)
        cell = tk.Label(
            inner,
            text=self._format_queue_cell_text(driver, distance_km),
            bg=bg,
            fg=fg,
            font=("Segoe UI", 8, "bold"),
            width=7,
            height=2,
            relief="solid",
            bd=bd,
            justify="center",
        )
        cell.grid(
            row=row,
            column=col,
            sticky="nsew",
            padx=2,
            pady=2,
        )
        self.inline_queue_cells.append(cell)
        self.inline_queue_cell_by_driver[driver.id] = cell

        if canvas:
            inner.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(1.0)

    def _style_inline_queue_cell(self, driver_id: str, state: str) -> None:
        cell_map = getattr(self, "inline_queue_cell_by_driver", {})
        cell = cell_map.get(driver_id)
        if not cell:
            return
        bg, fg, bd = self._queue_cell_style(state)
        try:
            cell.configure(bg=bg, fg=fg, bd=bd)
        except tk.TclError:
            pass

    def _style_inline_queue_group(self, driver_ids: set[str], state: str) -> None:
        for driver_id in driver_ids:
            self._style_inline_queue_cell(driver_id, state)

    def _rebuild_inline_queue_order(
        self,
        candidates: list[tuple[Driver, float]],
        *,
        default_state: str = "normal",
    ) -> None:
        self._clear_inline_queue()
        for index, (driver, distance) in enumerate(candidates):
            self._append_inline_queue_cell(
                driver,
                index,
                distance_km=distance,
                state=default_state,
            )

    def _choose_demo_selected_driver_id(
        self,
        selected_driver_id: str | None,
        top_candidates: list[tuple[Driver, float]],
    ) -> str | None:
        if not top_candidates:
            return None
        top_ids = {driver.id for driver, _distance in top_candidates}
        if selected_driver_id in top_ids:
            return selected_driver_id
        # Khi chỉ minh họa từ điểm đón khách hàng, chưa có tài xế thật sự được gán.
        # Vì vậy kết quả dừng sẽ được random trong top 3, đúng logic bài toán.
        return random.choice(top_candidates)[0].id

    def _flash_top_three_selection(
        self,
        *,
        top_candidates: list[tuple[Driver, float]],
        selected_driver_id: str | None,
        algorithm: str,
        radius: float,
        final_message: str,
        cycles: int = 12,
        interval_ms: int = 150,
    ) -> None:
        token = self.inline_queue_animation_token
        if not top_candidates:
            self.inline_queue_animation_job = None
            return

        top_ids = [driver.id for driver, _distance in top_candidates]
        selected_id = self._choose_demo_selected_driver_id(selected_driver_id, top_candidates)
        self._style_inline_queue_group(set(top_ids), "top")
        self._set_inline_demo_status(
            f"{algorithm}: random trong 3 tài xế gần nhất ({', '.join(top_ids)})."
        )
        self._add_inline_status_row(
            "Random top 3",
            radius,
            ", ".join(top_ids),
            None,
            "Đang chọn",
        )

        def tick(step: int) -> None:
            if token != self.inline_queue_animation_token:
                return
            if step > 0:
                previous_id = top_ids[(step - 1) % len(top_ids)]
                self._style_inline_queue_cell(previous_id, "top")

            if step >= cycles:
                for driver_id in top_ids:
                    self._style_inline_queue_cell(driver_id, "top")
                if selected_id:
                    self._style_inline_queue_cell(selected_id, "selected")
                    selected_distance = next(
                        (dist for drv, dist in top_candidates if drv.id == selected_id),
                        None,
                    )
                    self._add_inline_status_row(
                        "Random",
                        radius,
                        selected_id,
                        selected_distance,
                        "Dừng chọn",
                    )
                    self._set_inline_demo_status(final_message.format(selected=selected_id))
                self.inline_queue_animation_job = None
                return

            current_id = top_ids[step % len(top_ids)]
            self._style_inline_queue_cell(current_id, "flash")
            self.inline_queue_animation_job = self.root.after(
                interval_ms,
                lambda: tick(step + 1),
            )

        tick(0)

    def _animate_visual_driver_search_queue(
        self,
        *,
        ride: ActiveRide,
        radius: float,
        selected_driver_id: str | None,
        algorithm: str,
        queue_order: list[tuple[Driver, float]],
        ordered_candidates: list[tuple[Driver, float]],
        visited_steps: int,
        scan_message: str,
        reorder_message: str,
        add_result: str,
        sort_result: str,
    ) -> None:
        """Minh họa trực quan cho mọi thuật toán tìm tài xế.

        Luồng chung:
        1. Thêm từng tài xế theo thứ tự duyệt riêng của thuật toán.
        2. Sắp xếp/chuẩn hóa hàng đợi theo tiêu chí chọn ứng viên.
        3. Tô top 3 và chạy hiệu ứng random đến khi dừng ở tài xế được chọn.
        """
        token = self.inline_queue_animation_token
        delay_ms = self._driver_search_animation_delay_ms(algorithm)

        if not queue_order:
            self._render_inline_queue([])
            self._set_inline_demo_status(
                f"{algorithm}: không có tài xế nào phù hợp trong bán kính {radius:g} km."
            )
            self._add_inline_status_row(
                algorithm,
                radius,
                "-",
                None,
                f"Không có tài xế phù hợp sau {visited_steps} bước",
            )
            return

        self._set_inline_demo_status(scan_message)

        def add_candidate(index: int) -> None:
            if token != self.inline_queue_animation_token:
                return
            if index >= len(queue_order):
                self._add_inline_status_row(
                    algorithm,
                    radius,
                    "-",
                    None,
                    f"Đã duyệt {visited_steps} bước",
                )
                self._set_inline_demo_status(reorder_message)
                self.inline_queue_animation_job = self.root.after(650, reorder_queue)
                return

            # Giảm màu của ô vừa kiểm tra trước đó để ô hiện tại nổi bật hơn.
            if index > 0:
                previous_driver = queue_order[index - 1][0]
                self._style_inline_queue_cell(previous_driver.id, "normal")

            driver, distance = queue_order[index]
            self._append_inline_queue_cell(
                driver,
                index,
                distance_km=distance,
                state="checking",
            )
            self._add_inline_status_row(
                algorithm,
                radius,
                driver.id,
                distance,
                add_result,
            )
            self.inline_queue_animation_job = self.root.after(
                delay_ms,
                lambda: add_candidate(index + 1),
            )

        def reorder_queue() -> None:
            if token != self.inline_queue_animation_token:
                return
            self._rebuild_inline_queue_order(ordered_candidates, default_state="sorted")
            self._add_inline_status_row(
                "Sắp xếp",
                radius,
                "-",
                None,
                sort_result,
            )
            top_candidates = ordered_candidates[:3]
            top_ids = [driver.id for driver, _distance in top_candidates]
            self._style_inline_queue_group(set(top_ids), "top")
            self._add_inline_status_row(
                "Top 3",
                radius,
                ", ".join(top_ids),
                None,
                "Ứng viên chọn",
            )
            self.inline_queue_animation_job = self.root.after(
                750,
                lambda: self._flash_top_three_selection(
                    top_candidates=top_candidates,
                    selected_driver_id=selected_driver_id,
                    algorithm=algorithm,
                    radius=radius,
                    final_message=f"{algorithm}: màu chọn đã dừng ở tài xế {{selected}}.",
                ),
            )

        add_candidate(0)


    def _clear_inline_queue(self) -> None:
        inner = getattr(self, "inline_queue_inner", None)
        if not inner:
            return

        for child in inner.winfo_children():
            child.destroy()

        self.inline_queue_cells = []
        self.inline_queue_cell_by_driver = {}

        canvas = getattr(self, "inline_queue_canvas", None)
        if canvas:
            canvas.yview_moveto(0)

    def _render_inline_queue(
        self,
        candidates: list[tuple[Driver, float]],
        selected_driver_id: str | None = None,
    ) -> None:
        inner = getattr(self, "inline_queue_inner", None)
        canvas = getattr(self, "inline_queue_canvas", None)

        if not inner:
            return

        self._clear_inline_queue()

        columns = getattr(self, "inline_queue_columns", 8)

        for col in range(columns):
            inner.columnconfigure(col, weight=1, uniform="inline_queue")

        if not candidates:
            empty_label = tk.Label(
                inner,
                text="Chưa có tài xế trong hàng đợi",
                bg="#FFFFFF",
                fg=TEXT_SECONDARY,
                font=("Segoe UI", 8, "italic"),
                height=2,
            )
            empty_label.grid(
                row=0,
                column=0,
                columnspan=columns,
                sticky="nsew",
                padx=1,
                pady=1,
            )

            self.inline_queue_cells.append(empty_label)

            if canvas:
                inner.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))

            return

        for index, (driver, distance) in enumerate(candidates):
            state = "selected" if driver.id == selected_driver_id else "normal"
            self._append_inline_queue_cell(
                driver,
                index,
                distance_km=distance,
                state=state,
            )

        if canvas:
            inner.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(0)

    def _clear_inline_status_table(self) -> None:
        tree = getattr(self, "inline_status_tree", None)

        if not tree:
            self._build_inline_step_table()
            tree = getattr(self, "inline_status_tree", None)

        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

    def _add_inline_status_row(
        self,
        algorithm: str,
        radius: int | str,
        driver_id: str,
        distance_km: float | None,
        result: str,
    ) -> None:
        tree = getattr(self, "inline_status_tree", None)
        if not tree:
            return

        step = len(tree.get_children()) + 1
        distance_text = "-" if distance_km is None else f"{distance_km:.2f}"

        tree.insert(
            "",
            "end",
            values=(
                step,
                algorithm,
                radius,
                driver_id,
                distance_text,
                result,
            ),
        )

    def _section_header(self, parent: tk.Frame, title: str, subtitle: str | None = None) -> None:
        tk.Label(
            parent,
            text=title,
            bg=parent["bg"],
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        if subtitle:
            tk.Label(
                parent,
                text=subtitle,
                bg=parent["bg"],
                fg=TEXT_SECONDARY,
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=(2, 4))


    def _legend_item(self, parent: tk.Frame, label: str, color: str, row: int, column: int) -> None:
        item = tk.Frame(parent, bg=SURFACE)
        item.grid(row=row, column=column, sticky="w", padx=(0, 16), pady=4)
        dot = tk.Canvas(item, width=14, height=14, bg=SURFACE, highlightthickness=0, bd=0)
        dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
        dot.pack(side="left")
        tk.Label(item, text=label, bg=SURFACE, fg=TEXT_SECONDARY, font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))


    def _build_button(
        self,
        parent: tk.Frame,
        text: str,
        command: Callable[[], None],
        *,
        fill: str,
        hover_fill: str,
        fg: str = "#FFFFFF",
    ) -> None:
        button = RoundedButton(parent, text, command, bg=parent["bg"], fill=fill, hover_fill=hover_fill, fg=fg)
        button.pack(fill="x", pady=(8, 0))

    def _build_checkbox(
        self,
        parent: tk.Frame,
        label: str,
        variable: tk.BooleanVar,
        command: Callable[[], None] | None = None,
    ) -> None:
        checkbox = tk.Checkbutton(
            parent,
            text=label,
            variable=variable,
            command=command,
            bg=parent["bg"],
            fg=TEXT_PRIMARY,
            selectcolor=SURFACE,
            activebackground=parent["bg"],
            activeforeground=TEXT_PRIMARY,
            font=("Segoe UI", 8),
            anchor="w",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        checkbox.pack(anchor="w", pady=(4, 0), fill="x")

    def _build_road_condition_buttons(self, parent: tk.Frame) -> None:
        """Các lựa chọn cấp độ đường. Khung này chỉ mở khi tick đánh dấu đường xấu."""

        frame = tk.Frame(parent, bg=parent["bg"])
        frame.pack(fill="x", pady=(6, 0))
        self.editor_road_condition_buttons_frame = frame

        options = [
            ("Bình thường", ROAD_NORMAL, MUTED_BUTTON, MUTED_BUTTON_HOVER, TEXT_PRIMARY),
            ("Đường xấu", ROAD_BAD, COLOR_ROAD_BAD, "#D4A106", TEXT_PRIMARY),
            ("Rất xấu", ROAD_VERY_BAD, COLOR_ROAD_VERY_BAD, DANGER_HOVER, "#FFFFFF"),
            ("Đường cấm", ROAD_BLOCKED, "#991B1B", "#7F1D1D", "#FFFFFF"),
        ]
        self.editor_road_condition_buttons = []
        self.editor_road_condition_button_by_condition = {}
        for index, (label, condition, fill, hover, fg) in enumerate(options):
            button = RoundedButton(
                frame,
                label,
                command=lambda value=condition: self._set_editor_road_condition(value),
                bg=parent["bg"],
                fill=fill,
                hover_fill=hover,
                fg=fg,
                height=34,
                font=("Segoe UI", 8, "bold"),
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 4, 0))
            frame.columnconfigure(index, weight=1)
            self.editor_road_condition_buttons.append(button)
            self.editor_road_condition_button_by_condition[condition] = button
        self._update_road_condition_controls_visibility()
        self._refresh_action_buttons()

    def _update_road_condition_controls_visibility(self) -> None:
        frame = self.editor_road_condition_buttons_frame
        if frame is None:
            return
        if self.editor_mark_bad_road_var.get():
            frame.configure(height=38)
            frame.pack_propagate(True)
            for button in self.editor_road_condition_buttons:
                button.grid()
        else:
            for button in self.editor_road_condition_buttons:
                button.grid_remove()
            frame.pack_propagate(False)
            frame.configure(height=0)

    def _build_graph_display_controls(self, parent: tk.Frame) -> None:
        """Các nút hiển thị/ẩn graph và node trong Graph Editor."""

        graph_row = tk.Frame(parent, bg=parent["bg"])
        graph_row.pack(fill="x", pady=(8, 0))
        graph_row.columnconfigure(0, weight=1)
        graph_row.columnconfigure(1, weight=1)
        tk.Label(
            graph_row,
            text="Graph",
            bg=parent["bg"],
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.editor_graph_show_button = RoundedButton(
            graph_row,
            "Hiển thị",
            self.editor_show_graph,
            bg=parent["bg"],
            fill="#16A34A",
            hover_fill="#15803D",
            height=34,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.editor_graph_show_button.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        self.editor_graph_hide_button = RoundedButton(
            graph_row,
            "Ẩn",
            self.editor_hide_graph,
            bg=parent["bg"],
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
            height=34,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.editor_graph_hide_button.grid(row=1, column=1, sticky="ew", padx=(4, 0))

        nodes_row = tk.Frame(parent, bg=parent["bg"])
        nodes_row.pack(fill="x", pady=(8, 0))
        nodes_row.columnconfigure(0, weight=1)
        nodes_row.columnconfigure(1, weight=1)
        tk.Label(
            nodes_row,
            text="Nodes",
            bg=parent["bg"],
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.editor_nodes_show_button = RoundedButton(
            nodes_row,
            "Hiển thị",
            self.editor_show_nodes,
            bg=parent["bg"],
            fill="#2563EB",
            hover_fill="#1D4ED8",
            height=34,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.editor_nodes_show_button.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        self.editor_nodes_hide_button = RoundedButton(
            nodes_row,
            "Ẩn",
            self.editor_hide_nodes,
            bg=parent["bg"],
            fill=MUTED_BUTTON,
            hover_fill=MUTED_BUTTON_HOVER,
            fg=TEXT_PRIMARY,
            height=34,
            radius=10,
            font=("Segoe UI", 8, "bold"),
        )
        self.editor_nodes_hide_button.grid(row=1, column=1, sticky="ew", padx=(4, 0))
        self._refresh_action_buttons()

    def _build_graph_clear_controls(self, parent: tk.Frame) -> None:
        """Nút Xóa graph mở ra 3 thao tác: Chọn / Xóa tất cả / Hủy."""

        self.editor_clear_main_frame = tk.Frame(parent, bg=parent["bg"])
        self.editor_clear_main_frame.pack(fill="x", pady=(8, 0))
        self.editor_clear_main_button = RoundedButton(
            self.editor_clear_main_frame,
            "Xóa graph",
            self.editor_show_clear_actions,
            bg=parent["bg"],
            fill=DANGER,
            hover_fill=DANGER_HOVER,
        )
        self.editor_clear_main_button.pack(fill="x")

        actions = tk.Frame(parent, bg=parent["bg"])
        self.editor_clear_actions_frame = actions
        buttons = [
            ("Chọn", self.editor_select_delete_graph, MUTED_BUTTON, MUTED_BUTTON_HOVER, TEXT_PRIMARY),
            ("Xóa tất cả", self.editor_clear_all, DANGER, DANGER_HOVER, "#FFFFFF"),
            ("Hủy", self.editor_cancel_clear_graph, "#4B5563", "#374151", "#FFFFFF"),
        ]
        for index, (label, command, fill, hover, fg) in enumerate(buttons):
            btn = RoundedButton(
                actions,
                label,
                command,
                bg=parent["bg"],
                fill=fill,
                hover_fill=hover,
                fg=fg,
                height=38,
                font=("Segoe UI", 8, "bold"),
            )
            btn.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 4, 0))
            actions.columnconfigure(index, weight=1)
            if label == "Chọn":
                self.editor_clear_select_button = btn
            elif label == "Xóa tất cả":
                self.editor_clear_all_button = btn
            elif label == "Hủy":
                self.editor_clear_cancel_button = btn

    def _set_editor_road_condition(self, condition: str) -> None:
        if condition not in ROAD_CONDITION_LABELS:
            return
        if self._manual_tool_active():
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", "đánh dấu đường")
            return
        if self.editor_delete_graph_mode:
            self._warn_unrelated_action("xóa node graph", "đánh dấu đường")
            return
        self.editor_road_condition_var.set(condition)
        self.editor_mark_bad_road_var.set(True)
        label = ROAD_CONDITION_LABELS[condition]
        self.status_var.set(f"Chế độ đánh dấu: {label}. Kéo chuột đè/gần cạnh graph để cập nhật nhanh.")
        self._on_editor_option_changed()

    def _build_slider(self, parent: tk.Frame, label: str, variable: tk.IntVar, minimum: int, maximum: int) -> None:
        frame = tk.Frame(parent, bg=parent["bg"])
        frame.pack(fill="x", pady=(10, 6))
        header = tk.Frame(frame, bg=parent["bg"])
        header.pack(fill="x")
        tk.Label(header, text=label, bg=parent["bg"], fg=TEXT_PRIMARY, font=("Segoe UI", 9, "bold")).pack(side="left")
        badge = tk.Label(
            header,
            textvariable=variable,
            bg=SURFACE_SOFT,
            fg=ACCENT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
        )
        badge.pack(side="right")
        scale = ttk.Scale(
            frame,
            from_=minimum,
            to=maximum,
            orient="horizontal",
            style="Horizontal.TScale",
            command=lambda value: variable.set(int(float(value))),
        )
        scale.set(variable.get())
        scale.pack(fill="x", pady=(6, 0))

    def _init_map(self) -> None:
        self.map_container.rowconfigure(0, weight=1)
        self.map_container.columnconfigure(0, weight=1)

        if TkinterMapView is None:
            tk.Label(
                self.map_container,
                text=(
                    "Thiếu thư viện tkintermapview.\n"
                    "Chạy: python -m pip install -r requirements.txt"
                ),
                font=("Segoe UI", 12, "bold"),
                justify="center",
                bg=SURFACE,
                fg=TEXT_PRIMARY,
            ).pack(fill="both", expand=True)
            return

        self.map_widget = TkinterMapView(self.map_container, width=1000, height=847, corner_radius=22)
        self.map_widget.grid(row=0, column=0, sticky="nsew")

        def _apply_map_widget_size(width: int | None = None, height: int | None = None) -> None:
            if not self.map_widget:
                return
            if width is None:
                width = int(self.map_container.winfo_width())
            if height is None:
                height = int(self.map_container.winfo_height())
            width = max(560, width)
            height = max(620, height)
            try:
                self.map_widget.set_widget_size(width, height)
            except Exception:
                try:
                    self.map_widget.configure(width=width, height=height)
                except Exception:
                    pass

        def _resize_map_widget(event: tk.Event | None = None) -> None:
            if event is not None:
                _apply_map_widget_size(
                    int(getattr(event, "width", 0) or 0),
                    int(getattr(event, "height", 0) or 0),
                )
            else:
                _apply_map_widget_size()

        self.map_container.bind("<Configure>", _resize_map_widget, add="+")
        self.root.after(150, _resize_map_widget)
        self.root.after(500, _resize_map_widget)

        try:
            self.map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
        except Exception:
            pass
        self.map_widget.set_position(MAP_CENTER[0], MAP_CENTER[1])
        self.map_widget.set_zoom(MAP_ZOOM)

        add_click_command = getattr(self.map_widget, "add_left_click_map_command", None)
        if callable(add_click_command):
            add_click_command(self._handle_map_click)

    def _draw_graph(self) -> None:
        """Vẽ/ẩn graph nền hiện tại theo trạng thái nút Graph và Nodes."""

        if not self.map_widget:
            return

        for path in self.graph_paths:
            self._safe_delete(path)
        for marker in self.node_markers:
            self._safe_delete(marker)

        self.graph_paths.clear()
        self.node_markers.clear()

        raw_edges = list(self.graph.edges_raw())
        blocked_endpoint_ids = self._blocked_road_endpoint_ids(
            raw_edges,
            lambda u, v: self.graph.get_edge_condition(u, v),
        )

        if self.show_graph_var.get():
            # Vẽ từng cạnh thật sự trong graph; cạnh đã đánh dấu dùng màu trạng thái tương ứng.
            for u, v in raw_edges:
                lat1, lng1 = self.graph.node_position(u)
                lat2, lng2 = self.graph.node_position(v)
                condition = self.graph.get_edge_condition(u, v)
                color = self._editor_condition_color(condition)

                if condition == ROAD_BLOCKED:
                    dash_count = 12
                    for index in range(0, dash_count, 2):
                        start_ratio = index / dash_count
                        end_ratio = (index + 1) / dash_count
                        start = (lat1 + (lat2 - lat1) * start_ratio, lng1 + (lng2 - lng1) * start_ratio)
                        end = (lat1 + (lat2 - lat1) * end_ratio, lng1 + (lng2 - lng1) * end_ratio)
                        path = self.map_widget.set_path([start, end], color=COLOR_ROAD_BLOCKED, width=3)
                        self.graph_paths.append(path)
                    continue

                path = self.map_widget.set_path(
                    [(lat1, lng1), (lat2, lng2)],
                    color=color,
                    width=3,
                )
                self.graph_paths.append(path)

        # Nodes có thể hiển thị độc lập. Với đường cấm liên tiếp, chỉ gắn biển cấm
        # ở hai đầu đoạn cấm; các node nằm giữa đoạn cấm không bị phủ marker cấm.
        if self.show_nodes_var.get():
            for node_id, lat, lng in self.graph.base_node_positions():
                if self.show_graph_var.get() and node_id in blocked_endpoint_ids:
                    marker = self._set_no_entry_marker(lat, lng, node_id)
                else:
                    marker = self._set_marker(lat, lng, node_id, COLOR_GRAPH_NODE)
                self.node_markers.append(marker)
        elif self.show_graph_var.get() and blocked_endpoint_ids:
            for node_id, lat, lng in self.graph.base_node_positions():
                if node_id in blocked_endpoint_ids:
                    marker = self._set_no_entry_marker(lat, lng, node_id)
                    self.node_markers.append(marker)

    # ------------------------------------------------------------------
    # Graph editor: kéo chuột trên OSM để lấy tọa độ node-edge chính xác hơn
    # ------------------------------------------------------------------
    def _get_map_canvas(self) -> Any:
        if not self.map_widget:
            return None
        for attr in ("canvas", "map_canvas", "canvas_widget"):
            canvas = getattr(self.map_widget, attr, None)
            if canvas is not None and hasattr(canvas, "bind"):
                return canvas
        return self.map_widget if hasattr(self.map_widget, "bind") else None

    def _on_editor_option_changed(self) -> None:
        if self._suppress_editor_option_callback:
            return

        if self._manual_tool_active() and (self.editor_mode_var.get() or self.editor_mark_bad_road_var.get() or self.editor_delete_graph_mode):
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", "Graph Editor")
            self._suppress_editor_option_callback = True
            try:
                self.editor_mode_var.set(False)
                self.editor_mark_bad_road_var.set(False)
                self.editor_delete_graph_mode = False
            finally:
                self._suppress_editor_option_callback = False

        if self.editor_delete_graph_mode and (self.editor_mode_var.get() or self.editor_mark_bad_road_var.get()):
            self._warn_unrelated_action("xóa node graph", "vẽ/đánh dấu đường")
            self._suppress_editor_option_callback = True
            try:
                self.editor_mode_var.set(False)
                self.editor_mark_bad_road_var.set(False)
            finally:
                self._suppress_editor_option_callback = False

        self._update_road_condition_controls_visibility()
        self._refresh_action_buttons()
        enable = bool(
            self.editor_lock_map_var.get()
            and (self.editor_mode_var.get() or self.editor_mark_bad_road_var.get() or self.editor_delete_graph_mode)
        )
        self._set_editor_bindings(enable)
        if self.editor_delete_graph_mode:
            self.status_var.set("Chế độ xóa node graph: click hoặc kéo gần node cần xóa; các cạnh liên kết sẽ bị xóa theo.")
        elif self.editor_mark_bad_road_var.get() and self.editor_mode_var.get():
            condition = self.editor_road_condition_var.get()
            label = ROAD_CONDITION_LABELS.get(condition, "Đường xấu")
            self.status_var.set(
                f"Chế độ vẽ + đánh dấu: cạnh mới sẽ là {label}; kéo gần cạnh cũ để đổi trạng thái nhanh."
            )
        elif self.editor_mark_bad_road_var.get():
            condition = self.editor_road_condition_var.get()
            label = ROAD_CONDITION_LABELS.get(condition, "Đường xấu")
            self.status_var.set(f"Chế độ đánh dấu: {label}. Kéo chuột đè/gần cạnh graph để cập nhật trọng số đường.")
        elif self.editor_mode_var.get():
            self.status_var.set("Chế độ vẽ graph: kéo để tạo node/cạnh. Mặc định mỗi lần kéo là một nét độc lập; bật 'Nối vào node gần nhất' khi cần giao lộ.")
        else:
            self.status_var.set("Đã tắt chế độ vẽ graph. Có thể kéo bản đồ bình thường.")

    def _set_editor_bindings(self, enable: bool) -> None:
        canvas = self._get_map_canvas()
        if canvas is None:
            return

        sequences = ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>")

        if enable and not self.editor_bindings_active:
            self.editor_saved_bindings = {seq: canvas.bind(seq) for seq in sequences}
            canvas.bind("<ButtonPress-1>", self._editor_on_press)
            canvas.bind("<B1-Motion>", self._editor_on_drag)
            canvas.bind("<ButtonRelease-1>", self._editor_on_release)
            self.editor_bindings_active = True
            self._log("[Graph Editor] Đã bật thao tác Graph Editor. Có thể vẽ, đánh dấu đường hoặc xóa node tùy chế độ đang chọn.")
            return

        if not enable and self.editor_bindings_active:
            for seq, script in self.editor_saved_bindings.items():
                try:
                    canvas.bind(seq, script)
                except Exception:
                    canvas.bind(seq, "")
            self.editor_saved_bindings.clear()
            self.editor_bindings_active = False
            self._log("[Graph Editor] Đã tắt chế độ vẽ, khôi phục thao tác bản đồ.")

    def _event_to_lat_lng(self, event: tk.Event) -> tuple[float, float] | None:
        if not self.map_widget:
            return None

        converter = getattr(self.map_widget, "convert_canvas_coords_to_decimal_coords", None)
        if callable(converter):
            try:
                lat, lng = converter(event.x, event.y)
                return float(lat), float(lng)
            except Exception:
                pass

        # Một số phiên bản tkintermapview dùng tên hàm khác.
        for method_name in ("convert_widget_coords_to_decimal_coords", "convert_canvas_coords_to_position"):
            converter = getattr(self.map_widget, method_name, None)
            if callable(converter):
                try:
                    lat, lng = converter(event.x, event.y)
                    return float(lat), float(lng)
                except Exception:
                    continue

        self.status_var.set("Không đọc được tọa độ chuột từ tkintermapview. Hãy cập nhật tkintermapview nếu cần.")
        return None

    def _editor_on_press(self, event: tk.Event) -> str:
        if not self.editor_lock_map_var.get() or not (
            self.editor_mode_var.get() or self.editor_mark_bad_road_var.get() or self.editor_delete_graph_mode
        ):
            return ""

        self.editor_processed_edges_in_drag.clear()
        self.editor_drag_action = None
        coords = self._event_to_lat_lng(event)
        if not coords:
            return "break"

        lat, lng = coords
        if self.editor_delete_graph_mode:
            self.editor_drag_action = "delete"
            self._editor_delete_nearest_node(lat, lng)
            return "break"

        if self.editor_mark_bad_road_var.get():
            # Chỉ đánh dấu: luôn cập nhật cạnh gần nhất.
            # Vẽ + đánh dấu: nếu bấm gần cạnh cũ thì đổi trạng thái cạnh cũ,
            # nếu bấm xa cạnh cũ thì bắt đầu vẽ cạnh mới với trạng thái đang chọn.
            nearest = self._editor_nearest_edge_at(lat, lng, load_base=not self.editor_mode_var.get())
            if nearest is not None or not self.editor_mode_var.get():
                self.editor_drag_action = "mark"
                self._editor_mark_nearest_edge(lat, lng)
                return "break"

        if self.editor_mode_var.get():
            self.editor_drag_action = "draw"
            self.editor_is_drawing = True
            self.editor_current_stroke = []
            self._editor_add_point(lat, lng)
        return "break"

    def _editor_on_drag(self, event: tk.Event) -> str:
        if not self.editor_lock_map_var.get():
            return "break"
        coords = self._event_to_lat_lng(event)
        if not coords:
            return "break"
        lat, lng = coords

        if self.editor_delete_graph_mode or self.editor_drag_action == "delete":
            self.editor_drag_action = "delete"
            self._editor_delete_nearest_node(lat, lng)
            return "break"

        if self.editor_drag_action == "mark" or (self.editor_mark_bad_road_var.get() and not self.editor_mode_var.get()):
            self.editor_drag_action = "mark"
            self._editor_mark_nearest_edge(lat, lng)
            return "break"

        if self.editor_mode_var.get() and self.editor_is_drawing:
            self._editor_add_point(lat, lng)
        return "break"

    def _editor_on_release(self, event: tk.Event) -> str:
        if not self.editor_lock_map_var.get() or not (
            self.editor_mode_var.get() or self.editor_mark_bad_road_var.get() or self.editor_delete_graph_mode
        ):
            return ""

        if self.editor_drag_action in {"mark", "delete"}:
            self.editor_drag_action = None
            self.editor_processed_edges_in_drag.clear()
            return "break"

        coords = self._event_to_lat_lng(event)
        if coords and self.editor_mode_var.get() and self.editor_is_drawing:
            self._editor_add_point(*coords)

        if self.editor_dead_end_var.get() and self.editor_current_stroke:
            last_id = self.editor_current_stroke[-1]
            self.editor_dead_end_nodes.add(last_id)
            if hasattr(self.graph, "dead_end_ids"):
                self.graph.dead_end_ids.add(last_id)
                self._mark_graph_dirty()
            self._mark_editor_node_dead_end(last_id)
            self._log(f"[Graph Editor] Đánh dấu {last_id} là hẻm cụt. Các cạnh sau sẽ không nối tiếp từ node này.")

        self.editor_is_drawing = False
        self.editor_current_stroke = []
        self.editor_drag_action = None
        self.status_var.set(
            f"Graph đang vẽ: {len(self.editor_nodes)} node, {len(self.editor_edges)} cạnh, "
            f"{len(self.editor_dead_end_nodes)} hẻm cụt."
        )
        return "break"

    def _editor_next_node_id(self) -> str:
        """Sinh ID node mới không trùng với các node đã có trong editor."""
        max_number = 0
        known_ids = [node_id for node_id, _lat, _lng in self.editor_nodes]
        known_ids.extend(self.graph.nodes.keys())
        for node_id in known_ids:
            raw = node_id.replace("_DEAD_END", "")
            if raw.startswith("G") and raw[1:].isdigit():
                max_number = max(max_number, int(raw[1:]))
        return f"G{max_number + 1:03d}"

    def _editor_add_point(self, lat: float, lng: float) -> str | None:
        """Thêm 1 điểm khi kéo chuột trong Graph Editor.

        Logic mới để tránh lỗi 2 đường song song bị tự nối:
        - Bình thường: chỉ tạo node mới và nối với node trước trong cùng nét vẽ.
        - Không tự bắt vào node của nét khác dù ở gần.
        - Chỉ khi bật "Nối vào node gần nhất" mới snap vào node cũ để tạo giao lộ/ngã ba.
        """

        min_distance_km = max(1, self.editor_min_point_distance_var.get()) / 1000.0
        snap_distance_km = max(1, self.editor_snap_distance_var.get()) / 1000.0

        last_id = self.editor_current_stroke[-1] if self.editor_current_stroke else None
        last_pos = self._editor_node_position(last_id) if last_id else None
        distance_to_last = None

        if last_pos:
            distance_to_last = haversine_km(lat, lng, last_pos[0], last_pos[1])

        node_id: str | None = None

        # Chỉ snap vào node cũ khi người dùng chủ động bật chế độ này.
        # Đây là điểm khắc phục lỗi đường song song bị nối chéo.
        if self.editor_auto_join_var.get():
            nearby_id = self._editor_find_near_node(
                lat,
                lng,
                max_distance_km=snap_distance_km,
            )
            if nearby_id is not None:
                node_id = nearby_id
                lat, lng = self._editor_node_position(node_id) or (lat, lng)

        # Nếu không snap vào node cũ thì kiểm tra khoảng cách tới node cuối.
        # Mục đích là tránh tạo quá nhiều node khi kéo chuột chậm.
        if node_id is None:
            if last_id is not None and distance_to_last is not None and distance_to_last < min_distance_km:
                return last_id

            node_id = self._editor_next_node_id()
            self.editor_nodes.append((node_id, lat, lng))
            self.editor_created_nodes.add(node_id)
            self.graph.add_base_node(node_id, lat, lng)
            self._mark_graph_dirty()
            marker = self._set_marker(lat, lng, node_id, COLOR_GRAPH_NODE)
            self.editor_markers.append(marker)

        if not self.editor_current_stroke:
            self.editor_current_stroke.append(node_id)
            return node_id

        prev_id = self.editor_current_stroke[-1]
        if prev_id == node_id:
            return node_id

        # Nếu node trước là hẻm cụt thì không nối sang node mới.
        if prev_id in self.editor_dead_end_nodes:
            self.editor_current_stroke = [node_id]
            return node_id

        # Nếu node mới đang là hẻm cụt thì không tự động nối vào nó.
        if node_id in self.editor_dead_end_nodes:
            self.editor_current_stroke = [node_id]
            return node_id

        edge = (prev_id, node_id)
        rev_edge = (node_id, prev_id)
        if edge not in self.editor_edges and rev_edge not in self.editor_edges:
            self.editor_edges.append(edge)
            try:
                self.graph.add_base_edge(prev_id, node_id, ROAD_NORMAL)
                self._mark_graph_dirty()
            except Exception as exc:
                self._log(f"[Graph Editor] Không thêm được cạnh {prev_id} - {node_id} vào graph nền: {exc}")
            self._apply_selected_condition_to_edge(prev_id, node_id)
            self._draw_editor_edge(prev_id, node_id)

        self.editor_current_stroke.append(node_id)
        return node_id

    def _editor_find_near_node(
        self,
        lat: float,
        lng: float,
        max_distance_km: float | None = None,
    ) -> str | None:
        """Tìm node thủ công gần tọa độ chuột nhất trong bán kính cho phép."""

        if max_distance_km is None:
            max_distance_km = max(1, self.editor_snap_distance_var.get()) / 1000.0

        nearest_id: str | None = None
        nearest_distance = max_distance_km

        for node_id, node_lat, node_lng in self.editor_nodes:
            distance = haversine_km(lat, lng, node_lat, node_lng)
            if distance <= nearest_distance:
                nearest_distance = distance
                nearest_id = node_id

        return nearest_id

    def _editor_node_position(self, node_id: str) -> tuple[float, float] | None:
        for current_id, lat, lng in self.editor_nodes:
            if current_id == node_id:
                return lat, lng
        return None

    def _editor_edge_key(self, a: str, b: str) -> tuple[str, str]:
        """Chuẩn hóa key cạnh trong editor để lưu trạng thái đường."""

        return tuple(sorted((a, b)))

    def _editor_edge_condition(self, a: str, b: str) -> str:
        key = self._editor_edge_key(a, b)
        if key in self.editor_edge_conditions:
            return self.editor_edge_conditions[key]
        try:
            return self.graph.get_edge_condition(a, b)
        except Exception:
            return ROAD_NORMAL

    def _editor_condition_color(self, condition: str) -> str:
        if condition == ROAD_BAD:
            return COLOR_ROAD_BAD
        if condition == ROAD_VERY_BAD:
            return COLOR_ROAD_VERY_BAD
        if condition == ROAD_BLOCKED:
            return COLOR_ROAD_BLOCKED
        return COLOR_GRAPH_EDGE

    def _editor_point_to_edge_distance_km(self, lat: float, lng: float, a: str, b: str) -> float:
        """Tính khoảng cách từ click chuột tới đoạn thẳng cạnh editor."""

        pos_a = self._editor_node_position(a)
        pos_b = self._editor_node_position(b)
        if not pos_a or not pos_b:
            return float("inf")

        a_lat, a_lng = pos_a
        b_lat, b_lng = pos_b
        radius_km = 6371.0
        ref_lat = math.radians((lat + a_lat + b_lat) / 3.0)
        ref_lng = math.radians((lng + a_lng + b_lng) / 3.0)

        def to_xy(point_lat: float, point_lng: float) -> tuple[float, float]:
            x = (math.radians(point_lng) - ref_lng) * math.cos(ref_lat) * radius_km
            y = math.radians(point_lat) * radius_km
            return x, y

        px, py = to_xy(lat, lng)
        ax, ay = to_xy(a_lat, a_lng)
        bx, by = to_xy(b_lat, b_lng)
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 1e-12:
            return haversine_km(lat, lng, a_lat, a_lng)

        ratio = ((px - ax) * dx + (py - ay) * dy) / denom
        ratio = max(0.0, min(1.0, ratio))
        closest_x = ax + ratio * dx
        closest_y = ay + ratio * dy
        return math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

    def _editor_load_base_graph_silently(self) -> None:
        """Nạp graph nền vào editor khi người dùng muốn đánh dấu nhưng chưa tải graph."""

        if self.editor_nodes or self.editor_edges:
            return
        self.editor_nodes = list(self.graph.base_node_positions())
        self.editor_edges = list(self.graph.edges_raw())
        self.editor_dead_end_nodes = set(getattr(self.graph, "dead_end_ids", set()))
        self.editor_edge_conditions = dict(self.graph.road_conditions)
        self.editor_created_nodes.clear()

    def _editor_nearest_edge_at(
        self,
        lat: float,
        lng: float,
        *,
        load_base: bool = True,
    ) -> tuple[str, str, float] | None:
        """Tìm cạnh gần con trỏ đủ để thao tác đánh dấu/xóa."""

        if load_base:
            self._editor_load_base_graph_silently()
        if not self.editor_edges:
            return None

        nearest_edge = min(
            self.editor_edges,
            key=lambda edge: self._editor_point_to_edge_distance_km(lat, lng, edge[0], edge[1]),
        )
        distance_km = self._editor_point_to_edge_distance_km(lat, lng, nearest_edge[0], nearest_edge[1])
        max_distance_km = max(SNAP_TO_ROAD_MAX_DISTANCE_M / 1000.0, self.editor_snap_distance_var.get() / 1000.0)
        if distance_km > max_distance_km:
            return None
        return nearest_edge[0], nearest_edge[1], distance_km

    def _selected_editor_condition(self) -> str:
        condition = self.editor_road_condition_var.get()
        if condition not in ROAD_CONDITION_LABELS:
            return ROAD_BAD
        return condition

    def _apply_selected_condition_to_edge(self, a: str, b: str) -> None:
        """Khi vẽ graph mới, cạnh mới nhận ngay mức đường đang chọn nếu checkbox được bật."""

        if not self.editor_mark_bad_road_var.get():
            return
        condition = self._selected_editor_condition()
        key = self._editor_edge_key(a, b)
        if condition == ROAD_NORMAL:
            self.editor_edge_conditions.pop(key, None)
        else:
            self.editor_edge_conditions[key] = condition
        try:
            self.graph.set_edge_condition(a, b, condition)
            self._mark_graph_dirty()
            self._draw_graph()
        except Exception:
            pass

    def _editor_mark_edge(self, a: str, b: str, distance_km: float) -> bool:
        """Cập nhật trạng thái cho một cạnh. Trả về True nếu có thay đổi thật."""

        condition = self._selected_editor_condition()
        key = self._editor_edge_key(a, b)
        current_condition = self._editor_edge_condition(a, b)
        if current_condition == condition and key in self.editor_processed_edges_in_drag:
            return False

        if condition == ROAD_NORMAL:
            self.editor_edge_conditions.pop(key, None)
        else:
            self.editor_edge_conditions[key] = condition

        try:
            self.graph.set_edge_condition(a, b, condition)
            self._mark_graph_dirty()
            self._draw_graph()
        except Exception:
            pass

        self.editor_processed_edges_in_drag.add(key)
        self._redraw_editor_graph()
        label = ROAD_CONDITION_LABELS.get(condition, condition)
        self.status_var.set(f"Đã cập nhật {a} - {b}: {label}.")
        self._log(f"[Graph Editor] {a} - {b}: {label}. Khoảng cách thao tác tới cạnh: {distance_km * 1000:.0f}m.")
        return True

    def _editor_mark_nearest_edge(self, lat: float, lng: float) -> None:
        """Đánh dấu cạnh gần vị trí chuột nhất bằng cấp độ đang chọn."""

        nearest = self._editor_nearest_edge_at(lat, lng, load_base=True)
        if nearest is None:
            if not self.editor_edges:
                messagebox.showinfo("Chưa có graph", "Hãy vẽ graph hoặc hiển thị graph hiện tại trước khi đánh dấu đường.")
            else:
                self.status_var.set("Chuột chưa đủ gần cạnh graph để đánh dấu đường.")
            return
        a, b, distance_km = nearest
        self._editor_mark_edge(a, b, distance_km)

    def _editor_nearest_node_at(self, lat: float, lng: float, *, load_base: bool = True) -> tuple[str, float] | None:
        """Tìm node gần con trỏ đủ để thao tác xóa node."""

        if load_base:
            self._editor_load_base_graph_silently()
        if not self.editor_nodes:
            return None

        max_distance_km = max(SNAP_TO_ROAD_MAX_DISTANCE_M / 1000.0, self.editor_snap_distance_var.get() / 1000.0)
        nearest_id: str | None = None
        nearest_distance = max_distance_km
        for node_id, node_lat, node_lng in self.editor_nodes:
            distance = haversine_km(lat, lng, node_lat, node_lng)
            if distance <= nearest_distance:
                nearest_distance = distance
                nearest_id = node_id
        if nearest_id is None:
            return None
        return nearest_id, nearest_distance

    def _editor_delete_nearest_node(self, lat: float, lng: float) -> None:
        """Xóa node gần vị trí chuột; mọi cạnh liên kết sẽ biến mất theo."""

        nearest = self._editor_nearest_node_at(lat, lng, load_base=True)
        if nearest is None:
            if not self.editor_nodes:
                messagebox.showinfo("Chưa có graph", "Hãy vẽ graph hoặc hiển thị graph hiện tại trước khi xóa node.")
            else:
                self.status_var.set("Chuột chưa đủ gần node graph để xóa.")
            return

        node_id, distance_km = nearest
        if node_id in self.editor_processed_edges_in_drag:
            return

        linked_edges = [edge for edge in self.editor_edges if node_id in edge]
        linked_keys = {self._editor_edge_key(a, b) for a, b in linked_edges}
        self.editor_nodes = [item for item in self.editor_nodes if item[0] != node_id]
        self.editor_edges = [edge for edge in self.editor_edges if node_id not in edge]
        self.editor_dead_end_nodes.discard(node_id)
        self.editor_created_nodes.discard(node_id)
        for key in linked_keys:
            self.editor_edge_conditions.pop(key, None)
        if self.editor_current_stroke:
            self.editor_current_stroke = [item for item in self.editor_current_stroke if item != node_id]

        try:
            self.graph.remove_base_node(node_id)
            self._mark_graph_dirty()
            self._draw_graph()
        except Exception as exc:
            self._log(f"[Graph Editor] Không xóa được node {node_id} khỏi graph nền: {exc}")

        self.editor_processed_edges_in_drag.add(node_id)
        self._redraw_editor_graph()
        self.status_var.set(f"Đã xóa node {node_id} và {len(linked_edges)} cạnh liên kết.")
        self._log(
            f"[Graph Editor] Đã xóa node {node_id}; {len(linked_edges)} cạnh liên kết biến mất. "
            f"Khoảng cách thao tác tới node: {distance_km * 1000:.0f}m."
        )

    def _set_map_path(self, coords: list[tuple[float, float]], color: str, width: int = 5) -> Any:
        if not self.map_widget:
            return None
        try:
            return self.map_widget.set_path(coords, color=color, width=width)
        except TypeError:
            return self.map_widget.set_path(coords)

    def _draw_dashed_editor_edge(self, pos_a: tuple[float, float], pos_b: tuple[float, float]) -> None:
        """Vẽ đường cấm bằng nhiều đoạn ngắn để mô phỏng nét đứt."""

        dash_count = 12
        for index in range(0, dash_count, 2):
            start_ratio = index / dash_count
            end_ratio = (index + 1) / dash_count
            start = (
                pos_a[0] + (pos_b[0] - pos_a[0]) * start_ratio,
                pos_a[1] + (pos_b[1] - pos_a[1]) * start_ratio,
            )
            end = (
                pos_a[0] + (pos_b[0] - pos_a[0]) * end_ratio,
                pos_a[1] + (pos_b[1] - pos_a[1]) * end_ratio,
            )
            path = self._set_map_path([start, end], COLOR_ROAD_BLOCKED, width=5)
            self.editor_paths.append(path)

    def _blocked_road_endpoint_ids(
        self,
        edges: list[tuple[str, str]],
        condition_getter: Callable[[str, str], str],
    ) -> set[str]:
        """Trả về node đầu/cuối của từng đoạn đường cấm liên tiếp.

        Nếu nhiều cạnh cấm nối liền nhau thành một đoạn dài, hệ thống chỉ đặt
        biển cấm tại hai đầu đoạn đó. Các node trung gian vẫn chỉ là một phần
        của nét graph nên bản đồ không bị dày marker.
        """

        blocked_adj: dict[str, set[str]] = {}
        for a, b in edges:
            if condition_getter(a, b) != ROAD_BLOCKED:
                continue
            blocked_adj.setdefault(a, set()).add(b)
            blocked_adj.setdefault(b, set()).add(a)

        endpoints: set[str] = set()
        visited: set[str] = set()
        for start_node in blocked_adj:
            if start_node in visited:
                continue
            stack = [start_node]
            component: set[str] = set()
            visited.add(start_node)
            while stack:
                node_id = stack.pop()
                component.add(node_id)
                for next_node in blocked_adj.get(node_id, set()):
                    if next_node not in visited:
                        visited.add(next_node)
                        stack.append(next_node)

            leaves = {node_id for node_id in component if len(blocked_adj.get(node_id, set())) == 1}
            if leaves:
                endpoints.update(leaves)
            elif component:
                # Trường hợp hiếm: đường cấm tạo vòng kín nên không có đầu/cuối.
                # Đặt một biển đại diện để vẫn thấy đoạn này đang bị cấm.
                endpoints.add(sorted(component)[0])

        return endpoints

    def _set_no_entry_marker(self, lat: float, lng: float, node_id: str) -> Any:
        """Gắn biển cấm bằng ảnh PNG; nếu lỗi thì dùng marker chữ dự phòng."""

        if not self.map_widget:
            return None
        if self.no_entry_icon is None:
            return self._set_marker(lat, lng, f"⛔ {node_id}", COLOR_ROAD_BLOCKED)

        try:
            return self.map_widget.set_marker(lat, lng, text="", icon=self.no_entry_icon)
        except TypeError:
            try:
                return self.map_widget.set_marker(lat, lng, text="", image=self.no_entry_icon)
            except TypeError:
                return self._set_marker(lat, lng, f"⛔ {node_id}", COLOR_ROAD_BLOCKED)

    def _draw_no_entry_marker(self, node_id: str, pos: tuple[float, float]) -> None:
        """Gắn ký hiệu đường cấm tại node đầu/cuối của đoạn cấm."""

        seen: set[str] = getattr(self, "_editor_blocked_marker_node_ids", set())
        if node_id in seen:
            return
        seen.add(node_id)
        self._editor_blocked_marker_node_ids = seen
        marker = self._set_no_entry_marker(pos[0], pos[1], node_id)
        self.editor_markers.append(marker)

    def _draw_editor_edge(self, a: str, b: str) -> None:
        if not self.map_widget:
            return
        pos_a = self._editor_node_position(a)
        pos_b = self._editor_node_position(b)
        if not pos_a or not pos_b:
            return

        condition = self._editor_edge_condition(a, b)
        if condition == ROAD_BLOCKED:
            self._draw_dashed_editor_edge(pos_a, pos_b)
            return

        color = self._editor_condition_color(condition)
        path = self._set_map_path([pos_a, pos_b], color=color, width=5)
        self.editor_paths.append(path)

    def _mark_editor_node_dead_end(self, node_id: str) -> None:
        pos = self._editor_node_position(node_id)
        if not pos:
            return
        label = node_id if node_id.endswith("_DEAD_END") else f"{node_id}_DEAD_END"
        marker = self._set_marker(pos[0], pos[1], label, "black")
        self.editor_markers.append(marker)

    def editor_show_clear_actions(self) -> None:
        """Mở hàng thao tác xóa graph gồm Chọn / Xóa tất cả / Hủy."""

        if self._manual_tool_active():
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", "xóa graph")
            return
        if self.editor_mode_var.get() or self.editor_mark_bad_road_var.get():
            self._warn_unrelated_action("vẽ/đánh dấu đường", "xóa graph")
            return

        if self.editor_clear_main_frame is not None:
            self.editor_clear_main_frame.pack_forget()
        if self.editor_clear_actions_frame is not None and not self.editor_clear_actions_frame.winfo_ismapped():
            self.editor_clear_actions_frame.pack(fill="x", pady=(8, 0))
        self.status_var.set("Chọn kiểu xóa graph: xóa từng node, xóa tất cả hoặc hủy thao tác.")
        self._refresh_action_buttons()

    def editor_select_delete_graph(self) -> None:
        """Bật chế độ xóa từng node graph bằng cách click hoặc kéo gần node."""

        if self._manual_tool_active():
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", "xóa node graph")
            return
        if self.editor_mode_var.get() or self.editor_mark_bad_road_var.get():
            self._warn_unrelated_action("vẽ/đánh dấu đường", "xóa node graph")
            return

        self._editor_load_base_graph_silently()
        if not self.editor_nodes:
            messagebox.showinfo("Chưa có graph", "Hãy vẽ graph hoặc hiển thị graph hiện tại trước khi xóa node.")
            return
        self.editor_delete_graph_mode = True
        self.editor_mode_var.set(False)
        self.editor_mark_bad_road_var.set(False)
        self.editor_processed_edges_in_drag.clear()
        self._on_editor_option_changed()
        self._redraw_editor_graph()
        self._log("[Graph Editor] Đã bật chế độ xóa từng node graph. Click hoặc kéo gần node để xóa; các cạnh liên kết sẽ biến mất theo.")

    def editor_cancel_clear_graph(self) -> None:
        """Hủy giao diện xóa graph và tắt chế độ xóa từng node."""

        self.editor_delete_graph_mode = False
        self.editor_drag_action = None
        self.editor_processed_edges_in_drag.clear()
        if self.editor_clear_actions_frame is not None:
            self.editor_clear_actions_frame.pack_forget()
        if self.editor_clear_main_frame is not None and not self.editor_clear_main_frame.winfo_ismapped():
            self.editor_clear_main_frame.pack(fill="x", pady=(8, 0))
        self._on_editor_option_changed()
        self.status_var.set("Đã hủy thao tác xóa graph.")
        self._refresh_action_buttons()

    def editor_undo_last_node(self) -> None:
        if not self.editor_nodes:
            return
        removed_id, _, _ = self.editor_nodes[-1]
        if removed_id not in self.editor_created_nodes:
            messagebox.showwarning(
                "Không hoàn tác node nền",
                "Hoàn tác node cuối chỉ áp dụng cho node vừa vẽ trong phiên này. Dùng Xóa graph > Chọn để xóa node nền.",
            )
            return

        self.editor_nodes.pop()
        self.editor_created_nodes.discard(removed_id)
        self.editor_dead_end_nodes.discard(removed_id)
        if hasattr(self.graph, "dead_end_ids"):
            self.graph.dead_end_ids.discard(removed_id)

        removed_edges = [edge for edge in self.editor_edges if removed_id in edge]
        for a, b in removed_edges:
            self.editor_edge_conditions.pop(self._editor_edge_key(a, b), None)
        self.editor_edges = [edge for edge in self.editor_edges if removed_id not in edge]
        if self.editor_current_stroke and self.editor_current_stroke[-1] == removed_id:
            self.editor_current_stroke.pop()

        try:
            self.graph.remove_base_node(removed_id)
            self._mark_graph_dirty()
            self._draw_graph()
        except Exception as exc:
            self._log(f"[Graph Editor] Không hoàn tác được node {removed_id} khỏi graph nền: {exc}")

        self._redraw_editor_graph()
        self.status_var.set(f"Đã hoàn tác node {removed_id} và các cạnh liên kết.")

    def editor_clear_all(self) -> None:
        if (self.editor_nodes or self.editor_edges or self.graph.base_node_ids) and not messagebox.askyesno(
            "Xóa tất cả graph",
            "Bạn có chắc muốn xóa toàn bộ node, cạnh và các đánh dấu đường khỏi graph đang dùng trong phiên này không?\n\nNếu muốn giữ lại cho lần chạy sau, bấm Có khi đóng chương trình.",
        ):
            return
        for path in self.editor_paths:
            self._safe_delete(path)
        for marker in self.editor_markers:
            self._safe_delete(marker)
        self.editor_paths.clear()
        self.editor_markers.clear()
        self.editor_nodes.clear()
        self.editor_edges.clear()
        self.editor_dead_end_nodes.clear()
        self.editor_edge_conditions.clear()
        self.editor_created_nodes.clear()
        self.graph.replace_base_graph({}, [], set(), {})
        self._mark_graph_dirty()
        self._draw_graph()
        self.editor_current_stroke.clear()
        self.editor_is_drawing = False
        self.editor_delete_graph_mode = False
        self.editor_drag_action = None
        self.editor_processed_edges_in_drag.clear()
        self.editor_cancel_clear_graph()
        self.status_var.set("Đã xóa toàn bộ graph nền trong phiên hiện tại.")
        self._log("[Graph Editor] Đã xóa toàn bộ node/cạnh/tình trạng đường khỏi graph đang dùng trong phiên này.")

    def _redraw_editor_graph(self, show_nodes: bool = True) -> None:
        for path in self.editor_paths:
            self._safe_delete(path)
        for marker in self.editor_markers:
            self._safe_delete(marker)
        self.editor_paths.clear()
        self.editor_markers.clear()
        self._editor_blocked_marker_node_ids = set()

        if show_nodes:
            for node_id, lat, lng in self.editor_nodes:
                label = node_id
                if node_id in self.editor_dead_end_nodes and not node_id.endswith("_DEAD_END"):
                    label = f"{node_id}_DEAD_END"
                color = "black" if node_id in self.editor_dead_end_nodes else COLOR_GRAPH_NODE
                self.editor_markers.append(self._set_marker(lat, lng, label, color))
        for a, b in self.editor_edges:
            self._draw_editor_edge(a, b)

        blocked_endpoint_ids = self._blocked_road_endpoint_ids(
            list(self.editor_edges),
            lambda u, v: self._editor_edge_condition(u, v),
        )
        for node_id in blocked_endpoint_ids:
            pos = self._editor_node_position(node_id)
            if pos:
                self._draw_no_entry_marker(node_id, pos)

    def editor_show_graph(self) -> None:
        """Hiển thị các cạnh graph hiện tại, gồm cả đường đã đánh dấu."""

        if not self.graph.base_node_ids or not self.graph.edges_raw():
            messagebox.showinfo("Chưa có graph", "Graph hiện tại chưa có cạnh để hiển thị.")
            return
        self.show_graph_var.set(True)
        self._draw_graph()
        self._refresh_action_buttons()
        marked_count = len(self.graph.road_conditions)
        self.status_var.set(
            f"Đang hiển thị graph: {len(self.graph.edges_raw())} cạnh, {marked_count} cạnh đã đánh dấu."
        )
        self._log("[Graph Editor] Đã hiển thị graph đã vẽ/đánh dấu.")

    def editor_hide_graph(self) -> None:
        """Ẩn các cạnh graph khỏi bản đồ, không xóa dữ liệu graph."""

        self.show_graph_var.set(False)
        self._draw_graph()
        self._refresh_action_buttons()
        self.status_var.set("Đã ẩn graph khỏi bản đồ. Dữ liệu graph vẫn được giữ nguyên.")

    def editor_show_nodes(self) -> None:
        """Hiển thị node của graph hiện tại."""

        if not self.graph.base_node_ids:
            messagebox.showinfo("Chưa có graph", "Graph hiện tại chưa có node để hiển thị.")
            return
        self.show_nodes_var.set(True)
        self._draw_graph()
        self._refresh_action_buttons()
        self.status_var.set(f"Đang hiển thị {len(self.graph.base_node_ids)} node của graph.")
        self._log("[Graph Editor] Đã hiển thị node graph.")

    def editor_hide_nodes(self) -> None:
        """Ẩn node của graph khỏi bản đồ, không xóa dữ liệu graph."""

        self.show_nodes_var.set(False)
        self._draw_graph()
        self._refresh_action_buttons()
        self.status_var.set("Đã ẩn node graph khỏi bản đồ. Dữ liệu node vẫn được giữ nguyên.")

    # ------------------------------------------------------------------
    # Tạo thủ công tài xế/đơn hàng bằng cách click lên bản đồ
    # ------------------------------------------------------------------
    def _can_start_manual_action(self, requested: str, allowed_current: set[str] | None = None) -> bool:
        allowed_current = allowed_current or set()
        if self._graph_tool_active():
            self._warn_unrelated_action("Graph Editor", requested)
            return False
        if self.map_action and self.map_action not in allowed_current:
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", requested)
            return False
        return True

    def begin_add_driver(self) -> None:
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc rồi thêm tài xế.")
            return
        if not self._can_start_manual_action("thêm tài xế", {"add_driver_continuous"}):
            return

        self.clear_history_overlay()
        self._clear_pending_pickup()
        self.add_driver_mode = True
        self.create_order_mode = False
        self.map_action = "add_driver_continuous"
        self._set_order_button_state("idle")
        self._show_manual_cancel_button()
        self._refresh_action_buttons()
        self.status_var.set(
            "Chế độ thêm tài xế: click nhiều lần gần đường/node để thêm tài xế. Bấm Hủy để thoát."
        )

    def begin_create_order(self) -> None:
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc rồi tạo đơn mới.")
            return
        if not self._can_start_manual_action("tạo đơn", {"create_order_pickup", "create_order_destination"}):
            return

        self.clear_history_overlay()
        self._clear_pending_pickup()
        self.create_order_mode = True
        self.add_driver_mode = False
        self.map_action = "create_order_pickup"
        self.order_state_var.set("điểm đón")
        self._set_order_button_state("pickup")
        self._show_manual_cancel_button()
        self._refresh_action_buttons()
        self.status_var.set("Tạo đơn: click điểm đón gần đường/node. Bấm Hủy để thoát.")


    def delete_order(self) -> None:
        """Bật chế độ xóa đơn bằng cách click gần điểm đón hoặc điểm đến."""
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc rồi xóa đơn.")
            return
        if not self._can_start_manual_action("xóa đơn", {"delete_order"}):
            return

        waiting_customers = [customer for customer in self.sim.customers if not customer.served]
        if not waiting_customers:
            messagebox.showwarning("Không có đơn", "Chưa có đơn để xóa.")
            return

        self.clear_history_overlay()
        self._clear_pending_pickup()
        self.add_driver_mode = False
        self.create_order_mode = False
        self.map_action = "delete_order"
        self._set_order_button_state("idle")
        self._show_manual_cancel_button()
        self._refresh_action_buttons()
        self.status_var.set("Chế độ xóa đơn: click gần điểm đón hoặc điểm đến của đơn cần xóa. Bấm Hủy để thoát.")

    def cancel_manual_action(self) -> None:
        self.add_driver_mode = False
        self.create_order_mode = False
        self.map_action = None
        self._clear_pending_pickup()
        self.order_state_var.set("điểm đón")
        self._set_order_button_state("idle")
        self._hide_manual_cancel_button()
        self._refresh_action_buttons()
        self.status_var.set("Đã hủy thao tác tạo thủ công.")

    def cancel_map_action(self) -> None:
        """Alias dùng bởi các phần code cũ khi cần hủy thao tác bản đồ."""
        self.cancel_manual_action()

    def _show_manual_cancel_button(self) -> None:
        if self.manual_cancel_button:
            self.manual_cancel_button.pack(fill="x", pady=(8, 0))

    def _hide_manual_cancel_button(self) -> None:
        if self.manual_cancel_button:
            self.manual_cancel_button.pack_forget()

    def _set_order_button_state(self, state: str) -> None:
        if not self.manual_order_button:
            return

        if state == "pickup":
            self.manual_order_button.set_text("Tạo (điểm đón)")
            self.manual_order_button.set_colors("#F59E0B", "#D97706", "#FFFFFF")
            return

        if state == "destination":
            self.manual_order_button.set_text("Tạo (điểm đến)")
            self.manual_order_button.set_colors("#DC2626", "#B91C1C", "#FFFFFF")
            return

        self.manual_order_button.set_text("Tạo")
        self.manual_order_button.set_colors("#F97316", "#EA580C", "#FFFFFF")



    def _find_nearest_customer(self, lat: float, lng: float) -> Customer | None:
        max_distance_km = SNAP_TO_ROAD_MAX_DISTANCE_M / 1000.0
        nearest_customer: Customer | None = None
        nearest_distance = max_distance_km

        for customer in self.sim.customers:
            if customer.served:
                continue

            pickup_distance = haversine_km(lat, lng, customer.lat, customer.lng)
            destination_distance = haversine_km(lat, lng, customer.dest_lat, customer.dest_lng)
            distance = min(pickup_distance, destination_distance)

            if distance <= nearest_distance:
                nearest_distance = distance
                nearest_customer = customer

        return nearest_customer

    def _remove_driver_from_demo(self, driver: Driver) -> None:
        """Xóa tài xế khỏi mô phỏng và làm mới các marker liên quan."""

        if driver.marker:
            self._safe_delete(driver.marker)
            driver.marker = None

        self.clear_routes(clear_log=False, keep_entities=True)
        self._clear_entity_markers()
        self.sim.drivers = [item for item in self.sim.drivers if item.id != driver.id]
        self.sim.active_rides = [ride for ride in self.sim.active_rides if ride.driver.id != driver.id]
        if self.selected_driver_id == driver.id:
            self.selected_driver_id = None
            self._render_empty_driver_info()
        self._refresh_entities()
        self._update_summary_stats()
        self._log(f"Đã xóa tài xế {driver.id}.")

    def delete_selected_driver(self, driver_id: str) -> None:
        """Xóa trực tiếp tài xế đang mở trong thẻ Thông tin tài xế."""

        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc rồi xóa tài xế.")
            return
        if self._graph_tool_active():
            self._warn_unrelated_action("Graph Editor", "xóa tài xế")
            return
        if self.map_action:
            self._warn_unrelated_action("tạo/xóa thủ công trên bản đồ", "xóa tài xế")
            return

        driver = next((item for item in self.sim.drivers if item.id == driver_id), None)
        if driver is None:
            messagebox.showwarning("Không tìm thấy", "Tài xế này không còn trong danh sách hiện tại.")
            self._render_empty_driver_info()
            return

        if driver.busy or self._find_active_ride_by_driver_id(driver.id) is not None:
            messagebox.showwarning("Tài xế đang bận", "Không thể xóa tài xế đang phục vụ chuyến. Hãy hủy hoặc chờ chuyến kết thúc trước.")
            return

        if not messagebox.askyesno("Xóa tài xế", f"Bạn có chắc muốn xóa tài xế {driver.id} khỏi mô phỏng không?"):
            return

        self._remove_driver_from_demo(driver)
        self.status_var.set(f"Đã xóa tài xế {driver.id} khỏi danh sách mô phỏng.")


    def _delete_order_by_click(self, lat: float, lng: float) -> None:
        customer = self._find_nearest_customer(lat, lng)
        if not customer:
            messagebox.showwarning("Không tìm thấy", "Không tìm thấy đơn gần vị trí đã chọn.")
            return

        if customer.marker:
            self._safe_delete(customer.marker)
            customer.marker = None
        if customer.destination_marker:
            self._safe_delete(customer.destination_marker)
            customer.destination_marker = None

        self.clear_routes(clear_log=False, keep_entities=True)
        self._clear_entity_markers()
        self.sim.customers = [item for item in self.sim.customers if item.id != customer.id]
        self.sim.active_rides = [ride for ride in self.sim.active_rides if ride.customer.id != customer.id]
        self._refresh_entities()
        self._update_summary_stats()
        self._log(f"Đã xóa đơn {customer.id}, bao gồm điểm đón và điểm đến.")
        self.status_var.set("Đã xóa đơn. Có thể tiếp tục click để xóa đơn khác hoặc bấm Hủy.")

    def _clear_pending_pickup(self) -> None:
        if self.pending_pickup_marker:
            self._safe_delete(self.pending_pickup_marker)
        self.pending_pickup_marker = None
        self.pending_pickup = None

    def _snap_click_to_graph(self, lat: float, lng: float, prefix: str) -> tuple[str, float, float, float] | None:
        return self.graph.add_connected_point_near_road(
            lat,
            lng,
            prefix=prefix,
            max_distance_km=SNAP_TO_ROAD_MAX_DISTANCE_M / 1000.0,
        )

    def _handle_map_click(self, coords: tuple[float, float]) -> None:
        if not self.map_action:
            return
        if self._graph_tool_active():
            return

        lat, lng = float(coords[0]), float(coords[1])

        if self.map_action == "delete_order":
            self._delete_order_by_click(lat, lng)
            return

        if self.map_action == "add_driver_continuous":
            snapped = self._snap_click_to_graph(lat, lng, "MANUAL_DRIVER")
            if not snapped:
                self._warning_unknown_position()
                self.status_var.set("Không xác định vị trí tài xế. Hãy chọn gần đường/node hơn.")
                return
            node_id, new_lat, new_lng, distance_km = snapped
            driver = self.sim.add_manual_driver(node_id, new_lat, new_lng)
            driver.marker = self._set_driver_marker(driver, driver.id, COLOR_DRIVER_FREE)
            self._update_summary_stats()
            self._log(f"Đã thêm {driver.id} tại vị trí tự chọn, cách đường gần nhất {distance_km * 1000:.0f}m. (Chế độ tiếp tục - nhấn Hủy để dừng)")
            self.status_var.set(f"Đã thêm {driver.id}. Bấm Hủy để dừng hoặc tiếp tục thêm tài xế.")
            # Keep in add_driver mode for continuous addition
            return

        if self.map_action == "create_order_pickup":
            snapped = self._snap_click_to_graph(lat, lng, "ORDER_PICKUP")
            if not snapped:
                self._warning_unknown_position()
                self.status_var.set("Không xác định điểm đón. Hãy chọn gần đường/node hơn.")
                return
            node_id, new_lat, new_lng, distance_km = snapped
            self._clear_pending_pickup()
            self.pending_pickup = {
                "node_id": node_id,
                "lat": new_lat,
                "lng": new_lng,
            }
            self.pending_pickup_marker = self._set_marker(new_lat, new_lng, str(node_id), COLOR_CUSTOMER)
            self.map_action = "create_order_destination"
            self.order_state_var.set("điểm đến")
            self._set_order_button_state("destination")
            self._log(f"Đã chọn điểm đón mới, cách đường gần nhất {distance_km * 1000:.0f}m. Tiếp tục chọn điểm đến.")
            self.status_var.set("Đã chọn điểm đón. Bây giờ click điểm đến gần đường/node.")
            return

        if self.map_action == "create_order_destination":
            if not self.pending_pickup:
                self.map_action = "create_order_pickup"
                self.order_state_var.set("điểm đón")
                self._set_order_button_state("pickup")
                self.status_var.set("Thiếu điểm đón. Hãy chọn lại điểm đón.")
                return
            snapped = self._snap_click_to_graph(lat, lng, "ORDER_DEST")
            if not snapped:
                self._warning_unknown_position()
                self.status_var.set("Không xác định điểm đến. Hãy chọn gần đường/node hơn.")
                return
            dest_node_id, dest_lat, dest_lng, distance_km = snapped
            pickup_node_id = str(self.pending_pickup["node_id"])
            pickup_lat = float(self.pending_pickup["lat"])
            pickup_lng = float(self.pending_pickup["lng"])
            customer = self.sim.add_manual_customer(
                pickup_node_id,
                pickup_lat,
                pickup_lng,
                dest_node_id,
                dest_lat,
                dest_lng,
            )
            self._clear_pending_pickup()
            # Reset to pickup state for continuous order creation
            self.map_action = "create_order_pickup"
            self.order_state_var.set("điểm đón")
            self._set_order_button_state("pickup")
            self._refresh_entities()
            self._log(f"Đã tạo đơn {customer.id}; điểm đến cách đường gần nhất {distance_km * 1000:.0f}m. (Chế độ tiếp tục - nhấn Hủy để dừng)")
            self.status_var.set(f"Đã tạo đơn {customer.id}. Bấm Hủy để dừng hoặc tiếp tục tạo đơn.")
            # Keep in create_order mode for continuous creation
            return

    def _replace_driver_marker(self, driver: Driver, text: str, color: str) -> None:
        if driver.marker:
            self._safe_delete(driver.marker)
        driver.marker = self._set_driver_marker(driver, text, color)

    # ------------------------------------------------------------------
    # Lịch sử chuyến đi
    # ------------------------------------------------------------------
    def _refresh_history_list(self) -> None:
        if not self.history_listbox:
            return
        self.history_listbox.delete(0, "end")
        if not self.sim.ride_history:
            self.history_listbox.insert("end", "Chưa có chuyến nào")
            return
        for history in self.sim.ride_history:
            self.history_listbox.insert(
                "end",
                f"{history.id}: {history.driver_id} chở {history.customer_id} - {history.total_distance_km:.2f} km",
            )

    def _record_completed_ride(self, ride: ActiveRide) -> None:
        if ride.history_saved:
            return
        pickup_route_coords = [self.graph.node_position(node_id) for node_id in ride.pickup_node_path]
        dropoff_route_coords = [self.graph.node_position(node_id) for node_id in ride.dropoff_node_path]
        history = RideHistory(
            id=f"TRIP{len(self.sim.ride_history) + 1:03d}",
            driver_id=ride.driver.id,
            customer_id=ride.customer.id,
            pickup_lat=ride.customer.lat,
            pickup_lng=ride.customer.lng,
            dest_lat=ride.customer.dest_lat,
            dest_lng=ride.customer.dest_lng,
            driver_start_lat=ride.driver_start_lat,
            driver_start_lng=ride.driver_start_lng,
            pickup_distance_km=ride.pickup_distance_km,
            dropoff_distance_km=ride.dropoff_distance_km,
            total_distance_km=ride.pickup_distance_km + ride.dropoff_distance_km,
            driver_start_node_id=ride.pickup_node_path[0] if ride.pickup_node_path else ride.driver.node_id,
            pickup_node_id=ride.customer.pickup_node_id,
            destination_node_id=ride.customer.destination_node_id,
            pickup_node_path=ride.pickup_node_path[:],
            dropoff_node_path=ride.dropoff_node_path[:],
            pickup_route_coords=pickup_route_coords,
            dropoff_route_coords=dropoff_route_coords,
        )
        self.sim.ride_history.append(history)
        ride.history_saved = True
        self._refresh_history_list()
        self._log(f"Đã lưu lịch sử {history.id}: {history.driver_id} - {history.customer_id}, tổng {history.total_distance_km:.2f} km.")

    def clear_history_overlay(self) -> None:
        for path in self.history_overlay_paths:
            self._safe_delete(path)
        for marker in self.history_overlay_markers:
            self._safe_delete(marker)
        self.history_overlay_paths.clear()
        self.history_overlay_markers.clear()

    def _selected_history(self) -> RideHistory | None:
        if not self.history_listbox or not self.sim.ride_history:
            return None
        selected = self.history_listbox.curselection()
        if not selected:
            return None
        index = selected[0]
        if index < 0 or index >= len(self.sim.ride_history):
            return None
        return self.sim.ride_history[index]

    def show_selected_history(self) -> None:
        history = self._selected_history()
        if not history:
            return
        if not self.map_widget:
            return
        self.clear_history_overlay()
        try:
            pickup_path = self.map_widget.set_path(history.pickup_route_coords, color=COLOR_ROUTE_PICKUP, width=5)
            dropoff_path = self.map_widget.set_path(history.dropoff_route_coords, color=COLOR_ROUTE_DROPOFF, width=5)
        except TypeError:
            pickup_path = self.map_widget.set_path(history.pickup_route_coords)
            dropoff_path = self.map_widget.set_path(history.dropoff_route_coords)
        self.history_overlay_paths.extend([pickup_path, dropoff_path])
        self.history_overlay_markers.append(
            self._set_marker(history.pickup_lat, history.pickup_lng, history.id, COLOR_CUSTOMER)
        )
        self.history_overlay_markers.append(
            self._set_marker(history.dest_lat, history.dest_lng, history.id, COLOR_DESTINATION)
        )
        self.status_var.set(
            f"Đang xem lại {history.id}: {history.driver_id} chở {history.customer_id}, tổng {history.total_distance_km:.2f} km."
        )

    def _update_summary_stats(self) -> None:
        self.stats_driver_var.set(str(len(self.sim.drivers)))
        waiting_customers = sum(1 for customer in self.sim.customers if not customer.served)
        self.stats_customer_var.set(str(waiting_customers))
        active_count = sum(1 for ride in self.sim.active_rides if ride.stage != "done")
        self.stats_active_ride_var.set(str(active_count))


    def generate_random_drivers(self) -> None:
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc hoặc bấm reset.")
            return

        self.cancel_map_action()
        self.clear_history_overlay()
        self.clear_routes(clear_log=False, keep_entities=True)
        self._clear_entity_markers()

        self.sim.generate_random_drivers(self.driver_count_var.get())

        self._refresh_entities()
        self._update_summary_stats()
        self.status_var.set(
            f"Đã sinh {self.driver_count_var.get()} tài xế ngẫu nhiên. "
            "Khách hàng hiện có vẫn được giữ lại."
        )

    def generate_random_customers(self) -> None:
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc hoặc bấm reset.")
            return

        self.cancel_map_action()
        self.clear_history_overlay()
        self.clear_routes(clear_log=False, keep_entities=True)
        self._clear_entity_markers()

        self.sim.generate_random_customers(self.customer_count_var.get())

        self._refresh_entities()
        self._update_summary_stats()
        self.status_var.set(
            f"Đã sinh {self.customer_count_var.get()} khách hàng ngẫu nhiên. "
            "Tài xế hiện có vẫn được giữ lại."
        )

    def generate_random_data(self) -> None:
        """Hàm cũ để tương thích - sinh cả tài xế và khách hàng."""
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Hãy đợi giả lập hiện tại kết thúc hoặc bấm reset.")
            return
        self.cancel_map_action()
        self.clear_history_overlay()
        self.clear_routes(clear_log=False, keep_entities=True)
        self._clear_entity_markers()
        self.sim.generate_random_entities(self.driver_count_var.get(), self.customer_count_var.get())
        self._refresh_entities()
        self._update_summary_stats()
        self.status_var.set("Đã sinh dữ liệu. Chọn thuật toán rồi bấm Chạy giả lập.")
    
    def reset_demo(self) -> None:
        """Đưa chương trình về trạng thái ban đầu như lúc mới mở app."""
        self.is_animating = False
        self.cancel_map_action()
        self.clear_history_overlay()
        self._clear_pending_pickup()

        # Xóa marker tài xế / khách hàng hiện có
        self._clear_entity_markers()

        # Xóa tuyến đường đang vẽ
        for path in list(self.route_paths):
            self._safe_delete(path)
        self.route_paths.clear()

        # Reset dữ liệu mô phỏng
        self.sim.reset(clear_history=True)
        self.graph.reset_dynamic_nodes()

        # Reset log
        self.log_text.delete("1.0", "end")

        # Reset danh sách lịch sử và thống kê
        self._refresh_history_list()
        self._update_summary_stats()
        self._update_control_buttons()
        self._render_empty_driver_info()

        self.status_var.set("Sẵn sàng. Hãy sinh dữ liệu rồi chạy giả lập.")

    def _clear_entity_markers(self) -> None:
        for driver in self.sim.drivers:
            if driver.marker:
                self._safe_delete(driver.marker)
                driver.marker = None
        for customer in self.sim.customers:
            if customer.marker:
                self._safe_delete(customer.marker)
                customer.marker = None
            if customer.destination_marker:
                self._safe_delete(customer.destination_marker)
                customer.destination_marker = None

    def _refresh_entities(self) -> None:
        if not self.map_widget:
            return

        for driver in self.sim.drivers:
            if driver.marker:
                self._safe_delete(driver.marker)
            color = COLOR_DRIVER_BUSY if driver.busy else COLOR_DRIVER_FREE
            driver.marker = self._set_driver_marker(driver, driver.id, color)

        for customer in self.sim.customers:
            if customer.marker:
                self._safe_delete(customer.marker)
                customer.marker = None
            if customer.destination_marker:
                self._safe_delete(customer.destination_marker)
                customer.destination_marker = None
            if customer.served:
                continue

            if not self._is_customer_picked_up(customer.id):
                customer.marker = self._set_customer_marker(customer, customer.id, COLOR_CUSTOMER)

            customer.destination_marker = self._set_marker(
                customer.dest_lat,
                customer.dest_lng,
                customer.id,
                COLOR_DESTINATION,
            )

        self._update_summary_stats()

    def show_algorithm_comparison(self) -> None:
        """Mở cửa sổ so sánh BFS/Local Search và A*/UCS với bố cục giữ nguyên dữ liệu, chỉ làm mới giao diện."""

        waiting_customers = [customer for customer in self.sim.customers if not customer.served]
        customers = waiting_customers
        drivers = [driver for driver in self.sim.drivers if not driver.busy] or list(self.sim.drivers)

        has_driver_search_data = bool(customers and drivers) or bool(self.sim.ride_history and drivers)
        has_route_data = bool(self.sim.ride_history) or bool(customers and drivers)

        if not has_driver_search_data and not has_route_data:
            messagebox.showinfo(
                "Thiếu dữ liệu",
                "Chưa có dữ liệu để so sánh. Hãy sinh/tạo tài xế, tạo đơn hoặc hoàn thành chuyến trước.",
            )
            return

        self.cancel_map_action()
        self.clear_history_overlay()

        win = tk.Toplevel(self.root)
        win.title("So sánh thuật toán")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # Mở cửa sổ so sánh gần như phủ toàn bộ màn hình, giống bố cục ảnh mẫu.
        # Không đặt transient để Windows giữ đủ nút thu nhỏ / phóng to / đóng trên thanh tiêu đề.
        width = max(1120, screen_w - 120)
        height = max(650, screen_h - 190)
        width = min(width, screen_w - 40)
        height = min(height, screen_h - 80)
        pos_x = max(20, (screen_w - width) // 2)
        pos_y = max(20, min(60, (screen_h - height) // 2))
        win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        win.minsize(1120, 650)
        win.resizable(True, True)
        win.configure(bg=APP_BG)
        win.rowconfigure(1, weight=1)
        win.columnconfigure(0, weight=1)

        header = RoundedFrame(win, radius=20, padding=14, bg=APP_BG, fill=SURFACE, outline=BORDER)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.body.columnconfigure(0, weight=1)
        header.body.columnconfigure(1, weight=0)

        title_block = tk.Frame(header.body, bg=SURFACE)
        title_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="So sánh các thuật toán sử dụng",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Tìm tài xế: Local Search, BFS, DFS, Greedy, UCS. Tìm đường đi: A*, UCS, DFS, BFS, Greedy.",
            bg=SURFACE,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        # Nút đóng riêng trong nội dung đã được bỏ. Người dùng dùng nút hệ thống
        # trên thanh tiêu đề để đóng, thu nhỏ hoặc phóng to cửa sổ so sánh.

        notebook = ttk.Notebook(win, style="Modern.TNotebook")
        notebook.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 16))

        driver_tab = tk.Frame(notebook, bg=APP_BG)
        route_tab = tk.Frame(notebook, bg=APP_BG)
        notebook.add(driver_tab, text="Tìm kiếm tài xế")
        notebook.add(route_tab, text="Tìm đường đi")

        driver_metric_sources = self._build_driver_search_metric_sources(customers, drivers)
        route_metrics = self._collect_route_comparison(customers, drivers)

        self._render_driver_search_tab(driver_tab, driver_metric_sources)
        self._render_route_tab(route_tab, route_metrics)

        self._log("Đã mở bảng so sánh 5 thuật toán tìm tài xế và 5 thuật toán tìm đường.")
        self.status_var.set("Đang hiển thị bảng so sánh thuật toán.")

    def _build_driver_search_metric_sources(
        self,
        customers: list[Any],
        drivers: list[Driver],
    ) -> list[dict[str, Any]]:
        """Tạo các nguồn dữ liệu cho tab tìm tài xế.

        Người dùng có thể xem biểu đồ tổng hợp hoặc chọn riêng từng vị trí đặt xe.
        Với các chuyến đã hoàn thành, hệ thống bổ sung thêm vị trí đón từ lịch sử
        để vẫn xem lại được biểu đồ của từng chuyến.
        """
        source_items: list[tuple[str, list[Any]]] = []
        seen_keys: set[str] = set()

        def add_source(label: str, customer_like: Any) -> None:
            key = f"{getattr(customer_like, 'id', '')}:{getattr(customer_like, 'lat', 0):.7f}:{getattr(customer_like, 'lng', 0):.7f}"
            if key in seen_keys:
                return
            seen_keys.add(key)
            source_items.append((label, [customer_like]))

        for index, customer in enumerate(customers, start=1):
            customer_id = getattr(customer, "id", f"Đơn {index}")
            add_source(
                f"{customer_id} - vị trí đặt xe {index}",
                customer,
            )

        for index, history in enumerate(self.sim.ride_history, start=1):
            if not (history.pickup_lat and history.pickup_lng):
                continue
            pickup_node_id = self._resolve_node_id(
                history.pickup_node_id,
                history.pickup_lat,
                history.pickup_lng,
            )
            history_customer = SimpleNamespace(
                id=f"{history.id}/{history.customer_id}",
                pickup_node_id=pickup_node_id,
                lat=history.pickup_lat,
                lng=history.pickup_lng,
            )
            add_source(
                f"Chuyến {history.id} - điểm đặt {history.customer_id}",
                history_customer,
            )

        if not source_items:
            return []

        sources: list[dict[str, Any]] = []
        all_customers: list[Any] = []
        for _label, customer_list in source_items:
            all_customers.extend(customer_list)

        sources.append(
            {
                "label": "Tổng hợp tất cả vị trí đặt xe",
                "metrics": self._collect_driver_search_comparison(all_customers, drivers),
            }
        )
        for label, customer_list in source_items:
            sources.append(
                {
                    "label": label,
                    "metrics": self._collect_driver_search_comparison(customer_list, drivers),
                }
            )

        return sources

    def _algorithm_key(self, algorithm: str) -> str:
        return algorithm.lower().replace(" ", "_").replace("*", "star").replace("-", "_")

    def _set_equal_tree_columns(
        self,
        table: ttk.Treeview,
        columns: tuple[str, ...],
        *,
        min_width: int = 72,
    ) -> None:
        """Chia đều độ rộng các cột theo chiều rộng bảng hiện tại."""

        def apply_equal_width(event: tk.Event | None = None) -> None:
            try:
                table_width = int(getattr(event, "width", 0) or table.winfo_width())
                if table_width <= 1:
                    return
                usable_width = max(1, table_width - 6)
                column_width = max(min_width, usable_width // max(1, len(columns)))
                for column in columns:
                    table.column(
                        column,
                        width=column_width,
                        minwidth=min_width,
                        anchor="center",
                        stretch=True,
                    )
            except tk.TclError:
                return

        table.bind("<Configure>", apply_equal_width, add="+")
        table.after(80, apply_equal_width)
        table.after(300, apply_equal_width)

    def _stretch_card_body_height(self, card: RoundedFrame) -> None:
        """Cho phần body của card giãn theo chiều cao thật của card."""

        def apply_height(event: tk.Event | None = None) -> None:
            try:
                canvas_height = int(getattr(event, "height", 0) or card.canvas.winfo_height())
                body_height = max(1, canvas_height - card.padding * 2)
                card.canvas.itemconfigure(card._window, height=body_height)
            except tk.TclError:
                return

        card.canvas.bind("<Configure>", apply_height, add="+")
        card.canvas.after(80, apply_height)
        card.canvas.after(300, apply_height)

    def _collect_driver_search_comparison(self, customers: list[Any], drivers: list[Driver]) -> list[dict[str, float | int | str]]:
        metrics: list[dict[str, float | int | str]] = []
        available_drivers = [driver for driver in drivers if not getattr(driver, "busy", False)]
        for radius in SEARCH_RADII_KM:
            row: dict[str, float | int | str] = {"radius": radius, "radius_m": int(round(radius * 1000))}
            for algorithm in DRIVER_SEARCH_ALGORITHMS:
                key = self._algorithm_key(algorithm)
                found_driver_ids: set[str] = set()
                visited_total = 0
                start_time = time.perf_counter()
                for customer in customers:
                    pickup_node_id = self._resolve_node_id(getattr(customer, "pickup_node_id", None), customer.lat, customer.lng)
                    report = run_driver_search_algorithm(self.graph, pickup_node_id, available_drivers, radius, algorithm, None)
                    found_driver_ids.update(candidate.driver.id for candidate in report.candidates)
                    visited_total += report.visited_nodes
                row[f"{key}_found"] = len(found_driver_ids)
                row[f"{key}_time_ms"] = (time.perf_counter() - start_time) * 1000
                row[f"{key}_visited"] = visited_total
            metrics.append(row)
        return metrics

    def _node_exists(self, node_id: str | None) -> bool:
        """Kiểm tra node có còn tồn tại trong graph hiện tại không."""
        return bool(node_id) and node_id in self.graph.nodes

    def _resolve_node_id(self, node_id: str | None, lat: float, lng: float) -> str:
        """Trả về node hợp lệ để chạy A*/UCS.

        Một số chuyến thủ công dùng node động như PICKUP_0025/DEST_0026.
        Nếu người dùng sinh lại dữ liệu hoặc graph được dựng lại, các node động
        cũ có thể không còn trong self.graph.nodes. Khi đó ta gán lại về node
        gần nhất theo tọa độ đã lưu để không bị KeyError và vẫn so sánh được.
        """
        if self._node_exists(node_id):
            return str(node_id)
        return self.graph.nearest_node_id(lat, lng)

    def _path_result_metrics(self, start_id: str, goal_id: str) -> dict[str, float | int]:
        result_metrics: dict[str, float | int] = {}
        for algorithm in ROUTE_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            result_metrics[f"{key}_time_ms"] = 0.0
            result_metrics[f"{key}_visited"] = 0
            result_metrics[f"{key}_cost"] = 0.0
            result_metrics[f"{key}_path_len"] = 0
        if not self._node_exists(start_id) or not self._node_exists(goal_id):
            return result_metrics
        for algorithm in ROUTE_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            try:
                start_time = time.perf_counter()
                result = run_path_algorithm(self.graph, start_id, goal_id, algorithm)
                result_metrics[f"{key}_time_ms"] = (time.perf_counter() - start_time) * 1000
                result_metrics[f"{key}_visited"] = result.visited_nodes
                result_metrics[f"{key}_cost"] = 0.0 if result.cost_km == float("inf") else result.cost_km
                result_metrics[f"{key}_path_len"] = len(result.path)
            except Exception:
                pass
        return result_metrics

    def _merge_route_legs(
        self, *, label: str, route_detail: str, pickup_leg: dict[str, float | int], dropoff_leg: dict[str, float | int],
    ) -> dict[str, float | int | str]:
        row: dict[str, float | int | str] = {"label": label, "route_detail": route_detail}
        for algorithm in ROUTE_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            row[f"{key}_time_ms"] = float(pickup_leg.get(f"{key}_time_ms", 0.0)) + float(dropoff_leg.get(f"{key}_time_ms", 0.0))
            row[f"{key}_visited"] = int(pickup_leg.get(f"{key}_visited", 0)) + int(dropoff_leg.get(f"{key}_visited", 0))
            row[f"{key}_cost"] = float(pickup_leg.get(f"{key}_cost", 0.0)) + float(dropoff_leg.get(f"{key}_cost", 0.0))
            row[f"{key}_path_len"] = int(pickup_leg.get(f"{key}_path_len", 0)) + int(dropoff_leg.get(f"{key}_path_len", 0))
        return row

    def _collect_route_comparison(self, customers: list[Any], drivers: list[Driver]) -> list[dict[str, float | int | str]]:
        """Thu thập số liệu A*/UCS cho tất cả chuyến đã hoàn thành.

        Mỗi dòng là tổng 2 chặng của một chuyến:
        tài xế -> điểm đón và điểm đón -> điểm đến.
        Nếu node động trong lịch sử không còn tồn tại, hệ thống tự quy về node
        gần nhất từ tọa độ đã lưu thay vì báo KeyError.
        """
        metrics: list[dict[str, float | int | str]] = []

        for history in self.sim.ride_history:
            # Bỏ qua lịch sử quá cũ không có đủ tọa độ cơ bản.
            if not (history.driver_start_lat and history.driver_start_lng and history.pickup_lat and history.pickup_lng and history.dest_lat and history.dest_lng):
                continue

            driver_start_id = self._resolve_node_id(
                history.driver_start_node_id,
                history.driver_start_lat,
                history.driver_start_lng,
            )
            pickup_id = self._resolve_node_id(
                history.pickup_node_id,
                history.pickup_lat,
                history.pickup_lng,
            )
            destination_id = self._resolve_node_id(
                history.destination_node_id,
                history.dest_lat,
                history.dest_lng,
            )

            pickup_leg = self._path_result_metrics(driver_start_id, pickup_id)
            dropoff_leg = self._path_result_metrics(pickup_id, destination_id)

            metrics.append(
                self._merge_route_legs(
                    label=history.id,
                    route_detail=f"{history.driver_id} chở {history.customer_id}",
                    pickup_leg=pickup_leg,
                    dropoff_leg=dropoff_leg,
                )
            )

        if metrics:
            return metrics

        if not customers or not drivers:
            return []

        # Fallback khi chưa chạy xong chuyến nào: minh họa bằng một chuyến mẫu đang chờ.
        customer = customers[0]
        driver = min(
            drivers,
            key=lambda item: haversine_km(customer.lat, customer.lng, item.lat, item.lng),
        )
        driver_id = self._resolve_node_id(driver.node_id, driver.lat, driver.lng)
        pickup_id = self._resolve_node_id(customer.pickup_node_id, customer.lat, customer.lng)
        destination_id = self._resolve_node_id(customer.destination_node_id, customer.dest_lat, customer.dest_lng)

        pickup_leg = self._path_result_metrics(driver_id, pickup_id)
        dropoff_leg = self._path_result_metrics(pickup_id, destination_id)
        metrics.append(
            self._merge_route_legs(
                label="Mẫu",
                route_detail=f"{driver.id} chở {customer.id}",
                pickup_leg=pickup_leg,
                dropoff_leg=dropoff_leg,
            )
        )
        return metrics

    def _render_driver_search_tab(self, parent: tk.Frame, metric_sources: list[dict[str, Any]]) -> None:
        parent.configure(bg=APP_BG)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        summary_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(8, 6))
        summary_card.body.columnconfigure(1, weight=1)
        tk.Label(summary_card.body, text="Tìm kiếm tài xế", bg=SURFACE, fg=TEXT_PRIMARY, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", columnspan=2)
        tk.Label(summary_card.body, text="Vị trí đặt xe:", bg=SURFACE, fg=TEXT_PRIMARY, font=("Segoe UI", 8, "bold")).grid(row=1, column=0, sticky="w", padx=(0,8), pady=(6,0))
        option_values = [str(source["label"]) for source in metric_sources] or ["Không có dữ liệu"]
        source_by_label = {str(source["label"]): source.get("metrics", []) for source in metric_sources}
        selected_source = tk.StringVar(value=option_values[0])
        selector = ttk.Combobox(summary_card.body, textvariable=selected_source, values=option_values, state="readonly", width=56)
        selector.grid(row=1, column=1, sticky="ew", pady=(6,0))

        chart_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        chart_card.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        chart_card.body.rowconfigure(0, weight=1)
        chart_card.body.columnconfigure(0, weight=1)
        self._stretch_card_body_height(chart_card)
        chart = tk.Canvas(chart_card.body, height=390, bg="#F8FBFF", highlightthickness=0, bd=0)
        chart.grid(row=0, column=0, sticky="nsew")

        columns = ["radius"]
        for algorithm in DRIVER_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            columns.extend([f"{key}_found", f"{key}_time", f"{key}_visited"])
        columns = tuple(columns)

        table_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        table_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        table_card.body.columnconfigure(0, weight=1)
        tk.Label(table_card.body, text="Bảng số liệu chi tiết", bg=SURFACE, fg=TEXT_PRIMARY, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        table_frame = tk.Frame(table_card.body, bg=SURFACE)
        table_frame.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", style="Modern.Horizontal.TScrollbar")
        table = ttk.Treeview(table_frame, columns=columns, show="headings", height=3, xscrollcommand=x_scroll.set, style="Comparison.Treeview")
        x_scroll.config(command=table.xview)
        headings = {"radius": "Bán kính"}
        for algorithm in DRIVER_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            headings[f"{key}_found"] = f"{algorithm} tìm"
            headings[f"{key}_time"] = f"{algorithm} ms"
            headings[f"{key}_visited"] = f"{algorithm} bước"
        for col in columns:
            table.heading(col, text=headings.get(col, col))
            table.column(col, width=90, minwidth=72, anchor="center", stretch=True)
        self._set_equal_tree_columns(table, columns, min_width=72)
        table.grid(row=0, column=0, sticky="ew")
        x_scroll.grid(row=1, column=0, sticky="ew", pady=(4,0))

        def current_metrics() -> list[dict[str, float | int | str]]:
            return list(source_by_label.get(selected_source.get(), []) or [])
        def refresh_driver_metrics(*_args: Any) -> None:
            metrics = current_metrics()
            table.delete(*table.get_children())
            for item in metrics:
                values = [f"{float(item.get('radius',0.0)):.1f} km"]
                for algorithm in DRIVER_SEARCH_ALGORITHMS:
                    key = self._algorithm_key(algorithm)
                    values.extend([int(item.get(f"{key}_found",0)), f"{float(item.get(f'{key}_time_ms',0.0)):.3f}", int(item.get(f"{key}_visited",0))])
                table.insert("", "end", values=tuple(values))
            self._draw_time_driver_chart(
                chart,
                metrics=metrics,
                compact_x_axis=selected_source.get().startswith("Tổng hợp"),
            )
        chart.bind(
            "<Configure>",
            lambda _event: self._draw_time_driver_chart(
                chart,
                metrics=current_metrics(),
                compact_x_axis=selected_source.get().startswith("Tổng hợp"),
            ),
        )
        selector.bind("<<ComboboxSelected>>", lambda _event: refresh_driver_metrics())
        refresh_driver_metrics()

    def _render_route_tab(self, parent: tk.Frame, metrics: list[dict[str, float | int | str]]) -> None:
        """Vẽ tab so sánh thuật toán tìm đường.

        Khi có nhiều chuyến trong lịch sử, tab này cho phép xem tất cả theo từng
        nhóm tối đa 12 chuyến hoặc xem riêng từng chuyến. Cách này giúp biểu đồ
        không bị quá dày khi lịch sử đã có nhiều chuyến.
        """
        parent.configure(bg=APP_BG)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        summary_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        summary_card.grid(row=0, column=0, sticky="ew", pady=(8, 6))
        summary_card.body.columnconfigure(1, weight=1)

        tk.Label(
            summary_card.body,
            text="Tìm đường đi ngắn nhất",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", columnspan=2)

        view_all_label = "Hiển thị tất cả chuyến đi"
        average_label = "Trung bình tất cả các chuyến"
        mode_values = [view_all_label, average_label]
        metric_by_mode: dict[str, list[dict[str, float | int | str]]] = {}
        for item in metrics:
            label = str(item.get("label", "Chuyến"))
            detail = str(item.get("route_detail", ""))
            display = f"{label} - {detail}" if detail else label
            metric_by_mode[display] = [item]
            mode_values.append(display)

        if not metrics:
            mode_values = ["Không có dữ liệu"]

        selected_mode = tk.StringVar(value=mode_values[0])
        tk.Label(
            summary_card.body,
            text="Chế độ hiển thị:",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        mode_selector = ttk.Combobox(
            summary_card.body,
            textvariable=selected_mode,
            values=mode_values,
            state="readonly",
            width=52,
        )
        mode_selector.grid(row=1, column=1, sticky="ew", pady=(6, 0))

        grouped_metrics: dict[str, list[dict[str, float | int | str]]] = {}
        if metrics:
            for start in range(0, len(metrics), 12):
                end = min(start + 12, len(metrics))
                grouped_metrics[f"{start + 1}-{end}"] = metrics[start:end]
        range_values = list(grouped_metrics.keys()) or ["Không có dữ liệu"]
        selected_range = tk.StringVar(value=range_values[0])

        def average_route_metrics(source: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
            if not source:
                return []
            row: dict[str, float | int | str] = {
                "label": "Trung bình",
                "route_detail": f"Tất cả {len(source)} chuyến",
            }
            for algorithm in ROUTE_SEARCH_ALGORITHMS:
                key = self._algorithm_key(algorithm)
                row[f"{key}_cost"] = sum(float(item.get(f"{key}_cost", 0.0)) for item in source) / len(source)
                row[f"{key}_visited"] = sum(float(item.get(f"{key}_visited", 0.0)) for item in source) / len(source)
                row[f"{key}_time_ms"] = sum(float(item.get(f"{key}_time_ms", 0.0)) for item in source) / len(source)
                row[f"{key}_path_len"] = sum(float(item.get(f"{key}_path_len", 0.0)) for item in source) / len(source)
            return [row]

        average_metrics = average_route_metrics(metrics)

        range_label = tk.Label(
            summary_card.body,
            text="Nhóm chuyến:",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
        )
        range_selector = ttk.Combobox(
            summary_card.body,
            textvariable=selected_range,
            values=range_values,
            state="readonly",
            width=24,
        )

        info_var = tk.StringVar(value="")
        info_label = tk.Label(
            summary_card.body,
            textvariable=info_var,
            bg=METRIC_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=5,
            anchor="w",
            justify="left",
        )
        info_label.grid(row=3, column=0, sticky="ew", columnspan=2, pady=(6, 0))

        chart_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        chart_card.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        chart_card.body.rowconfigure(0, weight=1)
        chart_card.body.columnconfigure(0, weight=1)
        chart = tk.Canvas(chart_card.body, height=300, bg="#F8FBFF", highlightthickness=0, bd=0)
        chart.grid(row=0, column=0, sticky="nsew")

        columns = ["label", "route_detail"]
        for algorithm in ROUTE_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            columns.extend([f"{key}_cost", f"{key}_visited", f"{key}_time"])
        columns = tuple(columns)

        table_card = RoundedFrame(parent, radius=16, padding=8, bg=APP_BG, fill=SURFACE, outline=BORDER)
        table_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        table_card.body.columnconfigure(0, weight=1)
        tk.Label(
            table_card.body,
            text="Bảng số liệu chi tiết",
            bg=SURFACE,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        table_frame = tk.Frame(table_card.body, bg=SURFACE)
        table_frame.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", style="Modern.Horizontal.TScrollbar")
        table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=3,
            xscrollcommand=x_scroll.set,
            style="Comparison.Treeview",
        )
        x_scroll.config(command=table.xview)

        headings = {"label": "Chuyến", "route_detail": "Tài xế / khách"}
        for algorithm in ROUTE_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            headings[f"{key}_cost"] = f"{algorithm} km"
            headings[f"{key}_visited"] = f"{algorithm} node"
            headings[f"{key}_time"] = f"{algorithm} ms"
        for col in columns:
            table.heading(col, text=headings.get(col, col))
            table.column(
                col,
                width=90,
                minwidth=72,
                anchor="center",
                stretch=True,
            )
        self._set_equal_tree_columns(table, columns, min_width=72)
        table.grid(row=0, column=0, sticky="ew")
        x_scroll.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        colors = {"A*": "#10B981", "UCS": "#F97316", "DFS": "#8B5CF6", "BFS": "#EF4444", "Greedy": "#2563EB"}

        def current_route_metrics() -> list[dict[str, float | int | str]]:
            if not metrics:
                return []
            if selected_mode.get() == view_all_label:
                return list(grouped_metrics.get(selected_range.get(), []) or [])
            if selected_mode.get() == average_label:
                return list(average_metrics)
            return list(metric_by_mode.get(selected_mode.get(), []) or [])

        def draw_current_chart() -> None:
            current = current_route_metrics()
            self._draw_grouped_bar_chart(
                chart,
                labels=[str(item.get("label", "")) for item in current],
                series=[
                    (
                        algorithm,
                        [float(item.get(f"{self._algorithm_key(algorithm)}_visited", 0)) for item in current],
                        colors.get(algorithm, "#111827"),
                    )
                    for algorithm in ROUTE_SEARCH_ALGORITHMS
                ],
                y_label="Số node đã duyệt",
            )

        def refresh_route_metrics(*_args: Any) -> None:
            if selected_mode.get() == view_all_label and metrics:
                range_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
                range_selector.grid(row=2, column=1, sticky="w", pady=(6, 0))
            else:
                range_label.grid_remove()
                range_selector.grid_remove()

            current = current_route_metrics()
            for item_id in table.get_children():
                table.delete(item_id)
            for item in current:
                values = [item.get("label", ""), item.get("route_detail", "")]
                for algorithm in ROUTE_SEARCH_ALGORITHMS:
                    key = self._algorithm_key(algorithm)
                    visited_value = float(item.get(f"{key}_visited", 0.0))
                    visited_display: str | int
                    if selected_mode.get() == average_label:
                        visited_display = f"{visited_value:.1f}"
                    else:
                        visited_display = int(round(visited_value))
                    values.extend(
                        [
                            f"{float(item.get(f'{key}_cost', 0.0)):.3f}",
                            visited_display,
                            f"{float(item.get(f'{key}_time_ms', 0.0)):.3f}",
                        ]
                    )
                table.insert("", "end", values=tuple(values))

            if current:
                parts = []
                for algorithm in ROUTE_SEARCH_ALGORITHMS:
                    key = self._algorithm_key(algorithm)
                    avg_time = sum(float(item.get(f"{key}_time_ms", 0.0)) for item in current) / len(current)
                    parts.append(f"{algorithm}: {avg_time:.3f} ms")
                if selected_mode.get() == view_all_label:
                    info_var.set(f"Đang hiển thị chuyến {selected_range.get()} / tổng {len(metrics)} chuyến  •  " + "  •  ".join(parts))
                elif selected_mode.get() == average_label:
                    info_var.set(f"Trung bình tất cả {len(metrics)} chuyến  •  " + "  •  ".join(parts))
                else:
                    info_var.set("Số chuyến: 1  •  " + "  •  ".join(parts))
            else:
                info_var.set("Chưa có dữ liệu để so sánh.")

            draw_current_chart()

        chart.bind("<Configure>", lambda _event: draw_current_chart())
        mode_selector.bind("<<ComboboxSelected>>", lambda _event: refresh_route_metrics())
        range_selector.bind("<<ComboboxSelected>>", lambda _event: refresh_route_metrics())
        refresh_route_metrics()

    def _draw_time_driver_chart(
        self,
        canvas: tk.Canvas,
        *,
        metrics: list[dict[str, float | int | str]],
        compact_x_axis: bool = False,
    ) -> None:
        """Vẽ biểu đồ đường tăng dần theo thời gian chạy tích lũy.

        Trục X: thời gian chạy tích lũy (ms).
        Trục Y: số tài xế tìm được.

        Mỗi thuật toán có một đường riêng. Các điểm 0.5km, 1.0km, 1.5km được đặt theo
        thời gian tích lũy để đường đi từ trái sang phải, tránh trường hợp thời
        gian đo từng bán kính bị dao động làm điểm bị đảo thứ tự.
        """
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 220)
        left, right, top, bottom = 82, 42, 42, 72
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        if not metrics:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Chưa có dữ liệu so sánh",
                fill=TEXT_SECONDARY,
                font=("Segoe UI", 10),
            )
            return

        ordered_metrics = sorted(metrics, key=lambda item: float(item.get("radius", 0.0)))

        def radius_label(item: dict[str, float | int | str]) -> str:
            radius = float(item.get("radius", 0.0))
            return f"{radius:.1f}km"

        def build_cumulative_points(
            time_key: str,
            found_key: str,
        ) -> list[tuple[float, float, str]]:
            points: list[tuple[float, float, str]] = [(0.0, 0.0, "0")]
            cumulative_time = 0.0
            best_found = 0.0
            for item in ordered_metrics:
                # Thời gian đo từng lần có thể rất nhỏ hoặc dao động, nên cộng dồn
                # theo thứ tự bán kính để tạo đường tăng dần theo thời gian.
                elapsed = max(0.0, float(item.get(time_key, 0.0)))
                cumulative_time += elapsed

                # Số tài xế tìm được theo bán kính về nguyên tắc không giảm.
                # Dùng max để tránh nhiễu khi dữ liệu bị cập nhật không đồng bộ.
                best_found = max(best_found, float(item.get(found_key, 0.0)))
                points.append((cumulative_time, best_found, radius_label(item)))
            return points

        colors = {"Local Search":"#2563EB", "BFS":"#EF4444", "DFS":"#8B5CF6", "Greedy":"#10B981", "UCS":"#F97316"}
        series_points = []
        all_points = []
        for algorithm in DRIVER_SEARCH_ALGORITHMS:
            key = self._algorithm_key(algorithm)
            points = build_cumulative_points(f"{key}_time_ms", f"{key}_found")
            series_points.append((algorithm, points, colors.get(algorithm, "#111827")))
            all_points.extend(points)

        max_x = max(x for x, _y, _label in all_points)
        max_y = max(y for _x, y, _label in all_points)
        max_x = max(max_x, 0.001)
        max_y = max(max_y, 1.0)
        padded_x = max_x * 1.12
        padded_y = max_y * 1.15

        def scale_x(value: float) -> float:
            return left + (value / padded_x) * plot_w

        def scale_y(value: float) -> float:
            return top + plot_h - (value / padded_y) * plot_h

        # Nhãn trục
        canvas.create_text(
            18,
            top + plot_h / 2,
            text="Số tài xế tìm được",
            angle=90,
            fill=TEXT_SECONDARY,
            font=("Segoe UI", 8),
        )
        canvas.create_text(
            left + plot_w / 2,
            height - 18,
            text="Thời gian chạy tích lũy (ms)",
            fill=TEXT_SECONDARY,
            font=("Segoe UI", 8),
        )

        # Trục và lưới
        canvas.create_line(left, top, left, top + plot_h, fill="#CBD5E1")
        canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill="#CBD5E1")

        for tick in range(0, 5):
            value = padded_y * tick / 4
            y = scale_y(value)
            canvas.create_line(left - 4, y, left + plot_w, y, fill="#E2E8F0")
            canvas.create_text(
                left - 10,
                y,
                text=f"{value:.0f}",
                anchor="e",
                fill=TEXT_SECONDARY,
                font=("Segoe UI", 8),
            )

        # Với chế độ tổng hợp tất cả vị trí đặt xe, thời gian tích lũy có thể lớn,
        # nên trục X dùng bước lớn hơn để nhãn không dính sát nhau. Các vị trí riêng
        # lẻ vẫn giữ nhãn chính mỗi 0.4 ms như yêu cầu.
        if compact_x_axis:
            raw_step = max(0.4, padded_x / 8)
            magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 0.1
            step_base = raw_step / magnitude
            if step_base <= 1:
                nice_base = 1
            elif step_base <= 2:
                nice_base = 2
            elif step_base <= 5:
                nice_base = 5
            else:
                nice_base = 10
            x_tick_step = nice_base * magnitude
            x_label_step = x_tick_step
        else:
            x_tick_step = 0.2
            x_label_step = 0.4
        padded_x = max(x_tick_step, math.ceil(padded_x / x_tick_step) * x_tick_step)
        tick_count = int(round(padded_x / x_tick_step))
        label_every = max(1, int(round(x_label_step / x_tick_step)))

        for tick in range(0, tick_count + 1):
            value = tick * x_tick_step
            x = scale_x(value)

            is_label_tick = tick % label_every == 0
            tick_len = 7 if is_label_tick else 4
            tick_color = "#94A3B8" if is_label_tick else "#CBD5E1"

            canvas.create_line(
                x,
                top + plot_h,
                x,
                top + plot_h + tick_len,
                fill=tick_color,
            )

            if is_label_tick:
                canvas.create_text(
                    x,
                    top + plot_h + 20,
                    text=f"{value:.1f}",
                    angle=0,
                    fill=TEXT_SECONDARY,
                    font=("Segoe UI", 7),
                )

        def draw_line_series(
            name: str,
            points: list[tuple[float, float, str]],
            color: str,
            legend_x: int,
            label_offset: int,
        ) -> None:
            coords: list[float] = []
            for x_value, y_value, _label in points:
                coords.extend([scale_x(x_value), scale_y(y_value)])

            if len(coords) >= 4:
                canvas.create_line(*coords, fill=color, width=3, smooth=False)

            point_count = len(points)
            for index, (x_value, y_value, label) in enumerate(points):
                x = scale_x(x_value)
                y = scale_y(y_value)
                canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline="")

                if index == 0:
                    continue

                # Dịch vị trí nhãn để tránh chồng lên nhau khi các điểm nằm gần nhau.
                if point_count <= 2:
                    dx = 0
                    anchor = "s"
                elif index == 1:
                    dx = -14
                    anchor = "se"
                elif index == point_count - 1:
                    dx = 14
                    anchor = "sw"
                else:
                    dx = 0
                    anchor = "s"

                canvas.create_text(
                    x + dx,
                    y - label_offset,
                    text=label,
                    anchor=anchor,
                    fill=TEXT_PRIMARY,
                    font=("Segoe UI", 8, "bold"),
                )
                canvas.create_text(
                    x + dx,
                    y + label_offset,
                    text=f"{int(y_value)}",
                    anchor=("n" if anchor == "s" else ("ne" if anchor == "se" else "nw")),
                    fill=TEXT_PRIMARY,
                    font=("Segoe UI", 8),
                )

            canvas.create_rectangle(legend_x, 12 - 6, legend_x + 12, 12 + 6, fill=color, outline="")
            canvas.create_text(
                legend_x + 18,
                12,
                text=name,
                anchor="w",
                fill=TEXT_PRIMARY,
                font=("Segoe UI", 8),
            )

        for index, (algorithm, points, color) in enumerate(series_points):
            draw_line_series(algorithm, points, color, left + index * 125, 14 + (index % 2) * 8)

    def _draw_grouped_bar_chart(
        self,
        canvas: tk.Canvas,
        *,
        labels: list[str],
        series: list[tuple[str, list[float], str]],
        y_label: str,
    ) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 220)
        left, right, top, bottom = 70, 28, 34, 58
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)

        all_values = [value for _name, values, _color in series for value in values]
        max_value = max(all_values) if all_values else 1.0
        max_value = max(max_value, 1.0)
        padded_max = max_value * 1.15

        canvas.create_text(18, top + plot_h // 2, text=y_label, angle=90, fill=TEXT_SECONDARY, font=("Segoe UI", 9))
        canvas.create_line(left, top, left, top + plot_h, fill="#CBD5E1")
        canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill="#CBD5E1")

        for tick in range(0, 5):
            value = padded_max * tick / 4
            y = top + plot_h - (value / padded_max) * plot_h
            canvas.create_line(left - 4, y, left + plot_w, y, fill="#E2E8F0")
            canvas.create_text(left - 10, y, text=f"{value:.0f}", anchor="e", fill=TEXT_SECONDARY, font=("Segoe UI", 8))

        group_count = max(len(labels), 1)
        group_w = plot_w / group_count
        bar_gap = 6
        bar_count = max(len(series), 1)
        bar_w = min(54, max(12, (group_w - 28) / bar_count - bar_gap))

        for i, label in enumerate(labels):
            center = left + group_w * i + group_w / 2
            total_bars_w = bar_count * bar_w + (bar_count - 1) * bar_gap
            x0 = center - total_bars_w / 2
            for j, (_name, values, color) in enumerate(series):
                value = values[i] if i < len(values) else 0
                bar_h = (value / padded_max) * plot_h
                x1 = x0 + j * (bar_w + bar_gap)
                y1 = top + plot_h - bar_h
                x2 = x1 + bar_w
                y2 = top + plot_h
                canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                canvas.create_text((x1 + x2) / 2, y1 - 8, text=f"{value:.0f}", fill=TEXT_PRIMARY, font=("Segoe UI", 8, "bold"))
            canvas.create_text(center, top + plot_h + 20, text=label, fill=TEXT_PRIMARY, font=("Segoe UI", 9, "bold"))

        legend_x = left
        legend_y = 12
        for name, _values, color in series:
            canvas.create_rectangle(legend_x, legend_y - 6, legend_x + 12, legend_y + 6, fill=color, outline="")
            canvas.create_text(legend_x + 18, legend_y, text=name, anchor="w", fill=TEXT_PRIMARY, font=("Segoe UI", 9))
            legend_x += 120

    def run_simulation(self) -> None:
        if self.is_animating:
            messagebox.showinfo("Đang chạy", "Giả lập đang chạy.")
            return
        if not self.sim.drivers and not any(not customer.served for customer in self.sim.customers):
            self.generate_random_data()
        if not self.sim.drivers:
            messagebox.showinfo("Thiếu tài xế", "Chưa có tài xế. Hãy sinh dữ liệu hoặc thêm tài xế trên bản đồ.")
            return
        if not any(not customer.served for customer in self.sim.customers):
            messagebox.showinfo("Thiếu đơn", "Chưa có đơn chờ xử lý. Hãy tạo đơn bằng nút Tạo đơn.")
            return

        self.cancel_map_action()
        self.clear_history_overlay()
        # Giữ lịch sử các chuyến đã hoàn thành qua nhiều lần chạy giả lập.
        # Lịch sử chỉ bị xóa khi người dùng bấm Reset demo.
        self.clear_routes(clear_log=True, keep_entities=True)
        rides = self.sim.prepare_assignments(
            self._log,
            driver_algorithm=self.driver_algorithm_var.get(),
            route_algorithm=self.route_algorithm_var.get(),
        )
        self._refresh_entities()
        self._draw_ride_routes(rides)
        self._update_summary_stats()

        if rides:
            self._render_driver_trip_info(rides[0].driver, switch_to_rides=False)

        if not rides:
            self._update_summary_stats()
            self.status_var.set("Không tạo được chuyến nào. Hãy tăng số tài xế hoặc tạo tài xế gần điểm đón hơn.")
            return

        self.is_animating = True
        self._update_control_buttons()
        self.status_var.set(f"Đang animate {len(rides)} chuyến, cập nhật mỗi {self.animation_interval_var.get()} ms...")
        self._animate_step()

    def pause_simulation(self) -> None:
        """Tạm dừng giả lập."""
        if not self.is_animating:
            return
        self.is_animating = False
        self._update_control_buttons()
        self.status_var.set("Giả lập đã tạm dừng. Bấm Tiếp tục để chạy tiếp.")

    def resume_simulation(self) -> None:
        """Tiếp tục giả lập đã tạm dừng."""
        if self.is_animating:
            return
        self.is_animating = True
        self._update_control_buttons()
        self.status_var.set("Tiếp tục giả lập...")
        self._animate_step()

    def _update_control_buttons(self) -> None:
        """Cập nhật việc hiển thị/ẩn các nút điều khiển giả lập."""
        if not self.run_button or not self.pause_button or not self.resume_button:
            return
        
        if self.is_animating:
            # Khi đang chạy: ẩn nút Chạy, hiển thị nút Tạm dừng
            self.run_button.pack_forget()
            self.pause_button.pack(fill="x", side="left", expand=True, padx=(0, 4))
            self.resume_button.pack_forget()
        else:
            # Khi dừng: hiển thị nút Chạy
            # Nếu còn chuyến chưa hoàn thành thì hiển thị Tiếp tục
            if self.sim.active_rides and any(ride.stage != "done" for ride in self.sim.active_rides):
                self.run_button.pack_forget()
                self.pause_button.pack_forget()
                self.resume_button.pack(fill="x", side="left", expand=True, padx=(4, 0))
            else:
                self.run_button.pack(fill="x", side="left", expand=True, padx=(0, 4))
                self.pause_button.pack_forget()
                self.resume_button.pack_forget()

    def _draw_ride_routes(self, rides: list[ActiveRide]) -> None:
        if not self.map_widget:
            return
        for ride in rides:
            pickup_coords = [self.graph.node_position(node_id) for node_id in ride.pickup_node_path]
            dropoff_coords = [self.graph.node_position(node_id) for node_id in ride.dropoff_node_path]
            try:
                ride.pickup_path_obj = self.map_widget.set_path(pickup_coords, color=COLOR_ROUTE_PICKUP, width=4)
                ride.dropoff_path_obj = self.map_widget.set_path(dropoff_coords, color=COLOR_ROUTE_DROPOFF, width=4)
            except TypeError:
                ride.pickup_path_obj = self.map_widget.set_path(pickup_coords)
                ride.dropoff_path_obj = self.map_widget.set_path(dropoff_coords)
            self.route_paths.extend([ride.pickup_path_obj, ride.dropoff_path_obj])

    def _delete_ride_visuals(self, ride: ActiveRide) -> None:
        for path_obj in (ride.pickup_path_obj, ride.dropoff_path_obj):
            self._safe_delete(path_obj)
            if path_obj in self.route_paths:
                self.route_paths.remove(path_obj)
        ride.pickup_path_obj = None
        ride.dropoff_path_obj = None

        for marker in (ride.customer.marker, ride.customer.destination_marker):
            self._safe_delete(marker)
        ride.customer.marker = None
        ride.customer.destination_marker = None

    def _animate_step(self) -> None:
        if not self.is_animating:
            return
        
        running = False
        for ride in self.sim.active_rides:
            if ride.stage == "done":
                continue

            points = ride.pickup_points if ride.stage == "to_pickup" else ride.dropoff_points
            if ride.step_index < len(points):
                lat, lng = points[ride.step_index]
                ride.driver.lat = lat
                ride.driver.lng = lng
                if ride.driver.marker:
                    try:
                        ride.driver.marker.set_position(lat, lng)
                    except Exception:
                        pass
                ride.step_index += 1
                running = True
                continue

            if ride.stage == "to_pickup":
                ride.stage = "to_dropoff"
                ride.step_index = 0
                ride.driver.node_id = ride.customer.pickup_node_id
                ride.driver.lat = ride.customer.lat
                ride.driver.lng = ride.customer.lng

                if ride.customer.marker:
                    self._safe_delete(ride.customer.marker)
                    ride.customer.marker = None

                self._replace_driver_marker(ride.driver, ride.driver.id, COLOR_DRIVER_BUSY)
                self._refresh_selected_driver_info(ride.driver.id)
                self.status_var.set(f"{ride.driver.id} đã tới điểm đón {ride.customer.id}, trạng thái: đang chở khách.")
                self._log(f"{ride.driver.id} đã tới điểm đón {ride.customer.id} -> trạng thái đang chở khách.")
                running = True
            elif ride.stage == "to_dropoff":
                ride.stage = "done"
                ride.customer.served = True
                ride.driver.busy = False
                ride.driver.node_id = ride.customer.destination_node_id
                ride.driver.lat = ride.customer.dest_lat
                ride.driver.lng = ride.customer.dest_lng
                self._record_completed_ride(ride)
                self._delete_ride_visuals(ride)
                self._replace_driver_marker(ride.driver, ride.driver.id, COLOR_DRIVER_FREE)
                self._refresh_selected_driver_info(ride.driver.id)
                self._log(f"{ride.driver.id} đã trả khách {ride.customer.id}. Đã xóa điểm đón, điểm đến và đường đi hiện tại.")
                running = True

        if running and self.is_animating:
            self._update_summary_stats()
            self.root.after(max(30, int(self.animation_interval_var.get())), self._animate_step)
        else:
            self.is_animating = False
            self._update_control_buttons()
            self._update_summary_stats()
            self.status_var.set("Giả lập hoàn tất. Tài xế đã cập nhật vị trí mới, chuyến cũ nằm trong lịch sử.")

    def clear_routes(self, clear_log: bool = True, keep_entities: bool = False) -> None:
        for path in list(self.route_paths):
            self._safe_delete(path)
        self.route_paths.clear()

        self.sim.active_rides.clear()
        self.is_animating = False
        self._update_control_buttons()
        self._render_empty_driver_info()

        if not keep_entities:
            for driver in self.sim.drivers:
                driver.busy = False
            # Không mở lại các customer đã served, vì sau khi trả khách đơn đó
            # phải được xem là chuyến trong lịch sử, không còn là đơn đang chờ.
            self._refresh_entities()

        self._update_summary_stats()

        if clear_log:
            self.log_text.delete("1.0", "end")
            self.status_var.set("Đã làm mới tuyến và log.")


    def _set_marker(
        self,
        lat: float,
        lng: float,
        text: str,
        color: str,
        command: Callable[[Any], None] | None = None,
    ) -> Any:
        if not self.map_widget:
            return None
        try:
            return self.map_widget.set_marker(
                lat,
                lng,
                text=text,
                marker_color_circle=color,
                marker_color_outside=color,
                command=command,
            )
        except TypeError:
            try:
                return self.map_widget.set_marker(
                    lat,
                    lng,
                    text=text,
                    marker_color_circle=color,
                    marker_color_outside=color,
                )
            except TypeError:
                return self.map_widget.set_marker(lat, lng, text=text)

    def _set_driver_marker(self, driver: Driver, text: str, color: str) -> Any:
        if not self.map_widget:
            return None

        icon = self._get_driver_icon(driver)
        if icon is None:
            return self._set_marker(
                driver.lat,
                driver.lng,
                text,
                color,
                command=lambda _marker, driver_id=driver.id: self.show_driver_info(driver_id),
            )

        try:
            return self.map_widget.set_marker(
                driver.lat,
                driver.lng,
                text=text,
                icon=icon,
                command=lambda _marker, driver_id=driver.id: self.show_driver_info(driver_id),
            )
        except TypeError:
            try:
                return self.map_widget.set_marker(
                    driver.lat,
                    driver.lng,
                    text=text,
                    image=icon,
                    command=lambda _marker, driver_id=driver.id: self.show_driver_info(driver_id),
                )
            except TypeError:
                return self._set_marker(
                    driver.lat,
                    driver.lng,
                    text,
                    color,
                    command=lambda _marker, driver_id=driver.id: self.show_driver_info(driver_id),
                )

    def _set_customer_marker(self, customer: Customer, text: str, color: str) -> Any:
        if not self.map_widget:
            return None

        command = lambda _marker, customer_id=customer.id: self.show_algorithm_demo_for_customer(customer_id)

        if self.customer_icon is None:
            return self._set_marker(customer.lat, customer.lng, text, color, command=command)

        try:
            return self.map_widget.set_marker(
                customer.lat,
                customer.lng,
                text=text,
                icon=self.customer_icon,
                command=command,
            )
        except TypeError:
            try:
                return self.map_widget.set_marker(
                    customer.lat,
                    customer.lng,
                    text=text,
                    image=self.customer_icon,
                    command=command,
                )
            except TypeError:
                return self._set_marker(customer.lat, customer.lng, text, color, command=command)

    def show_driver_info(self, driver_id: str) -> None:
        for driver in self.sim.drivers:
            if driver.id == driver_id:
                self._render_driver_trip_info(driver)
                self.status_var.set(f"Đang xem thông tin {driver.id}.")
                return

    def _refresh_selected_driver_info(self, driver_id: str) -> None:
        """Render lại thẻ thông tin nếu tài xế đang được chọn có thay đổi trạng thái."""
        if self.selected_driver_id != driver_id:
            return

        for driver in self.sim.drivers:
            if driver.id == driver_id:
                self._render_driver_trip_info(driver, switch_to_rides=False)
                return

    def cancel_selected_ride(self) -> None:
        if not self.selected_driver_id:
            return

        target_ride = self._find_active_ride_by_driver_id(self.selected_driver_id)
        if target_ride is None:
            messagebox.showinfo("Thông báo", "Tài xế hiện không có chuyến đang hoạt động.")
            return

        ok = messagebox.askyesno(
            "Hủy chuyến",
            f"Bạn có chắc muốn hủy chuyến của {target_ride.driver.id} không?",
        )
        if not ok:
            return

        target_ride.driver.busy = False
        target_ride.driver.node_id = target_ride.customer.pickup_node_id
        target_ride.customer.served = False
        self._delete_ride_visuals(target_ride)

        try:
            self.sim.active_rides.remove(target_ride)
        except ValueError:
            pass

        self._replace_driver_marker(target_ride.driver, target_ride.driver.id, COLOR_DRIVER_FREE)
        self._refresh_entities()
        self._update_summary_stats()
        self._render_empty_driver_info()

        if not any(ride.stage != "done" for ride in self.sim.active_rides):
            self.is_animating = False
            self._update_control_buttons()

        self.status_var.set(f"Đã hủy chuyến của {target_ride.driver.id}.")
        self._log(f"Đã hủy chuyến của {target_ride.driver.id} - {target_ride.customer.id}.")

    def _load_map_icon(self, file_name: str, size: tuple[int, int]) -> Any:
        """Tải icon từ thư mục assets; lỗi thì trả về None để dùng marker màu."""
        try:
            image_path = Path(__file__).resolve().parent.parent / "assets" / file_name
            image = Image.open(image_path).convert("RGBA")
            image = image.resize(size, Image.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _get_driver_active_stage(self, driver_id: str) -> str | None:
        for ride in self.sim.active_rides:
            if ride.driver.id == driver_id and ride.stage != "done":
                return ride.stage
        return None

    def _get_driver_icon(self, driver: Driver) -> Any:
        stage = self._get_driver_active_stage(driver.id)
        if stage == "to_dropoff":
            return self.driver_busy_icon
        return self.driver_free_icon

    def _is_customer_picked_up(self, customer_id: str) -> bool:
        for ride in self.sim.active_rides:
            if ride.customer.id == customer_id and ride.stage == "to_dropoff":
                return True
        return False

    def _safe_delete(self, obj: Any) -> None:
        try:
            if obj:
                obj.delete()
        except Exception:
            pass

    def _log(self, message: str) -> None:
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
