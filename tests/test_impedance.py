from __future__ import annotations

import pytest

from app.services.calculations.impedance import (
    calculate_impedance,
    primary_to_secondary_impedance,
    secondary_to_primary_impedance,
)


def test_calculate_impedance_from_complex_phasors() -> None:
    impedance = calculate_impedance(voltage=complex(100.0, 50.0), current=complex(10.0, 0.0))

    assert impedance.real == pytest.approx(10.0)
    assert impedance.imag == pytest.approx(5.0)


def test_calculate_impedance_rejects_zero_current() -> None:
    with pytest.raises(ZeroDivisionError):
        calculate_impedance(voltage=1 + 0j, current=0 + 0j)


def test_primary_secondary_impedance_round_trip() -> None:
    primary = complex(12.0, 24.0)
    secondary = primary_to_secondary_impedance(primary, 110_000.0 / 100.0, 1000.0 / 1.0)

    assert secondary == pytest.approx(complex(10.9090909, 21.8181818))
    assert secondary_to_primary_impedance(
        secondary,
        110_000.0 / 100.0,
        1000.0 / 1.0,
    ) == pytest.approx(primary)
