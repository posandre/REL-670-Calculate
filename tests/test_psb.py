from __future__ import annotations

import pytest

from app.models.protection import PsbSettings
from app.services.calculations.psb import calculate_psb_characteristic


def test_psb_characteristic_builds_inner_and_outer_polygons() -> None:
    characteristic = calculate_psb_characteristic(
        PsbSettings(
            inner_resistance_ohm=5.0,
            inner_reactance_ohm=10.0,
            outer_resistance_ohm=8.0,
            outer_reactance_ohm=16.0,
            angle_deg=75.0,
        )
    )

    assert characteristic.inner_polygon[0] == (-5.0, -10.0)
    assert characteristic.outer_polygon[2] == (8.0, 16.0)


def test_psb_rejects_inner_larger_than_outer() -> None:
    with pytest.raises(ValueError):
        calculate_psb_characteristic(
            PsbSettings(
                inner_resistance_ohm=9.0,
                inner_reactance_ohm=10.0,
                outer_resistance_ohm=8.0,
                outer_reactance_ohm=16.0,
                angle_deg=75.0,
            )
        )
