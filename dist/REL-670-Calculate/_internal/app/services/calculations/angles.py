from __future__ import annotations

import math


def degrees_to_radians(angle_deg: float) -> float:
    """Convert electrical angle from degrees to radians."""
    return math.radians(angle_deg)


def radians_to_degrees(angle_rad: float) -> float:
    """Convert electrical angle from radians to degrees."""
    return math.degrees(angle_rad)


def normalize_degrees(angle_deg: float) -> float:
    """Normalize an angle to the interval [0, 360)."""
    return angle_deg % 360.0


def signed_degrees(angle_deg: float) -> float:
    """Normalize an angle to the interval (-180, 180]."""
    normalized = (angle_deg + 180.0) % 360.0 - 180.0
    return 180.0 if normalized == -180.0 else normalized
