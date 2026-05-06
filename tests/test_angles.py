from __future__ import annotations

import pytest

from app.services.calculations.angles import (
    degrees_to_radians,
    normalize_degrees,
    radians_to_degrees,
    signed_degrees,
)


def test_angle_conversions() -> None:
    assert degrees_to_radians(180.0) == pytest.approx(3.141592653589793)
    assert radians_to_degrees(3.141592653589793) == pytest.approx(180.0)


def test_angle_normalization() -> None:
    assert normalize_degrees(-30.0) == pytest.approx(330.0)
    assert signed_degrees(270.0) == pytest.approx(-90.0)
