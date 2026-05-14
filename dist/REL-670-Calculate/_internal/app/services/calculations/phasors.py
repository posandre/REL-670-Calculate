from __future__ import annotations

from app.models.electrical import Phasor
from app.services.calculations.complex_math import polar_to_complex


def phasor_to_complex(phasor: Phasor) -> complex:
    """Convert a named phasor to a complex value for vector diagrams."""
    return polar_to_complex(phasor.magnitude, phasor.angle_deg)


def balanced_three_phase_set(prefix: str, magnitude: float, angle_a_deg: float) -> list[Phasor]:
    """Build a positive-sequence three-phase phasor set A/B/C."""
    return [
        Phasor(f"{prefix}A", magnitude, angle_a_deg),
        Phasor(f"{prefix}B", magnitude, angle_a_deg - 120.0),
        Phasor(f"{prefix}C", magnitude, angle_a_deg + 120.0),
    ]
