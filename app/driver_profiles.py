from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DriverProfile:
    name: str
    phone: str
    vehicle_name: str
    license_plate: str
    rating: float
    acceptance_rate: int
    service: str
    payment_method: str
    badges: tuple[str, ...]


DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "driver_profiles.json"
)


def _default_profile(driver_id: str) -> DriverProfile:
    return DriverProfile(
        name=f"Tài xế {driver_id}",
        phone="Chưa cập nhật",
        vehicle_name="Xe máy",
        license_plate="Chưa cập nhật",
        rating=4.8,
        acceptance_rate=90,
        service="QKM Bike",
        payment_method="Tiền mặt",
        badges=("Thái độ tốt", "Lái xe an toàn", "Dịch vụ tốt"),
    )


def load_driver_profiles() -> dict[str, DriverProfile]:
    if not DATA_FILE.exists():
        print(f"[WARN] Không tìm thấy file: {DATA_FILE}")
        return {}

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    profiles: dict[str, DriverProfile] = {}

    for driver_id, item in raw.items():
        profiles[driver_id] = DriverProfile(
            name=item.get("name", f"Tài xế {driver_id}"),
            phone=item.get("phone", "Chưa cập nhật"),
            vehicle_name=item.get("vehicle_name", "Xe máy"),
            license_plate=item.get("license_plate", "Chưa cập nhật"),
            rating=float(item.get("rating", 4.8)),
            acceptance_rate=int(item.get("acceptance_rate", 90)),
            service=item.get("service", "QKM Bike"),
            payment_method=item.get("payment_method", "Tiền mặt"),
            badges=tuple(item.get("badges", [])),
        )

    return profiles


DRIVER_PROFILES = load_driver_profiles()


def get_driver_profile(driver_id: str) -> DriverProfile:
    return DRIVER_PROFILES.get(driver_id, _default_profile(driver_id))