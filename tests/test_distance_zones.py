from __future__ import annotations

import pytest

from app.models.protection import DistanceZoneSettings
from app.services.calculations.distance_zones import calculate_quadrilateral_zone


def test_quadrilateral_zone_contains_closed_polygon() -> None:
    polygon = calculate_quadrilateral_zone(
        DistanceZoneSettings(
            name="Zone 1",
            reach_ohm=10.0,
            angle_deg=90.0,
            resistive_reach_ohm=2.0,
        )
    )

    assert polygon.name == "Zone 1"
    assert polygon.points[0] == polygon.points[-1]
    assert polygon.points[2][1] == pytest.approx(10.0)


def test_quadrilateral_zone_rejects_non_positive_reach() -> None:
    with pytest.raises(ValueError):
        calculate_quadrilateral_zone(
            DistanceZoneSettings(name="Bad", reach_ohm=0.0, angle_deg=75.0, resistive_reach_ohm=2.0)
        )
