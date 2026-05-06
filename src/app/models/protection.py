from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ZoneDirection(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True)
class DistanceZoneSettings:
    name: str
    reach_ohm: float
    angle_deg: float
    resistive_reach_ohm: float
    direction: ZoneDirection = ZoneDirection.FORWARD


@dataclass(frozen=True)
class DistanceZonePolygon:
    name: str
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PsbSettings:
    inner_resistance_ohm: float
    inner_reactance_ohm: float
    outer_resistance_ohm: float
    outer_reactance_ohm: float
    angle_deg: float


@dataclass(frozen=True)
class PsbCharacteristic:
    inner_polygon: tuple[tuple[float, float], ...]
    outer_polygon: tuple[tuple[float, float], ...]
