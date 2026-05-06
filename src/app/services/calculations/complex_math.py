from __future__ import annotations

import cmath
from math import hypot

from app.models.electrical import ComplexValue
from app.services.calculations.angles import radians_to_degrees


def rectangular_to_complex(value: ComplexValue) -> complex:
    """Create a Python complex number from R/X rectangular components."""
    return complex(value.real, value.imag)


def polar_to_complex(magnitude: float, angle_deg: float) -> complex:
    """Create a complex value from magnitude and phase angle."""
    return cmath.rect(magnitude, cmath.pi * angle_deg / 180.0)


def complex_magnitude(value: complex) -> float:
    """Return magnitude of a complex electrical quantity."""
    return hypot(value.real, value.imag)


def complex_angle_deg(value: complex) -> float:
    """Return phase angle of a complex electrical quantity in degrees."""
    return radians_to_degrees(cmath.phase(value))
