from __future__ import annotations

from math import cos, sin

from app.models.protection import DistanceZonePolygon, DistanceZoneSettings, ZoneDirection
from app.services.calculations.angles import degrees_to_radians


def calculate_quadrilateral_zone(settings: DistanceZoneSettings) -> DistanceZonePolygon:
    """Build a basic quadrilateral distance zone on the R-X plane.

    This generic geometry uses reach, line angle, and resistive reach. RET670 has
    multiple characteristic options; validate final geometry against the selected
    terminal function block and setting group before applying it to real settings.
    TODO: Map this baseline to the exact RET670 distance protection characteristic.
    """
    if settings.reach_ohm <= 0 or settings.resistive_reach_ohm <= 0:
        msg = "Zone reach values must be positive."
        raise ValueError(msg)

    direction_sign = -1.0 if settings.direction == ZoneDirection.REVERSE else 1.0
    angle_rad = degrees_to_radians(settings.angle_deg)
    reach_r = direction_sign * settings.reach_ohm * cos(angle_rad)
    reach_x = direction_sign * settings.reach_ohm * sin(angle_rad)
    resistive = settings.resistive_reach_ohm

    points = (
        (0.0, 0.0),
        (direction_sign * resistive, 0.0),
        (reach_r + direction_sign * resistive, reach_x),
        (reach_r - direction_sign * resistive, reach_x),
        (direction_sign * -resistive, 0.0),
        (0.0, 0.0),
    )
    return DistanceZonePolygon(name=settings.name, points=points)


def calculate_distance_zones(
    zone_settings: list[DistanceZoneSettings],
) -> list[DistanceZonePolygon]:
    """Calculate all configured distance protection zones."""
    return [calculate_quadrilateral_zone(settings) for settings in zone_settings]
